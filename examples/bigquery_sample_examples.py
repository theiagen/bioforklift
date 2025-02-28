from datetime import datetime
from forklift.bigquery import BigQuery
from forklift.terra import Terra
from forklift.bigquery.utils import drop_system_value_columns
from forklift.terra.models import WorkflowConfig

# This example should start mimicing the workflow of the integration layer
# We'll start by downloading data from Terra, loading it into BigQuery, and then uploading it back to Terra
# We'll then update the BigQuery records to indicate they've been uploaded to Terra
# Finally, we'll submit a Terra workflow using the updated data

# Initialize Terra interface
terra = Terra(
    source_workspace="CDPH_Automation_Development",
    source_project="cdph-terrabio-taborda-manual",
)

terra_df = terra.entities.download_table("data")

bq = BigQuery(
    project="general-theiagen",
    dataset="automation_test",
)

bq_samples_ops = bq.get_sample_operations(
    table_name="samples", sample_schema_yaml="example_sample_schema.yaml"
)

response = bq_samples_ops.load_dataframe(df=terra_df)

# This looks messy right now, but will be cleaned up in the integration layer

# Load data into BigQuery
updated_samples_df = bq_samples_ops.get_samples_created_today()
if updated_samples_df.empty:
    print("No samples created today")
    exit(1)
print(updated_samples_df.head())

# # Drop system_value columns for Terra upload
updated_samples_dropped_sys_values_df = drop_system_value_columns(
    updated_samples_df, "example_sample_schema.yaml"
)
print(updated_samples_dropped_sys_values_df.head())

# # Upload data to Terra
uploaded_terra_df = terra.entities.upload_entities(
    data=updated_samples_dropped_sys_values_df, target="target"
)

# # Create Set name
set_name = "test_example_set"
terra.entities.create_entity_set(set_name, "target", uploaded_terra_df)

# Now we update the BigQuery records to indicate they've been uploaded to Terra
# We can use the original BigQuery dataframe to get the IDs directly
# This is more reliable since we know the column structure

id_values = updated_samples_df["id"].tolist()

# Current datetime in ISO format
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Create the updates list for bulk_update_samples
updates = [
    {"id": sample_id, "uploaded_at": current_time, "upload_source": set_name}
    for sample_id in id_values
]

# Update the records in BigQuery
update_result = bq_samples_ops.bulk_update_samples(updates)

# Print update results
print(f"Updated {update_result['updated_count']} records in BigQuery")
if update_result["failed_updates"]:
    print(f"Failed to update {len(update_result['failed_updates'])} records")
    print(update_result["failed_updates"])

# Now we can submit a Terra workflow using the updated data
example = {
    "methodConfigurationNamespace": "cdph-terrabio-taborda-manual",
    "methodConfigurationName": "TheiaCoV_Illumina_PE_PHB",
    "entityType": "target_set",
    "entityName": "test_example_set",
    "expression": "this.targets",
    "useCallCache": True,
    "deleteIntermediateOutputFiles": False,
    "useReferenceDisks": False,
    "memoryRetryMultiplier": 1.0,
    "workflowFailureMode": "NoNewCalls",
    "userComment": "Test example",
}

workflow_config = WorkflowConfig.model_validate(example)
submission = terra.submissions.submit_workflow(workflow_config)
print(f"Submitted {submission.get('submissionId')}")

submission_id = submission.get("submissionId")
if not submission_id:
    raise ValueError("Invalid submission response - missing submissionId")

# Extract entity names from workflows
entity_names = []
for workflow in submission.get("workflows", []):
    entity_name = workflow.get("entityName")
    if entity_name:
        entity_names.append(entity_name)

if not entity_names:
    raise ValueError("No entity names found in submission workflows")

# Current datetime in BigQuery-compatible format
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


entity_to_id_mapping_dict = bq_samples_ops.get_entity_id_mapping()
# Create updates list
updates = []
for entity_name in entity_names:
    # Get the BigQuery uuid for the entity
    id_value = entity_to_id_mapping_dict.get(entity_name)

    update = {
        "id": id_value,
        "submitted_at": current_time,
        "terra_submission_id": submission_id,
        "workflow_state": "submitted",
    }

    updates.append(update)

# Update the records
status = bq_samples_ops.bulk_update_samples(updates)
print(status)
