from pathlib import Path
from forklift.terra2bq import Terra2BQ
from forklift.bigquery import BigQuery

bq = BigQuery(project="general-theiagen", dataset="automation_test")

# Create table, commented out after first run
table_exists = bq.table_exists("configs")
if not table_exists:
    table_create_res = bq.create_table(
        table_name="configs", schema_yaml="example_config_schema.yaml"
    )
    config_ops = bq.get_config_operations(
        table_name="configs", config_schema_yaml="example_config_schema.yaml"
    )
    new_config = config_ops.create_config("example_configs/test_config.json")
    print(f"Created new config with ID: {new_config.get('id')}")
else:
    print("Table already exists")

terra2bq = Terra2BQ(
        bigquery_project="general-theiagen",
        bigquery_dataset="automation_test",
        samples_table="samples",
        configs_table="configs",
        samples_schema_yaml=Path("example_sample_schema.yaml"),
        configs_schema_yaml=Path("example_config_schema.yaml"),
        project_timezone="America/Los_Angeles",
    )

results = terra2bq.process_all_configs()
    
# Summarize results
success_count = sum(1 for r in results if r.get("status") == "success")
print(f"Completed processing {len(results)} configurations ({success_count} successful)")