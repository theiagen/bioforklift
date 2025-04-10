from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
import uuid
import json
import pandas as pd
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField, LoadJobConfig
from .client import BigQueryClient
from .utils import load_schema_from_yaml, parse_field_type
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)

class BigQueryConfigOperations:
    """Operations for BigQuery tables containing configuration data"""

    def __init__(
        self,
        client: "BigQueryClient",
        table_name: str,
        config_schema_yaml: Optional[str] = None,
        config_schema: Optional[List[SchemaField]] = None,
        location: str = "us-central1",
    ):
        self.bq_client = client
        self.table_name = f"{client.project}.{client.dataset}.{table_name}"
        self.location = location

        # Load schema from yaml if provided, otherwise use schema parameter
        self.field_attributes = {}
        if config_schema_yaml:
            schema_info = load_schema_from_yaml(config_schema_yaml)
            self.schema = schema_info["schema"]
            self.field_attributes = schema_info["field_attributes"]
        else:
            self.schema = config_schema

    def _get_schema_fields(self) -> List[str]:
        """Get list of field names defined in the schema"""
        return [field.name for field in self.schema]

    def _prepare_config_for_insert(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare a configuration for insertion"""
        # Create a copy to avoid modifying the original
        config = config_data.copy()

        # Generate uuid if not provided and required by schema
        if "id" not in config:
            for field_name, attrs in self.field_attributes.items():
                if attrs.get("primary_key") and field_name not in config:
                    config[field_name] = str(uuid.uuid4())

        # Set created_at datetime if not provided
        for field_name, attrs in self.field_attributes.items():
            if field_name == "created_at" and field_name not in config:
                config[field_name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Serialize JSON fields based on schema types
        for field in self.schema:
            field_name = field.name
            # Check if this is a JSON field based on field type
            if field.field_type.upper() == "JSON" and field_name in config:
                # If the field value is a dict or list, serialize it to JSON string
                if isinstance(config[field_name], (dict, list)):
                    config[field_name] = json.dumps(config[field_name])

            # Also check if any field is defined as an object type in field_attributes
            # This is a backup approach in case the schema doesn't directly use JSON type
            elif field_name in self.field_attributes:
                attrs = self.field_attributes[field_name]
                if attrs.get("type", "").lower() == "object" and field_name in config:
                    if isinstance(config[field_name], (dict, list)):
                        config[field_name] = json.dumps(config[field_name])

        return config
    
    def get_prefix_fields(self) -> str:
        """
        Get the field name that is marked with use_as_prefix=True
        
        Returns:
            String with the name of the field to be used as prefix
        """
        return next(
            (
                field_name
                for field_name, attrs in self.field_attributes.items()
                if attrs.get("use_as_prefix")
            ),
            None,
        )
        
    def get_alerts_display_field(self) -> str:
        """
        Get the field name that is marked with display_for_alerts=True
        
        Returns:
            String with the name of the field to be used as display for alerts
        """
        return next(
            (
                field_name
                for field_name, attrs in self.field_attributes.items()
                if attrs.get("display_for_alerts")
            ),
            None,
        )
        
        
    def create_config(
        self, config_data: Union[Dict[str, Any], str, Path]
    ) -> Dict[str, Any]:
        """
        Create a new configuration

        Args:
            config_data: Either a dictionary with configuration data or a path to a JSON file

        Returns:
            Dictionary with created configuration including ID (uuid)
        """
        # Load from JSON file if a string or Path is provided
        if isinstance(config_data, (str, Path)):
            path = Path(config_data) if isinstance(config_data, str) else config_data
            try:
                with path.open("r") as config_file:
                    config_data = json.load(config_file)
            except Exception as e:
                raise ValueError(f"Error loading JSON file {path}: {str(e)}")

        if not isinstance(config_data, dict):
            raise TypeError("config_data must be a dictionary or a path to a JSON file")

        # Prepare config for insertion
        config = self._prepare_config_for_insert(config_data)

        # Insert the config
        errors = self.bq_client.insert_rows(self.table_name, [config])

        if errors:
            raise RuntimeError(f"Error inserting configuration: {errors}")

        return config

    def create_configs_from_directory(
        self, directory_path: Union[str, Path], pattern: str = "*.json"
    ) -> List[Dict[str, Any]]:
        """
        Create multiple configurations from JSON files in a directory

        Args:
            directory_path: Path to directory containing JSON configuration files
            pattern: File pattern to match (default: "*.json")

        Returns:
            List of created configurations
        """
        # Convert to Path if string is provided
        directory = (
            Path(directory_path) if isinstance(directory_path, str) else directory_path
        )

        if not directory.is_dir():
            raise ValueError(f"Directory not found: {directory}")

        # Find all matching JSON files
        json_files = list(directory.glob(pattern))
        logger.info(f"Found {len(json_files)} JSON files in {directory}")
        if not json_files:
            logger.warning("No JSON files found")
            return []

        created_configs = []
        errors = []

        # Process each file
        for json_file in json_files:
            try:
                config = self.create_config(json_file)
                created_configs.append(config)
            except Exception as e:
                errors.append({"file": str(json_file), "error": str(e)})

        if errors and not created_configs:
            raise RuntimeError(f"Failed to create any configurations: {errors}")

        # Convert to loggign if there are errors
        if errors:
            logger.error(
                f"Warning: {len(errors)} out of {len(json_files)} configurations failed to load"
            )
            for error in errors:
                logger.error(f"  - {error['file']}: {error['error']}")

        return created_configs

    def get_config(self, config_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single configuration by ID

        Args:
            config_id: ID of the configuration

        Returns:
            Configuration dictionary or None if not found
        """
        query = f"""
        SELECT *
        FROM `{self.table_name}`
        WHERE id = @id
        """

        job_config = bigquery.QueryJobConfig()
        job_config.query_parameters = [
            bigquery.ScalarQueryParameter("id", "STRING", config_id)
        ]

        logger.info(f"Getting config with ID: {config_id}")
        query_job = self.bq_client.query(query, job_config=job_config)
        results = list(query_job.result())

        if not results:
            logger.warning(f"Config with ID {config_id} not found")
            return None

        return dict(results[0])

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
        return [dict(row) for row in query_job.result()]

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
        schema_fields = self._get_schema_fields()
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

                # Get field type from schema
                field_def = next((f for f in self.schema if f.name == field), None)
                param_type = parse_field_type(field_def.field_type)

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
        Delete a configuration

        Args:
            config_id: ID of the configuration to delete

        Returns:
            True if deleted successfully
        """
        query = f"""
        DELETE FROM `{self.table_name}`
        WHERE id = @id
        """

        job_config = bigquery.QueryJobConfig()
        job_config.query_parameters = [
            bigquery.ScalarQueryParameter("id", "STRING", config_id)
        ]

        query_job = self.bq_client.query(query, job_config=job_config)
        query_job.result()

        return True

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
                prepared_config = self._prepare_config_for_insert(config_data)
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
            field_def = next((f for f in self.schema if f.name == field), None)
            param_type = (
                parse_field_type(field_def.field_type) if field_def else "STRING"
            )

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
