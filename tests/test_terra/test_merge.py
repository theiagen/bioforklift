import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from bioforklift.terra import TerraMerge

# Sample data for mocking
PRIMARY_DATA = pd.DataFrame({
    "entity:sample_id": ["sample1", "sample2", "sample3", "sample4"],
    "attribute1": ["value1", "value2", "value3", "value4"],
    "attribute2": [1, 2, 3, 4]
})

SECONDARY_DATA = pd.DataFrame({
    "entity:sample_metadata_id": ["sample1", "sample2", "sample5", "sample6"],
    "attribute3": ["meta1", "meta2", "meta3", "meta4"],
    "attribute4": [10, 20, 30, 40]
})

MASTER_DATA = pd.DataFrame({
    "entity:sample_master_id": ["sample1", "sample7", "sample8"],
    "attribute1": ["old_value1", "value7", "value8"],
    "attribute2": [100, 200, 300],
    "attribute3": ["old_meta1", "meta7", "meta8"],
    "attribute4": [1000, 2000, 3000]
})

EMPTY_MASTER_DATA = pd.DataFrame()

# Expected merged data based on sample inputs
EXPECTED_MERGED_DATA = pd.DataFrame({
    "entity:sample_id": ["sample2"],
    "attribute1": ["value2"],
    "attribute2": [2],
    "attribute3": ["meta2"],
    "attribute4": [20]
})

EXPECTED_UPLOAD_DATA = pd.DataFrame({
    "entity:sample_master_id": ["sample2"],
    "attribute1": ["value2"],
    "attribute2": [2],
    "attribute3": ["meta2"],
    "attribute4": [20]
})


