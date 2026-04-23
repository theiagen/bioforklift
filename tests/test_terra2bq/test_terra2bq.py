import pytest
import pandas as pd
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY
from datetime import datetime
from bioforklift.terra2bq import Terra2BQ
from bioforklift.terra2bq.models import (
    ConfigProcessingResult,
    WorkflowResult,
    MetadataSyncResult,
    DataResult,
    UploadResult,
    DownloadResult,
    SubmissionResult,
    ProcessAllConfigsResult,
    OperationStatus
)

# This is really just testing happy paths so can be a bit simpler
# We'll use a lot of MagicMock objects to simulate the behavior of the real classes
# But will also test some error cases in another test file

@pytest.fixture(autouse=True)
def mock_google_auth():
    """Mock Google Cloud authentication to avoid credential errors"""
    with patch('google.auth.default') as mock_auth:
        # Return a mock credentials object and project ID
        mock_credentials = MagicMock()
        mock_auth.return_value = (mock_credentials, "test-project")
        yield mock_auth

@pytest.fixture
def mock_bigquery():
    """Create a mock BigQuery object with necessary methods"""
    mock = MagicMock()
    mock.get_sample_operations.return_value = MagicMock()
    mock.get_config_operations.return_value = MagicMock()
    return mock

@pytest.fixture
def mock_terra():
    """Create a mock Terra object with necessary methods"""
    mock = MagicMock()
    mock.entities = MagicMock()
    mock.submissions = MagicMock()
    return mock

@pytest.fixture
def sample_schema_path(tmp_path):
    """Create a temporary sample schema YAML file"""
    schema_file = tmp_path / "sample_schema.yaml"
    schema_file.write_text("""fields:
  sample_id:
    type: string
    sample_identifier: true
  config_id:
    type: string
    config_identifier: true
  entity_name:
    type: string
  sync_field_example:
    type: string
    sync_field: true
""")
    return str(schema_file)

@pytest.fixture
def config_schema_path(tmp_path):
    """Create a temporary config schema YAML file"""
    schema_file = tmp_path / "config_schema.yaml"
    schema_file.write_text("fields:\n  id:\n    type: string\n    configuration_identifier: true\n")
    return str(schema_file)

@pytest.fixture
def t2bq(sample_schema_path, config_schema_path):
    """Create a basic Terra2BQ instance with mocked dependencies"""
    with patch("bioforklift.data_processing.utils.load_schema_from_yaml") as mock_load:
        # Mock the schema loading to return minimal schemas
        mock_load.return_value = {
            "schema": [],
            "field_attributes": {}
        }

        instance = Terra2BQ(
            bigquery_project="test-project",
            bigquery_dataset="test-dataset",
            samples_schema_yaml=sample_schema_path,
            configs_schema_yaml=config_schema_path
        )

        instance.samples_ops = MagicMock()
        instance.config_ops = MagicMock()
        instance.terra = MagicMock()

        return instance

@pytest.fixture
def sample_config():
    """Return a sample configuration dictionary"""
    return {
        "id": "test-config-id",
        "entity_type": "test_entity",
        "terra_source_workspace": "source-workspace",
        "terra_source_project": "source-project",
        "terra_destination_workspace": "dest-workspace",
        "terra_destination_project": "dest-project",
        "terra_method_config": json.dumps({
            "methodConfigurationNamespace": "namespace",
            "methodConfigurationName": "method-name",
            "entityType": "sample_set",
            "expression": "this.sample_id",
            "useCallCache": True,
            "deleteIntermediateOutputFiles": True,
            "useReferenceDisks": True,
            "memoryRetryMultiplier": 1.0,
            "workflowFailureMode": "NoNewCalls"
        })
    }

# 3 fake samples so remember to check for 3 in assertions
@pytest.fixture
def sample_df():
    """Return a sample DataFrame with test data including sequence file columns"""
    return pd.DataFrame({
        "id": ["sample1", "sample2", "sample3"],
        "entity_name": ["entity1", "entity2", "entity3"],
        "config_id": ["test-config-id", "test-config-id", "test-config-id"],
        "read1": [
            "gs://source-bucket/path/to/file1.fastq.gz",
            "gs://source-bucket/path/to/file2.fastq.gz",
            "gs://source-bucket/path/to/file3.fastq.gz"
        ],
        "read2": [
            "gs://source-bucket/path/to/file1_r2.fastq.gz",
            "gs://source-bucket/path/to/file2_r2.fastq.gz",
            "gs://source-bucket/path/to/file3_r2.fastq.gz"
        ]
    })

# Test initialization
def test_init_with_required_params(sample_schema_path, config_schema_path):
    """Test initialization with only required parameters"""
    with patch("bioforklift.data_processing.utils.load_schema_from_yaml") as mock_load:
        mock_load.return_value = {"schema": [], "field_attributes": {}}

        t2bq = Terra2BQ(
            bigquery_project="test-project",
            bigquery_dataset="test-dataset",
            samples_schema_yaml=sample_schema_path,
            configs_schema_yaml=config_schema_path
        )

        assert t2bq.bigquery is not None
        assert t2bq.lookup_timeframe == "today"
        assert t2bq.samples_table == "samples"
        assert t2bq.configs_table == "configs"
        assert t2bq.project_timezone == "UTC"

