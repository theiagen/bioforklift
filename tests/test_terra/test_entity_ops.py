import pytest
from unittest.mock import Mock
from forklift.terra import TerraEntities
import pandas as pd


@pytest.fixture
def mock_terra_client():
    client = Mock()
    return client


@pytest.fixture
def mock_response():
    response = Mock()
    # Mock the iter_content method to return some test data
    response.iter_content.return_value = [
        b"entity_id\tvalue\n",
        b"sample1\ttest1\n",
        b"sample2\ttest2\n",
    ]
    return response


@pytest.fixture
def data_ops(mock_terra_client):
    return TerraEntities(mock_terra_client)


class TestDownloadTable:
    def test_download_table_basic(self, data_ops, mock_terra_client, mock_response):
        """Test basic table download without attributes"""
        # Setup mock response
        mock_terra_client._http_request.return_value = mock_response

        df = data_ops.download_table("sample")

        # Verify correct request was made
        mock_terra_client._http_request.assert_called_once_with(
            "GET", "entities/sample/tsv", params={"model": "flexible"}, stream=True
        )

        # Verify iter_content was called with correct chunk size
        mock_response.iter_content.assert_called_with(chunk_size=8192)

        # Verify DataFrame content
        assert len(df) == 2
        assert "entity_id" in df.columns
        assert "value" in df.columns

    def test_download_table_with_destination(
        self, data_ops, mock_terra_client, mock_response, tmp_path
    ):
        """Test table download with file destination"""
        mock_terra_client._http_request.return_value = mock_response

        destination = tmp_path / "test.tsv"
        df = data_ops.download_table("sample", destination=destination)

        # Verify file was created
        assert destination.exists()

        # Verify DataFrame content
        assert len(df) == 2
        assert "entity_id" in df.columns
        assert "value" in df.columns

    def test_download_table_with_attributes(
        self, data_ops, mock_terra_client, mock_response
    ):
        """Test table download with specific attributes"""
        # Setup mock response
        mock_terra_client._http_request.return_value = mock_response

        # Setup response content for these specific attributes
        mock_response.iter_content.return_value = [
            b"id\tstatus\tdate\n",
            b"sample1\tcomplete\t2024-02-13\n",
            b"sample2\tpending\t2024-02-14\n",
        ]

        # Make the actual call
        df = data_ops.download_table("sample", attributes=["id", "status", "date"])

        # Verify the request was made with correct parameters
        mock_terra_client._http_request.assert_called_once_with(
            "GET",
            "entities/sample/tsv",
            params={"model": "flexible", "attributeNames": "id,status,date"},
            stream=True,
        )

        # Verify iter_content was called with correct chunk size
        mock_response.iter_content.assert_called_with(chunk_size=8192)

        # Verify the DataFrame has the correct structure
        assert list(df.columns) == ["id", "status", "date"]
        assert len(df) == 2


class TestCreateEntitySet:
    def test_create_entity_set_basic(self, data_ops, mock_terra_client):
        """Test basic entity set creation"""
        entities = ["sample1", "sample2"]

        data_ops.create_entity_set(
            set_name="test_set", entity_type="sample", entities=entities
        )

        # Verify post request
        mock_terra_client.post.assert_called_once()
        args = mock_terra_client.post.call_args

        # Check endpoint
        assert args[0][0] == "flexibleImportEntities"

        # Check files content
        assert "files" in args[1]
        files = args[1]["files"]
        assert "entities" in files

        # Check TSV content
        tsv_content = files["entities"][1]
        assert "membership:sample_set_id" in tsv_content
        assert "sample1" in tsv_content
        assert "sample2" in tsv_content

    def test_create_entity_set_empty_list(self, data_ops):
        """Test creating set with empty entities list raises error"""
        with pytest.raises(ValueError) as exc:
            data_ops.create_entity_set(
                set_name="test_set", entity_type="sample", entities=[]
            )
        assert "No entities to add to set" in str(exc.value)

    def test_create_entity_set_strict_model(self, data_ops, mock_terra_client):
        """Test entity set creation with strict model"""
        data_ops.create_entity_set(
            set_name="test_set",
            entity_type="sample",
            entities=["sample1"],
            model="strict",
        )

        # Verify correct endpoint for strict model
        mock_terra_client.post.assert_called_once()
        assert "importEntities" in mock_terra_client.post.call_args[0][0]


