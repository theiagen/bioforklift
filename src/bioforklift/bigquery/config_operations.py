from pathlib import Path
from typing import Optional, Dict, Any, List, Union
import pandas as pd
import json
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField, LoadJobConfig
from .client import BigQueryClient
from bioforklift.forklift_logging import setup_logger
from bioforklift.data_processing import ConfigProcessor

logger = setup_logger(__name__)


class BigQueryConfigOperations:

    def __init__(
        self,
        client: "BigQueryClient",
        table_name: str,
        config_schema_yaml: Optional[str] = None,
        config_schema: Optional[List[SchemaField]] = None,
        location: str = "us-central1",
    ):
        """
        Initialize BigQuery config operations.

        Args:
            client: BigQuery client instance
            table_name: Name of the configs table
            config_schema_yaml: Path to YAML schema file (required for data processing)
            config_schema: Optional schema override (legacy support)
            location: BigQuery location
        """
        self.bq_client = client
        self.table_name = f"{client.project}.{client.dataset}.{table_name}"
        self.location = location

        # Initialize data processor - required for full functionality
        if config_schema_yaml:
            self.data_processor = ConfigProcessor(config_schema_yaml)
            self.schema = self.data_processor.schema
            self.field_attributes = self.data_processor.field_attributes
            logger.info(f"Initialized with ConfigProcessor: {config_schema_yaml}")
        else:
            raise ValueError("Either config_schema_yaml or config_schema must be provided")

    def create_config(
        self, config_data: Union[Dict[str, Any], str, Path]
    ) -> Dict[str, Any]:
        """
        Create a new configuration in BigQuery.

        Args:
            config_data: Configuration dict, JSON string, or path to JSON file

        Returns:
            Created configuration dictionary
        """
        # Load config from file if path provided
        if isinstance(config_data, (str, Path)):
            config_path = Path(config_data)
            if not config_path.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")

            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            config = config_data.copy()

        processed_config = self.data_processor.prepare_config_for_insert(config)

        # Insert into BigQuery
        try:
            _ = self.bq_client.insert_rows(self.table_name, [processed_config])

            logger.info(f"Created config with ID: {processed_config.get('id')}")
            return processed_config

        except Exception as exc:
            logger.error(f"Error creating config: {exc}")
            raise

    def create_configs_from_directory(
        self, directory_path: Union[str, Path], pattern: str = "*.json"
    ) -> List[Dict[str, Any]]:
        """
        Create multiple configurations from JSON files in a directory.

        Args:
            directory_path: Path to directory containing JSON configuration files
            pattern: File pattern to match (default: "*.json")

        Returns:
            List of created configurations
        """
        directory = Path(directory_path) if isinstance(directory_path, str) else directory_path

        if not directory.is_dir():
            raise ValueError(f"Directory not found: {directory}")

        json_files = list(directory.glob(pattern))
        logger.info(f"Found {len(json_files)} JSON files in {directory}")

        if not json_files:
            logger.warning("No JSON files found")
            return []

        created_configs = []
        errors = []

        for json_file in json_files:
            try:
                config = self.create_config(json_file)
                created_configs.append(config)
            except Exception as exc:
                errors.append({"file": str(json_file), "error": str(exc)})

        if errors and not created_configs:
            raise RuntimeError(f"All config creations failed. Errors: {errors}")
        elif errors:
            logger.warning(f"Some configs failed to create: {errors}")

        logger.info(f"Successfully created {len(created_configs)} configs")
        return created_configs

    def get_config(self, config_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single configuration by ID.

        Args:
            config_id: Configuration ID

        Returns:
            Configuration dictionary or None if not found
        """
        try:
            query = f"""
                SELECT *
                FROM `{self.table_name}`
                WHERE id = '{config_id}'
                LIMIT 1
            """
            result = self.bq_client.query(query).to_dataframe()

            if result.empty:
                logger.warning(f"Config not found: {config_id}")
                return None

            return result.iloc[0].to_dict()

        except Exception as exc:
            logger.error(f"Error getting config: {exc}")
            return None

    def get_configs(
        self,
        active_only: bool = False,
        entity_type: Optional[str] = None,
        skip_transferred: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get configurations with optional filters

        Args:
            active_only: Whether to return only active configurations
            entity_type: Filter by entity type
            state: Filter by state

        Returns:
            List of configuration dictionaries
        """
        conditions = []
        params = []

        if active_only:
            conditions.append("active = @active")
            params.append(bigquery.ScalarQueryParameter("active", "BOOL", True))

        if entity_type:
            conditions.append("entity_type = @entity_type")
            params.append(
                bigquery.ScalarQueryParameter("entity_type", "STRING", entity_type)
            )

        # Check if we need to skip transferred configs
        # This is for conditions where configs are one and done and to never consider them again
        if skip_transferred:
            conditions.append("(transferred IS NULL OR transferred = @transferred)")
            params.append(bigquery.ScalarQueryParameter("transferred", "BOOL", False))

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
        SELECT *
        FROM `{self.table_name}`
        {where_clause}
        ORDER BY created_at DESC
        """
        logger.info(f"Getting configs that are active: {active_only}")
        job_config = bigquery.QueryJobConfig()
        job_config.query_parameters = params

        query_job = self.bq_client.query(query, job_config=job_config)
        return [dict(row) for row in query_job.result()] if query_job.result() else []

    def update_config(
        self, config_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a configuration

        Args:
            config_id: ID of the configuration to update
            update_data: Dictionary with fields to update

        Returns:
            Updated configuration or None if not found
        """
        # Validate update data
        if not update_data:
            logger.warning("No fields to update")
            return self.get_config(config_id)

        # Ensure fields exist in schema
        
        schema_fields = self.data_processor.get_schema_fields()

        invalid_fields = set(update_data.keys()) - set(schema_fields)
        if invalid_fields:
            raise ValueError(f"Fields not in schema: {invalid_fields}")

        # Handle special fields like JSON objects
        processed_data = update_data.copy()
        for field in self.schema:
            if field.field_type.upper() == "STRING" and field.name in processed_data:
                if isinstance(processed_data[field.name], dict) or isinstance(
                    processed_data[field.name], list
                ):
                    processed_data[field.name] = json.dumps(processed_data[field.name])

        # Build update statement
        update_statements = []
        params = [bigquery.ScalarQueryParameter("id", "STRING", config_id)]

        for field, value in processed_data.items():
            if field not in ["id", "created_at"]:
                update_statements.append(f"{field} = @{field}")

                
                field_def = self.data_processor.schema_definition.get_field(field)
                param_type = field_def.field_type if field_def else "STRING"

                params.append(bigquery.ScalarQueryParameter(field, param_type, value))

        # Add updated_at timestamp
        for field_name, attrs in self.field_attributes.items():
            if field_name == "updated_at" or attrs.get("updated_datetime"):
                update_statements.append(f"{field_name} = CURRENT_DATETIME()")

        # Build and execute query
        update_query = f"""
        UPDATE `{self.table_name}`
        SET {', '.join(update_statements)}
        WHERE id = @id
        """

        job_config = bigquery.QueryJobConfig()
        job_config.query_parameters = params

        query_job = self.bq_client.query(update_query, job_config=job_config)
        query_job.result()

        # Return updated config
        return self.get_config(config_id)


    def mark_configs_as_transferred(
        self, config_ids: Union[str, List[str]]
    ) -> Dict[str, Any]:
        """
        Mark configurations as transferred by setting transferred = True for transiant configs
        This is used to mark configs that are one and done and should not be considered again

        Args:
            config_ids: Either a single configuration ID or a list of configuration IDs to mark as transferred

        Returns:
            {success: True, updated_count: int} if successful
        """

        if isinstance(config_ids, str):
            config_ids = [config_ids]

        if not config_ids:
            logger.warning("No configuration IDs provided to mark as transferred")
            return {"success": True, "updated_count": 0}

        params = []
        for i, config_id in enumerate(config_ids):
            params.append(bigquery.ScalarQueryParameter(f"id_{i}", "STRING", config_id))

        id_params = [f"@id_{i}" for i in range(len(config_ids))]
        id_list = ", ".join(id_params)

        update_query = f"""
        UPDATE `{self.table_name}`
        SET 
            transferred = TRUE,
            updated_at = CURRENT_DATETIME()
        WHERE id IN ({id_list})
        """

        job_config = bigquery.QueryJobConfig()
        job_config.query_parameters = params

        query_job = self.bq_client.query(update_query, job_config=job_config)
        query_job.result()

        # Get count of updated rows
        rows = query_job.num_dml_affected_rows
        logger.info(f"Marked {rows} configurations as transferred")

        return {"success": True, "updated_count": rows}

    def delete_config(self, config_id: str) -> bool:
        """
        Delete a configuration.

        Args:
            config_id: Configuration ID

        Returns:
            True if successful, False otherwise
        """
        try:
            query = f"""
                DELETE FROM `{self.table_name}`
                WHERE id = '{config_id}'
            """

            self.bq_client.query(query).result()
            logger.info(f"Deleted config: {config_id}")
            return True

        except Exception as exc:
            logger.error(f"Error deleting config: {exc}")
            return False

    def load_configs_dataframe(
        self,
        dataframe: pd.DataFrame,
        schema: Optional[List[SchemaField]] = None,
        write_disposition: str = "WRITE_APPEND",
    ) -> Dict[str, Any]:
        """
        Load DataFrame of configurations into BigQuery table

        Args:
            dataframe: pandas DataFrame containing configurations
            schema: Optional schema for the table
            write_disposition: Write disposition for the load job

        Returns:
            Dictionary with load results
        """
        try:
            # Skip if DataFrame is empty
            if len(dataframe) == 0:
                return {"success": True, "loaded": 0, "errors": None}

            # Process each row
            configs_to_load = []
            for _, row in dataframe.iterrows():
                config_data = row.to_dict()
                prepared_config = self.data_processor.prepare_config_for_insert(config_data)
                configs_to_load.append(prepared_config)

            # Setup load job
            job_config = LoadJobConfig()
            job_config.write_disposition = write_disposition

            if schema:
                job_config.schema = schema
            elif self.schema:
                job_config.schema = self.schema

            # Convert to DataFrame
            load_df = pd.DataFrame(configs_to_load)
            load_df.to_csv("debug_configs_to_load.csv", index=False)  # Debug output

            # Load to BigQuery
            logger.info(f"Loading {len(load_df)} configurations to BigQuery")
            load_job = self.bq_client.load_table_from_dataframe(
                dataframe=load_df,
                destination=self.table_name,
                job_config=job_config,
                location=self.location,
            )

            # Wait for job to complete
            load_job.result()

            return {
                "success": True,
                "loaded": len(load_df),
                "errors": None,
                "job_id": load_job.job_id,
            }

        except Exception as exc:
            return {"success": False, "errors": str(exc), "loaded": 0}

    def deactivate_configs(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deactivate configurations matching filters

        Args:
            filters: Dictionary of field/value pairs to match

        Returns:
            Dictionary with deactivation results
        """
        # Build conditions and parameters
        conditions = []
        params = []

        for i, (field, value) in enumerate(filters.items()):
            conditions.append(f"{field} = @val_{i}")

            # Get field type from schema
            field_def = self.data_processor.schema_definition.get_field(field)
            param_type = field_def.field_type if field_def else "STRING"
            
            params.append(bigquery.ScalarQueryParameter(f"val_{i}", param_type, value))

        # Add condition to only update active configs - once deactivated, they should not be updated again
        conditions.append("active = TRUE")

        # Build and execute query
        update_query = f"""
        UPDATE `{self.table_name}`
        SET 
            active = FALSE,
            updated_at = CURRENT_DATETIME()
        WHERE {' AND '.join(conditions)}
        """

        job_config = bigquery.QueryJobConfig()
        job_config.query_parameters = params

        query_job = self.bq_client.query(update_query, job_config=job_config)
        query_job.result()

        # Get count of deactivated rowswhere num_dml_affected_rows is how bigquery returns the number of rows affected by the query
        rows = query_job.num_dml_affected_rows
        logger.info(f"Deactivated {rows} configurations")

        return {"success": True, "deactivated_count": rows}