def test_init_with_custom_params(sample_schema_path, config_schema_path):
    """Test initialization with custom parameters"""
    with patch("bioforklift.data_processing.utils.load_schema_from_yaml") as mock_load:
        mock_load.return_value = {"schema": [], "field_attributes": {}}

        t2bq = Terra2BQ(
            bigquery_project="test-project",
            bigquery_dataset="test-dataset",
            lookup_timeframe="custom",
            lookup_days_back=7,
            samples_table="custom_samples",
            configs_table="custom_configs",
            source_workspace="test-workspace",
            source_project="test-project",
            source_datatable="test_entity",
            project_timezone="America/New_York",
            samples_schema_yaml=sample_schema_path,
            configs_schema_yaml=config_schema_path
        )

        assert t2bq.lookup_timeframe == "custom"
        assert t2bq.lookup_days_back == 7
        assert t2bq.samples_table == "custom_samples"
        assert t2bq.configs_table == "custom_configs"
        assert t2bq.source_workspace == "test-workspace"
        assert t2bq.source_project == "test-project"
        assert t2bq.source_datatable == "test_entity"
        assert t2bq.project_timezone == "America/New_York"

def test_init_with_custom_timeframe_validation(sample_schema_path, config_schema_path):
    """Test that custom timeframe requires days_back or hours_back"""
    with patch("bioforklift.data_processing.utils.load_schema_from_yaml") as mock_load:
        mock_load.return_value = {"schema": [], "field_attributes": {}}

        with pytest.raises(ValueError, match="Custom lookup timeframe requires lookup_days_back or lookup_hours_back"):
            Terra2BQ(
                bigquery_project="test-project",
                bigquery_dataset="test-dataset",
                samples_schema_yaml=sample_schema_path,
                configs_schema_yaml=config_schema_path,
            lookup_timeframe="custom"
        )

@patch("bioforklift.bigquery.BigQuery")
def test_initialize_operations(mock_bigquery_class, tmp_path):
    """Test initializing operations objects"""
    # Create temporary schema files with proper structure
    samples_schema = tmp_path / "samples_schema.yaml"
    configs_schema = tmp_path / "configs_schema.yaml"
    
    samples_schema.write_text("""fields:
  id:
    type: string
    required: true
  entity_name:
    type: string
    required: true
""")

    configs_schema.write_text("""fields:
  id:
    type: string
    required: true
  prefix_field:
    type: string
""")
            
    # Configure the mock BigQuery class before creating Terra2BQ
    mock_bigquery_instance = mock_bigquery_class.return_value
    mock_bigquery_instance.get_sample_operations.return_value = MagicMock()
    mock_bigquery_instance.get_config_operations.return_value = MagicMock()
    
    # Create instance with schema files
    # NOTE: Disable automatic initialization to avoid errors
    with patch("bioforklift.terra2bq.Terra2BQ.initialize_operations"):
        t2bq = Terra2BQ(
            bigquery_project="test-project",
            bigquery_dataset="test-dataset",
            samples_schema_yaml=samples_schema,
            configs_schema_yaml=configs_schema
        )
    
    # Set up manual mocks
    t2bq.bigquery = mock_bigquery_instance
    
    # Now call initialize_operations
    t2bq.initialize_operations()
    
    # Assert operations initialized
    assert t2bq.samples_ops is not None
    assert t2bq.config_ops is not None
    
    # Assert correct methods called
    mock_bigquery_instance.get_sample_operations.assert_called_once_with(
        table_name="samples",
        sample_schema_yaml=samples_schema
    )
    mock_bigquery_instance.get_config_operations.assert_called_once_with(
        table_name="configs",
        config_schema_yaml=configs_schema
    )

@patch("bioforklift.terra2bq.terra2bq.Terra")
def test_setup_terra_client(mock_terra_class, sample_config, t2bq):
    """Test setting up Terra client"""
    t2bq.setup_terra_client(sample_config)
    
    # Assert Terra client initialized with correct parameters
    mock_terra_class.assert_called_once_with(
        source_workspace=sample_config["terra_source_workspace"],
        source_project=sample_config["terra_source_project"],
        destination_workspace=sample_config["terra_destination_workspace"],
        destination_project=sample_config["terra_destination_project"],
        credentials=None
    )

@patch("bioforklift.terra2bq.terra2bq.Terra")
def test_setup_terra_client_with_instance_values(mock_terra_class, sample_config, sample_schema_path, config_schema_path):
    """Test that instance values take precedence over config values"""
    with patch("bioforklift.data_processing.utils.load_schema_from_yaml") as mock_load:
        mock_load.return_value = {"schema": [], "field_attributes": {}}

        t2bq = Terra2BQ(
            bigquery_project="test-project",
            bigquery_dataset="test-dataset",
            samples_schema_yaml=sample_schema_path,
            configs_schema_yaml=config_schema_path,
            source_workspace="instance-workspace",
            source_project="instance-project",
            destination_workspace="instance-dest-workspace",
            destination_project="instance-dest-project"
        )

    t2bq.setup_terra_client(sample_config)

    # Assert Terra client initialized with instance parameters
    mock_terra_class.assert_called_once_with(
        source_workspace="instance-workspace",
        source_project="instance-project",
        destination_workspace="instance-dest-workspace",
        destination_project="instance-dest-project",
        credentials=None
    )

def test_setup_terra_client_missing_source(sample_schema_path, config_schema_path):
    """Test error when source workspace/project not provided"""
    with patch("bioforklift.data_processing.utils.load_schema_from_yaml") as mock_load:
        mock_load.return_value = {"schema": [], "field_attributes": {}}

        t2bq = Terra2BQ(
            bigquery_project="test-project",
            bigquery_dataset="test-dataset",
            samples_schema_yaml=sample_schema_path,
            configs_schema_yaml=config_schema_path
        )

    # Config missing source workspace
    config = {"id": "test-config"}

    with pytest.raises(ValueError, match="No source workspace provided"):
        t2bq.setup_terra_client(config)

    # Config with workspace but missing project
    config = {"id": "test-config", "terra_source_workspace": "workspace"}

    with pytest.raises(ValueError, match="No source project provided"):
        t2bq.setup_terra_client(config)

