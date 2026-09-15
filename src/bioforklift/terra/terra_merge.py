import sys
import pandas as pd
from typing import List, Any, Optional
from bioforklift.forklift_logging import setup_logger
from .terra_entities import TerraEntities

logger = setup_logger(__name__)


class TerraMerge:
    """
    Class to handle merging of Terra datatables.
    This class is used to identify samples present in multiple tables,
    merge their attributes, and prepare the result for upload to a master table.
    """

    def __init__(self, terra_entities_client: TerraEntities):
        """
        Initialize the TerraMerge class.

        Args:
            terra_client: An initialized Terra client
        """
        self.terra_entities = terra_entities_client

    def merge_and_update_master(
        self,
        primary_table: str,
        secondary_table: str,
        master_table: str,
        primary_key: Optional[str] = None,
        secondary_key: Optional[str] = None,
        master_key: Optional[str] = None,
        fields_to_include: Optional[List[str]] = None,
        fields_to_exclude: Optional[List[str]] = None,
        use_destination: bool = False,
    ) -> pd.DataFrame:
        """
        Merge two tables and update a master table with new records.

        Args:
            primary_table: Primary table name (e.g., "sample")
            secondary_table: Secondary table name (e.g., "sample_metadata")
            master_table: Master table to upload merged results to (e.g., "sample_master")
            primary_key: Key field in primary table (auto-detected if None)
            secondary_key: Key field in secondary table (auto-detected if None)
            master_key: Key field for upload to master table (auto-detected if None)
            fields_to_include: List of specific fields to include in merge
            fields_to_exclude: List of fields to exclude from merge
            use_destination: Whether to use destination workspace

        Returns:
            DataFrame with newly added records
        """
        logger.info(
            f"Starting merge of {primary_table} and {secondary_table} for update to {master_table}"
        )

        # Download the primary and secondary tables , usually will be something like a sample table
        # With reads and a metadata table
        primary_df = self.terra_entities.download_table(
            primary_table, use_destination=use_destination
        )
        logger.info(
            f"Downloaded primary table: {primary_table} with {len(primary_df)} records"
        )

        secondary_df = self.terra_entities.download_table(
            secondary_table, use_destination=use_destination
        )
        logger.info(
            f"Downloaded secondary table: {secondary_table} with {len(secondary_df)} records"
        )

        try:
            master_df = self.terra_entities.download_table(
                master_table, use_destination=use_destination
            )
            logger.info(
                f"Downloaded master table: {master_table} with {len(master_df)} records"
            )
        except Exception as exc:
            # If master table doesn't exist or is empty, create an empty DataFrame, e.g., for new uploads
            logger.info(
                f"Master table {master_table} not found or empty, will create new"
            )
            master_df = pd.DataFrame()

        # Auto-enforce keys if not provided, we can do this automatically from the entity ids
        if primary_key is None:
            primary_key = f"entity:{primary_table}_id"
            logger.info(f"Using detected primary key: {primary_key}")

        if secondary_key is None:
            secondary_key = f"entity:{secondary_table}_id"
            logger.info(f"Using detected secondary key: {secondary_key}")

        if master_key is None:
            # For master table, we need to ensure the key follows Terra conventions
            master_key = f"entity:{master_table}_id"
            if not master_df.empty and master_key not in master_df.columns:
                # If master table exists but doesn't have expected key, try to detect it
                sys.exit(
                    f"Master table {master_table} does not contain expected key {master_key}"
                )

        # Merge primary and secondary tables where both ids are present
        logger.info(f"Merging tables on {primary_key}={secondary_key}")

        # Get the set of ids from both tables
        primary_ids = set(primary_df[primary_key].dropna())
        secondary_ids = set(secondary_df[secondary_key].dropna())

        # Now we need to find the intersection of these two sets
        common_ids = primary_ids.intersection(secondary_ids)
        logger.info(f"Found {len(common_ids)} sample IDs present in both tables")

        if not common_ids:
            logger.warning(
                "No matching records found between primary and secondary tables"
            )
            return pd.DataFrame()

        # We need to make sure we only keep the records in both tables that match
        primary_filtered = primary_df[primary_df[primary_key].isin(common_ids)]
        secondary_filtered = secondary_df[secondary_df[secondary_key].isin(common_ids)]

        # Prepare for merge by renaming the secondary key to match primary
        if primary_key != secondary_key:
            secondary_filtered = secondary_filtered.rename(
                columns={secondary_key: primary_key}
            )

        # Determine fields to include/exclude
        all_fields = list(
            set(primary_filtered.columns).union(set(secondary_filtered.columns))
        )

        if fields_to_include:
            # If specific fields are included, use only those that exist
            fields_to_use = [
                field for field in fields_to_include if field in all_fields
            ]
            # Always include the primary key
            if primary_key not in fields_to_use:
                fields_to_use.append(primary_key)

            # Filter primary and secondary dataframes to only include specified fields
            primary_fields = [
                field for field in fields_to_use if field in primary_filtered.columns
            ]
            secondary_fields = [
                field for field in fields_to_use if field in secondary_filtered.columns
            ]

            # Ensure primary key is included in both dataframes for merge
            if primary_key not in primary_fields:
                primary_fields.append(primary_key)
            if primary_key not in secondary_fields:
                secondary_fields.append(primary_key)

            primary_filtered = primary_filtered[primary_fields]
            secondary_filtered = secondary_filtered[secondary_fields]
        else:
            # Use all fields except excluded
            fields_to_use = all_fields
            if fields_to_exclude:
                # Apply exclusions , filter dataframes to exclude specified fields
                primary_fields = [
                    field
                    for field in primary_filtered.columns
                    if field not in fields_to_exclude or field == primary_key
                ]
                secondary_fields = [
                    field
                    for field in secondary_filtered.columns
                    if field not in fields_to_exclude or field == primary_key
                ]

                primary_filtered = primary_filtered[primary_fields]
                secondary_filtered = secondary_filtered[secondary_fields]

        # Perform merge - use outer join to ensure all records from both tables are included
        # Only keep records that appear in both tables
        merged_df = pd.merge(
            primary_filtered, secondary_filtered, on=primary_key, how="inner"
        )

        logger.info(
            f"Merged result contains {len(merged_df)} rows and {len(merged_df.columns)} columns"
        )

        if not master_df.empty:
            # Get existing ids from master table
            if master_key in master_df.columns:
                master_ids = set(master_df[master_key].dropna())
            else:
                master_ids = set()

            # Find ids in merged data not already in master
            new_ids = common_ids - master_ids

            if not new_ids:
                logger.info("No new records to add to master table")
                return pd.DataFrame()  # Return empty DataFrame

            logger.info(f"Found {len(new_ids)} new records to add to master table")

            # Filter to only new records
            merged_df = merged_df[merged_df[primary_key].isin(new_ids)]

        # Now we need to ensure the master table has the correct key (entity id)
        if primary_key != master_key:
            merged_df = merged_df.rename(columns={primary_key: master_key})

        # And finally now we can upload the merged data to the master table
        if not merged_df.empty:
            logger.info(f"Uploading {len(merged_df)} new records to {master_table}")
            uploaded_df = self.upload_to_master(
                merged_df=merged_df,
                master_table=master_table,
                id_column=master_key,
                use_destination=use_destination,
            )
            return uploaded_df
        else:
            logger.info("No records to upload after filtering")
            return pd.DataFrame()

    def upload_to_master(
        self,
        merged_df: pd.DataFrame,
        master_table: str,
        id_column: str,
        use_destination: bool = False,
    ) -> pd.DataFrame:
        """
        Upload merged data to master table.

        Args:
            merged_df: DataFrame with merged data
            master_table: Name of master table
            id_column: Column to use as entity ID
            use_destination: Whether to use destination workspace

        Returns:
            DataFrame with upload results
        """
        upload_df = merged_df.copy()

        return self.terra_entities.upload_entities(
            data=upload_df,
            target=master_table,
            entity_identifier_column=id_column,
            use_destination=use_destination,
        )
