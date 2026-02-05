from typing import Callable, Optional, Set
import pandas as pd
from bioforklift.forklift_logging import setup_logger
from bioforklift.terra.client import TerraClient
from bioforklift.terra.terra_entities import TerraEntities
from bioforklift.terra.models import TransferResult, TransferStatus
from bioforklift.terra.exceptions import (
    TerraTransferSourceError,
    TerraTransferUploadError,
    TerraNotFoundError,
)

logger = setup_logger(__name__)


class TerraToTerraTransfer:
    """Transfer entities between Terra workspaces with deduplication."""

    def __init__(
        self,
        client: TerraClient,
        source_table_name: str,
        destination_table_name: str,
        source_identifier_column: Optional[str] = None,
        destination_identifier_column: Optional[str] = None,
        batch_size: int = 500,
        transform: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = None,
    ):
        """
        Initialize TerraToTerraTransfer.

        Args:
            client: TerraClient configured with source and destination workspaces
            source_table_name: Name of the entity table in the source workspace
            destination_table_name: Name of the entity table in the destination workspace
            source_identifier_column: Column used to identify samples in source table.
                Defaults to {source_table_name}_id (Terra convention).
            destination_identifier_column: Column used to identify samples in destination table.
                Defaults to {destination_table_name}_id (Terra convention).
            batch_size: Number of entities per upload batch (default 500)
            transform: Optional callable to transform the DataFrame before upload.
                Receives the filtered DataFrame (new samples only) and should return
                a transformed DataFrame. Use this to filter rows, drop columns,
                or modify values before upload.
        """
        self.client = client
        self.entities = TerraEntities(client)
        self.source_table_name = source_table_name
        self.destination_table_name = destination_table_name
        self.source_identifier_column = source_identifier_column or f"entity:{source_table_name}_id"
        self.destination_identifier_column = destination_identifier_column or f"entity:{destination_table_name}_id"
        self.batch_size = batch_size
        self.transform = transform

    def get_new_sample_ids(self) -> Set[str]:
        """
        Compare source and destination tables to find new sample IDs.

        Returns:
            Set of sample IDs that exist in source but not in destination

        Raises:
            TerraTransferSourceError: If source table cannot be accessed or identifier column is missing
        """

        # Download source table (only identifier column needed for comparison)
        logger.info(f"Fetching sample IDs from source workspace")
        try:
            source_df = self.entities.download_table(
                entity_type=self.source_table_name,
                attributes=[self.source_identifier_column],
                use_destination=False
            )
        except TerraNotFoundError as e:
            raise TerraTransferSourceError(
                f"Source table '{self.source_table_name}' not found in workspace "
                f"'{self.client.source_project}/{self.client.source_workspace}'"
            ) from e
        except Exception as e:
            raise TerraTransferSourceError(
                f"Failed to access source table '{self.source_table_name}': {e}"
            ) from e

        if self.source_identifier_column not in source_df.columns:
            raise TerraTransferSourceError(
                f"Identifier column '{self.source_identifier_column}' not found in source table. "
                f"Available columns: {list(source_df.columns)}"
            )

        # Download destination table (may not exist yet)
        logger.info(f"Fetching sample IDs from destination workspace")
        try:
            dest_df = self.entities.download_table(
                entity_type=self.destination_table_name,
                attributes=[self.destination_identifier_column],
                use_destination=True
            )
        except TerraNotFoundError:
            logger.info(f"Destination table '{self.destination_table_name}' not found, treating as empty")
            dest_df = pd.DataFrame(columns=[self.destination_identifier_column])
        except Exception as e:
            logger.warning(f"Could not access destination table, treating as empty: {e}")
            dest_df = pd.DataFrame(columns=[self.destination_identifier_column])

        # Extract IDs
        source_ids = set(source_df[self.source_identifier_column].dropna().astype(str).tolist())
        dest_ids = set(dest_df[self.destination_identifier_column].dropna().astype(str).tolist()) if self.destination_identifier_column in dest_df.columns else set()
        new_ids = source_ids - dest_ids

        logger.info(f"Found {len(source_ids)} samples in source, {len(dest_ids)} in destination, {len(new_ids)} new")

        return new_ids

    def transfer(self) -> TransferResult:
        """
        Execute the transfer from source to destination workspace.

        Returns:
            TransferResult with status and details of the transfer

        Raises:
            TerraTransferSourceError: If source table cannot be accessed
            TerraTransferUploadError: If upload to destination fails
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
        try:
            source_df = self.entities.download_table(
                entity_type=self.source_table_name,
                use_destination=False
            )
        except Exception as e:
            raise TerraTransferSourceError(
                f"Failed to download full source data: {e}"
            ) from e

        # Filter to only new samples
        samples_to_transfer = source_df[source_df[self.source_identifier_column].isin(new_ids)].copy()

        logger.info(f"Filtered to {len(samples_to_transfer)} samples for transfer")

        # Apply optional transform
        if self.transform is not None:
            samples_to_transfer = self.transform(samples_to_transfer)
            logger.info(f"After transform: {len(samples_to_transfer)} samples remaining")

            if samples_to_transfer.empty:
                logger.info("No samples remaining after transform")
                return TransferResult(
                    status=TransferStatus.NO_NEW_SAMPLES,
                    message="No samples remaining after transform"
                )

        # Rename source ID column to destination ID column for upload
        samples_to_transfer = samples_to_transfer.rename(columns={self.source_identifier_column: self.destination_identifier_column})

        # Upload to destination
        try:
            self.entities.upload_entities(
                data=samples_to_transfer,
                target=self.destination_table_name,
                entity_identifier_column=self.destination_identifier_column,
                use_destination=True
            )
        except Exception as e:
            logger.error(f"Failed to upload samples to destination: {e}")
            raise TerraTransferUploadError(
                f"Failed to upload {len(samples_to_transfer)} samples to destination "
                f"'{self.client.destination_project}/{self.client.destination_workspace}': {e}"
            ) from e

        transferred_ids = samples_to_transfer[self.destination_identifier_column].tolist()
        logger.info(f"Successfully transferred {len(transferred_ids)} samples")

        return TransferResult(
            status=TransferStatus.SUCCESS,
            transferred_ids=transferred_ids,
            message=f"Successfully transferred {len(transferred_ids)} samples"
        )
