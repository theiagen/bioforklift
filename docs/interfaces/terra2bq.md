# Terra2BQ Layer

## Overview

The Terra2BQ subsystem serves as an integration layer between Terra and BigQuery, providing a seamless workflow for data transfer, workflow management, and status tracking. This module enables coordinated operations between the two platforms, automating the flow of source to destination sample tracking projects. 

## Purpose and Functionality

The Terra2BQ subsystem provides a unified interface to:

1. **Download Data**: Transfer data from Terra workspaces to BigQuery tables
2. **Process Samples**: Filter, validate, and prepare samples for analysis
3. **Upload to Terra**: Upload processed data to Terra destination workspaces
4. **Submit Workflows**: Trigger Terra workflows on uploaded data
5. **Track Status**: Monitor and update Terra workflow progress
6. **Synchronize Metadata**: Keep metadata consistent across source and destination tables

## Core Concepts

### Integrated Workflow

The Terra2BQ subsystem orchestrates the complete data journey:

???+ info "Data Flow"
    1. **Terra Source** → Data downloaded from source workspace
    2. **BigQuery** → Data stored, filtered, and tracked across all states
    3. **Terra Destination** → Processed data uploaded to destination table
    4. **Terra Workflows** → Analysis workflows executed with new data
    5. **BigQuery Update** → Status and results tracked from workflows

### Configurations

Terra2BQ uses configuration objects to define how data should be processed. Each configuration includes:

- Source and destination Terra workspaces
- Entity types and datatables
- Workflow method configurations
- Processing parameters

Configurations are stored in BigQuery and drive the automated processing pipeline.

??? example "Configuration Example"
    ```json
    {
      "name": "County",
      "state": "California",
      "prefix": "county_sample",
      "entity_type": "sample",
      "terra_source_project": "county-uploads",
      "terra_source_workspace": "raw-covid-data",
      "terra_destination_project": "state-processing",
      "terra_destination_workspace": "covid-analysis",
      "active": true,
      "terra_analysis_method": "TheiaCoV_Illumina_PE",
      "terra_method_config": {
        "methodConfigurationNamespace": "theiagen",
        "methodConfigurationName": "TheiaCoV_Illumina_PE",
        "entityType": "sample_set",
        "expression": "this.samples",
        "useCallCache": true,
        "deleteIntermediateOutputFiles": true,
        "useReferenceDisks": true,
        "workflowFailureMode": "NoNewCalls"
      }
    }
    ```

### Metadata Cleanup

Terra2BQ supports custom metadata cleanup functions to ensure data quality and consistency:

```python
def cleanse_metadata(dataframe, config):
    """
    Cleanup and transform metadata before loading into BigQuery
    
    Args:
        dataframe: DataFrame with Terra data
        config: Configuration dictionary
        
    Returns:
        Cleaned DataFrame
    """
    # Custom cleanup logic...
    return cleaned_df
```

## Setting Up Terra2BQ

### Basic Initialization

Here is how a basic setup for you project might look, where you give it your project id and dataset name for BigQuery along with the location. The `samples_table` and `configs_table` provided the name for the BigQuery tables that contain your samples and configurations respectively. The `samples_schema_yaml` contains the data schema for your samples table and the `configs_schema_yaml` contains the data schema for your configurations table. Optionally, so that the display set name in Terra has the embedded time of the project timezone you can pass an acceptable `project_timezone` (pytz accepted timezones).

```python
from pathlib import Path
from forklift.terra2bq import Terra2BQ

# Initialize Terra2BQ with base parameters...
terra2bq = Terra2BQ(
    bigquery_project="your-project-id",
    bigquery_dataset="your-dataset-name",
    bigquery_location="us-central1",
    samples_table="samples",
    configs_table="configs",
    samples_schema_yaml=Path("sample_schema.yaml"),
    configs_schema_yaml=Path("config_schema.yaml"),
    project_timezone="America/Los_Angeles"
)
```

