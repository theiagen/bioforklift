import os
import logging
from typing import Union
from .bigquery_service import BigQueryService
from .mock_data_service import MockDataService

logger = logging.getLogger(__name__)


class DataServiceFactory:
    """Factory to create appropriate data service based on configuration"""
    
    @staticmethod
    def create_data_service() -> Union[BigQueryService, MockDataService]:
        """
        Create data service based on environment configuration.
        Returns MockDataService if MOCK_DATA=true or if BigQuery config is missing.
        """
        
        # Check if mock data is explicitly requested
        use_mock = os.getenv("MOCK_DATA", "false").lower() == "true"
        
        if use_mock:
            logger.info("Using mock data service (MOCK_DATA=true)")
            return MockDataService()
        
        # Check if BigQuery configuration is available
        project_id = os.getenv("BIGQUERY_PROJECT_ID")
        dataset_id = os.getenv("BIGQUERY_DATASET_ID")
        
        if not project_id or not dataset_id:
            logger.warning(
                "BigQuery configuration missing (BIGQUERY_PROJECT_ID or BIGQUERY_DATASET_ID). "
                "Falling back to mock data service."
            )
            return MockDataService()
        
        try:
            # Try to create BigQuery service
            logger.info(f"Using BigQuery data service for project: {project_id}, dataset: {dataset_id}")
            return BigQueryService(project_id, dataset_id)
            
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery service: {e}")
            logger.warning("Falling back to mock data service")
            return MockDataService()


# Protocol/Interface to ensure both services have the same methods
class DataServiceProtocol:
    """Protocol defining the interface both services must implement"""
    
    def get_daily_runs_summary(self, days_back: int = 30):
        raise NotImplementedError
    
    def get_workflow_states_distribution(self, days_back: int = 7):
        raise NotImplementedError
    
    def get_configuration_metrics(self, days_back: int = 30):
        raise NotImplementedError
    
    def get_recent_failures(self, limit: int = 50):
        raise NotImplementedError
    
    def get_processing_time_trends(self, days_back: int = 30):
        raise NotImplementedError
    
    def get_active_configurations(self):
        raise NotImplementedError
    
    def get_system_health_metrics(self):
        raise NotImplementedError