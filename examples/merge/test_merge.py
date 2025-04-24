from bioforklift.terra import Terra
import logging
from datetime import datetime, timezone, timedelta
from google.auth.transport import requests as google_requests
from google.auth.transport import requests
from google.auth import default
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials

terra = Terra(
    source_project="theiagen-training-workspaces",
    source_workspace="Theiagen_Babinski_Sandbox"
)


# Test merging two tables
primary_table = "devSamples"
secondary_table = "devSamples_metadata"
master_table = "ohio_ar_test"

# Merge the tables
merged_df = terra.merge_tables.merge_and_update_master(
    primary_table=primary_table,
    secondary_table=secondary_table,
    master_table=master_table,
    use_destination=False
)

