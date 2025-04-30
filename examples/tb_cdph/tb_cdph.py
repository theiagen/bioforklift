from pathlib import Path
from bioforklift.bigquery import BigQuery
from bioforklift.terra2bq import Terra2BQ, ConfigBuilder
from filter_samples import filter_samples

bq = BigQuery(project="general-theiagen", dataset="automation_test")

# Create table, commented out after first run
config_table_exists = bq.table_exists("tb_configs")
if not config_table_exists:
    table_create_res = bq.create_table(
        table_name="tb_configs", schema_yaml="config.yaml"
    )
    config_ops = bq.get_config_operations(
        table_name="tb_configs", config_schema_yaml="config.yaml"
    )
    new_configs = config_ops.create_configs_from_directory(directory_path=Path("configs"))
    print(f"Created new configs: {len(new_configs)}")
else:
    print("Table already exists")
    

samples_table_exists = bq.table_exists("tb_samples")
if not samples_table_exists:
    table_create_res = bq.create_table(
        table_name="tb_samples", schema_yaml="samples.yaml"
    )
else:
    print("Table already exists")


run_process = True
if run_process:
    terra2bq = Terra2BQ(
            bigquery_project="general-theiagen",
            bigquery_dataset="automation_test",
            samples_table="tb_samples",
            configs_table="tb_configs",
            samples_schema_yaml=Path("samples.yaml"),
            configs_schema_yaml=Path("config.yaml"),
            project_timezone="America/Los_Angeles",
            metadata_cleanup_fn=filter_samples,
        )

    processed_result = terra2bq.process_all_configs(batch_size=3, skip_transferred=True)

sync_status = False
if sync_status:
    print("\n=== Terra2BQ Workflow Status Synchronization ===")

    # First run a dry run to see what would be updated
    print("Performing workflow status dry run...")
    update_status_run_results = terra2bq.update_workflow_status(
        days_back=2,
        batch_size=100, 
    )

    print(f"Dry run complete - would update {update_status_run_results['updated_count']} records")
    

build_config = False
if build_config:
    config_builder = ConfigBuilder(
            bigquery_project="general-theiagen",
            bigquery_dataset="automation_test",
            bigquery_config_table_name="tb_configs",
            bigquery_config_schema_yaml="config.yaml",
            template_config_path=Path("configs/WGSDST_2025-04-09_AS.json"),
            terra_source_project="cdph-terrabio-taborda-manual",
            terra_source_workspace="CDPH_Automation_Development",
        )

    wgsdst_pattern = r"^WGSDST_\d{4}-\d{2}-\d{2}_[A-Z]{2}$"

    list_all_datatables = config_builder.list_terra_datatables()
    print(f"List of all datatables: {list_all_datatables}")

    matching_entities = config_builder.get_new_entity_types(table_pattern=wgsdst_pattern)
    print(f"Matching entities: {matching_entities}")

    overwrite_dict = {
        "transferred": True
    }
    print("\nBuilding configurations for matching WGS datasets...")
    created_configs = config_builder.build_new_configs(
        table_pattern=wgsdst_pattern,
        override_values=overwrite_dict,
    )

    print(f"Created {len(created_configs)} new configurations for WGS datasets")

    if created_configs:
        print("\nExample configuration created:")
        print(created_configs[0])
    