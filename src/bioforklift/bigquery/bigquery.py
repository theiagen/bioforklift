from typing import Optional, Dict, Any
from .client import BigQueryClient
from .sample_operations import BigQuerySampleOperations
from .config_operations import BigQueryConfigOperations
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class BigQuery:
    """
    Main interface for BigQuery operations.
    Provides single access point to table operations and data loading.
    """

    def __init__(
        self,
        project: str,
        dataset: str,
        credentials: Optional[Dict] = None,
        location: Optional[str] = "us-central1",
    ):
        """
        Initialize BigQuery interface

        Args:
            project: GCP project ID
            dataset: BigQuery dataset name
            credentials: Optional service account credentials dict
            location: BigQuery dataset location - default is 'us-central1'
        """
        # Initialize base client
        self.client = BigQueryClient(
            project=project, dataset=dataset, credentials=credentials, location=location
        )

    @property
    def project(self) -> str:
        """Get project ID"""
        return self.client.project

    @property
    def dataset(self) -> str:
        """Get dataset name"""
        return self.client.dataset

    @property
    def location(self) -> str:
        """Get dataset location"""
        return self.client.location

    def create_table(
        self, table_name: str, schema_yaml: str, exists_ok: bool = True
    ) -> Dict[str, Any]:
        """
        Create a new table from YAML schema definition
        """
        return self.client.create_table_from_yaml(
            table_name=table_name, schema_yaml=schema_yaml, exists_ok=exists_ok
        )

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists"""
        return self.client.table_exists(table_name)

    def get_sample_operations(
        self, table_name: str, sample_schema_yaml: str
    ) -> BigQuerySampleOperations:
        """
        Get a sample operations interface for a specific table

        Args:
            table_name: Name of the samples table
            sample_schema_yaml: Path to the samples schema YAML file

        Returns:
            BigQuerySampleOperations instance
        """
        logger.info("Creating sample operations")
        return BigQuerySampleOperations(
            client=self.client,
            table_name=table_name,
            sample_schema_yaml=sample_schema_yaml,
            location=self.location,
        )

    def get_config_operations(
        self, table_name: str, config_schema_yaml: str
    ) -> BigQueryConfigOperations:
        """
        Get a config operations interface for a specific table

        Args:
            table_name: Name of the config table
            config_schema_yaml: Path to the config schema YAML file

        Returns:
            BigQueryConfigOperations instance
        """
        return BigQueryConfigOperations(
            client=self.client,
            table_name=table_name,
            config_schema_yaml=config_schema_yaml,
            location=self.location,
        )