### With Custom Metadata Cleanup

If needed you can pass a custom metadata cleaning function that takes a Pandas DataFrame and optionally a config (as a Dict), and returned a cleaned DataFrame before uploading the data to BigQuery. This cleaned metadata is then what would get reflected in the data uploaded to the target workspace. 

```python
from metadata_cleanser import cleanse_metadata

terra2bq = Terra2BQ(
    # Base parameters...
    metadata_cleanup_fn=cleanse_metadata
)
```

### With Explicit Terra Credentials

When working with a service account you can pass a google credentials json for auth.

```python
terra2bq = Terra2BQ(
    # Base parameters...
    google_credentials_json=Path("path/to/service-account-key.json"),
    # These are override options if using configurations from BigQuery
    source_workspace="optional-default-source",
    source_project="optional-default-project",
    destination_workspace="optional-default-destination",
    destination_project="optional-default-destination-project"
)
```

## Key Operations

### Configuration Management

Get active configurations from you configurations BigQuery data table.

```python
# Get active configurations
configs = terra2bq.get_active_configs()
print(f"Found {len(configs)} active configurations")

# Filter configurations by entity type
sample_configs = terra2bq.get_active_configs(entity_type="sample")
```

### Data Download from Terra to BigQuery

Download data for one configuration and upload the resulting data to BigQuery

```python
# Process a single configuration
config = terra2bq.config_ops.get_config("config-id")
result = terra2bq.download_from_terra_to_bigquery(config)

if result["status"] == "success":
    print(f"Downloaded {result['loaded_count']} samples")
else:
    print(f"Download failed: {result.get('message')}")
```

We can also transfer files between buckets before we upload them to BigQuery, this will take all sequencing_files present and move them between buckets. This takes a `destination_bucket` argument and a `preserve_path_structure` argument (defualt is `False`). The `destination_bucket` can have an appended folder structure if desired. The `preserve_path_structure` will automatically try and preserve the path from the source `gs uri`, otherwise it will put it directly in the bucket, or last depth of folder provded.

```python

# Download data and transfer sequence files
result = terra2bq.download_from_terra_to_bigquery(
    config=config,
    destination_bucket="gs://my-destination-bucket/folder".
    preserve_path_structure = False # Just move file to destination provided above (my-destination-bucket/folder/file.fastq)
)
```

### Sample Upload to Terra

Get samples from BigQuery that have been uploaded `today` (day of running operation), and upload to Terra destination table.

```python
# Get samples from BigQuery that need to be uploaded
samples_df = terra2bq.samples_ops.get_samples_by_timeframe(
    timeframe="today",
    uploaded_filter="not_uploaded",
    config_id=config["id"]
)

# Process upload
result = terra2bq.upload_to_terra(config, samples_df, upload_df)

if result["status"] == "success":
    print(f"Uploaded {result['uploaded_count']} samples")
    print(f"Created entity set: {result['set_name']}")
```

### Workflow Submission

Grab samples for submission, optionally by a specific set name, and pass them those to be submitted to Terra via configuration info and the terra_method_config on the configuration body. 

```python
# Get samples for submission (already uploaded but not submitted)
samples_for_submission = terra2bq.get_samples_for_submission(
    config=config,
    set_name="my-entity-set-name"  # Optional
)

# Submit workflow
result = terra2bq.submit_workflow(
    config=config,
    set_name="my-entity-set-name",
    samples_df=samples_for_submission
)

if result["status"] == "success":
    print(f"Submitted workflow: {result['submission_id']}")
    print(f"Workflow count: {result['workflow_count']}")
```

### End-to-End Processing

This process combines uploading and submitting data to Terra destination workspace in one operation as driven by a provided configuration.