# Test get_active_configs
def test_get_active_configs(t2bq):
    """Test getting active configurations"""
    t2bq.config_ops.get_configs.return_value = [{"id": "config1"}, {"id": "config2"}]
    
    configs = t2bq.get_active_configs()
    
    assert configs == [{"id": "config1"}, {"id": "config2"}]
    t2bq.config_ops.get_configs.assert_called_once_with(active_only=True, entity_type=None,  skip_transferred=False)

def test_get_active_configs_with_entity_type(t2bq):
    """Test getting active configurations filtered by entity type"""
    t2bq.config_ops.get_configs.return_value = [{"id": "config1"}]
    
    configs = t2bq.get_active_configs(entity_type="test_entity")
    
    assert configs == [{"id": "config1"}]
    t2bq.config_ops.get_configs.assert_called_once_with(active_only=True, entity_type="test_entity",  skip_transferred=False)

# Test download_from_terra_to_bigquery
def test_download_from_terra_to_bigquery_success(t2bq, sample_config):
    """Test successful download and load to BigQuery"""
    t2bq.terra.entities.download_table.return_value = pd.DataFrame({"col1": [1, 2, 3]})
    t2bq.samples_ops.load_dataframe.return_value = {
        "success": True,
        "loaded": 3,
        "filtered": 0
    }
    
    result = t2bq.download_from_terra_to_bigquery(sample_config)
    
    assert isinstance(result, DownloadResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.config_id == sample_config["id"]

def test_upload_to_terra_success(t2bq, sample_config, sample_df):
    """Test successful upload to Terra"""
    # Reset mocks to ensure clean state
    t2bq.terra = MagicMock()
    
    # Mock the upload behavior
    t2bq.terra.entities.upload_entities.return_value = pd.DataFrame({"entity_name": ["entity1", "entity2", "entity3"]})
    t2bq.samples_ops.bulk_update_samples.return_value = {
        "updated_count": 3,
        "failed_updates": []
    }
    t2bq.samples_ops.get_sample_identifier_field.return_value = "entity_name"
    t2bq.config_ops.get_prefix_fields.return_value = "prefix_field"
    
    # Make a sample DataFrame to upload
    upload_df = pd.DataFrame({"entity_name": ["entity1", "entity2", "entity3"], "attr1": [1, 2, 3]})

    result = t2bq.upload_to_terra(sample_config, sample_df, upload_df)
    
    # Check result
    assert isinstance(result, UploadResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.config_id == sample_config["id"]
    assert result.set_name is not None  # Just check it exists
    assert result.uploaded_count == 3
    
    # Check that the methods were called
    t2bq.terra.entities.upload_entities.assert_called_once()
    assert t2bq.terra.entities.create_entity_set.call_count == 1
    assert t2bq.samples_ops.bulk_update_samples.call_count == 1
    
    # Verify set_name is included in the create_entity_set call
    set_name = result.set_name
    # Use kwargs to access keyword arguments
    create_kwargs = t2bq.terra.entities.create_entity_set.call_args.kwargs
    assert "set_name" in create_kwargs
    assert create_kwargs["set_name"] == set_name
    
@patch("bioforklift.file_transfers.gcs_transfer.GCSTransferClient")
def test_download_with_file_transfer(mock_gcs_transfer_client, t2bq, sample_config, sample_df):
    """Test download_from_terra_to_bigquery with file transfer"""
    # Mock terra.entities.download_table to return our sample dataframe
    t2bq.terra.entities.download_table.return_value = sample_df
    
    # Mock the transfer_sequence_files method
    t2bq.transfer_sequence_files = MagicMock(return_value=sample_df)
    
    # Mock samples_ops.load_dataframe to return success
    t2bq.samples_ops.load_dataframe.return_value = {
        "success": True,
        "loaded": 3,
        "filtered": 0
    }
    
    # Call the method with a destination bucket
    result = t2bq.download_from_terra_to_bigquery(
        config=sample_config,
        destination_bucket="gs://dest-bucket/path",
        preserve_path_structure=True
    )
    
    # Assertions for the result
    assert isinstance(result, DownloadResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.config_id == sample_config["id"]
    assert result.loaded_count == 3
    assert result.filtered_count == 0
    
    # Verify transfer_sequence_files was called with the right parameters
    t2bq.transfer_sequence_files.assert_called_once_with(
        dataframe=sample_df,
        destination_bucket="gs://dest-bucket/path",
        preserve_path_structure=True
    )
    
def test_get_samples_for_submission_with_set_name(t2bq, sample_config):
    """Test getting samples for submission filtering by set name"""
    # Mock the get_samples_by_timeframe to return test data
    t2bq.samples_ops.get_samples_by_timeframe.return_value = pd.DataFrame({
        "id": ["sample1", "sample2"],
        "entity_name": ["entity1", "entity2"]
    })
    
    # Call the method with a set name
    result = t2bq.get_samples_for_submission(sample_config, set_name="test_set")
    
    # Check result - expect non-empty result based on our mock
    assert not result.empty
    assert len(result) == 2
    
    # Check that correct filters were applied
    t2bq.samples_ops.get_samples_by_timeframe.assert_called_once_with(
        timeframe=t2bq.lookup_timeframe,
        days_back=t2bq.lookup_days_back,
        hours_back=t2bq.lookup_hours_back,
        uploaded_filter="uploaded",
        submitted_filter="not_submitted",
        config_id=sample_config["id"],
        set_name="test_set"
    )

def test_submit_workflow_success(t2bq, sample_config, sample_df):
    """Test successful workflow submission"""
    
    t2bq.terra.submissions.submit_workflow.return_value = {"submissionId": "test-submission-id"}
    t2bq.samples_ops.bulk_update_samples.return_value = {
        "updated_count": 3,
        "failed_updates": []
    }
    t2bq.config_ops.get_prefix_fields.return_value = "prefix_field"
    
    with patch("bioforklift.terra2bq.terra2bq.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime.strftime.return_value = "2023-01-01 12:00:00"
        
        result = t2bq.submit_workflow(sample_config, "test_set", sample_df)
    
    # Check result for success
    assert isinstance(result, SubmissionResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.config_id == sample_config["id"]
    assert result.submission_id == "test-submission-id"
    assert result.workflow_count == 3
    
    # Check that sample updates were attempted
    t2bq.samples_ops.bulk_update_samples.assert_called_once()
    
# # Test process_upload_and_submit
def test_process_upload_and_submit_success(t2bq, sample_config):
    """Test successful upload and submission process"""
    # Mock samples data
    sample_df = pd.DataFrame({
        "id": ["sample1", "sample2", "sample3"],
        "entity_name": ["entity1", "entity2", "entity3"],
        "config_id": ["test-config-id", "test-config-id", "test-config-id"]
    })
    
    # Set up mocks for the entire flow
    t2bq.samples_ops.get_samples_by_timeframe.side_effect = [
        sample_df,  # First call - get samples to upload
        sample_df   # Second call - get samples for submission
    ]
    
    # Mock drop_system_columns method on sample_processor
    t2bq.sample_processor.drop_system_columns = MagicMock(return_value=pd.DataFrame({
        "entity_name": ["entity1", "entity2", "entity3"],
        "attr1": [1, 2, 3]
    }))

    # Mock upload_to_terra
    t2bq.upload_to_terra = MagicMock(return_value=UploadResult(
        status=OperationStatus.SUCCESS,
        config_id=sample_config["id"],
        set_name="test_set_20230101",
        uploaded_count=3
    ))

    # Mock submit_workflow
    t2bq.submit_workflow = MagicMock(return_value=SubmissionResult(
        status=OperationStatus.SUCCESS,
        config_id=sample_config["id"],
        submission_id="test-submission-id",
        workflow_count=3
    ))

    # Now let's upload and submit
    result = t2bq.process_upload_and_submit(sample_config)

    # Check result for success
    assert isinstance(result, ConfigProcessingResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.config_id == sample_config["id"]
    assert result.set_name == "test_set_20230101"
    assert result.submission_id == "test-submission-id"
    assert result.uploaded_count == 3
    assert result.workflow_count == 3

    # Check that components were called correctly
    t2bq.samples_ops.get_samples_by_timeframe.assert_called()
    t2bq.sample_processor.drop_system_columns.assert_called_once()
    t2bq.upload_to_terra.assert_called_once()
    t2bq.submit_workflow.assert_called_once()
    
# # Test process_configuration
def test_process_configuration_success(t2bq, sample_config):
    """Test successful processing of configuration"""
    # Mock the steps
    t2bq.download_from_terra_to_bigquery = MagicMock(return_value=DownloadResult(
        status=OperationStatus.SUCCESS,
        loaded_count=5,
        filtered_count=2
    ))
    
    t2bq.process_upload_and_submit = MagicMock(return_value=ConfigProcessingResult(
        status=OperationStatus.SUCCESS,
        config_id=sample_config["id"],
        uploaded_count=3,
        set_name="test_set",
        submission_id="test-submission"
    ))
    
    # Now we can process the config
    result = t2bq.process_configuration(sample_config, None, preserve_path_structure=True)
    
    # Check results
    assert isinstance(result, ConfigProcessingResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.config_id == sample_config["id"]
    assert result.loaded_count == 5
    assert result.filtered_count == 2
    assert result.uploaded_count == 3
    assert result.set_name == "test_set"
    assert result.submission_id == "test-submission"
    
    # Check that both methods were called with the right arguments
    t2bq.download_from_terra_to_bigquery.assert_called_once_with(
        config=sample_config,
        destination_bucket=None,
        page_size=None,
        preserve_path_structure=True,
        unique_ids_by_config=False
    )
    t2bq.process_upload_and_submit.assert_called_once_with(sample_config)

def test_process_all_configs(t2bq):
    """Test processing all configurations"""
    # Mock get_active_configs to return test configs
    configs = [
        {"id": "config1", "prefix_field": "prefix1"},
        {"id": "config2", "prefix_field": "prefix2"}
    ]
    t2bq.get_active_configs = MagicMock(return_value=configs)
    
    # Mock process_configuration, one success and one no new samples
    t2bq.process_configuration = MagicMock(side_effect=[
        ConfigProcessingResult(status=OperationStatus.SUCCESS, config_id="config1", loaded_count=3, uploaded_count=2),
        ConfigProcessingResult(status=OperationStatus.NO_NEW_SAMPLES, config_id="config2")
    ])
    
    # Mock get_prefix_fields
    t2bq.config_ops.get_prefix_fields.return_value = "prefix_field"

    with patch("bioforklift.terra2bq.terra2bq.sleep") as mock_sleep:
        results = t2bq.process_all_configs(entity_type="test_entity", batch_size=1, cooldown_seconds=0)
    
    assert len(results) == 2
    assert results[0].status == OperationStatus.SUCCESS
    assert results[1].status == OperationStatus.NO_NEW_SAMPLES
    
    # Check method calls
    t2bq.get_active_configs.assert_called_once_with(entity_type="test_entity", skip_transferred=False)
    assert t2bq.process_configuration.call_count == 2
    
    # Check sleep was called between batches (since batch_size=1)
    assert mock_sleep.call_count == 1

# # Test sync_metadata_for_config
def test_sync_metadata_for_config_success(t2bq, sample_config):
    """Test successful metadata sync for one config"""
    # Mock samples data
    sample_df = pd.DataFrame({
        "id": ["sample1", "sample2", "sample3"],
        "entity_name": ["entity1", "entity2", "entity3"],
        "config_id": ["test-config-id", "test-config-id", "test-config-id"]
    })
    
    # Mock Terra data
    terra_df = pd.DataFrame({
        "entity_name": ["entity1", "entity2", "entity3"],
        "attr1": ["val1", "val2", "val3"]
    })
    
    t2bq.samples_ops.get_samples_by_timeframe.return_value = sample_df
    t2bq.samples_ops.get_config_identifier_field.return_value = "config_id"
    t2bq.samples_ops.get_sync_fields.return_value = ["attr1"]
    t2bq.samples_ops.get_sample_identifier_field.return_value = "entity_name"
    
    # Mock the helper methods
    t2bq._get_terra_data = MagicMock(return_value=DataResult(status=OperationStatus.SUCCESS, data=terra_df))
    t2bq._update_bigquery_with_terra_metadata = MagicMock(return_value=MetadataSyncResult(
        status=OperationStatus.SUCCESS,
        bq_updated_count=3,
        updated_entities={"entity1": {"attr1": "val1"}, "entity2": {"attr1": "val2"}, "entity3": {"attr1": "val3"}},
        failed_updates=[]
    ))
    t2bq._update_terra_with_synced_metadata = MagicMock(return_value=MetadataSyncResult(
        status=OperationStatus.SUCCESS,
        destination_updated_count=3,
        failed_updates=[]
    ))
    t2bq._get_target_entity_from_config = MagicMock(return_value="sample")
    
    result = t2bq.sync_metadata_for_config(sample_config, days_back=7, sync_fields=["attr1"], update_bigquery=True, update_destination=True)

    # Check result
    assert isinstance(result, MetadataSyncResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.config_id == sample_config["id"]
    assert result.bq_updated_count == 3
    assert result.destination_updated_count == 3

    # Verify the methods were called with the correct parameters
    t2bq._get_terra_data.assert_called_once_with(entity_type=sample_config["entity_type"], use_destination=False, page_size=None)
    t2bq._update_bigquery_with_terra_metadata.assert_called_once()
    t2bq._update_terra_with_synced_metadata.assert_called_once()  

def test_sync_metadata_success(t2bq):
    """Test successful sync_metadata across all configs"""
    # Mock get_active_configs
    configs = [
        {"id": "config1", "prefix_field": "prefix1", "entity_type": "sample1"},
        {"id": "config2", "prefix_field": "prefix2", "entity_type": "sample2"}
    ]
    t2bq.get_active_configs = MagicMock(return_value=configs)
    
    # Mock sync_metadata_for_config
    t2bq.sync_metadata_for_config = MagicMock(side_effect=[
        MetadataSyncResult(status=OperationStatus.SUCCESS, config_id="config1", bq_updated_count=3, destination_updated_count=3, failed_updates=[]),
        MetadataSyncResult(status=OperationStatus.NO_UPDATES, config_id="config2", bq_updated_count=0, destination_updated_count=0, failed_updates=[])
    ])
    
    # Mock config_ops and setup_terra_client
    t2bq.config_ops.get_prefix_fields.return_value = "prefix_field"
    t2bq.setup_terra_client = MagicMock()
    t2bq._cleanup_terra_client = MagicMock()
    
    with patch("bioforklift.terra2bq.terra2bq.sleep") as mock_sleep:
        result = t2bq.sync_metadata(days_back=7, update_bigquery=True, update_destination=True, batch_size=1, cooldown_seconds=0)
    
    assert isinstance(result, MetadataSyncResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.bq_updated_count == 3
    assert result.destination_updated_count == 3
    assert result.total_updated_count == 6
    assert result.processed_configs == 2
    assert not result.failed_updates

    t2bq.get_active_configs.assert_called_once()
    assert t2bq.sync_metadata_for_config.call_count == 2
    assert t2bq.setup_terra_client.call_count == 2
    assert t2bq._cleanup_terra_client.call_count == 2
    assert mock_sleep.call_count == 1  # Sleep between batches, a little nap
    
def test_sync_metadata_for_config_invalid_parameter_combination(t2bq):
    """Test that sync_metadata_for_config rejects invalid parameter combination"""
    # Create a test config
    config = {"id": "test_config", "prefix_field": "test_prefix", "entity_type": "sample"}
    
    # Test with both update_destination=True and use_destination_entity=True (should be blocked)
    result = t2bq.sync_metadata_for_config(
        config=config,
        days_back=7,
        sync_fields=["field1"],
        update_bigquery=True,
        update_destination=True,
        use_destination_entity=True
    )
    
    # Verify the result shows an error
    assert isinstance(result, MetadataSyncResult)
    assert result.status == OperationStatus.ERROR
    assert "Invalid parameter combination" in result.message
    assert result.bq_updated_count == 0
    assert result.destination_updated_count == 0


def test_sync_metadata_for_config_calls_get_target_entity_with_use_destination_entity(t2bq):
    """Test that sync_metadata_for_config calls _get_target_entity_from_config when use_destination_entity is True (without update_destination)"""
    # Create a test config
    config = {"id": "test_config", "prefix_field": "test_prefix", "entity_type": "sample"}
    
    # Mock _get_target_entity_from_config
    t2bq._get_target_entity_from_config = MagicMock(return_value="destination_entity_type")
    
    # Mock the necessary dependencies to avoid actual execution
    t2bq.samples_ops = MagicMock()
    t2bq.samples_ops.get_config_identifier_field.return_value = "config_id"
    t2bq.samples_ops.get_sync_fields.return_value = ["field1", "field2"]
    t2bq.samples_ops.get_sample_identifier_field.return_value = "sample_id"
    
    # Create a mock dataframe for samples
    sample_df = pd.DataFrame({
        "config_id": ["test_config"],
        "sample_id": ["sample1"],
        "field1": ["value1"],
        "field2": ["value2"]
    })
    t2bq.samples_ops.get_samples_by_timeframe.return_value = sample_df
    
    # Mock _get_terra_data
    t2bq._get_terra_data = MagicMock(return_value=DataResult(status=OperationStatus.SUCCESS, data=pd.DataFrame()))
    
    # Mock _update_bigquery_with_terra_metadata
    t2bq._update_bigquery_with_terra_metadata = MagicMock(return_value=MetadataSyncResult(
        status=OperationStatus.SUCCESS,
        bq_updated_count=1,
        updated_entities={},
        failed_updates=[]
    ))
    
    # Test with use_destination_entity=True but update_destination=False
    result = t2bq.sync_metadata_for_config(
        config=config,
        days_back=7,
        sync_fields=["field1", "field2"],
        update_bigquery=True,
        update_destination=False,
        use_destination_entity=True
    )
    
    # Verify _get_target_entity_from_config was called once for getting the entity type
    assert t2bq._get_target_entity_from_config.call_count == 1
    t2bq._get_target_entity_from_config.assert_called_with(config)
    
    # Verify the result
    assert isinstance(result, MetadataSyncResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.bq_updated_count == 1
    
    # Reset the mock and test with use_destination_entity=False
    t2bq._get_target_entity_from_config.reset_mock()
    
    # Mock _update_bigquery_with_terra_metadata to return some updated entities for destination update
    t2bq._update_bigquery_with_terra_metadata = MagicMock(return_value=MetadataSyncResult(
        status=OperationStatus.SUCCESS,
        bq_updated_count=1,
        updated_entities={"entity1": {"attr1": "val1"}},  # Non-empty to trigger destination update
        failed_updates=[]
    ))
    
    # Mock _update_terra_with_synced_metadata for the destination update
    t2bq._update_terra_with_synced_metadata = MagicMock(return_value=MetadataSyncResult(
        status=OperationStatus.SUCCESS,
        destination_updated_count=1,
        failed_updates=[]
    ))
    
    result = t2bq.sync_metadata_for_config(
        config=config,
        days_back=7,
        sync_fields=["field1", "field2"],
        update_bigquery=True,
        update_destination=True,
        use_destination_entity=False
    )
    
    # Verify _get_target_entity_from_config was called only once
    # - Only when updating Terra, not for getting the initial entity type
    assert t2bq._get_target_entity_from_config.call_count == 1
    t2bq._get_target_entity_from_config.assert_called_once_with(config)

# # Test update_workflow_status_for_config
def test_update_workflow_status_for_config_success(t2bq, sample_config):
    """Test successful workflow status update for one config"""
    # Mock get_unique_submission_ids
    t2bq.samples_ops.get_unique_submission_ids.return_value = ["submission1", "submission2"]
    t2bq.samples_ops.get_config_identifier_field.return_value = "config_id"
    t2bq.config_ops.get_prefix_fields.return_value = "prefix_field"
    
    # Mock the submission processing
    t2bq._process_submission = MagicMock(side_effect=[
        SubmissionResult(status=OperationStatus.SUCCESS, workflow_count=2, workflow_states={"Running": 1, "Submitted": 1}, failed_updates=[]),
        SubmissionResult(status=OperationStatus.SUCCESS, workflow_count=1, workflow_states={"Submitted": 1}, failed_updates=[])
    ])
    
    # Mock incomplete workflow processing
    t2bq._process_incomplete_workflows = MagicMock(return_value={
        "status": "success", "updated_count": 1, "workflow_states": {"Succeeded": 1}, "failed_updates": []
    })
    
    result = t2bq.update_workflow_status_for_config(sample_config, days_back=7, batch_size=100, update_bigquery=True)
    
    # Check result for success
    assert isinstance(result, WorkflowResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.config_id == sample_config["id"]
    assert result.workflow_count == 4  # 2 + 1 + 1 from the mocks
    assert len(result.workflow_states) == 3
    assert result.workflow_states["Running"] == 1
    assert result.workflow_states["Submitted"] == 2
    assert result.workflow_states["Succeeded"] == 1
    assert not result.failed_updates
    
    # Check that processing methods were called
    assert t2bq._process_submission.call_count == 2
    t2bq._process_incomplete_workflows.assert_called_once()

# # Test update_workflow_status
def test_update_workflow_status_success(t2bq):
    """Test successful update_workflow_status across all configs"""
    # Mock get_active_configs
    configs = [
        {"id": "config1", "prefix_field": "prefix1"},
        {"id": "config2", "prefix_field": "prefix2"}
    ]
    t2bq.get_active_configs = MagicMock(return_value=configs)
    
    # Mock update_workflow_status_for_config
    t2bq.update_workflow_status_for_config = MagicMock(side_effect=[
        WorkflowResult(
            status=OperationStatus.SUCCESS,
            config_id="config1", 
            workflow_count=3,
            workflow_states={"Running": 2, "Submitted": 1},
            failed_updates=[]
        ),
        WorkflowResult(
            status=OperationStatus.NO_UPDATES,
            config_id="config2", 
            workflow_count=0,
            workflow_states={},
            failed_updates=[]
        )
    ])
    
    # Mock config_ops and terra setup
    t2bq.config_ops.get_prefix_fields.return_value = "prefix_field"
    t2bq.setup_terra_client = MagicMock()
    t2bq._cleanup_terra_client = MagicMock()
    
    with patch("bioforklift.terra2bq.terra2bq.sleep") as mock_sleep:
        result = t2bq.update_workflow_status(
            days_back=7, 
            batch_size=100, 
            update_bigquery=True,
            config_batch_size=1,
            cooldown_seconds=0
        )
    
    # Check result for success
    assert isinstance(result, WorkflowResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.workflow_count == 3
    assert len(result.workflow_states) == 2
    assert not result.failed_updates
    
    t2bq.get_active_configs.assert_called_once()
    assert t2bq.update_workflow_status_for_config.call_count == 2
    assert t2bq.setup_terra_client.call_count == 2
    assert t2bq._cleanup_terra_client.call_count == 2
    assert mock_sleep.call_count == 1  # Sleep between batches, another little nap
    

def test_update_bigquery_with_terra_metadata_overwrite_behavior(t2bq):
    """Test that overwrite_metadata parameter controls update behavior correctly"""
    
    # Mock the helper method that gets Terra field names
    t2bq._get_terra_field_name = MagicMock(side_effect=lambda field, row: field if field in row.index else None)
    
    # Mock the coerce_dataframe_types method
    t2bq.samples_ops.coerce_dataframe_types = MagicMock()
    
    # Create test data - BigQuery samples with existing values
    bq_samples = pd.DataFrame({
        "id": ["sample1", "sample2", "sample3", "sample4"],
        "entity_name": ["entity1", "entity2", "entity3", "entity4"], 
        "existing_field": ["old_value1", "", None, "old_value4"],  # Mix of existing, empty, and null values
        "empty_field": [None, None, "", ""]  # All empty/null values
    })
    
    # Create Terra data with new values
    terra_data = pd.DataFrame({
        "entity_name": ["entity1", "entity2", "entity3", "entity4"],
        "existing_field": ["new_value1", "new_value2", "new_value3", "new_value4"],
        "empty_field": ["fill_value1", "fill_value2", "fill_value3", "fill_value4"]
    })
    
    sync_fields = ["existing_field", "empty_field"]
    sample_identifier = "entity_name"
    
    # Test 1: overwrite_metadata=False (default behavior)
    # Should only update empty/null fields, not overwrite existing values
    t2bq.samples_ops.bulk_update_samples = MagicMock(return_value={
        "updated_count": 3,  # Only samples 2, 3, and all for empty_field should be updated
        "failed_updates": []
    })
    
    result = t2bq._update_bigquery_with_terra_metadata(
        config_samples=bq_samples,
        terra_df=terra_data,
        sync_fields=sync_fields,
        sample_identifier_field=sample_identifier,
        update_bigquery=True,
        overwrite_metadata=False
    )
    
    # Verify the correct samples were marked for update
    assert isinstance(result, MetadataSyncResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.bq_updated_count == 3
    
    # Check what updates were sent to bulk_update_samples
    call_args = t2bq.samples_ops.bulk_update_samples.call_args[0][0]  # First positional argument
    
    # Should have updates for:
    # - sample2: existing_field (was empty) and empty_field
    # - sample3: existing_field (was null) and empty_field  
    # - sample1: only empty_field (existing_field should not be overwritten)
    # - sample4: only empty_field (existing_field should not be overwritten)
    
    # Verify sample1 - should only update empty_field, not existing_field
    sample1_update = next((update for update in call_args if update["id"] == "sample1"), None)
    assert sample1_update is not None
    assert "empty_field" in sample1_update
    assert sample1_update["empty_field"] == "fill_value1"
    assert "existing_field" not in sample1_update  # Should not overwrite existing value
    
    # Verify sample2 - should update both fields (existing_field was empty)
    sample2_update = next((update for update in call_args if update["id"] == "sample2"), None)
    assert sample2_update is not None
    assert sample2_update["existing_field"] == "new_value2"
    assert sample2_update["empty_field"] == "fill_value2"
    
    # Verify sample3 - should update both fields (existing_field was null)
    sample3_update = next((update for update in call_args if update["id"] == "sample3"), None)
    assert sample3_update is not None
    assert sample3_update["existing_field"] == "new_value3"
    assert sample3_update["empty_field"] == "fill_value3"
    
    # Verify sample4 - should only update empty_field, not existing_field
    sample4_update = next((update for update in call_args if update["id"] == "sample4"), None)
    assert sample4_update is not None
    assert "empty_field" in sample4_update
    assert sample4_update["empty_field"] == "fill_value4"
    assert "existing_field" not in sample4_update  # Should not overwrite existing value
    
    # Reset the mock for the second test
    t2bq.samples_ops.bulk_update_samples.reset_mock()
    
    # Test 2: overwrite_metadata=True
    # Should update all fields where Terra values differ from BigQuery values
    t2bq.samples_ops.bulk_update_samples = MagicMock(return_value={
        "updated_count": 4,  # All samples should be updated
        "failed_updates": []
    })
    
    result = t2bq._update_bigquery_with_terra_metadata(
        config_samples=bq_samples,
        terra_df=terra_data,
        sync_fields=sync_fields,
        sample_identifier_field=sample_identifier,
        update_bigquery=True,
        overwrite_metadata=True
    )
    
    # Verify all samples were marked for update
    assert isinstance(result, MetadataSyncResult)
    assert result.status == OperationStatus.SUCCESS
    assert result.bq_updated_count == 4
    
    # Check what updates were sent to bulk_update_samples
    call_args = t2bq.samples_ops.bulk_update_samples.call_args[0][0]
    
    # All samples should now have updates for both fields
    for i in range(1, 5):
        sample_update = next((update for update in call_args if update["id"] == f"sample{i}"), None)
        assert sample_update is not None
        assert sample_update["existing_field"] == f"new_value{i}"
        assert sample_update["empty_field"] == f"fill_value{i}"
    
    # Test 3: overwrite_metadata=True with identical values
    # Should not update when Terra value equals BigQuery value
    bq_samples_identical = pd.DataFrame({
        "id": ["sample1"],
        "entity_name": ["entity1"],
        "existing_field": ["same_value"]  # Same as Terra value
    })
    
    terra_data_identical = pd.DataFrame({
        "entity_name": ["entity1"],
        "existing_field": ["same_value"]  # Same value
    })
    
    result = t2bq._update_bigquery_with_terra_metadata(
        config_samples=bq_samples_identical,
        terra_df=terra_data_identical,
        sync_fields=["existing_field"],
        sample_identifier_field=sample_identifier,
        update_bigquery=True,
        overwrite_metadata=True
    )
    
    # Should not update when values are identical
    assert isinstance(result, MetadataSyncResult)
    assert result.status == OperationStatus.NO_UPDATES
    assert result.bq_updated_count == 0


def test_update_bigquery_with_terra_metadata_allow_null_overwrite(t2bq):
    """Terra null/empty values clear BigQuery fields only when both overwrite_metadata
    and allow_null_overwrite are True, and never propagate to destination Terra."""

    t2bq._get_terra_field_name = MagicMock(
        side_effect=lambda field, row: field if field in row.index else None
    )
    t2bq.samples_ops.coerce_dataframe_types = MagicMock()

    # sample1: Terra null, BQ populated       -> should be cleared when flag is on
    # sample2: Terra empty string, BQ populated -> should be cleared when flag is on
    # sample3: Terra null, BQ null            -> no-op (nothing to clear)
    # sample4: Terra populated, BQ populated (different) -> normal overwrite path
    bq_samples = pd.DataFrame({
        "id": ["sample1", "sample2", "sample3", "sample4"],
        "entity_name": ["entity1", "entity2", "entity3", "entity4"],
        "existing_field": ["bq_value1", "bq_value2", None, "bq_value4"],
    })

    terra_data = pd.DataFrame({
        "entity_name": ["entity1", "entity2", "entity3", "entity4"],
        "existing_field": [None, "", None, "terra_value4"],
    })

    # Default behavior: allow_null_overwrite=False — null Terra values are skipped,
    # only sample4 gets its differing value overwritten.
    t2bq.samples_ops.bulk_update_samples = MagicMock(return_value={
        "updated_count": 1,
        "failed_updates": []
    })

    result = t2bq._update_bigquery_with_terra_metadata(
        config_samples=bq_samples,
        terra_df=terra_data,
        sync_fields=["existing_field"],
        sample_identifier_field="entity_name",
        update_bigquery=True,
        overwrite_metadata=True,
        allow_null_overwrite=False,
    )

    assert result.status == OperationStatus.SUCCESS
    call_kwargs = t2bq.samples_ops.bulk_update_samples.call_args.kwargs
    assert call_kwargs["allow_nulls"] is False
    updates = t2bq.samples_ops.bulk_update_samples.call_args[0][0]
    update_ids = {u["id"] for u in updates}
    assert update_ids == {"sample4"}

    # allow_null_overwrite=True — sample1 and sample2 should be cleared,
    # sample3 is a no-op (both sides empty), sample4 keeps its normal overwrite.
    t2bq.samples_ops.bulk_update_samples = MagicMock(return_value={
        "updated_count": 3,
        "failed_updates": []
    })

    result = t2bq._update_bigquery_with_terra_metadata(
        config_samples=bq_samples,
        terra_df=terra_data,
        sync_fields=["existing_field"],
        sample_identifier_field="entity_name",
        update_bigquery=True,
        overwrite_metadata=True,
        allow_null_overwrite=True,
    )

    assert result.status == OperationStatus.SUCCESS
    call_kwargs = t2bq.samples_ops.bulk_update_samples.call_args.kwargs
    assert call_kwargs["allow_nulls"] is True

    updates = t2bq.samples_ops.bulk_update_samples.call_args[0][0]
    updates_by_id = {u["id"]: u for u in updates}

    assert set(updates_by_id.keys()) == {"sample1", "sample2", "sample4"}
    assert updates_by_id["sample1"]["existing_field"] is None
    assert updates_by_id["sample2"]["existing_field"] is None
    assert updates_by_id["sample4"]["existing_field"] == "terra_value4"

    # Destination Terra should not receive the null clears — only sample4 flows through.
    assert set(result.updated_entities.keys()) == {"entity4"}
    assert result.updated_entities["entity4"] == {"existing_field": "terra_value4"}


def test_allow_null_overwrite_requires_overwrite_metadata(t2bq, caplog):
    """allow_null_overwrite without overwrite_metadata should warn and behave like the default."""
    import logging

    t2bq._get_terra_field_name = MagicMock(
        side_effect=lambda field, row: field if field in row.index else None
    )
    t2bq.samples_ops.coerce_dataframe_types = MagicMock()

    bq_samples = pd.DataFrame({
        "id": ["sample1"],
        "entity_name": ["entity1"],
        "existing_field": ["bq_value1"],
    })
    terra_data = pd.DataFrame({
        "entity_name": ["entity1"],
        "existing_field": [None],
    })

    t2bq.samples_ops.bulk_update_samples = MagicMock(return_value={
        "updated_count": 0,
        "failed_updates": []
    })

    with caplog.at_level(logging.WARNING):
        result = t2bq._update_bigquery_with_terra_metadata(
            config_samples=bq_samples,
            terra_df=terra_data,
            sync_fields=["existing_field"],
            sample_identifier_field="entity_name",
            update_bigquery=True,
            overwrite_metadata=False,
            allow_null_overwrite=True,
        )

    assert any("allow_null_overwrite" in record.message for record in caplog.records)
    assert result.status == OperationStatus.NO_UPDATES
    t2bq.samples_ops.bulk_update_samples.assert_not_called()