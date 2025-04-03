# Terra2BQ Class Reference

## Overview

The `Terra2BQ` class serves as an integration layer for Terra and BigQuery operations. It provides a comprehensive set of methods to automate the flow of genomic data between Terra workspaces and BigQuery tables, including data download, processing, upload, workflow submission, and status tracking.

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

## Attributes

- **bigquery** (BigQuery): BigQuery interface
- **samples_ops** (BigQuerySampleOperations): Sample operations interface
- **config_ops** (BigQueryConfigOperations): Config operations interface
- **terra** (Terra): Terra interface, created dynamically per configuration

## Methods

### `initialize_operations`

Initialize BigQuery operations objects if not already initialized.

```python
initialize_operations() -> None
```

### `setup_terra_client`

Set up Terra client based on a configuration.

```python
setup_terra_client(config: Dict[str, Any]) -> None
```

#### Parameters:
- **config** (Dict[str, Any]): Configuration dictionary containing Terra workspace and project details

### `get_active_configs`

Get active configurations from BigQuery.

```python
get_active_configs(entity_type: Optional[str] = None, skip_transferred: bool = False) -> List[Dict[str, Any]]
```

#### Parameters:
- **entity_type** (Optional[str]): Optional entity type filter
- **skip_transferred** Specific option for transient configs, where if set to true will skip configurations that already had their data transferred and will mark current config as transferred after data is submitted

#### Returns:
- List of active configuration dictionaries

### `download_from_terra_to_bigquery`

Pull data from source Terra table and load it into BigQuery.

```python
download_from_terra_to_bigquery(
    config: Dict[str, Any],
    destination_bucket: Optional[str] = None,
    preserve_path_structure: bool = True
) -> Dict[str, Any]
```

#### Parameters:
- **config** (Dict[str, Any]): Configuration dictionary
- **destination_bucket** Optional GCS bucket path where sequence files should be transferred (e.g., "gs://bucket-name/optional/folder/path" or "bucket-name/optional/folder/path")
- **preserve_path_structure** If True (default), preserve the original file path structure; if False, place files directly in the destination bucket/folder

#### Returns:
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

### `upload_to_terra`

Upload data to Terra destination table and create entity set.

```python
upload_to_terra(
    config: Dict[str, Any],
    samples_df: pd.DataFrame,
    upload_df: pd.DataFrame
) -> Dict[str, Any]
```

#### Parameters:
- **config** (Dict[str, Any]): Configuration dictionary
- **samples_df** (pd.DataFrame): DataFrame with full sample data including system columns
- **upload_df** (pd.DataFrame): DataFrame prepared for upload to Terra (system columns removed)

#### Returns:
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

### `get_samples_for_submission`

Get samples from BigQuery that have been uploaded but not yet submitted to a workflow.

```python
get_samples_for_submission(
    config: Dict[str, Any],
    set_name: Optional[str] = None,
    config_id: Optional[str] = None
) -> pd.DataFrame
```

#### Parameters:
- **config** (Dict[str, Any]): Configuration dictionary
- **set_name** (Optional[str]): Optional specific set name to filter by
- **config_id** (Optional[str]): Optional specific config_id to filter by

#### Returns:
- DataFrame with samples ready for submission

### `submit_workflow`

Submit a workflow to Terra for the given set and update tracking info.

```python
submit_workflow(
    config: Dict[str, Any],
    set_name: str,
    samples_df: pd.DataFrame
) -> Dict[str, Any]
```

#### Parameters:
- **config** (Dict[str, Any]): Configuration dictionary
- **set_name** (str): Terra entity set name to submit
- **samples_df** (pd.DataFrame): DataFrame with samples to be submitted

#### Returns:
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

### `process_upload_and_submit`

Process a configuration by uploading data and submitting a workflow.

```python
process_upload_and_submit(config: Dict[str, Any]) -> Dict[str, Any]
```

#### Parameters:
- **config** (Dict[str, Any]): Configuration dictionary

#### Returns:
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

### `process_configuration`

Process a single configuration with isolation guarantees.

```python
process_configuration(
    config: Dict[str, Any],
    destination_bucket: Optional[str] = None,
    preserve_path_structure: bool = True,
    skip_transferred: bool = False,
    ) -> Dict[str, Any]
```

