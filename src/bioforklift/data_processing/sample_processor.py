import re
import uuid
from typing import Optional, Dict, Any, List, Set
from datetime import datetime
import pandas as pd
import numpy as np
from .utils import load_schema_from_yaml
from bioforklift.forklift_logging import setup_logger
from .schema_models import SchemaDefinition, SampleFieldAttributes
from .schema_converter import convert_to_schema_definition

logger = setup_logger(__name__)


class SampleDataProcessor:
    """
    Processor for sample metadata DataFrames based on a defined schema.

    This class provides methods to process sample metadata DataFrames according to the defined schema.
    It includes functionality for mapping fields, validating data, adding system values, and more.
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
            self.field_attributes,
            SampleFieldAttributes
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

        # https://medium.com/@amit25173/what-is-pandas-pipe-and-why-should-you-use-it-ec62281f6a15
        processed_df = (
            dataframe
            .pipe(self._apply_entity_type_mapping, config)
            .pipe(self._map_field_names)
            .pipe(self._add_missing_schema_columns)
            .pipe(self._apply_config_field_inheritance, config)
            .pipe(self._filter_columns)
            .pipe(self._filter_existing_samples, existing_identifiers or set())
            .pipe(self._validate_sequence_files)
            .pipe(self._validate_field_patterns)
            .pipe(self._add_system_values)
            .pipe(self._process_date_formats)
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
            raise ValueError("No field marked as sample_identifier in schema, sample processing requires sample_identifier marked")

        # Check if column mappings are defined for the sample_identifier_field
        # Considering use_field_name as a fallback for renaming, but inherently a column mapping
        # This allows for flexibility in how the sample identifier is define
        if sample_identifier_field in self.field_attributes:
            attrs = self.field_attributes[sample_identifier_field]
            if "column_mappings" in attrs or attrs.get("use_field_name"):
                logger.debug(
                    f"Column mappings defined for {sample_identifier_field}, "
                    f"skipping entity_type mapping"
                )
                return dataframe

        # Map entity:entity_type_id to sample_identifier
        entity_column = f"entity:{entity_type}_id"
        if entity_column in dataframe.columns:
            logger.info(f"Mapping {entity_column} to {sample_identifier_field}")
            dataframe = dataframe.rename(columns={entity_column: sample_identifier_field})
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
        """
        Map source field names to BigQuery field names using column_mappings attributes.

        When multiple BigQuery fields map to the same Terra source column, the value is
        copied to all target fields.
        
        Ex: If both entity:specimen_id and entity:sample_id map to 'sample_id' column.
        """
        columns_to_copy = {}

        # Build complete mapping of source columns to target fields
        for field_name, attrs in self.field_attributes.items():
            if "column_mappings" in attrs:
                source_fields = attrs["column_mappings"]
                if isinstance(source_fields, str):
                    source_fields = [source_fields]

                # Find first available source field
                for source_field in source_fields:
                    if source_field in dataframe.columns:
                        if source_field not in columns_to_copy:
                            columns_to_copy[source_field] = []
                        columns_to_copy[source_field].append(field_name)
                        logger.debug(f"Mapping '{source_field}' -> '{field_name}'")
                        break

        # Apply the mappings
        schema_fields = self.get_schema_fields()

        for source_col, target_fields in columns_to_copy.items():
            for target_field in target_fields:
                dataframe[target_field] = dataframe[source_col]

            # Only drop the source column if it's NOT in the BigQuery schema
            if source_col not in schema_fields:
                dataframe = dataframe.drop(columns=[source_col])
                logger.debug(f"Dropped source column '{source_col}' (not in schema)")
            else:
                logger.debug(f"Keeping source column '{source_col}' (present in schema)")

        return dataframe

    def _filter_columns(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Keep only columns that are defined in the schema"""
        schema_fields = self.get_schema_fields()
        artifact_columns = set(dataframe.columns) - set(schema_fields)

        if artifact_columns:
            logger.debug(f"Filtering out artifact columns: {artifact_columns}")
            dataframe = dataframe.drop(columns=artifact_columns)
        else:
            logger.debug("No artifact columns to filter out")

        return dataframe

    def _filter_existing_samples(
        self,
        dataframe: pd.DataFrame,
        existing_identifiers: Set[str]
    ) -> pd.DataFrame:
        """Remove rows with existing sample identifiers"""
        
        # Base case: no existing identifiers provided
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
            
            logger.info(f"Validating sequence files for fields: {sequence_file_fields}")

            if not sequence_file_fields:
                logger.debug("No sequence file fields defined in schema")
                return dataframe

            # Check if at least one sequence file field has a non-empty value
            # Replace empty strings with NaN first, then check for non-null values
            sequence_data = dataframe[sequence_file_fields].replace('', pd.NA)
            has_sequence_file = sequence_data.notna().any(axis=1)
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
        Removes rows where field values don't match their defined accepted_patterns.
        """
        try:
            if dataframe.empty:
                return dataframe

            # Get fields with accepted_pattern attributes
            pattern_fields = {
                field_name: attrs.get('accepted_pattern')
                for field_name, attrs in self.field_attributes.items()
                if 'accepted_pattern' in attrs and attrs['accepted_pattern']
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

                    # Find rows that don't match the accepted_pattern - for regex always cast to string
                    invalid_mask = ~field_data.astype(str).str.match(regex, na=False)
                    invalid_indices = field_data[invalid_mask].index

                    if len(invalid_indices) > 0:
                        invalid_values = field_data[invalid_mask].tolist()
                        validation_failures.extend([
                            f"Field '{field_name}': '{value}' doesn't match pattern '{pattern}'"
                            for value in invalid_values[:5]
                        ])

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
            # created_at gets current datetime
            elif field_name == "created_at":
                system_values[field_name] = [current_datetime] * row_count

        return system_values

    def _process_date_formats(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Validate and coerce date fields according to their date_format specification.

        This processes fields that have a date_format attribute, validating that values
        can be parsed as dates and then coercing them to the specified format.

        Args:
            dataframe: Input DataFrame

        Returns:
            DataFrame with validated and coerced date values in the specified format
        """
        if dataframe.empty:
            return dataframe

        # Get fields with date_format attributes
        date_format_fields = {}
        for field_def in self.schema_definition.fields:
            if field_def.attributes.date_format:
                date_format_fields[field_def.name] = field_def.attributes

        if not date_format_fields:
            logger.debug("No date_format fields defined in schema")
            return dataframe

        logger.info(f"Processing date formats for fields: {list(date_format_fields.keys())}")

        initial_count = len(dataframe)
        validation_failures = []

        for field_name, attributes in date_format_fields.items():
            if field_name not in dataframe.columns:
                logger.debug(f"Date format field '{field_name}' not present in data, skipping")
                continue

            date_format = attributes.date_format
            logger.debug(f"Processing field '{field_name}' with date_format '{date_format}'")

            # Get non-null values for validation and coercion
            field_data = dataframe[field_name].dropna()

            if field_data.empty:
                logger.debug(f"No non-null values for date field '{field_name}', skipping")
                continue

            # Validate, parse, and coerce each value
            invalid_indices = []
            coerced_values = {}

            for idx, value in field_data.items():
                try:
                    # Parse the date value to a datetime object
                    parsed_date = self._parse_date_value(value, date_format)

                    if parsed_date is None:
                        invalid_indices.append(idx)
                        validation_failures.append(
                            f"Field '{field_name}': '{value}' could not be parsed as date"
                        )
                        continue

                    # Coerce to the target format
                    coerced_value = self._format_date_value(parsed_date, date_format)
                    coerced_values[idx] = coerced_value

                except Exception as exc:
                    logger.debug(f"Error processing date value '{value}' for field '{field_name}': {exc}")
                    invalid_indices.append(idx)
                    validation_failures.append(
                        f"Field '{field_name}': '{value}' processing error: {str(exc)}"
                    )

            # Apply coerced values
            if coerced_values:
                for idx, coerced_value in coerced_values.items():
                    dataframe.at[idx, field_name] = coerced_value
                logger.info(f"Coerced {len(coerced_values)} values for field '{field_name}' to format '{date_format}'")

            # Remove invalid rows
            if invalid_indices:
                dataframe = dataframe.drop(index=invalid_indices)
                logger.warning(
                    f"Removed {len(invalid_indices)} rows with invalid '{field_name}' "
                    f"date format (expected: {date_format})"
                )

        filtered_count = initial_count - len(dataframe)
        if filtered_count > 0:
            logger.info(f"Date format validation filtered out {filtered_count} rows")
            if validation_failures:
                logger.debug(f"Date format validation failures: {validation_failures[:10]}")

        return dataframe

    def _parse_date_value(self, value: Any, date_format: str) -> Optional[datetime]:
        """
        Parse a date value into a datetime object.

        This method accepts dates in various input formats and parses them flexibly,
        regardless of the target date_format. The target format is only used for
        output formatting in _format_date_value.

        Args:
            value: The value to parse (string or date-like)
            date_format: The target date format (used for context, not strict parsing)

        Returns:
            Parsed datetime object or None if parsing fails
        """
        if pd.isna(value) or value == '':
            return None

        str_value = str(value).strip()

        # Try common date formats in order of likelihood
        date_formats_to_try = [
            '%Y-%m-%d',           # 2024-01-15
            '%m/%d/%Y',           # 01/15/2024
            '%d/%m/%Y',           # 15/01/2024
            '%Y/%m/%d',           # 2024/01/15
            '%Y-%m-%d %H:%M:%S',  # 2024-01-15 10:30:45
            '%m/%d/%Y %H:%M:%S',  # 01/15/2024 10:30:45
            '%Y-%m-%dT%H:%M:%S',  # ISO format with time
            '%Y-%m-%dT%H:%M:%SZ', # ISO format with Z
        ]

        # First, try to parse using the target format if it's a strftime pattern
        if '%' in date_format:
            try:
                return datetime.strptime(str_value, date_format)
            except ValueError:
                pass  # Continue to try other formats

        # Try ISO format parsing (handles various ISO 8601 formats)
        try:
            return datetime.fromisoformat(str_value.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass

        # Try each common format
        for fmt in date_formats_to_try:
            try:
                return datetime.strptime(str_value, fmt)
            except ValueError:
                continue

        # Last resort: use pandas flexible date parsing
        try:
            parsed = pd.to_datetime(str_value, errors='coerce')
            if pd.notna(parsed):
                return parsed.to_pydatetime()
        except Exception:
            pass

        return None

    def _format_date_value(self, dt: datetime, date_format: str) -> str:
        """
        Format a datetime object into the specified date format string.

        Args:
            dt: The datetime object to format
            date_format: The target date format

        Returns:
            Formatted date string
        """
        if date_format in ('ISO 8601', 'ISO8601', 'RFC 3339', 'RFC3339'):
            # Return ISO 8601 format
            return dt.isoformat()
        elif '%' in date_format:
            # Custom strftime format
            return dt.strftime(date_format)
        elif date_format == 'YYYY-MM-DD':
            return dt.strftime('%Y-%m-%d')
        elif date_format == 'MM/DD/YYYY':
            return dt.strftime('%m/%d/%Y')
        elif date_format == 'DD/MM/YYYY':
            return dt.strftime('%d/%m/%Y')
        elif date_format == 'YYYY/MM/DD':
            return dt.strftime('%Y/%m/%d')
        else:
            # Default to ISO format
            return dt.isoformat()

    def _convert_numpy_type(self, value: Any) -> Any:
        """
        Convert numpy types to native Python types for JSON serialization.

        Args:
            value: Value that may contain numpy types

        Returns:
            Value with numpy types converted to Python native types
        """
        if value is None:
            return None

        if isinstance(value, (np.integer, np.int8, np.int16, np.int32, np.int64)):
            return int(value)

        if isinstance(value, (np.floating, np.float16, np.float32, np.float64)):
            return float(value)

        if isinstance(value, np.bool_):
            return bool(value)

        if isinstance(value, (np.str_, np.bytes_)):
            return str(value)

        if pd.isna(value):
            return None

        return value

    def _coerce_value_to_type(self, value: Any, bq_type: str) -> Any:
        """
        Coerce a single value to match the expected BigQuery type.

        Args:
            value: The value to coerce
            bq_type: The BigQuery field type (e.g., 'STRING', 'INTEGER', etc.)

        Returns:
            Coerced value ready for BigQuery
        """
        # First convert numpy types
        value = self._convert_numpy_type(value)

        if value is None:
            return None

        try:
            if bq_type in ('INTEGER', 'INT64'):
                # Convert to int, handling floats and numeric strings
                if value == '' or pd.isna(value):
                    return None
                return int(float(value))

            elif bq_type in ('FLOAT', 'FLOAT64'):
                if value == '' or pd.isna(value):
                    return None
                return float(value)

            elif bq_type in ('BOOLEAN', 'BOOL'):
                if isinstance(value, bool):
                    return value
                return bool(value)

            elif bq_type == 'DATE':
                if isinstance(value, str):
                    return pd.to_datetime(value).date()
                return value

            elif bq_type in ('DATETIME', 'TIMESTAMP'):
                if isinstance(value, str):
                    dt = pd.to_datetime(value)
                    if bq_type == 'TIMESTAMP' and dt.tzinfo is None:
                        # Add UTC timezone for TIMESTAMP fields
                        dt = dt.tz_localize('UTC')
                    return dt
                return value

            elif bq_type == 'STRING':
                # Convert to string, preserving None
                return str(value) if value is not None else None

            else:
                # For unknown types, return as-is
                return value

        except Exception as exc:
            logger.warning(f"Failed to coerce value {value} to type {bq_type}: {exc}")
            return value

    def coerce_dict_types(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coerce values in a dictionary to match schema field types.

        Converts numpy types to Python natives and applies schema type coercion.
        This is useful for bulk update operations where data comes as dictionaries
        rather than DataFrames. Reduces tension with BigQuery type expectations.

        Args:
            data: Dictionary with field names as keys

        Returns:
            Dictionary with coerced values
        """
        coerced = {}

        for field_name, value in data.items():
            # Get field definition from schema
            field_def = self.schema_definition.get_field(field_name)

            if field_def:
                coerced[field_name] = self._coerce_value_to_type(value, field_def.field_type)
            else:
                logger.warning(f"Field '{field_name}' not found in schema for type coercion, returning as is")
                coerced[field_name] = value

        return coerced

    def _coerce_dataframe_types(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Coerce DataFrame column types to match schema definition.
        Only converts columns where types don't already align.

        Args:
            dataframe: pandas DataFrame to coerce

        Returns:
            DataFrame with coerced types
        """
        logger.info("Coercing DataFrame types to match schema")

        if dataframe.empty:
            return dataframe

        coerced_df = dataframe.copy()

        # Create mapping from field name to field type
        field_type_map = {field.name: field.field_type for field in self.schema}

        # Convert each column to match its schema type
        # This ensures the DataFrame is ready for BigQuery upload
        # https://pandas-gbq.readthedocs.io/en/latest/writing.html#inferring-the-table-schema
        for column in coerced_df.columns:
            if column not in field_type_map:
                continue

            bq_type = field_type_map[column]
            pandas_dtype = str(coerced_df[column].dtype)
            
            logger.debug(f"Column '{column}': pandas dtype={pandas_dtype}, schema type={bq_type}")


            try:
                if bq_type in ('INTEGER', 'INT64'):
                    # Convert to nullable integer type
                    coerced_df[column] = pd.to_numeric(coerced_df[column], errors='coerce').astype('Int64')

                elif bq_type in ('FLOAT', 'FLOAT64'):
                    coerced_df[column] = pd.to_numeric(coerced_df[column], errors='coerce').astype('float64')

                elif bq_type in ('BOOLEAN', 'BOOL'):
                    # Handle various boolean representations, stuff can get crazy coming from Terra
                    # Better safe than sorry
                    bool_map = {
                        'true': True, 'True': True, 'TRUE': True, True: True, 1: True, '1': True,
                        'false': False, 'False': False, 'FALSE': False, False: False, 0: False, '0': False
                    }
                    coerced_df[column] = coerced_df[column].map(bool_map).astype(pd.BooleanDtype())
        
                elif bq_type == 'DATE':
                    coerced_df[column] = pd.to_datetime(coerced_df[column], errors='coerce').dt.date

                elif bq_type in ('DATETIME', 'TIMESTAMP'):
                    coerced_df[column] = pd.to_datetime(coerced_df[column], errors='coerce')
                    if bq_type == 'TIMESTAMP':
                        # Ensure UTC timezone for TIMESTAMP for our system
                        if coerced_df[column].dt.tz is None:
                            coerced_df[column] = coerced_df[column].dt.tz_localize('UTC')
                        else:
                            coerced_df[column] = coerced_df[column].dt.tz_convert('UTC')

                elif bq_type == 'STRING':
                    # Convert to string while preserving None as None --> Never string "None"
                    coerced_df[column] = coerced_df[column].apply(
                        lambda x: str(x) if pd.notna(x) else None
                    )

                logger.debug(f"Converted column {column} from {pandas_dtype} to {bq_type}")

            except Exception as exc:
                # Log error but continue with other columns
                logger.error(f"Failed to convert column {column} to {bq_type}: {str(exc)}", exc_info=True)

        return coerced_df

    def _add_missing_schema_columns(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Add any missing schema columns to DataFrame with null values
           Where nullable fields are added later on"""
        schema_fields = self.get_schema_fields()

        # Add any missing columns with None/null values
        for field in schema_fields:
            if field not in dataframe.columns:
                logger.debug(f"Adding missing schema field: {field}")
                dataframe[field] = None

        return dataframe

    def get_schema_fields(self) -> List[str]:
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
            if attrs.get("config_identifier") or attrs.get("configuration_identifier") or attrs.get("config_id"):
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
        
    def get_sync_fields(self) -> List[str]:
        """Get the field marked as sync_field"""
        return [
            field_name
            for field_name, attrs in self.field_attributes.items()
            if attrs.get("sync_field")
        ]
        
    def get_source_column_for_field(
      self, 
      field_name: str, 
      available_columns: List[str]
    ) -> Optional[str]:
      """
      Find which source column maps to this BigQuery field.
      
      Args:
          field_name: BigQuery field name
          available_columns: Available source columns (e.g., from Terra)
      
      Returns:
          Source column name that maps to this field, or None
      """
      field_def = self.schema_definition.get_field(field_name)

      if not field_def or not field_def.attributes.column_mappings:
          return None

      # Return first matching column from available columns
      for source_col in field_def.attributes.column_mappings:
          if source_col in available_columns:
              return source_col

      return None

    def drop_system_columns(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Drop columns marked as system_value from DataFrame.

        System value columns are auto-generated (like UUIDs, timestamps) and should
        be removed before syncing data back to Terra or other external systems.

        Args:
            dataframe: DataFrame containing the data

        Returns:
            DataFrame with system_value columns removed
        """
        logger.info("Dropping columns marked as system_value from DataFrame")

        # Find columns marked as system_value
        system_columns = [
            col
            for col, attrs in self.field_attributes.items()
            if attrs.get("system_value") is True
        ]

        # Remove system_value columns that are present in the dataframe
        columns_to_drop = [col for col in system_columns if col in dataframe.columns]

        if columns_to_drop:
            logger.debug(f"Dropping system columns: {columns_to_drop}")
            return dataframe.drop(columns=columns_to_drop)

        logger.debug("No system columns to drop")
        return dataframe