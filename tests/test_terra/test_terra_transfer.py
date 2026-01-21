# tests/test_terra/test_terra_transfer.py
import pytest
import pandas as pd
from unittest.mock import Mock
from bioforklift.terra.models import TransferResult, TransferStatus
from bioforklift.terra.terra_transfer import TerraToTerraTransfer


@pytest.fixture
def mock_terra_client():
    client = Mock()
    client.source_workspace = "source-ws"
    client.source_project = "source-proj"
    client.destination_workspace = "dest-ws"
    client.destination_project = "dest-proj"
    return client


class TestTerraToTerraTransfer:
    def test_init_with_defaults(self, mock_terra_client):
        """Test TerraToTerraTransfer initialization with default identifier columns"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            source_table_name="analyzed_sample",
            destination_table_name="sample",
        )

        assert transfer.source_table_name == "analyzed_sample"
        assert transfer.destination_table_name == "sample"
        # Defaults to {table_name}_id
        assert transfer.source_identifier_column == "analyzed_sample_id"
        assert transfer.destination_identifier_column == "sample_id"
        assert transfer.batch_size == 500  # default

    def test_init_with_custom_identifiers(self, mock_terra_client):
        """Test TerraToTerraTransfer initialization with custom identifier columns"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            source_table_name="analyzed_sample",
            destination_table_name="sample",
            source_identifier_column="custom_source_id",
            destination_identifier_column="custom_dest_id",
        )

        assert transfer.source_identifier_column == "custom_source_id"
        assert transfer.destination_identifier_column == "custom_dest_id"

    def test_get_new_sample_ids_all_new(self, mock_terra_client):
        """Test finding new samples when destination is empty"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            source_table_name="analyzed_sample",
            destination_table_name="sample",
        )

        # Mock source data with source table's ID column
        source_df = pd.DataFrame({
            "entity:analyzed_sample_id": ["s1", "s2", "s3"],
            "value": ["a", "b", "c"]
        })

        # Mock empty destination with destination table's ID column
        dest_df = pd.DataFrame(columns=["entity:sample_id", "value"])

        # Mock the entities.download_table method
        transfer.entities.download_table = Mock(side_effect=[source_df, dest_df])

        new_ids = transfer.get_new_sample_ids()

        assert new_ids == {"s1", "s2", "s3"}

    def test_get_new_sample_ids_some_existing(self, mock_terra_client):
        """Test finding new samples when some already exist in destination"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            source_table_name="analyzed_sample",
            destination_table_name="sample",
        )

        # Mock source data
        source_df = pd.DataFrame({
            "entity:analyzed_sample_id": ["s1", "s2", "s3"],
            "value": ["a", "b", "c"]
        })

        # Mock destination with s1 already present
        dest_df = pd.DataFrame({
            "entity:sample_id": ["s1"],
            "value": ["a"]
        })

        transfer.entities.download_table = Mock(side_effect=[source_df, dest_df])

        new_ids = transfer.get_new_sample_ids()

        assert new_ids == {"s2", "s3"}

    def test_get_new_sample_ids_none_new(self, mock_terra_client):
        """Test when all samples already exist in destination"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            source_table_name="analyzed_sample",
            destination_table_name="sample",
        )

        source_df = pd.DataFrame({
            "entity:analyzed_sample_id": ["s1", "s2"],
            "value": ["a", "b"]
        })

        dest_df = pd.DataFrame({
            "entity:sample_id": ["s1", "s2"],
            "value": ["a", "b"]
        })

        transfer.entities.download_table = Mock(side_effect=[source_df, dest_df])

        new_ids = transfer.get_new_sample_ids()

        assert new_ids == set()

    def test_transfer_success(self, mock_terra_client):
        """Test successful transfer of new samples"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            source_table_name="analyzed_sample",
            destination_table_name="sample",
        )

        # Mock source data (full table with all columns)
        source_df = pd.DataFrame({
            "entity:analyzed_sample_id": ["s1", "s2", "s3"],
            "col1": ["a", "b", "c"],
            "col2": [1, 2, 3]
        })

        # Mock get_new_sample_ids to return s2, s3 as new
        transfer.get_new_sample_ids = Mock(return_value={"s2", "s3"})

        # Mock download_table for full source data
        transfer.entities.download_table = Mock(return_value=source_df)

        # Mock upload_entities
        transfer.entities.upload_entities = Mock()

        result = transfer.transfer()

        assert result.status == TransferStatus.SUCCESS
        assert set(result.transferred_ids) == {"s2", "s3"}
        assert result.transferred_count == 2

        # Verify upload was called with renamed column
        upload_call = transfer.entities.upload_entities.call_args
        uploaded_df = upload_call.kwargs["data"]
        assert "entity:sample_id" in uploaded_df.columns
        assert "entity:analyzed_sample_id" not in uploaded_df.columns

    def test_transfer_no_new_samples(self, mock_terra_client):
        """Test transfer when no new samples exist"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            source_table_name="analyzed_sample",
            destination_table_name="sample",
        )

        transfer.get_new_sample_ids = Mock(return_value=set())

        result = transfer.transfer()

        assert result.status == TransferStatus.NO_NEW_SAMPLES
        assert result.transferred_count == 0

    def test_transfer_empty_source(self, mock_terra_client):
        """Test transfer when source table is empty"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            source_table_name="analyzed_sample",
            destination_table_name="sample",
        )

        # Empty source
        transfer.get_new_sample_ids = Mock(return_value=set())

        result = transfer.transfer()

        assert result.status == TransferStatus.NO_NEW_SAMPLES


class TestTerraModuleExports:
    def test_terra_transfer_importable(self):
        """Test TerraToTerraTransfer is importable from terra module"""
        from bioforklift.terra import TerraToTerraTransfer
        assert TerraToTerraTransfer is not None

    def test_transfer_models_importable(self):
        """Test transfer models are importable from terra module"""
        from bioforklift.terra import TransferResult, TransferStatus
        assert TransferResult is not None
        assert TransferStatus is not None


class TestTransferResult:
    def test_transfer_result_success(self):
        """Test creating a successful transfer result"""
        result = TransferResult(
            status=TransferStatus.SUCCESS,
            transferred_ids=["sample1", "sample2"],
            skipped_ids=["sample3"],
            message="Transferred 2 samples"
        )

        assert result.status == TransferStatus.SUCCESS
        assert result.transferred_count == 2
        assert result.skipped_count == 1
        assert len(result.transferred_ids) == 2