#### Parameters:
- **config** (Dict[str, Any]): Configuration dictionary
- **destination_bucket** Optional GCS bucket path where sequence files should be transferred (e.g., "gs://bucket-name/optional/folder/path" or "bucket-name/optional/folder/path")
- **preserve_path_structure** If True (default), preserve the original file path structure; if False, place files directly in the destination bucket/folder
- **skip_transferred** Specific option for transient configs, where if set to true will skip configurations that already had their data transferred and will mark current config as transferred after data is submitted

#### Returns:
- Dictionary with processing results (combined results from download and process operations)

### `process_all_configs`

Process all active configurations with progress tracking and batch processing.

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

#### Parameters:
- **entity_type** (Optional[str]): Optional entity type filter
- **batch_size** (int, optional): Number of configurations to process in a batch before cooldown, defaults to 1
- **cooldown_seconds** (int, optional): Seconds to wait between batches, defaults to 1
- **destination_bucket** (Optional[str]): Optional GCS bucket path where sequence files should be       transferred (e.g., "gs://bucket-name/optional/folder/path" or "bucket-name/optional/folder/path")
- **preserve_path_structure** If True (default), preserve the original file path structure; if False, place files directly in the destination bucket/folder
- **skip_transferred** Specific option for transient configs, where if set to true will skip configurations that already had their data transferred and will mark current config as transferred after data is submitted

#### Returns:
- List of results for each configuration processed

### `sync_metadata_for_config`

Sync metadata for a single configuration.

```python
sync_metadata_for_config(
    config: Dict[str, Any],
    days_back: int,
    update_bigquery: bool = True,
    update_destination: bool = True
) -> Dict[str, Any]
```

#### Parameters:
- **config** (Dict[str, Any]): Configuration dictionary
- **days_back** (int): Number of days to look back for samples
- **update_bigquery** (bool, optional): Whether to update BigQuery with Terra metadata, defaults to True
- **update_destination** (bool, optional): Whether to update destination Terra datatable, defaults to True

#### Returns:
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

### `sync_metadata`

Sync metadata between Terra data tables and BigQuery, and update destination Terra datatable.

```python
sync_metadata(
    days_back: int = 30,
    update_bigquery: bool = True,
    update_destination: bool = True,
    batch_size: int = 1,
    cooldown_seconds: int = 1
) -> Dict[str, Any]
```

#### Parameters:
- **days_back** (int, optional): Number of days to look back for samples, defaults to 30
- **update_bigquery** (bool, optional): Whether to update BigQuery with Terra metadata, defaults to True
- **update_destination** (bool, optional): Whether to update destination Terra datatable, defaults to True
- **batch_size** (int, optional): Number of configurations to process in a batch before cooldown, defaults to 1
- **cooldown_seconds** (int, optional): Seconds to wait between batches, defaults to 1

#### Returns:
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

### `update_workflow_status_for_config`

Update workflow status for a single configuration.

```python
update_workflow_status_for_config(
    config: Dict[str, Any],
    days_back: int,
    batch_size: int,
    update_bigquery: bool
) -> Dict[str, Any]
```

#### Parameters:
- **config** (Dict[str, Any]): Configuration dictionary
- **days_back** (int): Number of days to look back for samples
- **batch_size** (int): Number of sample updates to batch together
- **update_bigquery** (bool): Whether to update BigQuery

#### Returns:
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

### `update_workflow_status`

Update terra_workflow_ids and states from Terra submissions.

```python
update_workflow_status(
    days_back: int = 30,
    batch_size: int = 100,
    update_bigquery: bool = True,
    config_batch_size: int = 4,
    cooldown_seconds: int = 1
) -> Dict[str, Any]
```

#### Parameters:
- **days_back** (int, optional): Number of days to look back for samples, defaults to 30
- **batch_size** (int, optional): Number of sample updates to batch together, defaults to 100
- **update_bigquery** (bool, optional): Whether to update BigQuery, defaults to True
- **config_batch_size** (int, optional): Number of configurations to process in a batch before cooldown, defaults to 4
- **cooldown_seconds** (int, optional): Seconds to wait between configuration batches, defaults to 1

#### Returns:
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