class TestUpdateEntityAttributes:
    def test_update_entity_attributes_basic(self, data_ops, mock_terra_client):
        """Test basic attribute update"""
        attributes = {"status": "complete", "date": "2024-02-13"}

        data_ops.update_entity_attributes(
            entity_type="sample", entity_id="sample1", attributes=attributes
        )

        # Verify patch request
        mock_terra_client.patch.assert_called_once()
        args = mock_terra_client.patch.call_args

        # Check endpoint
        assert args[0][0] == "entities/sample/sample1"

        # Check update payload
        updates = args[1]["data"]
        assert len(updates) == 2
        assert all(update["op"] == "AddUpdateAttribute" for update in updates)
        assert any(
            update["attributeName"] == "status"
            and update["addUpdateAttribute"] == "complete"
            for update in updates
        )
        assert any(
            update["attributeName"] == "date"
            and update["addUpdateAttribute"] == "2024-02-13"
            for update in updates
        )

    def test_update_entity_attributes_empty(self, data_ops, mock_terra_client):
        """Test update with empty attributes"""
        data_ops.update_entity_attributes(
            entity_type="sample", entity_id="sample1", attributes={}
        )

        # Verify patch called with empty updates list
        mock_terra_client.patch.assert_called_once()
        assert len(mock_terra_client.patch.call_args[1]["data"]) == 0

    @pytest.mark.parametrize("attribute_value", [None, "", 0, False, [], {}])
    def test_update_entity_attributes_various_types(
        self, data_ops, mock_terra_client, attribute_value
    ):
        """Test update with various attribute value types"""
        data_ops.update_entity_attributes(
            entity_type="sample",
            entity_id="sample1",
            attributes={"test_attr": attribute_value},
        )

        # Verify patch handles different value types
        mock_terra_client.patch.assert_called_once()
        updates = mock_terra_client.patch.call_args[1]["data"]
        assert updates[0]["addUpdateAttribute"] == attribute_value


class TestUploadEntities:
    def test_upload_entities_basic(self, data_ops, mock_terra_client):
        """Test basic entity upload"""
        # Create test DataFrame
        test_data = pd.DataFrame(
            {"entity_id": ["sample1", "sample2"], "value": ["test1", "test2"]}
        )

        # Mock successful upload
        mock_terra_client.post.return_value = {"status": "success"}

        result = data_ops.upload_entities(data=test_data, target="test_table")

        # Verify correct endpoint and parameters
        mock_terra_client.post.assert_called_once()
        call_args = mock_terra_client.post.call_args

        assert call_args[0][0] == "flexibleImportEntities"
        assert call_args[1]["params"] == {
            "async": "false",
            "deleteEmptyValues": "false",
        }

        # Verify files content with renamed column
        files = call_args[1]["files"]
        assert "entities" in files
        tsv_content = files["entities"][1]
        assert "entity:test_table_id\tvalue" in tsv_content  # Check renamed column
        assert "sample1\ttest1" in tsv_content
        assert "sample2\ttest2" in tsv_content

    def test_upload_entities_empty_dataframe(self, data_ops):
        """Test upload with empty DataFrame"""
        empty_df = pd.DataFrame(columns=["entity_id", "value"])
        with pytest.raises(ValueError) as exc:
            data_ops.upload_entities(data=empty_df, target="test_table")
        assert "DataFrame has no rows" in str(exc.value)

    def test_upload_entities_with_missing_values(self, data_ops, mock_terra_client):
        """Test upload with DataFrame containing missing values"""
        test_data = pd.DataFrame(
            {"entity_id": ["sample1", "sample2"], "value": ["test1", None]}
        )

        data_ops.upload_entities(data=test_data, target="test_table", delete_empty=True)

        # Verify deleteEmptyValues parameter and column renaming
        mock_terra_client.post.assert_called_once()
        call_args = mock_terra_client.post.call_args
        params = call_args[1]["params"]
        assert params["deleteEmptyValues"] == "true"

        # Verify column renaming in TSV
        files = call_args[1]["files"]
        tsv_content = files["entities"][1]
        assert "entity:test_table_id\tvalue" in tsv_content

    def test_upload_entities_column_rename(self, data_ops, mock_terra_client):
        """Test that first column is correctly renamed to target"""
        test_data = pd.DataFrame(
            {
                "original_id": ["sample1", "sample2"],  # Different original column name
                "value": ["test1", "test2"],
            }
        )

        data_ops.upload_entities(
            data=test_data, target="participant_id"  # Different target name
        )

        # Verify column renaming
        call_args = mock_terra_client.post.call_args
        files = call_args[1]["files"]
        tsv_content = files["entities"][1]
        assert "entity:participant_id\tvalue" in tsv_content
        assert "entity:original_id" not in tsv_content