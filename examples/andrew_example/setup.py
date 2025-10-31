from pathlib import Path
from bioforklift.bigquery import BigQuery

bq = BigQuery(project="general-theiagen", dataset="automation_test", location="us-central1")

# Create table, commented out after first run
county_config_table_exists = bq.table_exists("theron_configs")
if not county_config_table_exists:
    table_create_res = bq.create_table(
        table_name="theron_configs", schema_yaml="example_config_schema.yaml"
    )
    config_ops = bq.get_config_operations(
        table_name="theron_configs", config_schema_yaml="example_config_schema.yaml"
    )
    new_configs = config_ops.create_config(Path("test_config.json"))
    print(f"Created new configs: {len(new_configs)}")
else:
    print("Table already exists")

samples_table_exists = bq.table_exists("theron_samples")
if not samples_table_exists:
    samples_table_create_res = bq.create_table(
        table_name="theron_samples", schema_yaml="theron_samples_schema.yaml"
    )
    print(f"Created samples table: {samples_table_create_res}")
else:
    print("Samples table already exists")