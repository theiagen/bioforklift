from pathlib import Path
from bioforklift.terra import TerraToTerraTransfer, TerraClient, TransferStatus
from bioforklift.terra2bq import Terra2BQ

# Configuration
SOURCE_WORKSPACE = "CDPH_Bioinformatics_Development"
SOURCE_PROJECT = "cdph-terrabio-taborda-manual"
DESTINATION_WORKSPACE = "CDPH_Automation_Development"
DESTINATION_PROJECT = "cdph-terrabio-taborda-manual"
SOURCE_TABLE = "freyja_sc2"
DESTINATION_TABLE = "master_sample"

BIGQUERY_PROJECT = "your-gcp-project"
BIGQUERY_DATASET = "your_dataset"
SAMPLES_TABLE = "samples"
CONFIGS_TABLE = "configs"
CONFIG_ID = "your-config-id"  # The config ID in BigQuery that represents this data

# Schema paths (adjust to your project structure)
SAMPLES_SCHEMA = Path("schemas/sample_schema.yaml")
CONFIGS_SCHEMA = Path("schemas/config_schema.yaml")



# Step 1: Create client with source and destination workspaces
client = TerraClient(
    source_workspace=SOURCE_WORKSPACE,
    source_project=SOURCE_PROJECT,
    destination_workspace=DESTINATION_WORKSPACE,
    destination_project=DESTINATION_PROJECT,
)

def clean_dataframe(df):
    df = df[~df['entity:freyja_sc2_id'].str.contains('PTB', na=False)]
    return df

# Step 2: Transfer unique samples between Terra workspaces
# Identifier columns default to entity:{table_name}_id (e.g., entity:freyja_sc2_id)
transfer = TerraToTerraTransfer(
    client=client,
    source_table_name=SOURCE_TABLE,
    destination_table_name=DESTINATION_TABLE,
    transform=clean_dataframe,
)
result = transfer.transfer()

print(f"Transfer status: {result.status.value}")
print(f"Transferred {result.transferred_count} samples")

# Step 3: Upload transferred samples to BigQuery with the config
