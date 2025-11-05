import pytest
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock, ANY, mock_open
from google.cloud import bigquery
from bioforklift.bigquery import BigQueryConfigOperations


@pytest.fixture(autouse=True)
def mock_google_auth():
    """Mock Google Cloud authentication to avoid credential errors"""
    with patch('google.auth.default') as mock_auth:
        # Return a mock credentials object and project ID
        mock_credentials = MagicMock()
        mock_auth.return_value = (mock_credentials, "test-project")
        yield mock_auth


@pytest.fixture
def test_config_schema_path():
    """Path to test config schema YAML"""
    return str(Path(__file__).parent.parent / "test_data" / "test_config_schema.yaml")


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
def config_operations(bigquery_client, test_config_schema_path):
    """Fixture to create a BigQueryConfigOperations instance for testing"""
    config_ops = BigQueryConfigOperations(
        client=bigquery_client,
        table_name="test_configs",
        config_schema_yaml=test_config_schema_path
    )
    return config_ops


@pytest.fixture
def sample_config():
    """Sample configuration for testing"""
    return {
        "name": "Test Config",
        "entity_type": "workflow",
        "active": True,
        "terra_method_config": {
            "parameters": {
                "threads": 4,
                "memory": "8GB",
            }
        }
    }


class TestBigQueryConfigOperations:
    def test_init_with_schema_yaml(self, bigquery_client, test_config_schema_path):
        """Test initialization with schema YAML"""
        config_ops = BigQueryConfigOperations(
            client=bigquery_client,
            table_name="test_configs",
            config_schema_yaml=test_config_schema_path
        )

        assert config_ops.bq_client == bigquery_client
        assert config_ops.table_name == "test-project.test-dataset.test_configs"
        assert config_ops.location == "us-central1"
        assert config_ops.data_processor is not None
        assert config_ops.schema is not None
        assert config_ops.field_attributes is not None

    def test_init_without_schema_yaml(self, bigquery_client):
        """Test initialization without schema YAML raises error"""
        with pytest.raises(ValueError, match="Either config_schema_yaml or config_schema must be provided"):
            BigQueryConfigOperations(
                client=bigquery_client,
                table_name="test_configs"
            )

    def test_get_prefix_fields(self, config_operations):
        """Test retrieving field marked for prefix use"""
        field = config_operations.data_processor.get_prefix_field()
        assert field == "name"

    def test_create_config(self, config_operations, sample_config, bigquery_client):
        """Test creating a new configuration"""
        # Mock insert_rows to return no errors
        bigquery_client.insert_rows.return_value = []

        created_config = config_operations.create_config(sample_config)

        bigquery_client.insert_rows.assert_called_once()
        table_name = bigquery_client.insert_rows.call_args[0][0]
        assert table_name == config_operations.table_name

        # Should have added system fields
        assert "id" in created_config
        assert isinstance(created_config["id"], str)
        assert created_config["name"] == sample_config["name"]
        # JSON should be serialized
        assert isinstance(created_config["terra_method_config"], str)

    def test_get_config(self, config_operations, bigquery_client):
        """Test retrieving a single configuration"""
        # Mock to_dataframe() response
        import pandas as pd
        mock_df = pd.DataFrame([{"id": "test-id", "name": "Test Config"}])

        # Set up the query job result
        mock_query_job = MagicMock()
        mock_query_job.to_dataframe.return_value = mock_df
        bigquery_client.query.return_value = mock_query_job

        config = config_operations.get_config("test-id")

        bigquery_client.query.assert_called_once()
        query_str = bigquery_client.query.call_args[0][0]
        assert "SELECT *" in query_str
        assert "WHERE id = 'test-id'" in query_str

        assert config["id"] == "test-id"
        assert config["name"] == "Test Config"

    def test_update_config(self, config_operations, bigquery_client):
        """Test updating a configuration"""
        update_data = {
            "active": False
        }

        mock_update_job = MagicMock()
        mock_update_job.result.return_value = None

        # Mock get_config to return updated config
        updated_config = {
            "id": "test-id",
            "name": "Test Config",
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
            assert "active = @active" in query_str

            assert result == updated_config
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
        assert "WHERE id = 'test-id'" in query_str

        assert result is True

    def test_get_configs_active_only(self, config_operations, bigquery_client):
        """Test retrieving active configurations"""
        # Mock query result
        class MockRow(dict):
            def __init__(self, data):
                super().__init__(data)
                for key, value in data.items():
                    setattr(self, key, value)

        mock_rows = [
            MockRow({"id": "cfg-1", "name": "Config 1", "active": True}),
            MockRow({"id": "cfg-2", "name": "Config 2", "active": True})
        ]

        mock_query_job = MagicMock()
        mock_query_job.result.return_value = mock_rows
        bigquery_client.query.return_value = mock_query_job

        configs = config_operations.get_configs(active_only=True)

        bigquery_client.query.assert_called_once()
        query_str = bigquery_client.query.call_args[0][0]
        # Check for parameterized query
        assert "WHERE active = @active" in query_str

        assert len(configs) == 2
        assert configs[0]["id"] == "cfg-1"
        assert configs[1]["id"] == "cfg-2"
