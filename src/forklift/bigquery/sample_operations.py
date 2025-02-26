from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid
import pandas as pd
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField, LoadJobConfig
from .client import BigQueryClient
from .utils import load_schema_from_yaml, parse_field_type


class BigQuerySampleOperations:
    """Base operations for BigQuery tables with support for custom field attributes containing sample data"""

    def __init__(
        self,
        client: "BigQueryClient",
        table_name: str,
        sample_schema_yaml: Optional[str] = None,
        schema: Optional[List[SchemaField]] = None,
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
        else:
            self.schema = schema

    def _generate_system_values(self, row_count: int) -> Dict[str, List[Any]]:
        """Generate system values for auto-populated fields going into the table"""
        # Need to cast the pandas equivalent to a BigQuery datetime - weirdly called Timestamp
        current_datetime = pd.Timestamp.now(tz="UTC")
        system_tracking_values = {}

        for field_name, attrs in self.field_attributes.items():
            if attrs.get("uuid_field"):
                system_tracking_values[field_name] = [
                    str(uuid.uuid4()) for _ in range(row_count)
                ]
            elif attrs.get("created_datetime"):
                system_tracking_values[field_name] = [current_datetime] * row_count

        return system_tracking_values

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

    def _filter_existing_samples(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove rows with existing sample identifiers"""
        try:
            # Need to find the sample identifier field from attributes
            sample_identifier_field = self.get_sample_identifier_field()

            if not sample_identifier_field:
                raise ValueError("No field marked as sample_identifier in schema")

            # Get existing identifiers for samples in the database
            existing_ids = set(self.get_existing_identifiers())

            # Filter out existing samples
            new_samples_df = df[~df[sample_identifier_field].isin(existing_ids)]

            filtered_count = len(df) - len(new_samples_df)
            if filtered_count > 0:
                print(f"Filtered out {filtered_count} existing samples")

            return new_samples_df

        except Exception as exc:
            raise RuntimeError(f"Error filtering existing samples: {str(exc)}")

    def _get_schema_fields(self) -> List[str]:
        """Get list of field names defined in the schema"""
        return [field.name for field in self.schema]

    def _filter_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Keep only columns that are defined in the schema"""
        schema_fields = self._get_schema_fields()
        extra_columns = set(df.columns) - set(schema_fields)
        if extra_columns:
            filtered_out_excess_columns_df = df.drop(columns=extra_columns)
        return filtered_out_excess_columns_df

    def _add_missing_schema_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add any missing schema columns to DataFrame with null values"""

        schema_fields = self._get_schema_fields()

        # Add any missing columns with None/null values
        for field in schema_fields:
            if field not in df.columns:
                df[field] = None

        return df

    def _map_field_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map source field names to BigQuery field names using mapping attributes"""

        for field_name, attrs in self.field_attributes.items():
            if "mapping" in attrs:
                source_fields = attrs["mapping"]
                if isinstance(source_fields, str):
                    source_fields = [source_fields]

                # Try each possible source field
                for source_field in source_fields:
                    if source_field in df.columns:
                        mapped_columns_df = df.rename(
                            columns={source_field: field_name}
                        )
                        break

        return self._add_missing_schema_columns(mapped_columns_df)

    def _prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare DataFrame by filtering duplicates and adding system-generated values"""
        df = df.copy()
        # First we need to map field names from source to BigQuery
        mapped_df = self._map_field_names(df)
        # Filter to only include schema-defined columns since this is what will be loaded
        bigquery_mapped_df = self._filter_columns(mapped_df)
        # Filter out rows with existing sample identifiers as to not port duplicates
        filtered_bigquery_mapped_df = self._filter_existing_samples(bigquery_mapped_df)

        if len(filtered_bigquery_mapped_df) == 0:
            return filtered_bigquery_mapped_df

        # Then add system values (datetime tracking) for remaining rows
        system_values = self._generate_system_values(len(df))

        for field_name, values in system_values.items():
            filtered_bigquery_mapped_df[field_name] = values

        return filtered_bigquery_mapped_df

    def load_dataframe(
        self,
        df: pd.DataFrame,
        schema: Optional[List[SchemaField]] = None,
        write_disposition: str = "WRITE_APPEND",
    ) -> Dict[str, Any]:
        """
        Load DataFrame into BigQuery table using load jobs

        Args:
            df: pandas DataFrame containing the data
            schema: Optional schema for the table
            write_disposition: Write append only supported in this operation
        """
        try:
            # Skip if DataFrame is empty
            if len(df) == 0:
                return {"success": True, "loaded": 0, "filtered": 0, "errors": None}

            job_config = LoadJobConfig()
            job_config.write_disposition = write_disposition

            if schema:
                job_config.schema = schema
            elif self.schema:
                job_config.schema = self.schema

            # Prepare DataFrame with filtering and system values
            initial_count = len(df)
            prepared_df = self._prepare_dataframe(df)
            filtered_count = initial_count - len(prepared_df)

            # Skip if all records were filtered
            if len(prepared_df) == 0:
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

            return {
                "success": True,
                "loaded": len(prepared_df),
                "filtered": filtered_count,
                "errors": None,
                "job_id": load_job.job_id,
            }

        except Exception as exc:
            return {"success": False, "errors": str(exc), "loaded": 0}

    def append_dataframe(
        self, df: pd.DataFrame, schema: Optional[List[SchemaField]] = None
    ) -> Dict[str, Any]:
        """Append DataFrame to existing table"""
        return self.load_dataframe(df, schema=schema, write_disposition="WRITE_APPEND")

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
        results = list(query_job.result())

        # Create mapping from BigQuery UUID to entity identifier
        entity_to_id_mapping = {row.entity_identifier: row.id for row in results}

        return entity_to_id_mapping

    def get_samples_created_today(self) -> pd.DataFrame:
        """
        Retrieves all samples that were created today using UTC timezone, but have not been uploaded yet.
        """
        try:
            # Build WHERE conditions, with uploaded_at being NULL
            where_conditions = [
                "DATE(created_at) = CURRENT_DATE()",
                "uploaded_at IS NULL",
            ]

            # Set up query parameters
            params = []

            # Check if we have a config identifier field in attributes
            config_id_field = next(
                (
                    field_name
                    for field_name, attrs in self.field_attributes.items()
                    if attrs.get("config_identifier")
                ),
                None,
            )

            if config_id_field:
                # If there is a config field in the schema - get its value from the field attributes
                config_id = self.field_attributes[config_id_field].get("value")
                if config_id:
                    where_conditions.append(f"{config_id_field} = @config_id")
                    params.append(
                        bigquery.ScalarQueryParameter("config_id", "STRING", config_id)
                    )

            # Build complete query
            samples_created_today_query = f"""
            SELECT *
            FROM `{self.table_name}`
            WHERE {' AND '.join(where_conditions)}
            ORDER BY created_at DESC
            """

            # Configure and run query
            bigquery_query_job_config = bigquery.QueryJobConfig()
            bigquery_query_job_config.query_parameters = params

            query_job = self.bq_client.query(
                samples_created_today_query, job_config=bigquery_query_job_config
            )

            # Convert results to dict
            samples_created_today_list_dict = [dict(row) for row in query_job.result()]

            return pd.DataFrame(samples_created_today_list_dict)

        except Exception as exc:
            raise RuntimeError(f"Error getting samples created today: {str(exc)}")

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
                return {"updated_count": 0, "updated_ids": [], "failed_updates": []}

            # Process updates
            updates_to_process = []
            for update in updates:
                if "id" not in update:
                    continue

                sample_id = update["id"]
                update_data = {
                    k: v for k, v in update.items() if k != "id" and v is not None
                }

                if update_data:
                    updates_to_process.append((sample_id, update_data))

            if not updates_to_process:
                return {"updated_count": 0, "updated_ids": [], "failed_updates": []}

            # Gather fields to update
            all_fields = set()
            for _, update_data in updates_to_process:
                all_fields.update(update_data.keys())

            # Ensure fields exist in schema
            schema_fields = self._get_schema_fields()
            invalid_fields = all_fields - set(schema_fields)
            if invalid_fields:
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

            # Build update query
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

            return {
                "updated_count": 0,
                "updated_ids": [],
                "failed_updates": failed_updates,
            }