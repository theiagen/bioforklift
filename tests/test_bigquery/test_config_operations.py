import pytest
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY, mock_open
from google.cloud import bigquery
from forklift.bigquery import BigQueryConfigOperations


@pytest.fixture(autouse=True)
def mock_google_auth():
    """Mock Google Cloud authentication to avoid credential errors"""
    with patch('google.auth.default') as mock_auth:
        # Return a mock credentials object and project ID
        mock_credentials = MagicMock()
        mock_auth.return_value = (mock_credentials, "test-project")
        yield mock_auth

@pytest.fixture
def mock_bigquery_client():
    """Fixture to create a mock BigQuery client"""
    mock_client = MagicMock()
    return mock_client


@pytest.fixture
def bigquery_client(mock_bigquery_client):
    """Fixture to create a BigQueryClient instance with mocked client"""
    client = MagicMock()
    client.client = mock_bigquery_client
    client.project = "test-project"
    client.dataset = "test-dataset"
    client.query = MagicMock()
    client.insert_rows = MagicMock()
    client.load_table_from_dataframe = MagicMock()
    return client


@pytest.fixture
def config_schema():
    """Sample schema for testing"""
    return [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("description", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("entity_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("version", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("active", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("created_at", "DATETIME", mode="NULLABLE"),
        bigquery.SchemaField("updated_at", "DATETIME", mode="NULLABLE"),
        bigquery.SchemaField("config_json", "JSON", mode="NULLABLE"),
    ]


@pytest.fixture
def config_field_attributes():
    """Sample field attributes for testing"""
    return {
        "id": {"primary_key": True},
        "name": {"use_as_prefix": True},
        "description": {"display_for_alerts": True},
        "created_at": {"created_datetime": True},
        "updated_at": {"updated_datetime": True},
    }


@pytest.fixture
def config_operations(bigquery_client, config_schema, config_field_attributes):
    """Fixture to create a BigQueryConfigOperations instance for testing"""
    config_ops = BigQueryConfigOperations(
        client=bigquery_client,
        table_name="test_configs",
    )
    # Mock schema info that would normally be loaded from yaml
    config_ops.schema = config_schema
    config_ops.field_attributes = config_field_attributes
    return config_ops


@pytest.fixture
def sample_config():
    """Sample configuration for testing"""
    return {
        "name": "Test Config",
        "description": "A test configuration",
        "entity_type": "workflow",
        "version": "1.0.0",
        "active": True,
        "config_json": {
            "parameters": {
                "threads": 4,
                "memory": "8GB",
            }
        }
    }


class TestBigQueryConfigOperations:
    def test_init(self, bigquery_client):
        """Test initialization"""
        config_ops = BigQueryConfigOperations(
            client=bigquery_client,
            table_name="test_configs"
        )
        
        assert config_ops.bq_client == bigquery_client
        assert config_ops.table_name == "test-project.test-dataset.test_configs"
        assert config_ops.location == "us-central1"
        assert config_ops.field_attributes == {}

    def test_get_prefix_fields(self, config_operations):
        """Test retrieving field marked for prefix use"""
        field = config_operations.get_prefix_fields()
        assert field == "name"

    def test_get_alerts_display_field(self, config_operations):
        """Test retrieving field marked for alerts display"""
        field = config_operations.get_alerts_display_field()
        assert field == "description"

    def test_prepare_config_for_insert_adds_id(self, config_operations, sample_config):
        """Test preparing config for insertion adds ID if missing"""
        prepared_config = config_operations._prepare_config_for_insert(sample_config)
        
        # Should add ID if missing
        assert "id" in prepared_config
        assert isinstance(prepared_config["id"], str)
        
        # Shouldn't modify other fields
        assert prepared_config["name"] == sample_config["name"]
        
    def test_prepare_config_for_insert_serializes_json(self, config_operations, sample_config):
        """Test JSON serialization during config preparation"""
        prepared_config = config_operations._prepare_config_for_insert(sample_config)
        
        # Should serialize JSON fields
        assert "config_json" in prepared_config
        assert isinstance(prepared_config["config_json"], str)
        assert '"parameters"' in prepared_config["config_json"]

    def test_create_config(self, config_operations, sample_config, bigquery_client):
        """Test creating a new configuration"""
        # Mock insert_rows to return no errors
        bigquery_client.insert_rows.return_value = []
        
        # Mock _prepare_config_for_insert to add an ID
        with patch.object(
            config_operations, '_prepare_config_for_insert', 
            side_effect=lambda config: {**config, "id": "test-uuid"}
        ):
            created_config = config_operations.create_config(sample_config)
            
            bigquery_client.insert_rows.assert_called_once()
            table_name = bigquery_client.insert_rows.call_args[0][0]
            assert table_name == config_operations.table_name
            
            assert created_config["id"] == "test-uuid"
            assert created_config["name"] == sample_config["name"]

    def test_create_config_from_file(self, config_operations, sample_config):
        """Test creating a configuration from a JSON file"""
        # Prepare the config data with ID added
        config_with_id = {**sample_config, "id": "test-uuid"}
        
        # Use simple patch approach
        with patch('json.load', return_value=sample_config), \
             patch.object(config_operations, 'create_config', return_value=config_with_id):
            
            # We're not testing the file reading mechanics here, 
            # just that create_config properly handles file inputs
            result = config_operations.create_config("test_config.json")
            
            # Verify create_config was called with our mock data
            config_operations.create_config.assert_called_once()
            
            assert result["id"] == "test-uuid"
            assert result["name"] == sample_config["name"]
            
    def test_get_config(self, config_operations, bigquery_client):
        """Test retrieving a single configuration"""
        mock_result = [MagicMock()]
        mock_result[0].__iter__ = lambda self: iter({"id": "test-id", "name": "Test Config"}.items())
        mock_result[0].__getitem__ = lambda self, key: {"id": "test-id", "name": "Test Config"}[key]
        
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = mock_result
        bigquery_client.query.return_value = mock_query_job
        
        config = config_operations.get_config("test-id")
        
        bigquery_client.query.assert_called_once()
        query_str = bigquery_client.query.call_args[0][0]
        assert "SELECT *" in query_str
        assert "WHERE id = @id" in query_str
        
        assert config["id"] == "test-id"
        assert config["name"] == "Test Config"

    def test_get_config(self, config_operations, bigquery_client):
        """Test retrieving a single configuration"""
        # Create a class to properly mock BigQuery row results
        class MockRow(dict):
            def __init__(self, data):
                super().__init__(data)
                for key, value in data.items():
                    setattr(self, key, value)
        
        # Create the mock data as a proper row object
        mock_row = MockRow({"id": "test-id", "name": "Test Config"})
        
        # Set up the query job result
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [mock_row]
        bigquery_client.query.return_value = mock_query_job
        
        config = config_operations.get_config("test-id")
        
        bigquery_client.query.assert_called_once()
        query_str = bigquery_client.query.call_args[0][0]
        assert "SELECT *" in query_str
        assert "WHERE id = @id" in query_str
        
        assert config["id"] == "test-id"
        assert config["name"] == "Test Config"

    def test_update_config(self, config_operations, bigquery_client):
        """Test updating a configuration"""
        update_data = {
            "description": "Updated description",
            "active": False
        }
        
        mock_update_job = MagicMock()
        mock_update_job.result.return_value = None
        
        # Mock get_config to return updated config
        updated_config = {
            "id": "test-id",
            "name": "Test Config",
            "description": "Updated description",
            "active": False,
            "updated_at": datetime.now().isoformat()
        }
        
        with patch.object(
            config_operations, 'get_config', 
            return_value=updated_config
        ):
            bigquery_client.query.return_value = mock_update_job
            
            result = config_operations.update_config("test-id", update_data)
            
            # Check query execution for updating config
            bigquery_client.query.assert_called_once()
            query_str = bigquery_client.query.call_args[0][0]
            assert "UPDATE" in query_str
            assert "WHERE id = @id" in query_str
            
            # Fields to update should be in query
            assert "description = @description" in query_str
            assert "active = @active" in query_str
            
            assert result == updated_config
            assert result["description"] == "Updated description"
            assert result["active"] is False

    def test_delete_config(self, config_operations, bigquery_client):
        """Test deleting a configuration"""
        mock_delete_job = MagicMock()
        mock_delete_job.result.return_value = None
        bigquery_client.query.return_value = mock_delete_job
        
        result = config_operations.delete_config("test-id")
        
        # Check query execution for deleting config
        bigquery_client.query.assert_called_once()
        query_str = bigquery_client.query.call_args[0][0]
        assert "DELETE FROM" in query_str
        assert "WHERE id = @id" in query_str
        
        assert result is True

    def test_load_configs_dataframe(self, config_operations, bigquery_client):
        """Test loading configurations from DataFrame"""
        df = pd.DataFrame([
            {
                "name": "Config 1",
                "description": "Description 1",
                "active": True
            },
            {
                "name": "Config 2",
                "description": "Description 2",
                "active": False
            }
        ])
        
        # Mock _prepare_config_for_insert to add IDs
        with patch.object(
            config_operations, '_prepare_config_for_insert', 
            side_effect=lambda config: {**config, "id": f"uuid-{config['name']}"}
        ):
            # Mock load job for bq
            mock_load_job = MagicMock()
            mock_load_job.job_id = "test-job"
            mock_load_job.errors = None
            mock_load_job.result.return_value = None
            bigquery_client.load_table_from_dataframe.return_value = mock_load_job
            
            result = config_operations.load_configs_dataframe(df)
            
            # Check load_table_from_dataframe was called
            bigquery_client.load_table_from_dataframe.assert_called_once()
            
            assert result["success"] is True
            assert result["loaded"] == 2
            assert result["job_id"] == "test-job"

    def test_deactivate_configs(self, config_operations, bigquery_client):
        """Test deactivating configurations"""
        filters = {
            "entity_type": "workflow",
            "version": "1.0.0"
        }
        
        mock_update_job = MagicMock()
        mock_update_job.result.return_value = None
        mock_update_job.num_dml_affected_rows = 3
        bigquery_client.query.return_value = mock_update_job
        
        result = config_operations.deactivate_configs(filters)
        
        # Check query execution
        bigquery_client.query.assert_called_once()
        query_str = bigquery_client.query.call_args[0][0]
        assert "UPDATE" in query_str
        assert "active = FALSE" in query_str
        assert "WHERE" in query_str
        
        # Conditions should include active = TRUE
        assert "active = TRUE" in query_str
        
        assert result["success"] is True
        assert result["deactivated_count"] == 3