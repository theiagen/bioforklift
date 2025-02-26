# This will be the integration point for the Terra2BQ pipeline

# What we will need to accomplish in this class
# 1. Grab data from Source Terra Data Table
# 2. Load data into BigQuery for unique sample IDs
# 3. Upload data to source Terra Data Table
# 5. Create a Set name for the uploaded data & create Set in Terra
# 6. Update the BigQuery records to indicate they've been uploaded to Terra with the Set name
# 7. Submit a workflow to Terra for data in that Set
# 8. Update the BigQuery records to indicate the workflow submission status

# Other Workflow
#1. Sync metadata from Terra source table to Bigquery to Terra target table