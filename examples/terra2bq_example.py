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

# Set to true to test out processing of a single configuration
test_sample_automation = False
if test_sample_automation:
    results = terra2bq.process_all_configs()
        
    # Summarize results
    success_count = sum(1 for r in results if r.get("status") == "success")
    print(f"Completed processing {len(results)} configurations ({success_count} successful)")


    # Summarize processing results
    success_count = sum(1 for r in results if r.get("status") == "success")
    print(f"Completed processing {len(results)} configurations ({success_count} successful)")
    
checkout_workflow_status_update = False
if checkout_workflow_status_update:
    print("\n=== Terra2BQ Workflow Status Synchronization ===")

    # First run a dry run to see what would be updated
    print("Performing workflow status dry run...")
    dry_run_results = terra2bq.update_workflow_status(
        days_back=30,
        batch_size=100, 
        update_bigquery=False
    )

    print(f"Dry run complete - would update {dry_run_results['destination_updated_count']} records")
    if dry_run_results.get('workflow_states'):
        print("Workflow states that would be updated:")
        for state, count in dry_run_results['workflow_states'].items():
            print(f"  - {state}: {count}")

    # Perform actual update
    print("\nPerforming actual workflow status update...")
    update_results = terra2bq.update_workflow_status(
        days_back=30,  
        batch_size=100,
        update_bigquery=True
    )

    # Summarize results
    print(f"\nWorkflow Status Update Summary:")
    print(f"- Status: {update_results['status']}")
    print(f"- Records updated in destination: {update_results['destination_updated_count']}")
    print(f"- Configurations processed: {update_results['processed_configs']}")
    print(f"- Submissions processed: {update_results['processed_submissions']}")

    # Show workflow state distribution
    if update_results.get('workflow_states'):
        print("\nWorkflow State Distribution:")
        for state, count in update_results['workflow_states'].items():
            print(f"  - {state}: {count}")

    # Show errors if any
    if update_results.get('failed_updates'):
        print(f"\nFailed updates: {len(update_results['failed_updates'])}")
        for i, failure in enumerate(update_results['failed_updates'][:5]):
            print(f"  {i+1}. Config {failure.get('config_id')}: {failure.get('error')}")
        
        if len(update_results['failed_updates']) > 5:
            print(f"  ... and {len(update_results['failed_updates']) - 5} more failures")

    print("\n=== Complete ===")
    
check_status_summary = False
if check_status_summary:
    # Run sync metadata from Terra back to BigQuery
    summary_results = terra2bq.get_workflow_summary_all_configs()

    print(f"Generated at: {summary_results['generated_at']}")
    print(f"Configurations processed: {summary_results['configs_processed']}")

    # Print overall summary
    print("\nOverall workflow state distribution:")
    overall = summary_results["overall"]
    total = sum(overall.values())
    for state, count in sorted(overall.items()):
        percentage = (count / total) * 100 if total > 0 else 0
        print(f"  - {state}: {count} ({percentage:.1f}%)")

     
# Set to true to test out sync, added dry run to see what would be updated without actually updating -- Andrew
checkout_sync = True
if checkout_sync:
    # Run sync metadata from Terra back to BigQuery
    print("\n=== Syncing Metadata from Terra ===")

    # First do a dry run to see what would be updated
    # print("Performing dry run...")
    # dry_run_results = terra2bq.sync_metadata_from_workflows(days_back=30, update_bigquery=False, update_destination=False)
    # print(f"Dry run complete - would sync {dry_run_results['destination_updated_count']} records")

    # # Then perform the actual update
    print("\nPerforming actual sync...")
    sync_results = terra2bq.sync_metadata_from_workflows(days_back=30, update_bigquery=True, update_destination=True)

    # Summarize sync results
    print(f"\nSync Summary:")
    print(f"- Status: {sync_results['status']}")
    print(f"- Records synced: {sync_results['destination_updated_count']}")
    print(f"- Configs processed: {sync_results['processed_configs']}")