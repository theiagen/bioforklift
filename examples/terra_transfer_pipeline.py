"""
Terra-to-Terra Data Promotion Pipeline

Transfers samples from a source workspace to a destination workspace,
then syncs to BigQuery.
"""

from bioforklift.terra import TerraToTerraTransfer, TransferStatus
from bioforklift.terra2bq import Terra2BQ

# Step 1: Transfer samples between Terra workspaces
transfer = TerraToTerraTransfer.from_config("terra_transfer_config.yaml")
result = transfer.transfer()

print(f"Transfer status: {result.status.value}")
print(f"Transferred {result.transferred_count} samples")

# Step 2: Sync transferred samples to BigQuery
if result.status == TransferStatus.SUCCESS and result.transferred_ids:
    terra2bq = Terra2BQ(
        bigquery_project="your-gcp-project",
        bigquery_dataset="your_dataset",
        samples_schema_yaml="example_sample_schema.yaml",
        configs_schema_yaml="example_config_schema.yaml",
        source_workspace="destination-workspace",
        source_project="dest-billing-project",
        source_datatable="sample",
    )
    terra2bq.download_from_terra_to_bigquery()
    print("BigQuery sync complete")
