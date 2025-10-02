import os
from pathlib import Path
from bioforklift.terra2bq import Terra2BQ
from bioforklift.bigquery import BigQuery
from bioforklift.alerting import SlackAlert, SlackNotifier, TerraSummary

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
    # results = terra2bq.process_all_configs(destination_bucket="theiagen-public-files/terra/test", preserve_path_structure=True)
    # Summarize results
    success_count = sum(1 for r in results if r.status == "success")
    print(f"Completed processing {len(results)} configurations ({success_count} successful)")
    
checkout_workflow_status_update = False
if checkout_workflow_status_update:
    print("\n=== Terra2BQ Workflow Status Synchronization ===")


    # Perform actual update
    print("\nPerforming actual workflow status update...")
    update_results = terra2bq.update_workflow_status(
        days_back=30,  
        batch_size=100,
        update_bigquery=True
    )

    # Summarize results
    print(f"\nWorkflow Status Update Summary:")
    print(f"- Status: {update_results.status}")
    print(f"- Records updated in destination: {update_results.workflow_count}")
    print(f"- Configurations processed: {update_results.config_id}")
    print(f"- Submissions processed: {update_results.submission_id}")

    if update_results.failed_updates:
        print(f"- Failed updates: {len(update_results.failed_updates)}")

    print("\n=== Complete ===")
     
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
    sync_results = terra2bq.sync_metadata(days_back=60, update_bigquery=True, update_destination=True, overwrite_metadata=True)

    # Summarize sync results
    print(f"\nSync Summary:")
    print(f"- Status: {sync_results.status}")
    print(f"- Records synced: {sync_results.destination_updated_count}")
    print(f"- Configs processed: {sync_results.processed_configs}")

alerting = False
if alerting:
    # Set up alerting
    # Initialize Slack notifier and alert system
    slack_notifier = SlackNotifier(token=os.environ["SLACK_TOKEN"], channel_id=os.environ["SLACK_CHANNEL"])
    alert = SlackAlert(notifier=slack_notifier)
    
    print("Sending a test alert...")
    response = alert.send_message(f"Hello, this is a test message from bioforklift")
    print(f"Message sent: {response.get('ok', False)}")
    
    print("Generating and sending hourly summary...")
    response = alert.send_hourly_summary(terra2bq, hours_back=1)
    if response.get('status') == 'skipped':
        print(f"Hourly summary skipped: {response.get('reason')}")
    else:
        print(f"Hourly summary sent: {response.get('ok', False)}")
    
    # Generate and send a daily summary
    print("Generating and sending daily summary...")
    response = alert.send_daily_summary(terra2bq)
    print(f"Daily summary sent: {response.get('ok', False)}")
    
    # Generate and send a workflow summary for the last 7 days
    print("Generating and sending workflow summary...")
    response = alert.send_workflow_summary(terra2bq, days_back=7)
    print(f"Workflow summary sent: {response.get('ok', False)}")
    
    print("Done!")