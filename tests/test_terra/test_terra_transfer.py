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
    def test_init(self, mock_terra_client):
        """Test TerraToTerraTransfer initialization"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            table_name="sample",
            identifier_column="sample_id"
        )

        assert transfer.table_name == "sample"
        assert transfer.identifier_column == "sample_id"
        assert transfer.batch_size == 500  # default

    def test_get_new_sample_ids_all_new(self, mock_terra_client):
        """Test finding new samples when destination is empty"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            table_name="sample",
            identifier_column="sample_id"
        )

        # Mock source data
        source_df = pd.DataFrame({
            "entity:sample_id": ["s1", "s2", "s3"],
            "value": ["a", "b", "c"]
        })

        # Mock empty destination
        dest_df = pd.DataFrame(columns=["entity:sample_id", "value"])

        # Mock the entities.download_table method
        transfer.entities.download_table = Mock(side_effect=[source_df, dest_df])

        new_ids = transfer.get_new_sample_ids()

        assert new_ids == {"s1", "s2", "s3"}

    def test_get_new_sample_ids_some_existing(self, mock_terra_client):
        """Test finding new samples when some already exist in destination"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            table_name="sample",
            identifier_column="sample_id"
        )

        # Mock source data
        source_df = pd.DataFrame({
            "entity:sample_id": ["s1", "s2", "s3"],
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
            table_name="sample",
            identifier_column="sample_id"
        )

        source_df = pd.DataFrame({
            "entity:sample_id": ["s1", "s2"],
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
            table_name="sample",
            identifier_column="sample_id"
        )

        # Mock source data (full table with all columns)
        source_df = pd.DataFrame({
            "entity:sample_id": ["s1", "s2", "s3"],
            "col1": ["a", "b", "c"],
            "col2": [1, 2, 3]
        })

        # Mock get_new_sample_ids to return s2, s3 as new
        transfer.get_new_sample_ids = Mock(return_value={"s2", "s3"})

        # Mock download_table for full source data
        transfer.entities.download_table = Mock(return_value=source_df)

        # Mock upload_entities
        transfer.entities.upload_entities = Mock(return_value=source_df)

        result = transfer.transfer()

        assert result.status == TransferStatus.SUCCESS
        assert set(result.transferred_ids) == {"s2", "s3"}
        assert result.transferred_count == 2

    def test_transfer_no_new_samples(self, mock_terra_client):
        """Test transfer when no new samples exist"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            table_name="sample",
            identifier_column="sample_id"
        )

        transfer.get_new_sample_ids = Mock(return_value=set())

        result = transfer.transfer()

        assert result.status == TransferStatus.NO_NEW_SAMPLES
        assert result.transferred_count == 0

    def test_transfer_empty_source(self, mock_terra_client):
        """Test transfer when source table is empty"""
        transfer = TerraToTerraTransfer(
            client=mock_terra_client,
            table_name="sample",
            identifier_column="sample_id"
        )

        # Empty source
        transfer.get_new_sample_ids = Mock(return_value=set())

        result = transfer.transfer()

        assert result.status == TransferStatus.NO_NEW_SAMPLES

    def test_from_config(self, tmp_path):
        """Test creating TerraToTerraTransfer from YAML config"""
        # Create temp config file
        config_content = """
source:
  workspace_namespace: "source-billing-project"
  workspace_name: "source-workspace"
  table_name: "sample"

destination:
  workspace_namespace: "dest-billing-project"
  workspace_name: "dest-workspace"
  table_name: "sample"

transfer:
  identifier_column: "sample_id"
  batch_size: 250
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_content)

        transfer = TerraToTerraTransfer.from_config(str(config_path))

        assert transfer.table_name == "sample"
        assert transfer.identifier_column == "sample_id"
        assert transfer.batch_size == 250
        assert transfer.client.source_workspace == "source-workspace"
        assert transfer.client.destination_workspace == "dest-workspace"


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