```python
# Process a configuration end-to-end
result = terra2bq.process_upload_and_submit(config)

if result["status"] == "success":
    print(f"Uploaded {result['uploaded_count']} samples")
    print(f"Created entity set: {result['set_name']}")
    print(f"Submitted workflow: {result['submission_id']}")
else:
    # If we got a failure or error occured
    print(f"Processing failed: {result.get('message')}")
```

### Batch Processing

Here we can can grab all active confiurations, grab new data from source Terra workspaces and datatables, upload to BigQuery then upload new samples to destination Terra Workspace and submit them to the designated analysis method in Terra. 

```python
# Process all active configurations with defualts
results = terra2bq.process_all_configs()

# Summarize results
success_count = sum(1 for r in results if r["status"] == "success")
print(f"Processed {len(results)} configurations ({success_count} successful)")

# Process configurations in batches with cooldown
results = terra2bq.process_all_configs(
    entity_type="sample",  # Optional filter
    batch_size=5,          # Process 5 configs per batch
    cooldown_seconds=1    # Wait 1 second between batches (added this for limit rate safety)
)
```

If you process needs to transfer files between source and destination buckets, you can provide the top level `processs_all_configs()` with `destination_bucket` and `preserve_path_structure` args:

```python

results = terra2bq.process_all_configs(
    entity_type="sample",
    batch_size=5,             
    cooldown_seconds=1,         
    destination_bucket="gs://destination-bucket/folder",
    preserve_path_structure=True # Keep original folder structure in destination
)
```

## Workflow Status Updates

Terra2BQ provides methods to update workflow status information from Terra to BigQuery:

### Update Workflow Status

We also provide methods to update the workflow status of the Terra workflows for samples submitted across all active configurations going x days back. This allows for tracking the workflow status over time.

```python
# Update workflow status for all configurations
result = terra2bq.update_workflow_status(
    days_back=1,        # Look back 30 days
    batch_size=100,      # Update 100 samples at a time
    update_bigquery=True # Actually update (False for dry run)
)

print(f"Updated {result['updated_count']} workflow records")
print(f"Processed {result['processed_submissions']} submissions")

# Show workflow state distribution
for state, count in result['workflow_states'].items():
    print(f"  {state}: {count}")
```

### Dry Run

```python
# Perform a dry run to see what would be updated
dry_run = terra2bq.update_workflow_status(
    days_back=30,
    batch_size=100,
    update_bigquery=False  # Don't actually update
)

print(f"Would update {dry_run['updated_count']} records")
```

## Metadata Synchronization

Terra2BQ can synchronize metadata between Terra and BigQuery:

### Sync Metadata

Here we have another important feature to go look at samples created withing a certain timeframe, look if there is any new metadata in the source workspace that is not in BigQuery, update the data in BigQuery and then in the destination Terra table. This is done for any fields marked as `sync_field: true` in the sample YAML. 

```python
# Sync metadata for all configurations
result = terra2bq.sync_metadata(
    days_back=30,            # Look back 30 days
    update_bigquery=True,    # Update BigQuery
    update_destination=True  # Update destination Terra workspace
)

print(f"Updated {result['bq_updated_count']} records in BigQuery")
print(f"Updated {result['destination_updated_count']} entities in Terra")
```

### Dry Run

```python
# Perform a dry run
dry_run = terra2bq.sync_metadata(
    days_back=30,
    update_bigquery=False,
    update_destination=False
)

print(f"Would update {dry_run['bq_updated_count']} records in BigQuery")
print(f"Would update {dry_run['destination_updated_count']} entities in Terra")
```

## Tracking Fields

Terra2BQ manages several fields to track the status of samples through the workflow:

???+ info "Tracking Fields"
    | Field | Description |
    |-------|-------------|
    | `uploaded_at` | When the sample was uploaded to Terra |
    | `upload_source` | Name of the entity set created during upload |
    | `submitted_at` | When the sample was submitted to a workflow |
    | `terra_submission_id` | Terra submission ID |
    | `terra_workflow_id` | Terra workflow ID |
    | `workflow_state` | Current state of the workflow |

