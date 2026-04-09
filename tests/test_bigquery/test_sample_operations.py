import pytest
import pandas as pd
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock, ANY
from google.cloud import bigquery
from bioforklift.bigquery import BigQuerySampleOperations


@pytest.fixture(autouse=True)
def mock_google_auth():
    """Mock Google Cloud authentication to avoid credential errors"""
    with patch('google.auth.default') as mock_auth:
        # Return a mock credentials object and project ID
        mock_credentials = MagicMock()
        mock_auth.return_value = (mock_credentials, "test-project")
        yield mock_auth


@pytest.fixture
def test_schema_path():
    """Path to test schema YAML"""
    return str(Path(__file__).parent.parent / "test_data" / "test_sample_schema.yaml")


@pytest.fixture
def mock_bigquery_client():
    """Fixture to create a mock BigQuery client"""
    mock_client = MagicMock()
    return mock_client


@pytest.fixture
def bigquery_client(mock_bigquery_client):
    """Fixture to create a BigQueryClient instance with mocked underlying client"""
    client = MagicMock()
    client.client = mock_bigquery_client
    client.project = "test-project"
    client.dataset = "test-dataset"
    client.query = MagicMock()
    client.load_table_from_dataframe = MagicMock()
    return client


@pytest.fixture
def sample_operations(bigquery_client, test_schema_path):
    """Fixture to create a BigQuerySampleOperations instance for testing"""
    sample_ops = BigQuerySampleOperations(
        client=bigquery_client,
        table_name="test_samples",
        sample_schema_yaml=test_schema_path
    )
    return sample_ops


@pytest.fixture
def sample_dataframe():
    """Sample DataFrame for testing"""
    return pd.DataFrame([
        {
            "sample_name": "Sample1",
            "sample_id": "SMP001",
            "config_id": "CFG001",
            "fastq_file": "gs://bucket/sample1.fastq"
        },
        {
            "sample_name": "Sample2",
            "sample_id": "SMP002",
            "config_id": "CFG001",
            "fastq_file": "gs://bucket/sample2.fastq"
        }
    ])


