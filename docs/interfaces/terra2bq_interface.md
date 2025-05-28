# Terra2BQ  Classes, Methods, and Usage

## Module: `bioforklift.terra2bq`

Access these classes and methods using `from bioforklift.terra2bq import Terra2BQ` as your import statement.

This module serves as an integration layer for Terra and BigQuery operations. It orchestrates the complete data journey and provides a unified interface to:

1. **Download Data**: Transfer data from Terra workspaces to BigQuery tables
2. **Process Samples**: Filter, validate, and prepare samples for analysis
3. **Upload to Terra**: Upload processed data to Terra destination workspaces
4. **Submit Workflows**: Trigger Terra workflows on uploaded data
5. **Track Status**: Monitor and update Terra workflow progress
6. **Synchronize Metadata**: Keep metadata consistent across source and destination tables

???+ tip "Terra2BQ Data Flow"
    1. **Terra Source** → Data downloaded from source workspace
    2. **BigQuery** → Data stored, filtered, and tracked across all states
    3. **Terra Destination** → Processed data uploaded to destination table
    4. **Terra Workflows** → Analysis workflows executed with new data
    5. **BigQuery Update** → Status and results tracked from workflows

## Important Notes

!!! info "Configuration-Driven"
    The `Terra2BQ` class uses configuration objects to define how data should be processed. Each configuration includes:

    - Source and destination workspaces
    - Entity types and datatables
    - Workflow method configurations
    - Processing parameters

    Configurations are stored in BigQuery and drive the automated processing pipeline. Please see the [Schema Setup](../getting_started.md#setup-schemas-and-initialize-components) section for details on how to create and manage these configurations.

!!! info "Metadata Cleanup"
    `Terra2BQ` supports custom metadata cleanup functions to ensure data quality and consistency:

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

    This function is held in a separate file that is passed to the `metadata_cleanup_fn` parameter during initialization. It allows you to define custom transformations or validations on the metadata before it is uploaded to BigQuery.

!!! info "Architecture Details"
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

---

## Constructor

```python
Terra2BQ(
    bigquery_project: str,
    bigquery_dataset: str,
    bigquery_location: str = "us-central1",
    google_credentials_json: Optional[Path] = None,
    samples_table: str = "samples",
    configs_table: str = "configs",
    lookup_timeframe: str = "today",
    lookup_days_back: Optional[int] = None,
    lookup_hours_back: Optional[int] = None,
    samples_schema_yaml: Optional[Path] = None,
    configs_schema_yaml: Optional[Path] = None,
    source_workspace: Optional[str] = None,
    source_project: Optional[str] = None,
    source_datatable: Optional[str] = None,
    destination_workspace: Optional[str] = None,
    destination_project: Optional[str] = None,
    destination_datatable: Optional[str] = None,
    project_timezone: str = "UTC",
    bigquery_upload_df: Optional[pd.DataFrame] = None,
    metadata_cleanup_fn: Optional[callable] = None
)
```

### Parameters

- **bigquery_project** (str): GCP project ID for BigQuery
- **bigquery_dataset** (str): BigQuery dataset name
- **bigquery_location** (str, optional): BigQuery dataset location, defaults to "us-central1"
- **google_credentials_json** (Optional[Path]): Path to service account credentials JSON file
- **samples_table** (str, optional): Name of the samples table in BigQuery, defaults to "samples"
- **configs_table** (str, optional): Name of the configs table in BigQuery, defaults to "configs"
- **lookup_timeframe** (str, optional): Default timeframe for sample lookup, defaults to "today"
- **lookup_days_back** (Optional[int]): Number of days to look back for custom timeframe
- **lookup_hours_back** (Optional[int]): Number of hours to look back for custom timeframe
- **samples_schema_yaml** (Optional[Path]): Path to samples schema YAML file
- **configs_schema_yaml** (Optional[Path]): Path to configs schema YAML file
- **source_workspace** (Optional[str]): Default source workspace for Terra
- **source_project** (Optional[str]): Default source project for Terra
- **source_datatable** (Optional[str]): Source data table for Terra
- **destination_workspace** (Optional[str]): Destination workspace for Terra
- **destination_project** (Optional[str]): Destination project for Terra
- **destination_datatable** (Optional[str]): Destination data table for Terra
- **project_timezone** (str, optional): Timezone for the project, defaults to "UTC"
- **bigquery_upload_df** (Optional[pd.DataFrame]): Optional DataFrame to use for BigQuery upload
- **metadata_cleanup_fn** (Optional[callable]): Optional function to clean up metadata before upload

### Attributes

- **bigquery** (BigQuery): BigQuery interface
- **samples_ops** (BigQuerySampleOperations): Sample operations interface
- **config_ops** (BigQueryConfigOperations): Config operations interface
- **terra** (Terra): Terra interface, created dynamically per configuration

### Example Construction

Here is a basic setup:

```python
from pathlib import Path
from bioforklift.terra2bq import Terra2BQ

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

With a custom metadata function: 

```python
from metadata_cleanser import cleanse_metadata

terra2bq = Terra2BQ(
    # Base parameters...
    metadata_cleanup_fn=cleanse_metadata
)
```

With a Google credentials JSON for authentication:

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

## Methods

### `initialize_operations`

Initializes BigQuery operations objects, if not already initialized.

```python
initialize_operations() -> None
```

_**Example**_
```python
terra2bq.initialize_operations()
```

### `setup_terra_client`

Sets up Terra client based on a specific configuration.

```python
setup_terra_client(config: Dict[str, Any]) -> None
```

_**Example**_
```python
config = { ... }  # Configuration dictionary with source and destination details
terra2bq.setup_terra_client(config)
```

### `get_active_configs`

Gets all active configurations from BigQuery.

```python
get_active_configs(
    entity_type: Optional[str] = None, 
    skip_transferred: bool = False
    ) -> List[Dict[str, Any]]
```

**Returns:**

- A list of the active configuration dictionaries

_**Example**_

```python
# Get active configurations
configs = terra2bq.get_active_configs()
print(f"Found {len(configs)} active configurations")

# Filter configurations by entity type and skip any configurations that have already been transferred (for transient configs)
sample_configs = terra2bq.get_active_configs(entity_type="sample", skip_transferred=True)
```

### `download_from_terra_to_bigquery`

Pulls the data from the configuration's source Terra table and loads it into BigQuery.

```python
download_from_terra_to_bigquery(
    config: Dict[str, Any],
    destination_bucket: Optional[str] = None,
    preserve_path_structure: bool = True
) -> Dict[str, Any]
```

**Returns:**

- Dictionary with load results and status:
    ```python
    {
        "status": "success" | "no_data" | "error",
        "config_id": str,  # Configuration ID
        "loaded_count": int,  # Number of records loaded
        "filtered_count": int,  # Number of records filtered
        "message": str  # Error message if status is "error"
    }
    ```

_**Example**_
```python
# Process a single configuration
config = terra2bq.config_ops.get_config("config-id")

# Download data from Terra to BigQuery and move the fields marked 
#  as sequence_files to a GCS bucket and do not preserve the path structure 
#  (place the files directly in the destination bucket/folder)
result = terra2bq.download_from_terra_to_bigquery(config)
if result["status"] == "success":
    print(f"Downloaded {result['loaded_count']} samples")
else:
    print(f"Download failed: {result.get('message')}")

# Download data and transfer sequence files without preserving path structure
result = terra2bq.download_from_terra_to_bigquery(
    config=config,
    destination_bucket="gs://my-destination-bucket/folder".
    preserve_path_structure = False # Just move file to destination provided above (my-destination-bucket/folder/file.fastq)
)
```

### `upload_to_terra`

Uploads data to a Terra destination table and creates an entity set.

The `samples_df` is a DataFrame with full sample data including system columns, while the `upload_df` is a DataFrame prepared for upload to Terra (system columns removed).

```python
upload_to_terra(
    config: Dict[str, Any],
    samples_df: pd.DataFrame,
    upload_df: pd.DataFrame
) -> Dict[str, Any]
```

**Returns:**

- Dictionary with upload results:
    ```python
    {
        "status": "success" | "error",
        "config_id": str,  # Configuration ID
        "set_name": str,  # Entity set name created in Terra
        "uploaded_count": int,  # Number of records uploaded
        "message": str  # Error message if status is "error"
    }
    ```

_**Example**_
```python
# Process upload
result = terra2bq.upload_to_terra(config, samples_df, upload_df)

if result["status"] == "success":
    print(f"Uploaded {result['uploaded_count']} samples")
    print(f"Created entity set: {result['set_name']}")
```

### `get_samples_for_submission`

Gets all samples from BigQuery that have been uploaded but not yet submitted to a workflow, with optional filtration for specific set names or config IDs.

```python
get_samples_for_submission(
    config: Dict[str, Any],
    set_name: Optional[str] = None,
    config_id: Optional[str] = None
) -> pd.DataFrame
```

**Returns:**

- DataFrame with samples ready for submission

_**Example**_
```python
# Get samples for submission (already uploaded but not submitted)
samples_for_submission = terra2bq.get_samples_for_submission(
    config=config,
    set_name="my-entity-set-name"  # Optional
)
```

### `submit_workflow`

Submits a workflow to Terra for the provided set name and updates tracking info. The `samples_df` is the DataFrame with the samples to be submitted.

```python
submit_workflow(
    config: Dict[str, Any],
    set_name: str,
    samples_df: pd.DataFrame
) -> Dict[str, Any]
```

**Returns:**

- Dictionary with submission results:
    ```python
    {
        "status": "success" | "error",
        "config_id": str,  # Configuration ID
        "set_name": str,  # Entity set name
        "submission_id": str,  # Terra submission ID
        "workflow_count": int,  # Number of workflows submitted
        "message": str  # Error message if status is "error"
    }
    ```

_**Example**_

```python
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

### `process_upload_and_submit`

Processes a configuration by uploading data and submitting a workflow; this is a convenience method that combines the upload and submission steps into one operation.

```python
process_upload_and_submit(config: Dict[str, Any]) -> Dict[str, Any]
```

**Returns:**

- Dictionary containing results of the operation:
    ```python
    {
        "status": "success" | "no_new_samples" | "error",
        "config_id": str,  # Configuration ID
        "uploaded_count": int,  # Number of records uploaded
        "set_name": str,  # Entity set name (if successful)
        "submission_id": str,  # Terra submission ID (if successful)
        "workflow_count": int,  # Number of workflows submitted
        "message": str  # Error message if status is "error"
    }
    ```

_**Example**_

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

### `process_configuration`

Processes a single configuration with isolation guarantees.

```python
process_configuration(
    config: Dict[str, Any],
    destination_bucket: Optional[str] = None,
    preserve_path_structure: bool = True,
    skip_transferred: bool = False,
    ) -> Dict[str, Any]
```

**Returns:**

- A Dictionary with processing results (the combined results from download and process operations)

_**Example**_

```python
# Process a single configuration with optional parameters
result = terra2bq.process_configuration(
    config=config,
    destination_bucket="gs://my-destination-bucket/folder",
    preserve_path_structure=False,  # Do not preserve path structure
    skip_transferred=True  # Skip configurations that have already been transferred
)
```

### `process_all_configs`

Processes all active configurations with progress tracking and batch processing.

```python
process_all_configs(
    entity_type: Optional[str] = None,
    batch_size: int = 1,
    cooldown_seconds: int = 1,
    destination_bucket: Optional[str] = None,
    preserve_path_structure: bool = True,
    skip_transferred: bool = False,
) -> List[Dict[str, Any]]
```

**Returns:**

- List of results for each configuration processed

_**Example**_

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

results = terra2bq.process_all_configs(
    entity_type="sample",
    batch_size=5,             
    cooldown_seconds=1,         
    destination_bucket="gs://destination-bucket/folder",
    preserve_path_structure=True # Keep original folder structure in destination
)
```

### `sync_metadata_for_config`

Syncs metadata for a single configuration between Terra data tables and BigQuery, and updates destination Terra datatable.

```python
sync_metadata_for_config(
    config: Dict[str, Any],
    days_back: int,
    update_bigquery: bool = True,
    update_destination: bool = True
) -> Dict[str, Any]
```

**Returns:**

- Dictionary with sync results:
    ```python
    {
        "status": "success" | "no_updates" | "error",
        "config_id": str,  # Configuration ID
        "bq_updated_count": int,  # Number of records updated in BigQuery
        "destination_updated_count": int,  # Number of entities updated in Terra
        "failed_updates": List[Dict[str, Any]]  # List of failed updates
    }
    ```

_**Example**_

```python
# Sync metadata for a single configuration
result = terra2bq.sync_metadata_for_config(
    config=config,
    days_back=30,  # Look back 30 days for samples
    update_bigquery=True,  # Update BigQuery with Terra metadata
    update_destination=True  # Update destination Terra datatable
)
```

### `sync_metadata`

Syncs metadata for all configurations between Terra data tables and BigQuery, and updates destination Terra datatable.

```python
sync_metadata(
    days_back: int = 30,
    update_bigquery: bool = True,
    update_destination: bool = True,
    batch_size: int = 1,
    cooldown_seconds: int = 1
) -> Dict[str, Any]
```

**Returns:**

- Dictionary with sync results:
    ```python
    {
        "status": "success" | "no_updates" | "no_configs",
        "bq_updated_count": int,  # Number of records updated in BigQuery
        "destination_updated_count": int,  # Number of entities updated in Terra
        "total_updated_count": int,  # Total number of updates
        "processed_configs": int,  # Number of configurations processed
        "failed_updates": List[Dict[str, Any]]  # List of failed updates
    }
    ```

_**Example**_

```python
# Sync metadata for all configurations from the source entity table
result = terra2bq.sync_metadata(
    days_back=30,            # Look back 30 days
    update_bigquery=True,    # Update BigQuery
    update_destination=True  # Update destination Terra workspace
)
print(f"Updated {result['bq_updated_count']} records in BigQuery")
print(f"Updated {result['destination_updated_count']} entities in Terra")

# Sync BigQuery metadata from the destination entity table
result = terra2bq.sync_metadata(
    days_back=30,            # Look back 30 days
    update_bigquery=True,    # Update BigQuery
    update_destination=False  # Don't update destination since we just want to sync data in Biguery
    use_destination_entity=True # We want to sync the BigQuery table from the target/destination entity table
)

# perform a dry run by setting update_bigquery and update_destination to False
# Perform a dry run
dry_run = terra2bq.sync_metadata(
    days_back=30,
    update_bigquery=False,
    update_destination=False
)

print(f"Would update {dry_run['bq_updated_count']} records in BigQuery")
print(f"Would update {dry_run['destination_updated_count']} entities in Terra")
```

### `update_workflow_status_for_config`

Updates workflow status for a single configuration.

```python
update_workflow_status_for_config(
    config: Dict[str, Any],
    days_back: int,
    batch_size: int,
    update_bigquery: bool
) -> Dict[str, Any]
```

**Returns:**

- Dictionary with update results:
    ```python
    {
        "status": "success" | "no_updates" | "error",
        "config_id": str,  # Configuration ID
        "updated_count": int,  # Number of records updated
        "processed_submissions": int,  # Number of submissions processed
        "workflow_states": Dict[str, int],  # Count of workflow states
        "failed_updates": List[Dict[str, Any]]  # List of failed updates
    }
    ```

_**Example**_

```python
# Update workflow status for a single configuration
result = terra2bq.update_workflow_status_for_config(
    config=config,
    days_back=30,  # Look back 30 days for workflow updates
    batch_size=100,  # Process 100 records at a time
    update_bigquery=True  # Update BigQuery with workflow status
)
```

### `update_workflow_status`

Updates terra_workflow_ids and states for all configurations from Terra submissions.

```python
update_workflow_status(
    days_back: int = 30,
    batch_size: int = 100,
    update_bigquery: bool = True,
    config_batch_size: int = 4,
    cooldown_seconds: int = 1
) -> Dict[str, Any]
```

**Returns:**

- Dictionary with update results:
    ```python
    {
        "status": "success" | "no_updates" | "no_configs",
        "updated_count": int,  # Number of records updated
        "processed_configs": int,  # Number of configurations processed
        "processed_submissions": int,  # Number of submissions processed
        "workflow_states": Dict[str, int],  # Count of workflow states
        "failed_updates": List[Dict[str, Any]]  # List of failed updates
    }
    ```

_**Example**_

```python
# Update workflow status for all configurations
result = terra2bq.update_workflow_status(
    days_back=1,         # Look back 30 days
    batch_size=100,      # Update 100 samples at a time
    update_bigquery=True # Actually update (False for dry run)
)

print(f"Updated {result['updated_count']} workflow records")
print(f"Processed {result['processed_submissions']} submissions")

# Show workflow state distribution
for state, count in result['workflow_states'].items():
    print(f"  {state}: {count}")

# Perform a dry run to see what would be updated
dry_run = terra2bq.update_workflow_status(
    days_back=30,
    batch_size=100,
    update_bigquery=False  # Don't actually update
)

print(f"Would update {dry_run['updated_count']} records")
```

## Practical Examples

### Daily Processing Script

This script handles daily processing of new samples by initializing the Terra2BQ client and processing all configs in 5 batches with a cooldown of 1 second between batches. All workflow states are updated for the last seven days and metadata is synced for the last 30 days. 

```python
from pathlib import Path
from bioforklift.terra2bq import Terra2BQ
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
