from typing import Optional, Dict, Any, List, Union
import pandas as pd
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField, LoadJobConfig
from .client import BigQueryClient
from bioforklift.data_processing.utils import infer_bigquery_param_type
from bioforklift.forklift_logging import setup_logger
from bioforklift.data_processing import SampleDataProcessor

logger = setup_logger(__name__)


class BigQuerySampleOperations:
    """
    BigQuery API operations for sample tables and their schemas.
    """

    def __init__(
        self,
        client: "BigQueryClient",
        table_name: str,
        sample_schema_yaml: Optional[str] = None,
        location: str = "us-central1",
    ):
        """
        Initialize BigQuery sample operations.

        Args:
            client: BigQuery client instance
            table_name: Name of the samples table
            sample_schema_yaml: Path to YAML schema file (required for data processing)
            sample_schema: Optional schema override (legacy support)
            location: BigQuery location
        """
        self.bq_client = client
        self.table_name = f"{client.project}.{client.dataset}.{table_name}"
        self.location = location

        # Initialize data processor - required for full functionality
        if sample_schema_yaml:
            self.data_processor = SampleDataProcessor(sample_schema_yaml)
            self.schema = self.data_processor.schema
            self.field_attributes = self.data_processor.field_attributes
            logger.info(f"Initialized with SampleDataProcessor: {sample_schema_yaml}")
        else:
            raise ValueError("Either sample_schema_yaml or sample_schema must be provided")

    def prepare_samples_dataframe(
        self,
        dataframe: pd.DataFrame,
        unique_ids_by_config: bool = False,
        config: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """
        Prepare DataFrame by filtering duplicates and adding system-generated values.

        Delegates all processing to SampleDataProcessor.

        Args:
            dataframe: Raw sample data from source
            config: Optional configuration for entity type mapping and field inheritance

        Returns:
            Processed DataFrame ready for BigQuery upload
        """
        if not self.data_processor:
            raise ValueError("Data processor not initialized - cannot process samples")

        logger.info("Preparing samples via SampleDataProcessor")

        # Get existing identifiers, optionally filtered by config_id for processes that might
        # have scenarios where multiple configurations are being processed, but duplicates are only considered for their own config
        if unique_ids_by_config and config and "id" in config:
            config_id = config["id"]
        else:
            config_id = None
        existing_ids = set(self.get_existing_identifiers(config_id=config_id))

        return self.data_processor.process_samples(dataframe, existing_ids, config)

    def coerce_dataframe_types(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Coerce DataFrame types to match schema.

        Delegates to data processor if available.
        """
        if self.data_processor:
            return self.data_processor._coerce_dataframe_types(dataframe)
        return dataframe

    def load_dataframe(
        self,
        dataframe: pd.DataFrame,
        schema: Optional[List[SchemaField]] = None,
        write_disposition: str = "WRITE_APPEND",
        config: Optional[Dict[str, Any]] = None,
        unique_ids_by_config: bool = False
    ) -> Dict[str, Any]:
        """
        Load DataFrame into BigQuery table.

        Args:
            dataframe: DataFrame to load (should be pre-processed)
            schema: Optional schema override
            write_disposition: BigQuery write disposition
            config: Optional configuration for processing

        Returns:
            Dictionary with load results
        """
        try:
            if len(dataframe) == 0:
                logger.info("No data to load, dataframe is empty")
                return {"success": True, "loaded": 0, "filtered": 0, "errors": None}

            # Process samples through data processor wrapper function
            processed_df = self.prepare_samples_dataframe(dataframe, unique_ids_by_config, config)

            if len(processed_df) == 0:
                logger.info("No samples to load after processing")
                return {"success": True, "loaded": 0, "filtered": len(dataframe), "errors": None}

            # Setup load job
            load_job_config = LoadJobConfig()
            load_job_config.write_disposition = write_disposition
            load_job_config.schema = schema or self.schema

            # Load to BigQuery
            logger.info(f"Loading {len(processed_df)} samples to BigQuery")
            load_job = self.bq_client.load_table_from_dataframe(
                processed_df, self.table_name, job_config=load_job_config, location=self.location
            )
            
            load_job.result() 

            logger.info(f"Successfully loaded {len(processed_df)} samples")
            return {
                "success": True,
                "loaded": len(processed_df),
                "filtered": len(dataframe) - len(processed_df),
                "errors": None,
            }

        except Exception as exc:
            logger.error(f"Error loading DataFrame: {str(exc)}")
            return {"success": False, "loaded": 0, "filtered": 0, "errors": str(exc)}

    def append_dataframe(self, dataframe: pd.DataFrame) -> Dict[str, Any]:
        """Append DataFrame without processing (legacy support)."""
        return self.load_dataframe(dataframe, write_disposition="WRITE_APPEND", config=None)

    def get_existing_identifiers(self, config_id: Optional[str] = None) -> List[str]:
        """
        Query existing sample identifiers from BigQuery.

        Args:
            config_id: Optional configuration ID to filter samples by

        Returns:
            List of existing sample identifiers
        """
        sample_id_field = self.data_processor.get_sample_identifier_field()
        if not sample_id_field:
            raise ValueError(
                "No field marked as 'sample_identifier' in schema. "
                "At least one field must have 'sample_identifier: true' attribute."
            )

        try:
            # Build query with optional config_id filter
            where_clauses = [f"{sample_id_field} IS NOT NULL"]

            if config_id:
                config_id_field = self.data_processor.get_config_identifier_field()
                if not config_id_field:
                    logger.warning("No config_identifier field defined in schema, ignoring config_id filter")
                else:
                    where_clauses.append(f"{config_id_field} = '{config_id}'")

            query = f"""
                SELECT DISTINCT {sample_id_field}
                FROM `{self.table_name}`
                WHERE {' AND '.join(where_clauses)}
            """
            result = self.bq_client.query(query).result()
            return [row[sample_id_field] for row in result]
        except Exception as exc:
            logger.error(f"Error querying existing identifiers: {str(exc)}")
            return []

    def get_recent_sample_uuids(self, config_id: str, limit: int = 1000) -> List[str]:
        """
        Get the UUIDs of the most recently loaded samples for a specific configuration.

        Args:
            config_id: Configuration ID
            limit: Maximum number of sample UUIDs to return
            
        Returns:
            List of sample UUIDs
        """
        # Get the field to use as the config identifier for identifying samples
        config_identifier_field = self.data_processor.get_config_identifier_field()
        
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
        
        # This function is a behomoth of a function, but it is needed to cover the various use cases
        # and its served its purpose well in the google-workflows implementation
        
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
                config_id_field = self.data_processor.get_config_identifier_field()
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
            samples_by_timeframe_job_config = bigquery.QueryJobConfig()
            samples_by_timeframe_job_config.query_parameters = params

            query_job = self.bq_client.query(
                samples_query, job_config=samples_by_timeframe_job_config
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
        
    
    def bulk_update_samples(self, updates: List[Dict[str, Any]], batch_size: int = 1000) -> Dict[str, Any]:
        """
        Bulk update samples using a single query.

        Args:
            updates: List of dictionaries with updates, each must have an 'id' field
                    Example: [{'id': '123', 'status': 'succeeded', 'upload_date': '2024-02-24'}]
            batch_size: Number of records to process in each batch (default: 1000)

        Returns:
            Dictionary with update results
        """
        # Function largely ported from the original bulk_update_samples function in google-workflows, 
        # but with some modifications to work with the BigQuery client and schema attributes
        
        all_updated_ids = []
        all_failed_updates = []
        
        try:
            if not updates:
                logger.info("No updates provided")
                return {"updated_count": 0, "updated_ids": [], "failed_updates": []}

            # Process updates and coerce types
            updates_to_process = []
            for update in updates:
                if "id" not in update:
                    logger.error("Update missing 'id' field, skipping")
                    continue

                sample_id = update["id"]
                update_data = {
                    k: v for k, v in update.items() if k != "id" and v is not None
                }

                # Coerce types using the data processor to handle numpy types and schema types
                if update_data:
                    update_data = self.data_processor.coerce_dict_types(update_data)
                    updates_to_process.append((sample_id, update_data))

            if not updates_to_process:
                logger.info("No updates provided")
                return {"updated_count": 0, "updated_ids": [], "failed_updates": []}

            # Gather fields to update
            all_fields = set()
            for _, update_data in updates_to_process:
                all_fields.update(update_data.keys())

            # Ensure fields exist in schema
            schema_fields = self.data_processor.get_schema_fields()
            invalid_fields = all_fields - set(schema_fields)
            if invalid_fields:
                logger.exception(f"Fields not in schema: {invalid_fields}")
                raise ValueError(f"Fields not in schema: {invalid_fields}")
            
            total_batches = (len(updates_to_process) + batch_size - 1) // batch_size
            logger.info(f"Processing {len(updates_to_process)} updates in {total_batches} batches of max {batch_size}")

            for batch_index in range(total_batches):
                start_idx = batch_index * batch_size
                end_idx = min(start_idx + batch_size, len(updates_to_process))
                batch = updates_to_process[start_idx:end_idx]
                
                logger.info(f"Processing batch {batch_index + 1}/{total_batches} with {len(batch)} updates")
                
                # Build CASE statements for each field
                update_statements = []
                for field in all_fields:
                    cases = []
                    for i, (sample_id, update_data) in enumerate(batch):
                        if field in update_data:
                            cases.append(f"WHEN id = @id_{i} THEN @val_{i}_{field}")

                    if cases:
                        update_statements.append(
                            f"{field} = CASE {' '.join(cases)} ELSE {field} END"
                        )

                # Build parameters
                params = []
                for i, (sample_id, update_data) in enumerate(batch):
                    params.append(
                        bigquery.ScalarQueryParameter(f"id_{i}", "STRING", sample_id)
                    )

                    for field, value in update_data.items():
                        param_name = f"val_{i}_{field}"

                        # Get field type from schema
                        field_def = self.data_processor.schema_definition.get_field(field)
                        param_type = field_def.field_type if field_def else "STRING"

                        params.append(
                            bigquery.ScalarQueryParameter(param_name, param_type, value)
                        )

                # Build update query, automatically update updated_at field
                update_query = f"""
                UPDATE `{self.table_name}`
                SET 
                    {', '.join(update_statements)},
                    updated_at = CURRENT_DATETIME()
                WHERE id IN ({','.join([f'@id_{i}' for i in range(len(batch))])})
                """

                execute_update_job_config = bigquery.QueryJobConfig()
                execute_update_job_config.query_parameters = params

                logger.debug(f"Executing bulk update query for batch {batch_index + 1} with {len(params)} parameters")

                execute_query_job = self.bq_client.query(
                    update_query, job_config=execute_update_job_config
                )
                execute_query_job.result()

                # Verify updates were applied
                verification_query = f"""
                SELECT id
                FROM `{self.table_name}`
                WHERE id IN ({','.join([f'@id_{i}' for i in range(len(batch))])})
                AND updated_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 1 MINUTE)
                """

                verify_job = self.bq_client.query(
                    verification_query, job_config=execute_update_job_config
                )
                batch_updated_ids = [row.id for row in verify_job.result()]
                all_updated_ids.extend(batch_updated_ids)

                # Determine which updates failed if any
                batch_failed_ids = set(item[0] for item in batch) - set(batch_updated_ids)
                batch_failed_updates = [
                    {
                        "id": item[0],
                        "error": "Update verification failed",
                        "data": item[1],
                    }
                    for item in batch
                    if item[0] in batch_failed_ids
                ]
                
                all_failed_updates.extend(batch_failed_updates)

                if len(batch_failed_updates) > 0:
                    logger.error(f"Failed to update {len(batch_failed_updates)} records in batch {batch_index + 1}")
                    logger.error(batch_failed_updates)
            
            # Final results
            if len(all_failed_updates) > 0:
                logger.error(f"Failed to update a total of {len(all_failed_updates)} records")
                
            return {
                "updated_count": len(all_updated_ids),
                "updated_ids": all_updated_ids,
                "failed_updates": all_failed_updates,
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
            
            query_params = []
            for name, value in parameters.items():
                param_type = infer_bigquery_param_type(value)
                query_params.append(
                    bigquery.ScalarQueryParameter(name, param_type, value)
                )

            custom_query_job_config = bigquery.QueryJobConfig()
            custom_query_job_config.query_parameters = query_params

            logger.debug(f"Executing query with parameters: {query_params}")

            query_job = self.bq_client.query(query, job_config=custom_query_job_config)
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
            config_identifier_field = self.data_processor.get_config_identifier_field()
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
            unique_submissions_job_config = bigquery.QueryJobConfig()
            unique_submissions_job_config.query_parameters = [
                bigquery.ScalarQueryParameter("config_id", "STRING", config_id)
            ]

            query_job = self.bq_client.query(query, job_config=unique_submissions_job_config)
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
            config_identifier_field = self.data_processor.get_config_identifier_field()
            if not config_identifier_field:
                raise ValueError("No config_identifier field defined in sample schema")
            
            # Get sample identifier field
            sample_identifier_field = self.data_processor.get_sample_identifier_field()
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
            config_identifier_field = self.data_processor.get_config_identifier_field()
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
            config_identifier_field = self.data_processor.get_config_identifier_field()
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