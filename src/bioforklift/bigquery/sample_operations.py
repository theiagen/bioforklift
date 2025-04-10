from datetime import datetime
from typing import Optional, Dict, Any, List, Union
import uuid
import pandas as pd
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField, LoadJobConfig
from .client import BigQueryClient
from .utils import load_schema_from_yaml, parse_field_type
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)

class BigQuerySampleOperations:
    """Base operations for BigQuery tables with support for custom field attributes containing sample data"""

    def __init__(
        self,
        client: "BigQueryClient",
        table_name: str,
        sample_schema_yaml: Optional[str] = None,
        sample_schema: Optional[List[SchemaField]] = None,
        location: str = "us-central1",
    ):
        self.bq_client = client
        self.table_name = f"{client.project}.{client.dataset}.{table_name}"
        self.location = location

        # Load schema from YAML if provided, otherwise use schema parameter
        self.field_attributes = {}
        if sample_schema_yaml:
            schema_info = load_schema_from_yaml(sample_schema_yaml)
            self.schema = schema_info["schema"]
            self.field_attributes = schema_info["field_attributes"]
            logger.info(f"Schema loaded from YAML: {sample_schema_yaml}")
        else:
            self.schema = sample_schema
            logger.info("Schema loaded from parameter")

    def _generate_system_values(self, row_count: int) -> Dict[str, List[Any]]:
        """Generate system values for auto-populated fields going into the table"""
        # Need to cast the pandas equivalent to a BigQuery datetime - weirdly called Timestamp
        current_datetime = pd.Timestamp.now(tz="UTC")
        system_tracking_values = {}
        logger.debug(f"Timestamp for system values: {current_datetime}")
    
        for field_name, attrs in self.field_attributes.items():
            # Check for primary key fields
            if attrs.get("primary_key"):
                system_tracking_values[field_name] = [
                    str(uuid.uuid4()) for _ in range(row_count)
                ]
            # Direct check for created_at field
            elif field_name == "created_at":
                system_tracking_values[field_name] = [current_datetime] * row_count

        return system_tracking_values
    
    def _filter_existing_samples(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Remove rows with existing sample identifiers"""
        try:
            # Need to find the sample identifier field from attributes
            sample_identifier_field = self.get_sample_identifier_field()

            if not sample_identifier_field:
                logger.error("No field marked as sample_identifier in schema")
                raise ValueError("No field marked as sample_identifier in schema")

            # Get existing identifiers for samples in the database
            existing_ids = set(self.get_existing_identifiers())

            # Filter out existing samples
            new_samples_df = dataframe[~dataframe[sample_identifier_field].isin(existing_ids)]

            filtered_count = len(dataframe) - len(new_samples_df)
            if filtered_count > 0:
                logger.debug(f"Filtered out {filtered_count} existing samples")

            return new_samples_df

        except Exception as exc:
            logger.exception("Error filtering existing samples")
            raise RuntimeError(f"Error filtering existing samples: {str(exc)}")
        
    def _get_schema_fields(self) -> List[str]:
        """Get list of field names defined in the schema"""
        return [field.name for field in self.schema]
    
    def _add_missing_schema_columns(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Add any missing schema columns to DataFrame with null values"""

        schema_fields = self._get_schema_fields()

        # Add any missing columns with None/null values
        for field in schema_fields:
            if field not in dataframe.columns:
                logger.debug(f"Adding missing schema field: {field}")
                dataframe[field] = None

        return dataframe
    
    def _get_config_source_fields(self) -> Dict[str, str]:
        """
        Get fields that should be populated from parent configuration.
        
        Returns:
            Dictionary mapping field names to their config source fields
            e.g., {'config_identifier': 'id', 'workflow_name': 'terra_analysis_method'}
        """
        return {
            field_name: attrs.get('inherit_from_config')
            for field_name, attrs in self.field_attributes.items()
            if attrs.get('inherit_from_config')
        }
        
    def _filter_columns(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Keep only columns that are defined in the schema"""
        schema_fields = self._get_schema_fields()
        extra_columns = set(dataframe.columns) - set(schema_fields)
        if extra_columns:
            logger.debug(f"Filtering out extra columns: {extra_columns}")
            filtered_out_excess_columns_df = dataframe.drop(columns=extra_columns)
        return filtered_out_excess_columns_df
    
    def _map_field_names(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Map source field names to BigQuery field names using column_mappings attributes"""

        mapped_columns_df = dataframe.copy()
        
        for field_name, attrs in self.field_attributes.items():
            if "column_mappings" in attrs:
                source_fields = attrs["column_mappings"]
                if isinstance(source_fields, str):
                    source_fields = [source_fields]

                # Try each possible source field
                for source_field in source_fields:
                    if source_field in dataframe.columns:
                        mapped_columns_df = dataframe.rename(
                            columns={source_field: field_name}
                        )
                        break

        # Always return the DataFrame, whether mappings were applied or not
        return self._add_missing_schema_columns(mapped_columns_df)
    
    def _validate_sequence_files(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Validate that each sample has at least one sequence file field with a value.
        Removes rows that don't have any sequence files.
        
        Args:
            dataframe: DataFrame containing the data to validate
            
        Returns:
            DataFrame with only valid samples that have at least one sequence file
        """
        try:
            # Get fields marked as sequence_file
            sequence_file_fields = self.get_sequence_file_fields()
            
            if not sequence_file_fields:
                logger.info("No sequence file fields defined in schema, returning original DataFrame")
                # If no sequence file fields defined in schema, return original DataFrame
                return dataframe
            
            # Check if at least one sequence file field has a value for each row, fill with boolean
            has_sequence_file = dataframe[sequence_file_fields].notna().any(axis=1)
            
            # Filter DataFrame to keep only rows with at least one sequence file
            valid_samples_df = dataframe[has_sequence_file]
            
            filtered_count = len(dataframe) - len(valid_samples_df)
            if filtered_count > 0:
                logger.info(f"_validate_sequence_files: Filtered out {filtered_count} samples without sequence files")\
                
            return valid_samples_df
            
        except Exception as exc:
            raise RuntimeError(f"Error validating sequence files: {str(exc)}")
        
    def coerce_dataframe_types(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Coerce DataFrame column types to match schema definition
        Only converts columns where types don't already align
        
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
        
        # Map pandas dtypes to corresponding BigQuery types for comparison
        pandas_to_bq_type_map = {
            'int64': 'INTEGER',
            'Int64': 'INTEGER',
            'float64': 'FLOAT',
            'bool': 'BOOLEAN',
            'datetime64[ns]': 'DATETIME',
            'datetime64[ns, UTC]': 'DATETIME',
            'object': 'STRING',  # Most string columns will be object type
            'string': 'STRING'   # Some versions of pandas use string dtype
        }
        
        # Iterate through each column and attempt type conversion only if needed
        for column in coerced_df.columns:
            if column in field_type_map:
                bq_type = field_type_map[column]
                pandas_dtype = str(coerced_df[column].dtype)
                
                # Check if conversion is needed
                needs_conversion = True
                
                # Compare current pandas dtype with expected BigQuery type
                if pandas_dtype in pandas_to_bq_type_map:
                    pandas_equivalent_bq_type = pandas_to_bq_type_map[pandas_dtype]
                    
                    # Skip conversion if types already align
                    if (pandas_equivalent_bq_type == bq_type or
                        (pandas_equivalent_bq_type == 'INTEGER' and bq_type == 'INT64') or
                        (pandas_equivalent_bq_type == 'FLOAT' and bq_type == 'FLOAT64') or
                        (pandas_equivalent_bq_type == 'BOOLEAN' and bq_type == 'BOOL') or
                        (pandas_equivalent_bq_type == 'DATETIME' and bq_type == 'TIMESTAMP')):
                        needs_conversion = False
                        logger.debug(f"Column {column} already has compatible type {pandas_dtype}, skipping conversion")
                
                # Special case for strings as object type in pandas
                if bq_type == 'STRING' and pandas_dtype == 'object':
                    # Check if all non-null values are already strings
                    if all(isinstance(val, str) for val in coerced_df[column].dropna()):
                        needs_conversion = False
                        logger.debug(f"Column {column} already contains string values, skipping conversion")
                
                # Only attempt conversion if needed
                if needs_conversion:
                    try:
                        if bq_type == 'INTEGER' or bq_type == 'INT64':
                            # Convert to nullable integer type
                            coerced_df[column] = pd.to_numeric(coerced_df[column], errors='coerce')
                            coerced_df[column] = coerced_df[column].astype('Int64')  # pandas nullable integer type
                        elif bq_type == 'FLOAT' or bq_type == 'FLOAT64':
                            coerced_df[column] = pd.to_numeric(coerced_df[column], errors='coerce')
                        elif bq_type == 'BOOLEAN' or bq_type == 'BOOL':
                            coerced_df[column] = coerced_df[column].map({'true': True, 'false': False})
                        elif bq_type == 'DATE':
                            coerced_df[column] = pd.to_datetime(coerced_df[column], errors='coerce').dt.date
                        elif bq_type == 'DATETIME' or bq_type == 'TIMESTAMP':
                            coerced_df[column] = pd.to_datetime(coerced_df[column], errors='coerce')
                        elif bq_type == 'STRING':
                            # Convert all values to strings, handling possible numeric values like if sample id is 1234
                            coerced_df[column] = coerced_df[column].astype(str)
                        
                        logger.debug(f"Converted column {column} from {pandas_dtype} to {bq_type}")
                    except Exception as e:
                        # Log error but continue with other columns, will fail downstream if necessary
                        logger.warning(f"Error converting column {column} to {bq_type}: {str(e)}")
        
        return coerced_df

    def prepare_samples_dataframe(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        logger.info("Preparing samples; filtering duplicates and adding time tracking")
        """Prepare DataFrame by filtering duplicates and adding system-generated values"""
        dataframe = dataframe.copy()
        # First we need to map field names from source to BigQuery
        mapped_df = self._map_field_names(dataframe)
        # Filter to only include schema-defined columns since this is what will be loaded
        bigquery_mapped_df = self._filter_columns(mapped_df)
        # Filter out rows with existing sample identifiers as to not port duplicates
        filtered_bigquery_mapped_df = self._filter_existing_samples(bigquery_mapped_df)

        if len(filtered_bigquery_mapped_df) == 0:
            logger.info("No new samples to load after filtering duplicates")
            return filtered_bigquery_mapped_df
        
        # Validate that each sample has at least one sequence file
        validated_sequence_df = self._validate_sequence_files(filtered_bigquery_mapped_df)

        
        if len(validated_sequence_df) == 0:
            return validated_sequence_df


        # Then add system values (datetime tracking) for remaining rows
        system_values = self._generate_system_values(len(validated_sequence_df))

        for field_name, values in system_values.items():
            validated_sequence_df[field_name] = values
            
        # Coerce DataFrame types to match schema
        coerced_df = self.coerce_dataframe_types(validated_sequence_df)

        return coerced_df
    
    def get_sample_identifier_field(self) -> Optional[str]:
        """Get the field name marked as sample_identifier"""
        return next(
            (
                field_name
                for field_name, attrs in self.field_attributes.items()
                if attrs.get("sample_identifier")
            ),
            None,
        )
        
    def get_config_identifier_field(self) -> Optional[str]:
        """Get the field name marked as sample_identifier"""
        return next(
            (
                field_name
                for field_name, attrs in self.field_attributes.items()
                if attrs.get("config_identifier") or attrs.get("configuration_identifier") or attrs.get("config_id")
            ),
            None,
        )
        
    def get_sequence_file_fields(self) -> List[str]:
        """Get list of field names that are marked as sequence files in the schema"""
        return [
            field_name
            for field_name, attrs in self.field_attributes.items()
            if attrs.get("sequence_file") is True
        ]

    def get_sync_fields(self) -> List[str]:
        """
        Get fields marked as sync_field in the schema.

        Returns:
            List of field names that have sync_field: true
        """
        # Find fields with sync_field: true
        sync_fields = [
            field_name
            for field_name, attrs in self.field_attributes.items()
            if attrs.get("sync_field") is True
        ]

        return sync_fields
    
    def apply_configuration_sourced_fields(self, dataframe: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """
        Apply configuration values to fields in a DataFrame of samples.
        
        Args:
            dataframe: DataFrame containing sample records
            config: Dictionary containing configuration values
            
        Returns:
            DataFrame with configuration values applied to inheritance fields
        """
        if dataframe.empty or not config:
            return dataframe
        
        # Get fields that inherit from configuration
        config_inheritance_fields = self._get_config_source_fields()
        
        if not config_inheritance_fields:
            return dataframe
        
        config_sourced_field_df = dataframe.copy()
        
        for field_name, config_field in config_inheritance_fields.items():
            if config_field in config:
                # Apply the configuration field value to all rows in the DataFrame
                config_sourced_field_df[field_name] = config[config_field]
            else:
                # Log warning if configuration field not found
                logger.warning(f"Warning: Configuration field '{config_field}' not found in configuration")
        
        return config_sourced_field_df
    
    def prepare_samples_with_config(self, dataframe: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """
        Full preparation of samples with configuration applied.
        
        Args:
            dataframe: DataFrame containing sample data
            config: Dictionary containing configuration values
            
        Returns:
            DataFrame ready for upload with all validations and transformations applied
        """
        
        # Apply standard preparation
        prepared_df = self.prepare_samples_dataframe(dataframe)
        
        if prepared_df.empty:
            return prepared_df
        
        # Apply configuration inheritance, if no config identifier field, will return prepared_df
        return self.apply_configuration_sourced_fields(prepared_df, config)
        
    def get_existing_identifiers(self) -> List[str]:
        """Get all existing sample identifiers from the table"""
        try:
            # Find the sample key field from attributes
            sample_identifier_field = self.get_sample_identifier_field()

            if not sample_identifier_field:
                raise ValueError("No field marked as sample_identifier in schema")

            sample_identifier_query = f"""
            SELECT DISTINCT {sample_identifier_field}
            FROM `{self.table_name}`
            WHERE {sample_identifier_field} IS NOT NULL
            AND {sample_identifier_field} != ''
            ORDER BY {sample_identifier_field}
            """

            query_job = self.bq_client.query(sample_identifier_query)
            # Return list of identifiers for ease of use
            return [getattr(row, sample_identifier_field) for row in query_job.result()]

        except Exception as error:
            raise RuntimeError(f"Error fetching existing identifiers: {str(error)}")


    def load_dataframe(
        self,
        dataframe: pd.DataFrame,
        schema: Optional[List[SchemaField]] = None,
        write_disposition: str = "WRITE_APPEND",
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Load DataFrame into BigQuery table using load jobs

        Args:
            dataframe: pandas DataFrame containing the data
            schema: Optional schema for the table
            write_disposition: Write append only supported in this operation
        """
        try:
            # Skip if DataFrame is empty
            if len(dataframe) == 0:
                logger.info("No data to load, dataframe is empty")
                return {"success": True, "loaded": 0, "filtered": 0, "errors": None}

            job_config = LoadJobConfig()
            job_config.write_disposition = write_disposition
            logger.info(f"JobConfig created with write_disposition set to: {write_disposition}")

            if schema:
                logger.info("Schema provided")

                # This comes from schema passed to load_dataframe
                job_config.schema = schema
            elif self.schema:
                logger.info("No schema provided, using self's schema")

                # This self.schema is from creation of operations object (example_sample_shema.yaml)
                job_config.schema = self.schema

            # Prepare DataFrame with filtering and system values
            initial_count = len(dataframe)
            logger.info(f"Initial record count: {initial_count}")

            #might want to rename this config and the schema so they arent confused. 
            if config:
                prepared_df = self.prepare_samples_with_config(dataframe, config)
            else:
                prepared_df = self.prepare_samples_dataframe(dataframe)

            filtered_count = initial_count - len(prepared_df)
            logger.info(f"Filtered {filtered_count} total records")

            # Skip if all records were filtered
            if len(prepared_df) == 0:
                logger.info("No records to load after filtering, all were skipped")
                return {
                    "success": True,
                    "loaded": 0,
                    "filtered": filtered_count,
                    "errors": None,
                }

            load_job = self.bq_client.load_table_from_dataframe(
                dataframe=prepared_df,
                destination=self.table_name,
                job_config=job_config,
                location=self.location,
            )

            # Wait for job to complete
            load_job.result()
            logger.info(f"Loading dataframe to BigQuery complete; job_id: {load_job.job_id}, loaded: {len(prepared_df)}")
            return {
                "success": True,
                "loaded": len(prepared_df),
                "filtered": filtered_count,
                "errors": None,
                "job_id": load_job.job_id,
            }
            
        except Exception as exc:
            logger.exception(f"Error loading DataFrame {str(exc)}")
            return {"success": False, "errors": str(exc), "loaded": 0}

    def append_dataframe(
        self, dataframe: pd.DataFrame, schema: Optional[List[SchemaField]] = None
    ) -> Dict[str, Any]:
        """Append DataFrame to existing table"""
        # Helper function to append data to an existing table
        return self.load_dataframe(dataframe, schema=schema, write_disposition="WRITE_APPEND")

    def get_entity_id_mapping(self) -> Dict[str, str]:
        """
        Get a mapping between BigQuery UUIDs and entity identifiers.

        Returns:
            Dictionary mapping BigQuery entity identifiers to UUIDS
            {"entity_identifier1": ""uuid1","entity_identifier2": "uuid2", ...}
        """
        # Will need to optomize this function for large datasets

        sample_identifier_field_name = self.get_sample_identifier_field()

        query = f"""
        SELECT id, {sample_identifier_field_name}
        FROM `{self.table_name}`
        """
        
        query_job = self.bq_client.query(query)
        logger.info(f"Querying BigQuery for entity identifier mapping")
        results = list(query_job.result())

        # Create mapping from BigQuery UUID to entity identifier
        entity_to_id_mapping = {row.entity_identifier: row.id for row in results}

        return entity_to_id_mapping
    
    def get_recent_sample_ids(self, config_id: str, limit: int = 1000) -> List[str]:
        """
        Get the IDs of the most recently loaded samples for a specific configuration.
        
        Args:
            config_id: Configuration ID
            limit: Maximum number of sample IDs to return
            
        Returns:
            List of sample IDs
        """
        # Get the field to use as the config identifier for identifying samples
        config_identifier_field = self.get_config_identifier_field()
        
        query = f"""
        SELECT id
        FROM `{self.table_name}`
        WHERE {config_identifier_field} = @config_id
        AND uploaded_at IS NULL
        ORDER BY created_at DESC
        LIMIT @limit
        """
        
        query_params = [
            bigquery.ScalarQueryParameter("config_id", "STRING", config_id),
            bigquery.ScalarQueryParameter("limit", "INTEGER", limit)
        ]
        
        job_config = bigquery.QueryJobConfig(query_parameters=query_params)
        
        query_job = self.bq_client.query(query, job_config=job_config)
        
        return [row["id"] for row in query_job]
    
    def get_samples_by_timeframe(
        self, 
        timeframe: str = "today",
        days_back: int = None,
        hours_back: int = None,
        start_datetime: str = None, 
        end_datetime: str = None,
        uploaded_filter: str = "not_uploaded",
        submitted_filter: str = "not_submitted",
        config_id: str = None, 
        set_name: str = None
    ) -> pd.DataFrame:
        """
        Retrieves samples based on a configurable timeframe.
        
        Args:
            timeframe: Predefined timeframe - "today", "yesterday", "week", "month", "custom", "hourly" for when to grab samples
            days_back: Number of days to look back (used when timeframe is "custom")
            hours_back: Number of hours to look back (used when timeframe is "hourly" or "custom")
            start_datetime: Start datetime in 'YYYY-MM-DD HH:MM:SS' format (used when timeframe is "custom")
            end_datetime: End datetime in 'YYYY-MM-DD HH:MM:SS' format (used when timeframe is "custom")
            uploaded_filter: Filter for uploaded status - "not_uploaded", "uploaded", "all"
            submitted_filter: Filter for submission status - "not_submitted", "submitted", "all"
            config_id: Configuration identifier to filter samples by
            set_name: Name of the set to filter samples by
        
        Returns:
            DataFrame containing the samples matching the timefrime criteria
        """
        
        # This function is a behomoth and a good candidate for refactoring
        # But need to still figure out the best way to implement a more modular solution
        # For how to configure when to grab samples to meet different use cases
        # But trying to be flexible enough to meet ~most use cases
        
        try:
            # Determine date condition based on timeframe using match statement
            # Love the python match statements from 3.10+
            timeframe = timeframe.lower() if timeframe else "today"
            
            match timeframe:
                case "today":
                    date_condition = "DATE(created_at) = CURRENT_DATE()"
                case "yesterday":
                    date_condition = "DATE(created_at) = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)"
                case "week":
                    date_condition = "DATE(created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)"
                case "month":
                    date_condition = "DATE(created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)"
                case "hourly":
                    hours = hours_back if hours_back is not None else 1
                    date_condition = f"created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL {hours} HOUR)"
                case "custom":
                    if hours_back is not None:
                        date_condition = f"created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL {hours_back} HOUR)"
                    elif days_back is not None:
                        date_condition = f"DATE(created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)"
                    elif start_datetime and end_datetime:
                        date_condition = f"created_at BETWEEN DATETIME('{start_datetime}') AND DATETIME('{end_datetime}')"
                    elif start_datetime:
                        date_condition = f"created_at >= DATETIME('{start_datetime}')"
                    else:
                        # Default to today for any unrecognized custom timeframe
                        date_condition = "DATE(created_at) = CURRENT_DATE()"
                case _:
                    # Default to today for any unrecognized timeframe - may want to be stricter here
                    date_condition = "DATE(created_at) = CURRENT_DATE()"
            
            # Build WHERE conditions to feed to the bigquery query
            where_conditions = [date_condition]
            
            # Add uploaded filter condition using match statement
            uploaded_filter = uploaded_filter.lower() if uploaded_filter else "not_uploaded"
            
            # When all specified should just be for necessary overrides, not for general use
            match uploaded_filter:
                case "not_uploaded":
                    where_conditions.append("uploaded_at IS NULL")
                case "uploaded":
                    where_conditions.append("uploaded_at IS NOT NULL")
                case "all":
                    pass
                
            submitted_filter = submitted_filter.lower() if submitted_filter else "all"
            # Grab samples that have been submitted at yet or not
            match submitted_filter:
                case "not_submitted":
                    where_conditions.append("submitted_at IS NULL")
                case "submitted":
                    where_conditions.append("submitted_at IS NOT NULL")
                case "all":
                    pass
            
            # Set up query parameters
            params = []
            
            if config_id:
                config_id_field = self.get_config_identifier_field()
                if config_id_field:
                    where_conditions.append(f"{config_id_field} = @config_id")
                    params.append(
                        bigquery.ScalarQueryParameter("config_id", "STRING", config_id)
                    )
                else:
                    logger.info("Config identifier source field not found in sample schema, ignoring config_id filter")
            
            # Add filter by set name (upload_source) if provided
            if set_name:
                where_conditions.append("upload_source = @set_name")
                params.append(
                    bigquery.ScalarQueryParameter("set_name", "STRING", set_name)
                )
                
            # Build complete query
            samples_query = f"""
            SELECT *
            FROM `{self.table_name}`
            WHERE {' AND '.join(where_conditions)}
            ORDER BY created_at DESC
            """
            
            # Configure and run query
            bigquery_query_job_config = bigquery.QueryJobConfig()
            bigquery_query_job_config.query_parameters = params
            
            query_job = self.bq_client.query(
                samples_query, job_config=bigquery_query_job_config
            )
            
            # Convert results to dict
            samples_list_dict = [dict(row) for row in query_job.result()]
            
            return pd.DataFrame(samples_list_dict)
        
        except Exception as exc:
            logger.exception(f"Error getting samples by timeframe: {str(exc)}")
            raise RuntimeError(f"Error getting samples by timeframe: {str(exc)}")

    def get_samples_created_today(self) -> pd.DataFrame:
        """
        Retrieves all samples that were created today using UTC timezone, but have not been uploaded yet.
        This will be the most common use case for getting samples to upload.
        """
        return self.get_samples_by_timeframe(
            timeframe="today", 
            uploaded_filter="not_uploaded"
        )
        
    def get_recent_samples_by_hour(self, hours: int = 1, uploaded_filter: str = "not_uploaded") -> pd.DataFrame:
        """
        Retrieves samples created within the last specified hours.
        
        Args:
            hours: Number of hours to look back when processing the query
            uploaded_filter: Filter for uploaded status - "not_uploaded", "uploaded", "all"
            
        Returns:
            DataFrame containing the samples from the last specified hours
        """
        return self.get_samples_by_timeframe(
            timeframe="hourly",
            hours_back=hours,
            uploaded_filter=uploaded_filter
        )
        
    
    def bulk_update_samples(self, updates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Bulk update samples using a single query.

        Args:
            updates: List of dictionaries with updates, each must have an 'id' field
                    Example: [{'id': '123', 'status': 'succeeded', 'upload_date': '2024-02-24'}]

        Returns:
            Dictionary with update results
        """
        # Function largely ported from the original bulk_update_samples function in google-workflows, 
        # but with some modifications to work with the BigQuery client and schema attributes
        try:
            if not updates:
                logger.info("No updates provided")
                return {"updated_count": 0, "updated_ids": [], "failed_updates": []}

            # Process updates
            updates_to_process = []
            for update in updates:
                if "id" not in update:
                    logger.error("Update missing 'id' field, skipping")
                    continue

                sample_id = update["id"]
                update_data = {
                    k: v for k, v in update.items() if k != "id" and v is not None
                }

                if update_data:
                    updates_to_process.append((sample_id, update_data))

            if not updates_to_process:
                logger.info("No updates provided")
                return {"updated_count": 0, "updated_ids": [], "failed_updates": []}

            # Gather fields to update
            all_fields = set()
            for _, update_data in updates_to_process:
                all_fields.update(update_data.keys())

            # Ensure fields exist in schema
            schema_fields = self._get_schema_fields()
            invalid_fields = all_fields - set(schema_fields)
            if invalid_fields:
                logger.exception(f"Fields not in schema: {invalid_fields}")
                raise ValueError(f"Fields not in schema: {invalid_fields}")

            # Build CASE statements for each field
            update_statements = []
            for field in all_fields:
                cases = []
                for i, (sample_id, update_data) in enumerate(updates_to_process):
                    if field in update_data:
                        cases.append(f"WHEN id = @id_{i} THEN @val_{i}_{field}")

                if cases:
                    update_statements.append(
                        f"{field} = CASE {' '.join(cases)} ELSE {field} END"
                    )

            # Build parameters
            params = []
            for i, (sample_id, update_data) in enumerate(updates_to_process):
                params.append(
                    bigquery.ScalarQueryParameter(f"id_{i}", "STRING", sample_id)
                )

                for field, value in update_data.items():
                    param_name = f"val_{i}_{field}"

                    # Determine parameter type from schema or value
                    field_def = next((f for f in self.schema if f.name == field), None)
                    param_type = parse_field_type(field_def.field_type)

                    params.append(
                        bigquery.ScalarQueryParameter(param_name, param_type, value)
                    )

            # Build update query, automatically update updated_at field
            update_query = f"""
            UPDATE `{self.table_name}`
            SET 
                {', '.join(update_statements)},
                updated_at = CURRENT_DATETIME()
            WHERE id IN ({','.join([f'@id_{i}' for i in range(len(updates_to_process))])})
            """

            # Execute update
            exectue_job_config = bigquery.QueryJobConfig()
            exectue_job_config.query_parameters = params

            logger.debug(f"Executing bulk update query with params: \n{params}")

            execute_query_job = self.bq_client.query(
                update_query, job_config=exectue_job_config
            )
            execute_query_job.result()

            # Verify updates were applied
            verification_query = f"""
            SELECT id
            FROM `{self.table_name}`
            WHERE id IN ({','.join([f'@id_{i}' for i in range(len(updates_to_process))])})
            AND updated_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 1 MINUTE)
            """

            verify_job = self.bq_client.query(
                verification_query, job_config=exectue_job_config
            )
            updated_ids = [row.id for row in verify_job.result()]

            # Determine which updates failed if any
            failed_ids = set(update[0] for update in updates_to_process) - set(
                updated_ids
            )
            failed_updates = [
                {
                    "id": update[0],
                    "error": "Update verification failed",
                    "data": update[1],
                }
                for update in updates_to_process
                if update[0] in failed_ids
            ]

            if len(failed_updates) > 0:
                logger.error(f"Failed to update {len(failed_updates)} records")
                logger.error(failed_updates)
                
            return {
                "updated_count": len(updated_ids),
                "updated_ids": updated_ids,
                "failed_updates": failed_updates,
            }

        except Exception as exc:
            error_message = f"Error in bulk update: {str(exc)}"
            failed_updates = [
                {
                    "id": update.get("id", "unknown"),
                    "error": error_message,
                    "data": {k: v for k, v in update.items() if k != "id"},
                }
                for update in updates
            ]

            if len(failed_updates) > 0:
                logger.error(f"Failed to update {len(failed_updates)} records")
                logger.error(failed_updates)

            return {
                "updated_count": 0,
                "updated_ids": [],
                "failed_updates": failed_updates,
            }
            
    def query_samples(
        self,
        conditions: List[str] = None,
        parameters: Dict[str, Any] = None,
        fields: List[str] = None,
        order_by: str = "created_at DESC",
        limit: int = None,
        return_as_df: bool = True
    ) -> Union[pd.DataFrame, List[Dict[str, Any]]]:
        """
        Execute a custom query against the samples table with flexible conditions.
        
        Args:
            conditions: List of SQL WHERE conditions (will be joined with AND)
            parameters: Dictionary of query parameters (for safe parameterized queries)
            fields: List of fields to select (defaults to all fields)
            order_by: Field(s) to order results by
            limit: Maximum number of results to return
            return_as_df: Whether to return results as DataFrame (True) or list of dicts (False)
            
        Returns:
            Either pandas DataFrame or list of dictionaries with query results
        """
        # Needed to add more generic query function to allow for more flexible querying
        logger.debug(f"Querying samples with conditions: {conditions}, parameters: {parameters}")
        try:
            # Set default values
            if conditions is None:
                conditions = []
            if parameters is None:
                parameters = {}
            
            # Build field selection
            select_clause = "*"
            if fields:
                select_clause = ", ".join(fields)
            
            # Build WHERE clause
            where_clause = ""
            if conditions:
                where_clause = f"WHERE {' AND '.join(conditions)}"
            
            # Build ORDER BY clause
            order_clause = ""
            if order_by:
                order_clause = f"ORDER BY {order_by}"
            
            # Build LIMIT clause
            limit_clause = ""
            if limit:
                limit_clause = f"LIMIT {limit}"
            
            # Construct full query
            query = f"""
            SELECT {select_clause}
            FROM `{self.table_name}`
            {where_clause}
            {order_clause}
            {limit_clause}
            """
            
            # Set up query parameters
            query_params = []
            for name, value in parameters.items():
                # Determine parameter type based on Python type
                param_type = "STRING"
                if isinstance(value, int):
                    param_type = "INT64"
                elif isinstance(value, float):
                    param_type = "FLOAT64"
                elif isinstance(value, bool):
                    param_type = "BOOL"
                elif isinstance(value, (datetime, pd.Timestamp)):
                    param_type = "TIMESTAMP"
                
                query_params.append(
                    bigquery.ScalarQueryParameter(name, param_type, value)
                )
            
            # Configure and execute query
            job_config = bigquery.QueryJobConfig()
            job_config.query_parameters = query_params

            logger.debug(f"Executing query with parameters: {query_params}")

            query_job = self.bq_client.query(query, job_config=job_config)
            results = query_job.result()
            
            # Convert to desired output format
            if return_as_df:
                logger.info("Returning results as DataFrame")
                return pd.DataFrame([dict(row) for row in results])
            else:
                logger.info("Returning results in array format")
                return [dict(row) for row in results]
        
        except Exception as exc:
            logger.exception(f"Error executing query: {str(exc)}")
            raise RuntimeError(f"Error executing query: {str(exc)}")

    def get_unique_submission_ids(
        self,
        config_id: str,
        need_workflow_id: bool = True,
        days_back: int = 30
    ) -> List[str]:
        """
        Get unique Terra submission IDs for samples associated with a configuration.
        
        Args:
            config_id: Configuration ID to filter by
            need_workflow_id: If True, only return IDs for samples missing workflow IDs
            days_back: Number of days to look back
            
        Returns:
            List of unique submission IDs
        """
        try:
            # Get config identifier field
            config_identifier_field = self.get_config_identifier_field()
            if not config_identifier_field:
                logger.error("No config_identifier field defined in sample schema")
                raise ValueError("No config_identifier field defined in sample schema")
            
            # Build query conditions
            conditions = [
                f"{config_identifier_field} = @config_id",
                "terra_submission_id IS NOT NULL",
                "terra_submission_id != ''",
                f"created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL {days_back} DAY)"
            ]
            
            # Add workflow id condition if needed
            if need_workflow_id:
                conditions.append("(terra_workflow_id IS NULL OR terra_workflow_id = '')")
            
            # Execute a simpler query that doesn't try to order by created_at
            query = f"""
            SELECT DISTINCT terra_submission_id
            FROM `{self.table_name}`
            WHERE {' AND '.join(conditions)}
            """
            
            # Configure and execute query
            job_config = bigquery.QueryJobConfig()
            job_config.query_parameters = [
                bigquery.ScalarQueryParameter("config_id", "STRING", config_id)
            ]
            
            query_job = self.bq_client.query(query, job_config=job_config)
            results = query_job.result()
            
            # Extract submission IDs
            submission_ids = [row.terra_submission_id for row in results if row.terra_submission_id]
            
            return submission_ids
            
        except Exception as exc:
            raise RuntimeError(f"Error getting unique submission IDs: {str(exc)}")

    def get_samples_by_entity_names(
        self,
        config_id: str,
        entity_names: List[str]
    ) -> pd.DataFrame:
        """
        Get samples matching specific entity names for a configuration.
        
        Args:
            config_id: Configuration ID to filter by
            entity_names: List of entity names to match
            
        Returns:
            DataFrame containing matched samples
        """
        try:
            if not entity_names:
                return pd.DataFrame()  # Return empty DataFrame if no entity names provided
                
            # Get config identifier field
            config_identifier_field = self.get_config_identifier_field()
            if not config_identifier_field:
                raise ValueError("No config_identifier field defined in sample schema")
            
            # Get sample identifier field
            sample_identifier_field = self.get_sample_identifier_field()
            if not sample_identifier_field:
                raise ValueError("No sample_identifier field defined in sample schema")
            
            # Create parameter placeholders for entity names
            placeholders = []
            params = {"config_id": config_id}
            
            for i, name in enumerate(entity_names):
                param_name = f"entity_{i}"
                placeholders.append(f"@{param_name}")
                params[param_name] = name
            
            # Build conditions, use standard IN operator with the list of parameters
            conditions = [
                f"{config_identifier_field} = @config_id",
                f"{sample_identifier_field} IN ({', '.join(placeholders)})"
            ]
            
            # Execute query
            return self.query_samples(
                conditions=conditions,
                parameters=params
            )
            
        except Exception as exc:
            raise RuntimeError(f"Error getting samples by entity names: {str(exc)}")

    def get_incomplete_workflow_samples(
        self,
        config_id: str,
        days_back: int = 30,
        limit: int = 1000
    ) -> pd.DataFrame:
        """
        Get samples with incomplete workflow states.
        Final States: 'Succeeded', 'Failed', 'Aborted'
        
        Args:
            config_id: Configuration ID to filter by
            days_back: Number of days to look back
            limit: Maximum number of samples to return
            
        Returns:
            DataFrame containing samples with incomplete workflow states
        """
        # Sometimes workflow metadata is not immediately available, so we need to check for incomplete states
        try:
            # Get config identifier field
            config_identifier_field = self.get_config_identifier_field()
            if not config_identifier_field:
                raise ValueError("No config_identifier field defined in sample schema")
            
            # Build conditions
            conditions = [
                f"{config_identifier_field} = @config_id",
                "terra_workflow_id IS NOT NULL",
                "terra_workflow_id != ''",
                "(workflow_state IS NULL OR workflow_state = '' OR workflow_state NOT IN ('Succeeded', 'Failed', 'Aborted'))",
                f"created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL {days_back} DAY)"
            ]
            
            # Query the samples where the workflow state is not in a final state
            return self.query_samples(
                conditions=conditions,
                parameters={"config_id": config_id},
                limit=limit
            )
            
        except Exception as exc:
            raise RuntimeError(f"Error getting incomplete workflow samples: {str(exc)}")

    def get_workflow_state_summary(
        self,
        config_id: str
    ) -> Dict[str, int]:
        """
        Get a summary of workflow states for a configuration.
        
        Args:
            config_id: Configuration ID to filter by
            
        Returns:
            Dictionary mapping workflow states to counts
        """
        try:
            # Get config identifier field
            config_identifier_field = self.get_config_identifier_field()
            if not config_identifier_field:
                raise ValueError("No config_identifier field defined in sample schema")
            
            # Build query
            query = f"""
            SELECT workflow_state, COUNT(*) as count
            FROM `{self.table_name}`
            WHERE {config_identifier_field} = @config_id
            GROUP BY workflow_state
            """
            
            # Configure and execute query
            job_config = bigquery.QueryJobConfig()
            job_config.query_parameters = [
                bigquery.ScalarQueryParameter("config_id", "STRING", config_id)
            ]
            
            query_job = self.bq_client.query(query, job_config=job_config)
            results = query_job.result()
            
            # Build summary dictionary
            summary = {}
            for row in results:
                state = row.get('workflow_state')
                if state is None:
                    state = 'None'
                summary[state] = row.get('count', 0)
            
            return summary
            
        except Exception as exc:
            raise RuntimeError(f"Error getting workflow state summary: {str(exc)}")