class TestTerraMerge:
    
    @pytest.fixture
    def mock_terra_entities(self):
        """Create a mock TerraEntities client."""
        mock = MagicMock()
        
        # Configure the mock to return test data
        def mock_download_table(table_name, use_destination=False):
            if table_name == "sample":
                return PRIMARY_DATA.copy()
            elif table_name == "sample_metadata":
                return SECONDARY_DATA.copy()
            elif table_name == "sample_master":
                return MASTER_DATA.copy()
            elif table_name == "new_master":
                # Simulate table not existing
                raise Exception("Table not found")
            return pd.DataFrame()
        
        mock.download_table.side_effect = mock_download_table
        
        # Mock the upload method to return the input data
        mock.upload_entities.return_value = EXPECTED_UPLOAD_DATA.copy()
        
        return mock
    
    @pytest.fixture
    def terra_merge(self, mock_terra_entities):
        """Create a TerraMerge instance with the mock client."""
        return TerraMerge(mock_terra_entities)
    
    def test_merge_existing_master(self, terra_merge, mock_terra_entities):
        """Test merging when master table exists."""
        result = terra_merge.merge_and_update_master(
            primary_table="sample",
            secondary_table="sample_metadata", 
            master_table="sample_master"
        )
        
        # Verify download_table was called with the right parameters
        assert mock_terra_entities.download_table.call_count == 3
        mock_terra_entities.download_table.assert_any_call("sample", use_destination=False)
        mock_terra_entities.download_table.assert_any_call("sample_metadata", use_destination=False)
        mock_terra_entities.download_table.assert_any_call("sample_master", use_destination=False)
        
        # Verify upload_entities was called with the right parameters
        mock_terra_entities.upload_entities.assert_called_once()
        call_args = mock_terra_entities.upload_entities.call_args[1]
        
        # Check if the upload data format is correct
        assert call_args["target"] == "sample_master"
        assert call_args["use_destination"] == False
        assert call_args["entity_identifier_column"] == "entity:sample_master_id"
        
        # Check the returned data
        pd.testing.assert_frame_equal(result, EXPECTED_UPLOAD_DATA)
    
    def test_merge_new_master(self, terra_merge, mock_terra_entities):
        """Test merging when master table doesn't exist."""
        # Change mock to return empty for master table
        mock_terra_entities.download_table.side_effect = lambda table, use_destination: (
            PRIMARY_DATA.copy() if table == "sample" else
            SECONDARY_DATA.copy() if table == "sample_metadata" else
            pd.DataFrame()  # Empty for master table
        )
        
        result = terra_merge.merge_and_update_master(
            primary_table="sample",
            secondary_table="sample_metadata", 
            master_table="new_master"
        )
        
        # Verify upload was called with all common records
        mock_terra_entities.upload_entities.assert_called_once()
        call_args = mock_terra_entities.upload_entities.call_args[1]
        
        # For new master, all common records should be uploaded (samples 1 and 2)
        upload_data = call_args["data"]
        assert len(upload_data) == 2
        assert set(upload_data["entity:new_master_id"].tolist()) == {"sample1", "sample2"}
    
    def test_merge_with_no_matches(self, terra_merge, mock_terra_entities):
        """Test merging when there are no matching IDs."""
        # Setup no matches between tables
        mock_terra_entities.download_table.side_effect = lambda table, use_destination: (
            pd.DataFrame({"entity:sample_id": ["sampleA", "sampleB"]}) if table == "sample" else
            pd.DataFrame({"entity:sample_metadata_id": ["sampleC", "sampleD"]}) if table == "sample_metadata" else
            pd.DataFrame()
        )
        
        result = terra_merge.merge_and_update_master(
            primary_table="sample",
            secondary_table="sample_metadata", 
            master_table="sample_master"
        )
        
        # Should return empty DataFrame if no matches
        assert result.empty
        # Verify upload was not called
        mock_terra_entities.upload_entities.assert_not_called()
    
    def test_merge_with_custom_keys(self, terra_merge, mock_terra_entities):
        """Test merging with custom key names."""
        # Setup custom key names
        mock_terra_entities.download_table.side_effect = lambda table, use_destination: (
            pd.DataFrame({"custom_primary_id": ["sample1", "sample2"]}) if table == "sample" else
            pd.DataFrame({"custom_secondary_id": ["sample1", "sample2"]}) if table == "sample_metadata" else
            pd.DataFrame({"custom_master_id": ["sample1"]})
        )
        
        result = terra_merge.merge_and_update_master(
            primary_table="sample",
            secondary_table="sample_metadata", 
            master_table="sample_master",
            primary_key="custom_primary_id",
            secondary_key="custom_secondary_id",
            master_key="custom_master_id"
        )
        
        # Verify keys were used correctly
        mock_terra_entities.upload_entities.assert_called_once()
        call_args = mock_terra_entities.upload_entities.call_args[1]
        assert call_args["entity_identifier_column"] == "custom_master_id"
    
    def test_merge_with_field_filtering(self, terra_merge, mock_terra_entities):
        """Test merging with field inclusion/exclusion."""
        result = terra_merge.merge_and_update_master(
            primary_table="sample",
            secondary_table="sample_metadata", 
            master_table="sample_master",
            fields_to_include=["entity:sample_id", "attribute1", "attribute3"],
            fields_to_exclude=["attribute2", "attribute4"]
        )
        
        # Verify upload was called with filtered fields
        mock_terra_entities.upload_entities.assert_called_once()
        call_args = mock_terra_entities.upload_entities.call_args[1]
        upload_data = call_args["data"]
        
        # Should include only the specified fields
        assert "attribute1" in upload_data.columns
        assert "attribute3" in upload_data.columns
        assert "attribute2" not in upload_data.columns
        assert "attribute4" not in upload_data.columns
    
    def test_merge_with_no_new_records(self, terra_merge, mock_terra_entities):
        """Test merging when all records already exist in master."""
        # Setup so all common records are already in master
        mock_terra_entities.download_table.side_effect = lambda table, use_destination: (
            pd.DataFrame({"entity:sample_id": ["sample1", "sample2"]}) if table == "sample" else
            pd.DataFrame({"entity:sample_metadata_id": ["sample1", "sample2"]}) if table == "sample_metadata" else
            pd.DataFrame({"entity:sample_master_id": ["sample1", "sample2"]})
        )
        
        result = terra_merge.merge_and_update_master(
            primary_table="sample",
            secondary_table="sample_metadata", 
            master_table="sample_master"
        )
        
        # Should return empty DataFrame if no new records
        assert result.empty
        # Verify upload was not called
        mock_terra_entities.upload_entities.assert_not_called()
    
    def test_upload_to_master(self, terra_merge, mock_terra_entities):
        """Test the upload_to_master method directly."""
        test_data = pd.DataFrame({
            "entity:sample_master_id": ["test1", "test2"],
            "attribute1": ["value1", "value2"]
        })
        
        result = terra_merge.upload_to_master(
            merged_df=test_data,
            master_table="sample_master",
            id_column="entity:sample_master_id"
        )
        
        # Verify upload was called correctly
        mock_terra_entities.upload_entities.assert_called_once()
        call_args = mock_terra_entities.upload_entities.call_args[1]
        assert call_args["target"] == "sample_master"
        assert call_args["entity_identifier_column"] == "entity:sample_master_id"
        pd.testing.assert_frame_equal(call_args["data"], test_data)