class TestBigQuerySampleOperations:
    def test_init_with_schema_yaml(self, bigquery_client, test_schema_path):
        """Test initialization with schema YAML"""
        sample_ops = BigQuerySampleOperations(
            client=bigquery_client,
            table_name="test_samples",
            sample_schema_yaml=test_schema_path
        )

        assert sample_ops.bq_client == bigquery_client
        assert sample_ops.table_name == "test-project.test-dataset.test_samples"
        assert sample_ops.location == "us-central1"
        assert sample_ops.data_processor is not None
        assert sample_ops.schema is not None
        assert sample_ops.field_attributes is not None

    def test_init_without_schema_yaml(self, bigquery_client):
        """Test initialization without schema YAML raises error"""
        with pytest.raises(ValueError, match="Either sample_schema_yaml or sample_schema must be provided"):
            BigQuerySampleOperations(
                client=bigquery_client,
                table_name="test_samples"
            )

    def test_get_sample_identifier_field(self, sample_operations):
        """Test retrieving sample identifier field"""
        field = sample_operations.data_processor.get_sample_identifier_field()
        assert field == "sample_id"

    def test_get_config_identifier_field(self, sample_operations):
        """Test retrieving config identifier field"""
        field = sample_operations.data_processor.get_config_identifier_field()
        assert field == "config_id"

    def test_get_sequence_file_fields(self, sample_operations):
        """Test retrieving sequence file fields"""
        fields = sample_operations.data_processor.get_sequence_file_fields()
        assert fields == ["fastq_file"]

    def test_get_existing_identifiers(self, sample_operations, bigquery_client):
        """Test retrieving existing sample identifiers"""
        # Mock query result - rows support dict-like access
        mock_row1 = MagicMock()
        mock_row1.__getitem__ = MagicMock(return_value="SMP001")
        mock_row2 = MagicMock()
        mock_row2.__getitem__ = MagicMock(return_value="SMP003")

        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [mock_row1, mock_row2]
        bigquery_client.query.return_value = mock_query_job

        identifiers = sample_operations.get_existing_identifiers()

        # Check query execution and results
        bigquery_client.query.assert_called_once()
        assert "SELECT DISTINCT sample_id" in bigquery_client.query.call_args[0][0]
        assert identifiers == ["SMP001", "SMP003"]

    def test_get_existing_identifiers_with_config_id(self, sample_operations, bigquery_client):
        """Test retrieving existing sample identifiers filtered by config_id"""
        # Mock query result - rows support dict-like access
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(return_value="SMP001")

        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [mock_row]
        bigquery_client.query.return_value = mock_query_job

        identifiers = sample_operations.get_existing_identifiers(config_id="CFG001")

        # Check query execution includes config_id filter
        bigquery_client.query.assert_called_once()
        query_str = bigquery_client.query.call_args[0][0]
        assert "SELECT DISTINCT sample_id" in query_str
        assert "config_id = 'CFG001'" in query_str
        assert identifiers == ["SMP001"]

    def test_prepare_samples_dataframe(self, sample_operations, sample_dataframe, bigquery_client):
        """Test full preparation of samples DataFrame"""
        # Mock get_existing_identifiers to return empty set
        with patch.object(
            sample_operations, 'get_existing_identifiers',
            return_value=[]
        ):
            prepared_df = sample_operations.prepare_samples_dataframe(sample_dataframe)

            # Check that system values were added
            assert "id" in prepared_df.columns
            assert "created_at" in prepared_df.columns
            assert len(prepared_df) == 2

    def test_prepare_samples_dataframe_with_config(self, sample_operations, sample_dataframe, bigquery_client):
        """Test preparation of samples DataFrame with config"""
        config = {
            "id": "CFG001",
            "entity_type": "sample",
            "method_name": "TestWorkflow"
        }

        # Mock get_existing_identifiers to return empty set
        with patch.object(
            sample_operations, 'get_existing_identifiers',
            return_value=[]
        ):
            prepared_df = sample_operations.prepare_samples_dataframe(sample_dataframe, config=config)

            # Check that system values were added
            assert "id" in prepared_df.columns
            assert "created_at" in prepared_df.columns
            # Check config field inheritance worked
            assert "workflow_name" in prepared_df.columns
            assert prepared_df.iloc[0]["workflow_name"] == "TestWorkflow"
            assert len(prepared_df) == 2

    def test_load_dataframe(self, sample_operations, sample_dataframe, bigquery_client):
        """Test loading DataFrame into BigQuery"""
        # Mock the prepare_samples_dataframe method
        with patch.object(
            sample_operations, 'prepare_samples_dataframe',
            return_value=sample_dataframe
        ):
            # Mock the load_table_from_dataframe method
            mock_load_job = MagicMock()
            mock_load_job.job_id = "test_job_id"
            mock_load_job.errors = None
            mock_load_job.result.return_value = None
            bigquery_client.load_table_from_dataframe.return_value = mock_load_job

            result = sample_operations.load_dataframe(sample_dataframe)

            # Check that load job was called correctly with positional args
            bigquery_client.load_table_from_dataframe.assert_called_once()
            call_args = bigquery_client.load_table_from_dataframe.call_args
            # Check positional args: (dataframe, table_name, ...)
            assert call_args[0][1] == sample_operations.table_name
            # Check keyword args
            assert "job_config" in call_args[1]
            assert "location" in call_args[1]

            # Check result structure
            assert result["success"] is True
            assert result["loaded"] == len(sample_dataframe)
            assert result["filtered"] == 0
            assert result["errors"] is None

    def test_bulk_update_samples(self, sample_operations, bigquery_client):
        """Test bulk updating samples"""
        updates = [
            {
                "id": "uuid1",
                "workflow_state": "Succeeded",
                "uploaded_at": datetime.now()
            },
            {
                "id": "uuid2",
                "workflow_state": "Failed"
            }
        ]

        # Mock the UPDATE query job
        mock_update_job = MagicMock()
        mock_update_job.result.return_value = None
        mock_update_job.num_dml_affected_rows = 2

        bigquery_client.query.return_value = mock_update_job

        # Test the bulk update
        result = sample_operations.bulk_update_samples(updates)

        # Check query execution - only the UPDATE query, no verification
        assert bigquery_client.query.call_count == 1
        assert "UPDATE" in bigquery_client.query.call_args_list[0][0][0]

        # Check result
        assert result["updated_count"] == 2
        assert result["updated_ids"] == ["uuid1", "uuid2"]
        assert result["failed_updates"] == []

    def test_get_samples_by_timeframe_today(self, sample_operations, bigquery_client):
        """Test retrieving samples by timeframe - today"""
        # Mock query result
        mock_result = [
            {"id": "uuid1", "sample_id": "SMP001", "created_at": datetime.now()},
            {"id": "uuid2", "sample_id": "SMP002", "created_at": datetime.now()}
        ]
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = mock_result
        bigquery_client.query.return_value = mock_query_job

        result_df = sample_operations.get_samples_by_timeframe(
            timeframe="today",
            uploaded_filter="not_uploaded"
        )

        bigquery_client.query.assert_called_once()
        query_str = bigquery_client.query.call_args[0][0]

        assert "DATE(created_at) = CURRENT_DATE()" in query_str
        assert "uploaded_at IS NULL" in query_str

        assert len(result_df) == 2
        assert "id" in result_df.columns
        assert "sample_id" in result_df.columns
        assert result_df.iloc[0]["id"] == "uuid1"
        assert result_df.iloc[1]["id"] == "uuid2"

    def test_coerce_dataframe_types(self, sample_operations):
        """Test coercing DataFrame types to match schema"""
        df = pd.DataFrame([
            {
                "sample_id": "SMP001",
                "created_at": "2024-01-01",
                "config_id": "CFG001"
            }
        ])

        coerced_df = sample_operations.coerce_dataframe_types(df)

        # Verify delegation to processor
        assert coerced_df is not None
        assert "sample_id" in coerced_df.columns
