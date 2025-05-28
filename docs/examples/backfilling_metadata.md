# Case Study: Backfilling Metadata

In several cases, we have been able to use bioforklift to backfill metadata for existing datasets.

## Backfilling Workflow Metadata 

This example describes how Sage backfilled workflow metadata (submission status, etc.) for the H5N1 USDA dashboard.

Theiagen organization members can see the full code in the cdph-automations _private_ GitHub repository.

```python
from bioforklift.terra2bq import Terra2BQ
from bioforklift.terra import Terra

# initialize Terra2BQ instance
terra2bq = Terra2BQ(bigquery_project="h5n1-looker", 
                    bigquery_dataset="h5n1_data",
                    samples_schema_yaml="../data/samples.yaml",
                    configs_schema_yaml="../data/config.yaml",
                    destination_workspace="dataAnalysis_VRDL_H5N1_USDA",
                    destination_project="cdph-terrabio-taborda-manual",
                    destination_datatable="h5n1_specimen"
                    )

# initialize Terra instance
terra_client = Terra(
    source_workspace="dataAnalysis_VRDL_H5N1_USDA",
    source_project="cdph-terrabio-taborda-manual",
)

# BACKFILLING WORKFLOW METADATA
# get the samples operations object from terra2bq
samples_ops = terra2bq.samples_ops
# find all samples in BigQuery that are *missing* the 
#  terra_submission_id system value
samples_df = samples_ops.query_samples(
    conditions=["terra_submission_id IS NULL"],
    limit=7000 # the limit is optional
)

# get the sample identifier field from the samples operations object
sample_id_field = samples_ops.get_sample_identifier_field()

# Get workflow data from Terra for each entity
submission_data = {} # create a blank dictionary to hold the submission data

# get all submissions from the Terra workspace that was used to 
#  initialize the Terra instance
workflows = terra_client.submissions.get_all_submissions()

# iterate through each submission
for submission in workflows:
    # extract all workflows in the submission
    workflow_data = terra_client.submissions.get_workflows_by_submission(submission.submission_id)
    # foir each workflow in the submission
    for workflow in workflow_data:
        # search for the entity name in the workflow
        entity_name = workflow.entity_name
        # if it exists and if the workflow status is "Succeeded" 
        #  (the second half of this conditional is OPTIONAL)
        if entity_name and workflow.status == "Succeeded":
            # Only add if this entity doesn't exist yet in submission_data
            # or if this submission is newer than the current one
            if (entity_name not in submission_data  or 
                workflow.submission_date > submission_data[entity_name]["submitted_at"] ):
                # create a dictionary of values for the entity
                submission_data[entity_name] = {
                    "terra_submission_id": workflow.submission_id,
                    "terra_workflow_id": workflow.workflow_id,
                    "workflow_state": workflow.status,
                    "submitted_at": workflow.submission_date
                }

# create a list to hold the update dictionaries            
updates = []

# iterate through the samples that are missing the terra_submission_id
for idx, row in samples_df.iterrows():
    entity_id = row['h5n1_id']
    # if the entity_id is in the submission_data dictionary
    if entity_id in submission_data:
        # add the sample identifier to the update dictionary
        update_dict = {'id': row['id']} 
        # and add all the values from the submission_data dictionary 
        #  to the update dictionary
        for key, value in submission_data[entity_id].items():
            print(f"Updating {key} for {entity_id} with value: {value}")
            # Add to update dictionary
            update_dict[key] = value
        # add the update dictionary to the list of updates
        updates.append(update_dict)

#Bulk update the samples in BigQuery

# if there are any updates to be made, update the samples in BigQuery
if updates:
    # to prevent BigQuery errors when updating too many rows at once, 
    #  we will chunk the updates into smaller batches
    chunk_size = 1000
    # iterate through the updates in chunks
    for i in range(0, len(updates), chunk_size):
        chunk = updates[i:i + chunk_size]
        
        print(f"Updating {len(chunk)} samples in BigQuery")
        # update the samples in BigQuery using the sample operations object from Terra2BQ
        update_result = samples_ops.bulk_update_samples(chunk)
        print(f"Updated {update_result.get('updated_count', 0)} samples with workflow information")
        
        if update_result.get('failed_updates'):
            print(f"Failed to update {len(update_result.get('failed_updates'))} samples")
else:
    print("No samples to update")
            
```

The code above can be modified to backfill any metadata that is available in the Terra workspace.

## Backfilling Result or Metadata Fields

This example describes how Sage backfilled a metadata entry for the H5N1 USDA dashboard that only appeared in the destination table -- specifically, `upload_date`.

This approach would work for any result fields that only appear in the destination table.

Theiagen organization members can see the full code in the cdph-automations _private_ GitHub repository. See the previous example for more detailed comments as many of the same processes are used.

```python
from bioforklift.terra2bq import Terra2BQ
from bioforklift.terra import Terra

terra2bq = Terra2BQ(bigquery_project="h5n1-looker", 
                    bigquery_dataset="h5n1_data",
                    samples_schema_yaml="../data/samples.yaml",
                    configs_schema_yaml="../data/config.yaml",
                    destination_workspace="dataAnalysis_VRDL_H5N1_USDA",
                    destination_project="cdph-terrabio-taborda-manual",
                    destination_datatable="h5n1_specimen"
                    )

terra = Terra(
    source_workspace="dataAnalysis_VRDL_H5N1_USDA",
    source_project="cdph-terrabio-taborda-manual",
)

samples_ops = terra2bq.samples_ops

# Extract all samples that are missing the upload_date field
bq_df = samples_ops.query_samples(conditions=["upload_date IS NULL"])

# In a *separate* DataFrame, download all samples from the Terra workspace 
#  which contains the metadata field we want to add to BigQuery
samples_df = terra.entities.download_table(entity_type="h5n1_specimen")

# we will rename the terra table columns to match the BigQuery table columns
samples_df = samples_df.rename(columns={"entity:h5n1_specimen_id": "h5n1_id"})

# Add the upload_date column to the BigQuery DataFrame
bq_df['upload_date'] = samples_df['upload_date']

updates = []
for idx, row in bq_df.iterrows():
    # this is because when you upload to BigQuery, the "id" column 
    #  is required to tell BigQuery which row to update
    # the id column is the UUID in BigQuery, not the sample name in Terra.
    update_dict = {'id': row['id'], 'upload_date': row['upload_date']} 
    updates.append(update_dict)

if updates:
    chunk_size = 1000
    for i in range(0, len(updates), chunk_size):
        chunk = updates[i:i + chunk_size]
        update_result = samples_ops.bulk_update_samples(chunk)
else:
    print("No samples to update")
```

More examples to follow soon.