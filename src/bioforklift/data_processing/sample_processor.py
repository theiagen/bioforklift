import re
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List, Set
import pandas as pd
from google.cloud.bigquery import SchemaField
from bioforklift.bigquery.utils import load_schema_from_yaml
from bioforklift.forklift_logging import setup_logger
from .schema_models import SchemaDefinition
from .schema_converter import convert_to_schema_definition

logger = setup_logger(__name__)


class SampleDataProcessor:
    """
    Handles all data processing operations for sample data.

    This class is responsible for:
    - Field mapping and column filtering
    - Pattern validation
    - Sequence file validation
    - System value generation
    - Type coercion
    - Duplicate filtering
    """

    def __init__(self, schema_yaml: str):
        """
        Initialize the processor with schema information.

        Args:
            schema_yaml: Path to YAML schema file
        """
        schema_info = load_schema_from_yaml(schema_yaml)
        self.schema = schema_info["schema"]
        self.field_attributes = schema_info["field_attributes"]

        # Add typed schema definition for type-safe attribute access
        self.schema_definition: SchemaDefinition = convert_to_schema_definition(
            self.schema,
            self.field_attributes
        )

        logger.info(f"SampleDataProcessor initialized with schema: {schema_yaml}")

    def process_samples(
        self,
        dataframe: pd.DataFrame,
        existing_identifiers: Optional[Set[str]] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """
        Complete sample processing pipeline.

        Args:
            dataframe: Raw input DataFrame
            existing_identifiers: Set of existing sample IDs to filter out
            config: Optional configuration dictionary for entity type mapping and field inheritance

        Returns:
            Processed DataFrame ready for BigQuery upload
        """
        logger.info(f"Processing {len(dataframe)} samples through pipeline")

        if dataframe.empty:
            logger.info("Empty DataFrame provided, returning as-is")
            return dataframe

        # Data transformation pipeline
        processed_df = (
            dataframe
            .pipe(self._apply_entity_type_mapping, config)
            .pipe(self._map_field_names)
            .pipe(self._apply_config_field_inheritance, config)
            .pipe(self._filter_columns)
            .pipe(self._filter_existing_samples, existing_identifiers or set())
            .pipe(self._validate_sequence_files)
            .pipe(self._validate_field_patterns)
            .pipe(self._add_system_values)
            .pipe(self._coerce_dataframe_types)
        )

        logger.info(f"Processing complete: {len(processed_df)} samples ready for upload")
        return processed_df

    def _apply_entity_type_mapping(
        self,
        dataframe: pd.DataFrame,
        config: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """
        Map Terra entity:entity_type_id column to sample identifier if needed.

        This handles the special Terra naming pattern where columns are named
        like 'entity:sample_id' based on the entity_type in the config.
        Only applies if column_mappings are not already defined for the sample identifier.

        Args:
            dataframe: Input DataFrame
            config: Configuration dictionary containing entity_type

        Returns:
            DataFrame with entity column mapped to sample identifier
        """
        if config is None:
            return dataframe

        entity_type = config.get("entity_type")
        if not entity_type:
            return dataframe

        sample_identifier_field = self.get_sample_identifier_field()
        if not sample_identifier_field:
            return dataframe

        # Check if column mappings already handle this
        if sample_identifier_field in self.field_attributes:
            attrs = self.field_attributes[sample_identifier_field]
            if "column_mappings" in attrs or attrs.get("use_field_name"):
                logger.debug(
                    f"Column mappings defined for {sample_identifier_field}, "
                    f"skipping entity_type mapping"
                )
                return dataframe

        # Map entity:entity_type_id to sample_identifier (in place)
        entity_column = f"entity:{entity_type}_id"
        if entity_column in dataframe.columns:
            logger.info(f"Mapping {entity_column} to {sample_identifier_field}")
            dataframe.rename(columns={entity_column: sample_identifier_field}, inplace=True)
        else:
            logger.debug(f"Column '{entity_column}' not found for entity type mapping")

        return dataframe

    def _apply_config_field_inheritance(
        self,
        dataframe: pd.DataFrame,
        config: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """
        Apply configuration values to fields that inherit from config.

        Fields with 'inherit_from_config' attribute will have their values
        populated from the corresponding config field.

        Args:
            dataframe: Input DataFrame
            config: Configuration dictionary

        Returns:
            DataFrame with config-inherited fields populated
        """
        if config is None or dataframe.empty:
            return dataframe

        config_fields = self.get_config_source_fields()
        if not config_fields:
            return dataframe

        # Apply config values in place
        for field_name, config_field in config_fields.items():
            if config_field in config:
                dataframe[field_name] = config[config_field]
                logger.debug(f"Inherited field '{field_name}' from config['{config_field}']")
            else:
                logger.warning(
                    f"Configuration field '{config_field}' not found in config for "
                    f"field '{field_name}'"
                )

        return dataframe

    def _map_field_names(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Map source field names to BigQuery field names using column_mappings attributes"""
        for field_name, attrs in self.field_attributes.items():
            if "column_mappings" in attrs:
                source_fields = attrs["column_mappings"]
                if isinstance(source_fields, str):
                    source_fields = [source_fields]

                # Try each possible source field
                for source_field in source_fields:
                    if source_field in dataframe.columns:
                        dataframe.rename(columns={source_field: field_name}, inplace=True)
                        logger.debug(f"Mapped column '{source_field}' to '{field_name}'")
                        break

        return self._add_missing_schema_columns(dataframe)

    def _filter_columns(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Keep only columns that are defined in the schema"""
        schema_fields = self._get_schema_fields()
        extra_columns = set(dataframe.columns) - set(schema_fields)

        if extra_columns:
            logger.debug(f"Filtering out extra columns: {extra_columns}")
            dataframe.drop(columns=extra_columns, inplace=True)
        else:
            logger.debug("No extra columns to filter out")

        return dataframe

    def _filter_existing_samples(
        self,
        dataframe: pd.DataFrame,
        existing_identifiers: Set[str]
    ) -> pd.DataFrame:
        """Remove rows with existing sample identifiers"""
        if not existing_identifiers:
            logger.debug("No existing identifiers provided, skipping duplicate filtering")
            return dataframe

        try:
            sample_identifier_field = self.get_sample_identifier_field()
            if not sample_identifier_field:
                logger.warning("No field marked as sample_identifier in schema")
                return dataframe

            if sample_identifier_field not in dataframe.columns:
                logger.debug(f"Sample identifier field '{sample_identifier_field}' not in data")
                return dataframe

            # Filter out existing samples
            new_samples_df = dataframe[
                ~dataframe[sample_identifier_field].isin(existing_identifiers)
            ]

            filtered_count = len(dataframe) - len(new_samples_df)
            if filtered_count > 0:
                logger.info(f"Filtered out {filtered_count} existing samples")

            return new_samples_df

        except Exception as exc:
            logger.exception("Error filtering existing samples")
            raise RuntimeError(f"Error filtering existing samples: {str(exc)}")

    def _validate_sequence_files(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Validate that each sample has at least one sequence file field with a value.
        Removes rows that don't have any sequence files.
        """
        try:
            sequence_file_fields = self.get_sequence_file_fields()

            if not sequence_file_fields:
                logger.debug("No sequence file fields defined in schema")
                return dataframe

            # Check if at least one sequence file field has a value for each row
            has_sequence_file = dataframe[sequence_file_fields].notna().any(axis=1)
            valid_samples_df = dataframe[has_sequence_file]

            filtered_count = len(dataframe) - len(valid_samples_df)
            if filtered_count > 0:
                logger.info(f"Filtered out {filtered_count} samples without sequence files")

            return valid_samples_df

        except Exception as exc:
            logger.exception("Error validating sequence files")
            raise RuntimeError(f"Error validating sequence files: {str(exc)}")

    def _validate_field_patterns(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Validate DataFrame fields against regex patterns defined in schema.
        Removes rows where field values don't match their defined patterns.
        """
        try:
            if dataframe.empty:
                return dataframe

            # Get fields with pattern attributes
            pattern_fields = {
                field_name: attrs.get('pattern')
                for field_name, attrs in self.field_attributes.items()
                if 'pattern' in attrs and attrs['pattern']
            }

            if not pattern_fields:
                logger.debug("No pattern validation fields defined in schema")
                return dataframe

            logger.info(f"Validating patterns for fields: {list(pattern_fields.keys())}")

            # Track validation results
            initial_count = len(dataframe)
            validation_failures = []

            for field_name, pattern in pattern_fields.items():
                if field_name not in dataframe.columns:
                    logger.debug(f"Pattern field '{field_name}' not present in data, skipping")
                    continue

                try:
                    # Compile regex pattern
                    regex = re.compile(pattern)

                    # Get non-null values for validation
                    field_data = dataframe[field_name].dropna()

                    if field_data.empty:
                        logger.debug(f"No non-null values for pattern field '{field_name}', skipping")
                        continue

                    # Find rows that don't match the pattern
                    invalid_mask = ~field_data.astype(str).str.match(regex, na=False)
                    invalid_indices = field_data[invalid_mask].index

                    if len(invalid_indices) > 0:
                        invalid_values = field_data[invalid_mask].tolist()
                        validation_failures.extend([
                            f"Field '{field_name}': '{value}' doesn't match pattern '{pattern}'"
                            for value in invalid_values[:5]
                        ])

                        # Remove invalid rows
                        dataframe = dataframe.drop(index=invalid_indices)
                        logger.warning(f"Removed {len(invalid_indices)} rows with invalid '{field_name}' values")

                except re.error as regex_error:
                    logger.error(f"Invalid regex pattern for field '{field_name}': {pattern} - {regex_error}")
                    raise ValueError(f"Invalid regex pattern for field '{field_name}': {regex_error}")

            filtered_count = initial_count - len(dataframe)
            if filtered_count > 0:
                logger.info(f"Pattern validation filtered out {filtered_count} rows")
                if validation_failures:
                    logger.debug(f"Pattern validation failures: {validation_failures[:10]}")

            return dataframe

        except Exception as exc:
            logger.exception("Error during pattern validation")
            raise RuntimeError(f"Error validating field patterns: {str(exc)}")

    def _add_system_values(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Add system-generated values like UUIDs and timestamps"""
        if dataframe.empty:
            return dataframe

        system_values = self._generate_system_values(len(dataframe))

        for field_name, values in system_values.items():
            dataframe[field_name] = values

        return dataframe

    def _generate_system_values(self, row_count: int) -> Dict[str, List[Any]]:
        """Generate system values for auto-populated fields"""
        current_datetime = pd.Timestamp.now(tz="UTC")
        system_values = {}
        logger.debug(f"Generating system values for {row_count} rows")

        for field_name, attrs in self.field_attributes.items():
            # Primary key fields get UUIDs
            if attrs.get("primary_key"):
                system_values[field_name] = [str(uuid.uuid4()) for _ in range(row_count)]
            # created_at gets current timestamp
            elif field_name == "created_at":
                system_values[field_name] = [current_datetime] * row_count

        return system_values

    def _coerce_dataframe_types(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Coerce DataFrame column types to match schema definition"""
        logger.debug("Coercing DataFrame types to match schema")

        if dataframe.empty:
            return dataframe

        # Create mapping from field name to field type
        field_type_map = {field.name: field.field_type for field in self.schema}

        # Map pandas dtypes to corresponding BigQuery types for comparison
        pandas_to_bq_type_map = {
            'int64': 'INTEGER',
            'Int64': 'INTEGER',
            'float64': 'FLOAT',
            'bool': 'BOOLEAN',
            'datetime64[ns]': 'DATETIME',
            'datetime64[ns, UTC]': 'DATETIME',
            'object': 'STRING',
            'string': 'STRING'
        }

        # Iterate through each column and attempt type conversion only if needed
        for column in dataframe.columns:
            if column in field_type_map:
                bq_type = field_type_map[column]
                pandas_dtype = str(dataframe[column].dtype)

                # Check if conversion is needed
                needs_conversion = True

                if pandas_dtype in pandas_to_bq_type_map:
                    pandas_equivalent_bq_type = pandas_to_bq_type_map[pandas_dtype]
                    if pandas_equivalent_bq_type == bq_type:
                        needs_conversion = False

                if needs_conversion:
                    logger.debug(f"Converting column '{column}' from {pandas_dtype} to {bq_type}")

                    try:
                        if bq_type == "INTEGER":
                            dataframe[column] = pd.to_numeric(dataframe[column], errors='coerce').astype('Int64')
                        elif bq_type == "FLOAT":
                            dataframe[column] = pd.to_numeric(dataframe[column], errors='coerce')
                        elif bq_type == "BOOLEAN":
                            dataframe[column] = dataframe[column].astype('boolean')
                        elif bq_type == "DATETIME":
                            dataframe[column] = pd.to_datetime(dataframe[column], errors='coerce')
                        elif bq_type == "STRING":
                            dataframe[column] = dataframe[column].astype('string')
                    except Exception as e:
                        logger.warning(f"Failed to convert column '{column}' to {bq_type}: {e}")

        return dataframe

    def _add_missing_schema_columns(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Add any missing schema columns to DataFrame with null values"""
        schema_fields = self._get_schema_fields()

        # Add any missing columns with None/null values
        for field in schema_fields:
            if field not in dataframe.columns:
                logger.debug(f"Adding missing schema field: {field}")
                dataframe[field] = None

        return dataframe

    def _get_schema_fields(self) -> List[str]:
        """Get list of field names defined in the schema"""
        return [field.name for field in self.schema]

    def get_sample_identifier_field(self) -> Optional[str]:
        """Get the field marked as sample_identifier"""
        for field_name, attrs in self.field_attributes.items():
            if attrs.get("sample_identifier"):
                return field_name
        return None
    
    def get_config_identifier_field(self) -> Optional[str]:
        """Get the field marked as config_identifier"""
        for field_name, attrs in self.field_attributes.items():
            if attrs.get("config_identifier"):
                return field_name
        return None

    def get_sequence_file_fields(self) -> List[str]:
        """Get fields marked as sequence_file"""
        return [
            field_name
            for field_name, attrs in self.field_attributes.items()
            if attrs.get("sequence_file")
        ]

    def get_config_source_fields(self) -> Dict[str, str]:
        """Get fields that should be populated from parent configuration"""
        return {
            field_name: attrs.get('inherit_from_config')
            for field_name, attrs in self.field_attributes.items()
            if attrs.get('inherit_from_config')
        }