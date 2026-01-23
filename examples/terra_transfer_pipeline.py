from bioforklift.terra import TerraToTerraTransfer, TerraClient, TransferStatus
from bioforklift.terra2bq import Terra2BQ

# Step 1: Create client with source and destination workspaces
client = TerraClient(
    source_workspace="CDPH_Bioinformatics_Development",
    source_project="cdph-terrabio-taborda-manual",
    destination_workspace="CDPH_Automation_Development",
    destination_project="cdph-terrabio-taborda-manual",
)

# Step 2: Transfer samples between Terra workspaces
# Identifier columns default to {table_name}_id (e.g., analyzed_sample_id, sample_id)
transfer = TerraToTerraTransfer(
    client=client,
    source_table_name="freyja_sc2",
    destination_table_name="master_sample",
)
result = transfer.transfer()

print(f"Transfer status: {result.status.value}")
print(f"Transferred {result.transferred_count} samples")

# # Step 3: Sync transferred samples to BigQuery
# if result.status == TransferStatus.SUCCESS and result.transferred_ids:
#     terra2bq = Terra2BQ(
#         bigquery_project="your-gcp-project",
#         bigquery_dataset="your_dataset",
#         samples_schema_yaml="example_sample_schema.yaml",
#         configs_schema_yaml="example_config_schema.yaml",
#         source_workspace="production-workspace",
#         source_project="dest-billing-project",
#         source_datatable="sample",
#     )
#     terra2bq.download_from_terra_to_bigquery()
#     print("BigQuery sync complete")
