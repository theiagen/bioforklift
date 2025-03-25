import pytest
import pandas as pd
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY
from datetime import datetime
from forklift.terra2bq import Terra2BQ

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
def t2bq():
    """Create a basic Terra2BQ instance with mocked dependencies"""
    instance = Terra2BQ(
        bigquery_project="test-project",
        bigquery_dataset="test-dataset"
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
    """Return a sample DataFrame with test data"""
    return pd.DataFrame({
        "id": ["sample1", "sample2", "sample3"],
        "entity_name": ["entity1", "entity2", "entity3"],
        "config_id": ["test-config-id", "test-config-id", "test-config-id"],
        "uploaded_at": [None, None, None],
        "upload_source": [None, None, None]
    })

# Test initialization
def test_init_with_required_params():
    """Test initialization with only required parameters"""
    t2bq = Terra2BQ(
        bigquery_project="test-project",
        bigquery_dataset="test-dataset"
    )
    
    assert t2bq.bigquery is not None
    assert t2bq.lookup_timeframe == "today"
    assert t2bq.samples_table == "samples"
    assert t2bq.configs_table == "configs"
    assert t2bq.project_timezone == "UTC"

def test_init_with_custom_params():
    """Test initialization with custom parameters"""
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
        project_timezone="America/New_York"
    )
    
    assert t2bq.lookup_timeframe == "custom"
    assert t2bq.lookup_days_back == 7
    assert t2bq.samples_table == "custom_samples"
    assert t2bq.configs_table == "custom_configs"
    assert t2bq.source_workspace == "test-workspace"
    assert t2bq.source_project == "test-project"
    assert t2bq.source_datatable == "test_entity"
    assert t2bq.project_timezone == "America/New_York"

def test_init_with_custom_timeframe_validation():
    """Test that custom timeframe requires days_back or hours_back"""
    with pytest.raises(ValueError, match="Custom lookup timeframe requires lookup_days_back or lookup_hours_back"):
        Terra2BQ(
            bigquery_project="test-project",
            bigquery_dataset="test-dataset",
            lookup_timeframe="custom"
        )

