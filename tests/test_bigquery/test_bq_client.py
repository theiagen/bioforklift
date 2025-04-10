import io
import json
import os
import pytest
from unittest.mock import patch, MagicMock, mock_open
from google.cloud import bigquery
from google.api_core import exceptions
from bioforklift.bigquery import BigQueryClient

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
    with patch("google.cloud.bigquery.Client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def bigquery_client(mock_bigquery_client):
    """Fixture to create a BigQueryClient instance with mocked underlying client"""
    return BigQueryClient(project="test-project", dataset="test-dataset")


@pytest.fixture
def sample_schema():
    """Sample schema for testing"""
    return [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("created_at", "DATETIME", mode="NULLABLE"),
    ]


@pytest.fixture
def sample_schema_yaml_content():
    """Sample YAML content for schema definition"""
    return """
    fields:
      - name: id
        type: STRING
        mode: REQUIRED
        description: Unique identifier
      - name: name
        type: STRING
        mode: NULLABLE
        description: User name
      - name: created_at
        type: DATETIME
        mode: NULLABLE
        description: Creation datetime
    """


class TestBigQueryClient:
    def test_init_without_credentials(self, mock_bigquery_client):
        """Test initialization without credentials"""
        client = BigQueryClient(project="test-project", dataset="test-dataset")

        assert client.project == "test-project"
        assert client.dataset == "test-dataset"
        assert client.location == "us-central1"
        assert client.client == mock_bigquery_client

    def test_init_with_credentials(self):
        """Test initialization with credentials"""
        mock_credentials = json.dumps({"type": "service_account", "project_id": "test-project"})

        with patch(
            "google.cloud.bigquery.Client.from_service_account_info"
        ) as mock_from_service_account:
            mock_client = MagicMock()
            mock_from_service_account.return_value = mock_client

            client = BigQueryClient(
                project="test-project",
                dataset="test-dataset",
                credentials=mock_credentials,
            )

            mock_from_service_account.assert_called_once_with(json.loads(mock_credentials))
            assert client.client == mock_client

    def test_getattr_passthrough(self, bigquery_client, mock_bigquery_client):
        """Test that unimplemented methods pass through to the underlying client"""
        mock_bigquery_client.some_method.return_value = "test_result"

        result = bigquery_client.some_method(arg1="test", arg2=123)

        mock_bigquery_client.some_method.assert_called_once_with(arg1="test", arg2=123)
        assert result == "test_result"

    def test_create_table_from_yaml_new_table(
        self, bigquery_client, mock_bigquery_client, sample_schema
    ):
        """Test creating a new table from YAML schema when table doesn't exist"""
        # Setup mocks
        mock_bigquery_client.get_table.side_effect = exceptions.NotFound(
            "Table not found"
        )
        mock_created_table = MagicMock()
        mock_bigquery_client.create_table.return_value = mock_created_table

        # Create a minimal field attributes structure that matches what's returned
        field_attributes = {
            "id": {"system_value": True, "primary_key": True},
            "active": {"default": True},
            "created_at": {"created_datetime": True, "system_value": True},
            "terra_method_config": {
                "properties": {
                    "deleteIntermediateOutputFiles": {
                        "description": "Whether to delete intermediate output files"
                    }
                }
            },
        }

        # Mock the load_schema_from_yaml function
        schema_info = {"schema": sample_schema, "field_attributes": field_attributes}

        # Get absolute path to the schema file
        test_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.normpath(
            os.path.join(test_dir, "../test_data/test_config_schema.yaml")
        )

        with patch(
            "bioforklift.bigquery.utils.load_schema_from_yaml", return_value=schema_info
        ):
            result = bigquery_client.create_table_from_yaml(
                table_name="test_table", schema_yaml=schema_path
            )

        # Verify calls
        expected_table_id = "test-project.test-dataset.test_table"
        mock_bigquery_client.get_table.assert_called_once_with(expected_table_id)

        # Check that create_table was called with correct arguments
        mock_bigquery_client.create_table.assert_called_once()
        table_arg = mock_bigquery_client.create_table.call_args[0][0]
        assert table_arg.table_id == "test_table"
        assert table_arg.dataset_id == "test-dataset"
        assert table_arg.project == "test-project"

        # Check result has expected structure
        assert "table" in result
        assert result["table"] == mock_created_table

        # Verify only the essential structure using more flexible assertions
        assert "field_attributes" in result

        # Check key fields exist with key properties
        assert "id" in result["field_attributes"]
        assert result["field_attributes"]["id"]["system_value"] == True
        assert result["field_attributes"]["id"]["primary_key"] == True

        assert "active" in result["field_attributes"]
        assert result["field_attributes"]["active"]["default"] == True

        assert "created_at" in result["field_attributes"]
        assert result["field_attributes"]["created_at"]["created_datetime"] == True
        assert result["field_attributes"]["created_at"]["system_value"] == True

        assert "terra_method_config" in result["field_attributes"]
        assert "properties" in result["field_attributes"]["terra_method_config"]
        assert (
            "deleteIntermediateOutputFiles"
            in result["field_attributes"]["terra_method_config"]["properties"]
        )

    def test_create_table_from_yaml_existing_table(
        self, bigquery_client, mock_bigquery_client, sample_schema
    ):
        """Test creating a table from YAML schema when table already exists"""
        # Setup mocks
        mock_existing_table = MagicMock()
        mock_bigquery_client.get_table.return_value = mock_existing_table

        # Create a minimal field attributes structure
        field_attributes = {
            "id": {"system_value": True, "primary_key": True},
            "active": {"default": True},
            "created_at": {"created_datetime": True, "system_value": True},
            "terra_method_config": {
                "properties": {
                    "deleteIntermediateOutputFiles": {
                        "description": "Whether to delete intermediate output files"
                    }
                }
            },
        }

        # Mock the load_schema_from_yaml function to return a structure that will be processed
        schema_info = {"schema": sample_schema, "field_attributes": field_attributes}

        test_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.normpath(
            os.path.join(test_dir, "../test_data/test_config_schema.yaml")
        )

        with patch(
            "bioforklift.bigquery.utils.load_schema_from_yaml", return_value=schema_info
        ):
            result = bigquery_client.create_table_from_yaml(
                table_name="test_table", schema_yaml=schema_path
            )

        # Verify get_table was called
        expected_table_id = "test-project.test-dataset.test_table"
        mock_bigquery_client.get_table.assert_called_with(expected_table_id)

        # Verify create_table was not called
        mock_bigquery_client.create_table.assert_not_called()

        # Verify the table in the result
        assert result["table"] == mock_existing_table

        # Verify only the essential structure using more flexible assertions
        assert "field_attributes" in result

        # Check key fields exist with key properties
        assert "id" in result["field_attributes"]
        assert result["field_attributes"]["id"]["system_value"] == True
        assert result["field_attributes"]["id"]["primary_key"] == True

        assert "active" in result["field_attributes"]
        assert result["field_attributes"]["active"]["default"] == True

        assert "created_at" in result["field_attributes"]
        assert result["field_attributes"]["created_at"]["created_datetime"] == True
        assert result["field_attributes"]["created_at"]["system_value"] == True

        assert "terra_method_config" in result["field_attributes"]
        assert "properties" in result["field_attributes"]["terra_method_config"]
        assert (
            "deleteIntermediateOutputFiles"
            in result["field_attributes"]["terra_method_config"]["properties"]
        )

    def test_create_table_from_yaml_existing_table_error(
        self, bigquery_client, mock_bigquery_client, sample_schema
    ):
        """Test creating a table from YAML schema when table exists but exists_ok=False"""
        # Setup mocks
        mock_existing_table = MagicMock()
        mock_bigquery_client.get_table.return_value = mock_existing_table

        # Mock the load_schema_from_yaml function
        schema_info = {
            "schema": sample_schema,
            "field_attributes": {"id": {"description": "Unique identifier"}},
        }

        test_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.normpath(
            os.path.join(test_dir, "../test_data/test_config_schema.yaml")
        )

        with patch(
            "bioforklift.bigquery.utils.load_schema_from_yaml", return_value=schema_info
        ):
            # Test with exists_ok=False
            with pytest.raises(ValueError) as excinfo:
                bigquery_client.create_table_from_yaml(
                    table_name="test_table", schema_yaml=schema_path, exists_ok=False
                )

            assert "already exists" in str(excinfo.value)

    def test_table_exists_true(self, bigquery_client, mock_bigquery_client):
        """Test table_exists when table exists"""
        mock_bigquery_client.get_table.return_value = MagicMock()

        result = bigquery_client.table_exists("test_table")

        expected_table_id = "test-project.test-dataset.test_table"
        mock_bigquery_client.get_table.assert_called_once_with(expected_table_id)
        assert result is True

    def test_table_exists_false(self, bigquery_client, mock_bigquery_client):
        """Test table_exists when table doesn't exist"""
        mock_bigquery_client.get_table.side_effect = exceptions.NotFound(
            "Table not found"
        )

        result = bigquery_client.table_exists("test_table")

        expected_table_id = "test-project.test-dataset.test_table"
        mock_bigquery_client.get_table.assert_called_once_with(expected_table_id)
        assert result is False

    def test_insert_rows_success(self, bigquery_client, mock_bigquery_client):
        """Test successful insertion of rows"""

        sample_rows = [
            {
                "id": "3f0900b6-8b0b-48ca-948e-fdaccefb5220",
                "name": "VRDL",
                "created_at": "2025-02-24T00:00:00",
            },
            {
                "id": "3f0900b6-8b0b-48ca-948e-fdaccefb5221",
                "name": "VRDL",
                "created_at": "2025-02-24T00:00:00",
            },
        ]

        # Mock get_table with proper schema fields
        mock_table = MagicMock()
        schema_fields = [
            bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("created_at", "DATETIME", mode="NULLABLE"),
        ]
        mock_table.schema = schema_fields
        mock_bigquery_client.get_table.return_value = mock_table

        # Mock load_table_from_file
        mock_job = MagicMock()
        mock_job.errors = None
        mock_job.result.return_value = None
        mock_bigquery_client.load_table_from_file.return_value = mock_job

        # Call the method
        table_id = "test-project.test-dataset.test_table"
        bigquery_client.insert_rows(table_id, sample_rows)

        # Verify get_table call
        mock_bigquery_client.get_table.assert_called_once_with(table_id)

        # Verify load_table_from_file call
        mock_bigquery_client.load_table_from_file.assert_called_once()

        # Check that the first argument is a BytesIO
        file_obj = mock_bigquery_client.load_table_from_file.call_args[0][0]
        assert isinstance(file_obj, io.BytesIO)

        # Read back the content to verify the JSON
        file_obj.seek(0)
        content = file_obj.read().decode("utf-8")
        assert "3f0900b6-8b0b-48ca-948e-fdaccefb5220" in content
        assert "3f0900b6-8b0b-48ca-948e-fdaccefb5221" in content

        # Check that the second argument is the table_id
        assert mock_bigquery_client.load_table_from_file.call_args[0][1] == table_id

        # Check job_config in kwargs
        job_config = mock_bigquery_client.load_table_from_file.call_args[1][
            "job_config"
        ]
        assert job_config.source_format == bigquery.SourceFormat.NEWLINE_DELIMITED_JSON

        # Test the schema fields individually instead of comparing the entire list
        for i, field in enumerate(job_config.schema):
            assert field.name == schema_fields[i].name
            assert field.field_type == schema_fields[i].field_type
            assert field.mode == schema_fields[i].mode

        assert job_config.write_disposition == bigquery.WriteDisposition.WRITE_APPEND

        # Verify job result was called
        mock_job.result.assert_called_once()

    def test_insert_rows_job_errors(self, bigquery_client, mock_bigquery_client):
        """Test handling of errors during row insertion"""
        # Sample data
        sample_rows = [{"id": "3f0900b6-8b0b-48ca-948e-fdaccefb5220", "name": "VRDL"}]

        # Mock get_table
        mock_table = MagicMock()
        mock_bigquery_client.get_table.return_value = mock_table

        # Mock load_table_from_file with errors
        mock_job = MagicMock()
        mock_job.errors = ["Error 1", "Error 2"]
        mock_job.result.return_value = None
        mock_bigquery_client.load_table_from_file.return_value = mock_job

        # Call the method and expect exception
        table_id = "test-project.test-dataset.test_table"
        with pytest.raises(Exception) as excinfo:
            bigquery_client.insert_rows(table_id, sample_rows)

        assert "Load job errors" in str(excinfo.value)
        assert str(mock_job.errors) in str(excinfo.value)

    def test_insert_rows_exception(self, bigquery_client, mock_bigquery_client):
        """Test handling of exceptions during row insertion"""
        # Sample data
        sample_rows = [{"id": "3f0900b6-8b0b-48ca-948e-fdaccefb5220", "name": "VRDL"}]

        # Mock get_table to raise exception
        error_message = "Connection error"
        mock_bigquery_client.get_table.side_effect = Exception(error_message)

        # Call the method and expect exception
        table_id = "test-project.test-dataset.test_table"
        with pytest.raises(Exception) as excinfo:
            bigquery_client.insert_rows(table_id, sample_rows)

        assert "Load job failed" in str(excinfo.value)
        assert error_message in str(excinfo.value)
