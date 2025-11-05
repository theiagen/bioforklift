import io
import json
from typing import Optional, Dict, Any, List
from google.cloud import bigquery
from bioforklift.data_processing.utils import load_schema_from_yaml
from google.api_core import exceptions
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class BigQueryClient:
    """Base client for BigQuery operations"""

    def __init__(
        self,
        project: str,
        dataset: str,
        credentials: Optional[str] = None,
        location: str = "us-central1",
    ):
        self.project = project
        self.dataset = dataset
        self.location = location

        # Initialize the actual client with location
        if credentials:
            credentials_json = json.loads(credentials)
            self.client = bigquery.Client.from_service_account_info(
                credentials_json, location=location
            )
        else:
            self.client = bigquery.Client(location=location)

    def __getattr__(self, name):
        """Pass through any unimplemented methods to the underlying client"""
        return getattr(self.client, name)

    def create_table_from_yaml(
        self, table_name: str, schema_yaml: str, exists_ok: bool = True
    ) -> Dict[str, Any]:
        """
        Create a BigQuery table using schema defined in YAML.

        Args:
            table_name: Name of the table to create
            schema_yaml: Path to YAML file containing schema definition
            exists_ok: If True, don't error if table exists

        Returns:
            Dict containing table and field attributes
        """

        # Load schema and attributes from YAML
        schema_info = load_schema_from_yaml(schema_yaml)
        schema = schema_info["schema"]

        # Create table reference with location
        table_id = f"{self.project}.{self.dataset}.{table_name}"
        table = bigquery.Table(table_id, schema=schema)
        logger.info(f"BigQuery table reference created: {table_id}")

        try:
            # Check if table exists
            existing_table = self.client.get_table(table_id)

            if not exists_ok:
                logger.error(f"Table {table_id} already exists")
                raise ValueError(f"Table {table_id} already exists")

            logger.info(f"Table {table_id} already exists")
            return {
                "table": existing_table,
                "field_attributes": schema_info["field_attributes"],
            }

        except exceptions.NotFound:
            # Table doesn't exist, create it with location from client
            logger.info(f"Creating new table: {table_id} in location: {self.location}")
            created_table = self.client.create_table(table)
            return {
                "table": created_table,
                "field_attributes": schema_info["field_attributes"],
            }

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists"""

        table_id = f"{self.project}.{self.dataset}.{table_name}"
        try:
            self.client.get_table(table_id)
            return True
        except exceptions.NotFound:
            return False

    def insert_rows(self, table: str, rows: list) -> None:
        """Insert rows into a table using load job for immediate availability"""
        logger.info(f"Inserting {len(rows)} rows into {table}")

        try:
            # Get table reference instance from google.cloud.bigquery
            table_obj = self.client.get_table(table)

            logger.info("Configuring row insert job config")
            # Configure load job with location
            job_config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                schema=table_obj.schema,
                # Set write disposition to append by default
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            )

            # Convert rows to newline-delimited JSON
            json_rows = [json.dumps(row) for row in rows]
            data = "\n".join(json_rows).encode("utf-8")

            # Create and run load job
            # Location is inherited from self.client which was initialized with location
            logger.info(f"Running row insert job with location: {self.location}")
            load_job = self.client.load_table_from_file(
                io.BytesIO(data), table, job_config=job_config
            )

            load_job.result()

            if load_job.errors:
                logger.error(f"Error in loading job: {load_job.errors}")
                raise Exception(f"Load job errors: {load_job.errors}")

        except Exception as exc:
            raise Exception(f"Load job failed: {str(exc)}")