@patch("forklift.bigquery.BigQuery")
def test_initialize_operations(mock_bigquery_class, tmp_path):
    """Test initializing operations objects"""
    # Create temporary schema files with proper structure
    samples_schema = tmp_path / "samples_schema.yaml"
    configs_schema = tmp_path / "configs_schema.yaml"
    
    samples_schema.write_text("""
        fields:
        id:
            type: string
            required: true
        entity_name:
            type: string
            required: true
        """)

    configs_schema.write_text("""
        fields:
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
    with patch("forklift.terra2bq.Terra2BQ.initialize_operations"):
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

@patch("forklift.terra2bq.terra2bq.Terra")
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

@patch("forklift.terra2bq.terra2bq.Terra")
def test_setup_terra_client_with_instance_values(mock_terra_class, sample_config):
    """Test that instance values take precedence over config values"""
    t2bq = Terra2BQ(
        bigquery_project="test-project",
        bigquery_dataset="test-dataset",
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

def test_setup_terra_client_missing_source():
    """Test error when source workspace/project not provided"""
    t2bq = Terra2BQ(
        bigquery_project="test-project",
        bigquery_dataset="test-dataset"
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
    t2bq.config_ops.get_configs.assert_called_once_with(active_only=True, entity_type=None)

def test_get_active_configs_with_entity_type(t2bq):
    """Test getting active configurations filtered by entity type"""
    t2bq.config_ops.get_configs.return_value = [{"id": "config1"}]
    
    configs = t2bq.get_active_configs(entity_type="test_entity")
    
    assert configs == [{"id": "config1"}]
    t2bq.config_ops.get_configs.assert_called_once_with(active_only=True, entity_type="test_entity")

def test_get_active_configs_no_config_ops():
    """Test error when config_ops not initialized"""
    t2bq = Terra2BQ(
        bigquery_project="test-project",
        bigquery_dataset="test-dataset"
    )
    
    # No config_ops initialized
    with pytest.raises(ValueError, match="Config operations not initialized"):
        t2bq.get_active_configs()

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
    
    assert result["status"] == "success"
    assert result["config_id"] == sample_config["id"]

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
    assert result["status"] == "success"
    assert result["config_id"] == sample_config["id"]
    assert "set_name" in result  # Just check it exists
    assert result["uploaded_count"] == 3
    
    # Check that the methods were called
    t2bq.terra.entities.upload_entities.assert_called_once()
    assert t2bq.terra.entities.create_entity_set.call_count == 1
    assert t2bq.samples_ops.bulk_update_samples.call_count == 1
    
    # Verify set_name is included in the create_entity_set call
    set_name = result["set_name"]
    # Use kwargs to access keyword arguments
    create_kwargs = t2bq.terra.entities.create_entity_set.call_args.kwargs
    assert "set_name" in create_kwargs
    assert create_kwargs["set_name"] == set_name
    
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
    
    with patch("forklift.terra2bq.terra2bq.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime.strftime.return_value = "2023-01-01 12:00:00"
        
        result = t2bq.submit_workflow(sample_config, "test_set", sample_df)
    
    # Check result for success
    assert result["status"] == "success"
    assert result["config_id"] == sample_config["id"]
    assert result["set_name"] == "test_set"
    assert result["submission_id"] == "test-submission-id"
    assert result["workflow_count"] == 3
    
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
    
    # Mock drop_system_value_columns function
    with patch("forklift.terra2bq.terra2bq.drop_system_value_columns") as mock_drop:
        mock_drop.return_value = pd.DataFrame({
            "entity_name": ["entity1", "entity2", "entity3"],
            "attr1": [1, 2, 3]
        })
        
        # Mock upload_to_terra
        t2bq.upload_to_terra = MagicMock(return_value={
            "status": "success",
            "config_id": sample_config["id"],
            "set_name": "test_set_20230101",
            "uploaded_count": 3
        })
        
        # Mock submit_workflow
        t2bq.submit_workflow = MagicMock(return_value={
            "status": "success",
            "config_id": sample_config["id"],
            "set_name": "test_set_20230101",
            "submission_id": "test-submission-id",
            "workflow_count": 3
        })
        
        # Now let's upload and submit
        result = t2bq.process_upload_and_submit(sample_config)
    
    # Check result for success
    assert result["status"] == "success"
    assert result["config_id"] == sample_config["id"]
    assert result["set_name"] == "test_set_20230101"
    assert result["submission_id"] == "test-submission-id"
    assert result["uploaded_count"] == 3
    assert result["workflow_count"] == 3
    
    # Check that components were called correctly
    t2bq.samples_ops.get_samples_by_timeframe.assert_called()
    mock_drop.assert_called_once()
    t2bq.upload_to_terra.assert_called_once()
    t2bq.submit_workflow.assert_called_once()
    
# # Test process_configuration
def test_process_configuration_success(t2bq, sample_config):
    """Test successful processing of configuration"""
    # Mock the steps
    t2bq.download_from_terra_to_bigquery = MagicMock(return_value={
        "status": "success",
        "loaded_count": 5,
        "filtered_count": 2
    })
    
    t2bq.process_upload_and_submit = MagicMock(return_value={
        "status": "success", 
        "config_id": sample_config["id"],
        "uploaded_count": 3,
        "set_name": "test_set",
        "submission_id": "test-submission"
    })
    
    # Now we can process the config
    result = t2bq.process_configuration(sample_config)
    
    # Check results
    assert result["status"] == "success"
    assert result["config_id"] == sample_config["id"]
    assert result["loaded_count"] == 5
    assert result["filtered_count"] == 2
    assert result["uploaded_count"] == 3
    assert result["set_name"] == "test_set"
    assert result["submission_id"] == "test-submission"
    
    # Check that both methods were called with the right arguments
    t2bq.download_from_terra_to_bigquery.assert_called_once_with(sample_config)
    t2bq.process_upload_and_submit.assert_called_once_with(sample_config)

# # Test process_all_configs
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
        {"status": "success", "config_id": "config1", "loaded_count": 3, "uploaded_count": 2},
        {"status": "no_new_samples", "config_id": "config2"}
    ])
    
    # Mock get_prefix_fields
    t2bq.config_ops.get_prefix_fields.return_value = "prefix_field"
    
    # Call the method
    with patch("forklift.terra2bq.terra2bq.sleep") as mock_sleep:
        results = t2bq.process_all_configs(entity_type="test_entity", batch_size=1, cooldown_seconds=0)
    
    # Check results
    assert len(results) == 2
    assert results[0]["status"] == "success"
    assert results[1]["status"] == "no_new_samples"
    
    # Check method calls
    t2bq.get_active_configs.assert_called_once_with(entity_type="test_entity")
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
    t2bq._get_terra_data = MagicMock(return_value={"status": "success", "data": terra_df})
    t2bq._update_bigquery_with_terra_metadata = MagicMock(return_value={
        "status": "success",
        "updated_count": 3,
        "updated_entities": {"entity1": {"attr1": "val1"}, "entity2": {"attr1": "val2"}, "entity3": {"attr1": "val3"}},
        "failed_updates": []
    })
    t2bq._update_terra_with_synced_metadata = MagicMock(return_value={
        "status": "success",
        "updated_count": 3,
        "failed_updates": []
    })
    t2bq._get_target_entity_from_config = MagicMock(return_value="sample")
    
    result = t2bq.sync_metadata_for_config(sample_config, days_back=7, update_bigquery=True, update_destination=True)
    
    # Check result
    assert result["status"] == "success"
    assert result["config_id"] == sample_config["id"]
    assert result["bq_updated_count"] == 3
    assert result["destination_updated_count"] == 3  
    
    # Verify the methods were called with the correct parameters
    t2bq._get_terra_data.assert_called_once_with(sample_config["entity_type"])
    t2bq._update_bigquery_with_terra_metadata.assert_called_once()
    t2bq._update_terra_with_synced_metadata.assert_called_once()  

# # Test sync_metadata
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
        {"status": "success", "config_id": "config1", "bq_updated_count": 3, "destination_updated_count": 3, "failed_updates": []},
        {"status": "no_updates", "config_id": "config2", "bq_updated_count": 0, "destination_updated_count": 0, "failed_updates": []}
    ])
    
    # Mock config_ops and setup_terra_client
    t2bq.config_ops.get_prefix_fields.return_value = "prefix_field"
    t2bq.setup_terra_client = MagicMock()
    t2bq._cleanup_terra_client = MagicMock()
    
    with patch("forklift.terra2bq.terra2bq.sleep") as mock_sleep:
        result = t2bq.sync_metadata(days_back=7, update_bigquery=True, update_destination=True, batch_size=1, cooldown_seconds=0)
    
    assert result["status"] == "success"
    assert result["bq_updated_count"] == 3
    assert result["destination_updated_count"] == 3
    assert result["total_updated_count"] == 6
    assert result["processed_configs"] == 2
    assert not result["failed_updates"]

    t2bq.get_active_configs.assert_called_once()
    assert t2bq.sync_metadata_for_config.call_count == 2
    assert t2bq.setup_terra_client.call_count == 2
    assert t2bq._cleanup_terra_client.call_count == 2
    assert mock_sleep.call_count == 1  # Sleep between batches, a little nap

# # Test update_workflow_status_for_config
def test_update_workflow_status_for_config_success(t2bq, sample_config):
    """Test successful workflow status update for one config"""
    # Mock get_unique_submission_ids
    t2bq.samples_ops.get_unique_submission_ids.return_value = ["submission1", "submission2"]
    t2bq.samples_ops.get_config_identifier_field.return_value = "config_id"
    t2bq.config_ops.get_prefix_fields.return_value = "prefix_field"
    
    # Mock the submission processing
    t2bq._process_submission = MagicMock(side_effect=[
        {"status": "success", "updated_count": 2, "workflow_states": {"Running": 1, "Submitted": 1}, "failed_updates": []},
        {"status": "success", "updated_count": 1, "workflow_states": {"Submitted": 1}, "failed_updates": []}
    ])
    
    # Mock incomplete workflow processing
    t2bq._process_incomplete_workflows = MagicMock(return_value={
        "status": "success", "updated_count": 1, "workflow_states": {"Succeeded": 1}, "failed_updates": []
    })
    
    result = t2bq.update_workflow_status_for_config(sample_config, days_back=7, batch_size=100, update_bigquery=True)
    
    # Check result for success
    assert result["status"] == "success"
    assert result["config_id"] == sample_config["id"]
    assert result["updated_count"] == 4  # 2 + 1 + 1 from the mocks
    assert result["processed_submissions"] == 2
    assert len(result["workflow_states"]) == 3
    assert result["workflow_states"]["Running"] == 1
    assert result["workflow_states"]["Submitted"] == 2
    assert result["workflow_states"]["Succeeded"] == 1
    assert not result["failed_updates"]
    
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
        {
            "status": "success", 
            "config_id": "config1", 
            "updated_count": 3, 
            "processed_submissions": 2,
            "workflow_states": {"Running": 2, "Submitted": 1},
            "failed_updates": []
        },
        {
            "status": "no_submissions", 
            "config_id": "config2", 
            "updated_count": 0,
            "processed_submissions": 0,
            "workflow_states": {},
            "failed_updates": []
        }
    ])
    
    # Mock config_ops and terra setup
    t2bq.config_ops.get_prefix_fields.return_value = "prefix_field"
    t2bq.setup_terra_client = MagicMock()
    t2bq._cleanup_terra_client = MagicMock()
    
    with patch("forklift.terra2bq.terra2bq.sleep") as mock_sleep:
        result = t2bq.update_workflow_status(
            days_back=7, 
            batch_size=100, 
            update_bigquery=True,
            config_batch_size=1,
            cooldown_seconds=0
        )
    
    # Check result for success
    assert result["status"] == "success"
    assert result["updated_count"] == 3
    assert result["processed_configs"] == 2
    assert result["processed_submissions"] == 2
    assert len(result["workflow_states"]) == 2
    assert not result["failed_updates"]
    
    t2bq.get_active_configs.assert_called_once()
    assert t2bq.update_workflow_status_for_config.call_count == 2
    assert t2bq.setup_terra_client.call_count == 2
    assert t2bq._cleanup_terra_client.call_count == 2
    assert mock_sleep.call_count == 1  # Sleep between batches, another little nap