These fields are used for querying and reporting, and are automatically updated during processing.

## Practical Examples

### Daily Processing Script

Here is an example of a script that would be that handles daily processing of new samples. The Terra2BQ client is set up and initalized, then we can process all configs in 5 batches with a cooldown of 1 second in between batches. 

Then we update all workflow states in the last 7 days.

Then we check to sync all metadata for data that has been uploaded in the last 30 days. 

```python
from pathlib import Path
from forklift.terra2bq import Terra2BQ
from metadata_cleanser import cleanse_metadata

terra2bq = Terra2BQ(
    bigquery_project="your-project",
    bigquery_dataset="your-dataset",
    samples_table="samples",
    configs_table="configs",
    samples_schema_yaml=Path("sample_schema.yaml"),
    configs_schema_yaml=Path("config_schema.yaml"),
    project_timezone="America/Los_Angeles",
    metadata_cleanup_fn=cleanse_metadata
)

# Process all configs
results = terra2bq.process_all_configs(
    batch_size=5,
    cooldown_seconds=1
)

# Summarize results
success_count = sum(1 for r in results if r.get("status") == "success")
print(f"Processed {len(results)} configurations ({success_count} successful)")

# Update workflow status
update_results = terra2bq.update_workflow_status(days_back=7)
print(f"Updated {update_results['updated_count']} workflow states")

# Sync metadata
sync_results = terra2bq.sync_metadata(days_back=30)
print(f"Synced metadata for {sync_results['processed_configs']} configurations")
```

### Processing a Single Configuration

Here we have an example of how we can go ahead and just process one configuration at a time.

```python
# Get a specific configuration
config_ops = bq.get_config_operations(
    table_name="configs",
    config_schema_yaml="config_schema.yaml"
)
config = config_ops.get_config("config-id")

# Process just this configuration
result = terra2bq.process_configuration(config)
print(f"Processing result: {result['status']}")

if result.get("set_name"):
    print(f"Created entity set: {result['set_name']}")
    
if result.get("submission_id"):
    print(f"Submitted workflow: {result['submission_id']}")
```

## Troubleshooting

### Common Issues

??? question "Configuration Issues"
    **Problem**: Configuration is not being processed
    
    **Solution**:
    - Check if the configuration is marked as active
    - Verify that Terra source workspace exists and is accessible
    - Confirm that all required fields in the configuration are populated
    - Ensure the schema marked the right fields with appropriate attributes

??? question "Upload Failures"
    **Problem**: Samples not uploading to Terra
    
    **Solution**:
    - Check Terra permissions for the destination workspace
    - Verify sample identifiers are unique
    - Ensure all sequence files exist and are accessible
    - Look for formatting issues in the data

??? question "Workflow Status Not Updating"
    **Problem**: Workflow states are not being updated
    
    **Solution**:
    - Verify that `terra_submission_id` is correctly set
    - Check if enough time has passed for workflows to complete
    - Ensure Terra API is accessible
    - Look for errors in the workflow submissions

## Architecture Details

The Terra2BQ subsystem connects the Terra and BigQuery subsystems, coordinating operations between them:

```
Terra2BQ
├── bigquery: BigQuery
├── samples_ops: BigQuerySampleOperations
├── config_ops: BigQueryConfigOperations
├── terra: Terra (created per configuration)
├── get_active_configs()
├── download_from_terra_to_bigquery()
├── upload_to_terra()
├── submit_workflow()
├── process_upload_and_submit()
├── process_configuration()
├── process_all_configs()
├── update_workflow_status()
└── sync_metadata()
```

The subsystem creates Terra clients dynamically for each configuration, ensuring isolation and proper authentication. This way we can also make sure the client is reset between operations and new state variables can be set for source / destination tables and there is more predicatability over where we retrieve and push data. 