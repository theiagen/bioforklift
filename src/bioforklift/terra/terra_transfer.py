from typing import Set
from pathlib import Path
import pandas as pd
import yaml
from bioforklift.forklift_logging import setup_logger
from bioforklift.terra.client import TerraClient
from bioforklift.terra.terra_entities import TerraEntities
from bioforklift.terra.models import TransferResult, TransferStatus

logger = setup_logger(__name__)


class TerraToTerraTransfer:
    """Transfer entities between Terra workspaces with deduplication."""

    def __init__(
        self,
        client: TerraClient,
        table_name: str,
        identifier_column: str,
        batch_size: int = 500,
    ):
        """
        Initialize TerraToTerraTransfer.

        Args:
            client: TerraClient configured with source and destination workspaces
            table_name: Name of the entity table to transfer
            identifier_column: Column used to identify unique samples for deduplication
            batch_size: Number of entities per upload batch (default 500)
        """
        self.client = client
        self.entities = TerraEntities(client)
        self.table_name = table_name
        self.identifier_column = identifier_column
        self.batch_size = batch_size

    @classmethod
    def from_config(cls, config_path: str) -> "TerraToTerraTransfer":
        """
        Create TerraToTerraTransfer from a YAML config file.

        Args:
            config_path: Path to YAML configuration file

        Returns:
            Configured TerraToTerraTransfer instance
        """
        config_path = Path(config_path)

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        source = config['source']
        destination = config['destination']
        transfer_config = config.get('transfer', {})

        # Create TerraClient with source and destination
        client = TerraClient(
            source_workspace=source['workspace_name'],
            source_project=source['workspace_namespace'],
            destination_workspace=destination['workspace_name'],
            destination_project=destination['workspace_namespace'],
        )

        # Use source table_name, fallback to destination if different
        table_name = source.get('table_name', destination.get('table_name', 'sample'))

        return cls(
            client=client,
            table_name=table_name,
            identifier_column=transfer_config.get('identifier_column', 'sample_id'),
            batch_size=transfer_config.get('batch_size', 500),
        )

    def get_new_sample_ids(self) -> Set[str]:
        """
        Compare source and destination tables to find new sample IDs.

        Returns:
            Set of sample IDs that exist in source but not in destination
        """
        # Download source table (only identifier column needed for comparison)
        id_col = f"entity:{self.identifier_column}"

        logger.info(f"Fetching sample IDs from source workspace")
        source_df = self.entities.download_table(
            entity_type=self.table_name,
            attributes=[self.identifier_column],
            use_destination=False
        )

        logger.info(f"Fetching sample IDs from destination workspace")
        try:
            dest_df = self.entities.download_table(
                entity_type=self.table_name,
                attributes=[self.identifier_column],
                use_destination=True
            )
        except Exception as e:
            # Destination table might not exist yet
            logger.info(f"Destination table not found or empty, treating as empty: {e}")
            dest_df = pd.DataFrame(columns=[id_col])

        # Extract IDs
        source_ids = set(source_df[id_col].dropna().astype(str).tolist()) if id_col in source_df.columns else set()
        dest_ids = set(dest_df[id_col].dropna().astype(str).tolist()) if id_col in dest_df.columns else set()

        new_ids = source_ids - dest_ids

        logger.info(f"Found {len(source_ids)} samples in source, {len(dest_ids)} in destination, {len(new_ids)} new")

        return new_ids

    def transfer(self) -> TransferResult:
        """
        Execute the transfer from source to destination workspace.

        Returns:
            TransferResult with status and details of the transfer
        """
        # Find samples to transfer
        new_ids = self.get_new_sample_ids()

        if not new_ids:
            logger.info("No new samples to transfer")
            return TransferResult(
                status=TransferStatus.NO_NEW_SAMPLES,
                message="No new samples to transfer"
            )

        logger.info(f"Transferring {len(new_ids)} new samples")

        # Download full source data (all columns)
        source_df = self.entities.download_table(
            entity_type=self.table_name,
            use_destination=False
        )

        # Filter to only new samples
        id_col = f"entity:{self.identifier_column}"
        samples_to_transfer = source_df[source_df[id_col].isin(new_ids)].copy()

        logger.info(f"Filtered to {len(samples_to_transfer)} samples for transfer")

        transferred_ids = []
        failed_ids = []

        # Upload to destination
        try:
            self.entities.upload_entities(
                data=samples_to_transfer,
                target=self.table_name,
                entity_identifier_column=id_col,
                use_destination=True
            )
            transferred_ids = samples_to_transfer[id_col].tolist()
            logger.info(f"Successfully transferred {len(transferred_ids)} samples")
        except Exception as e:
            logger.error(f"Failed to transfer samples: {e}")
            failed_ids = list(new_ids)
            return TransferResult(
                status=TransferStatus.ERROR,
                failed_ids=failed_ids,
                message=f"Transfer failed: {str(e)}"
            )

        return TransferResult(
            status=TransferStatus.SUCCESS,
            transferred_ids=transferred_ids,
            message=f"Successfully transferred {len(transferred_ids)} samples"
        )
