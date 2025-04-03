# BigQuery Classes and Methods

## Module: `forklift.bigquery`

### Classes

- [BigQuery](#class-bigquery)
- [BigQueryClient](#class-bigqueryclient)
- [BigQuerySampleOperations](#class-bigquerysampleoperations)
- [BigQueryConfigOperations](#class-bigqueryconfigoperations)

---

## Class: `BigQuery`

Main interface for BigQuery operations. Provides a single access point to table operations and data loading. For both samples and configurations.

### Constructor

```python
BigQuery(
    project: str,
    dataset: str,
    credentials: Optional[Dict] = None,
    location: str = "us-central1"
)
```

#### Parameters:
- **project** (str): GCP project ID
- **dataset** (str): BigQuery dataset name
- **credentials** (Optional[Dict]): Optional service account credentials dict
- **location** (str): BigQuery dataset location - default is 'us-central1'

### Properties

- **project** (str): Get project ID
- **dataset** (str): Get dataset name
- **location** (str): Get dataset location

### Methods

#### `create_table`

Create a new table from YAML schema definition.

```python
create_table(
    table_name: str, 
    schema_yaml: str, 
    exists_ok: bool = True
) -> Dict[str, Any]
```

**Returns:**
- Dict containing table and field attributes

#### `table_exists`

Check if a table exists.

```python
table_exists(table_name: str) -> bool
```

**Returns:**
- True if the table exists, False otherwise

#### `get_sample_operations`

Get a sample operations interface for a specific table.

```python
get_sample_operations(
    table_name: str,
    sample_schema_yaml: str
) -> BigQuerySampleOperations
```

**Returns:**
- BigQuerySampleOperations instance

#### `get_config_operations`

Get a config operations interface for a specific table.

```python
get_config_operations(
    table_name: str,
    config_schema_yaml: str
) -> BigQueryConfigOperations
```

**Returns:**
- BigQueryConfigOperations instance

---

## Class: `BigQueryClient`

Base client for BigQuery operations.

### Constructor

```python
BigQueryClient(
    project: str,
    dataset: str,
    credentials: Optional[str] = None,
    location: str = "us-central1"
)
```

#### Parameters:
- **project** (str): GCP project ID
- **dataset** (str): BigQuery dataset name
- **credentials** (Optional[str]): Optional service account credentials JSON string
- **location** (str): BigQuery dataset location - default is 'us-central1'

### Methods

#### `create_table_from_yaml`

Create a BigQuery table using schema defined in YAML.

```python
create_table_from_yaml(
    table_name: str, 
    schema_yaml: str, 
    exists_ok: bool = True
) -> Dict[str, Any]
```

**Returns:**
- Dict containing table and field attributes

#### `table_exists`

Check if a table exists.

```python
table_exists(table_name: str) -> bool
```

**Returns:**
- True if the table exists, False otherwise

#### `insert_rows`

Insert rows into a table using load job for immediate availability.

```python
insert_rows(table: str, rows: list) -> None
```

---

## Class: `BigQuerySampleOperations`

Operations for BigQuery tables containing sample data.

### Constructor

```python
BigQuerySampleOperations(
    client: "BigQueryClient",
    table_name: str,
    sample_schema_yaml: Optional[str] = None,
    sample_schema: Optional[List[SchemaField]] = None,
    location: str = "us-central1"
)
```

### Methods

#### `prepare_samples_dataframe`

Prepare DataFrame by filtering duplicates and adding system-generated values.

```python
prepare_samples_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame
```

**Returns:**
- Prepared DataFrame ready for loading into BigQuery

#### `get_sample_identifier_field`

Get the field name marked as sample_identifier.

```python
get_sample_identifier_field() -> Optional[str]
```

**Returns:**
- Field name or None if not found

#### `get_config_identifier_field`

Get the field name marked as config_identifier.

```python
get_config_identifier_field() -> Optional[str]
```

**Returns:**
- Field name or None if not found

#### `get_sequence_file_fields`

Get list of field names that are marked as sequence files in the schema.

```python
get_sequence_file_fields() -> List[str]
```

**Returns:**
- List of field names

#### `get_sync_fields`

Get fields marked as sync_field in the schema.

```python
get_sync_fields() -> List[str]
```

**Returns:**
- List of field names that have sync_field: true

#### `apply_configuration_sourced_fields`

Apply configuration values to fields in a DataFrame of samples.

```python
apply_configuration_sourced_fields(
    dataframe: pd.DataFrame, 
    config: Dict[str, Any]
) -> pd.DataFrame
```

**Returns:**
- DataFrame with configuration values applied to inheritance fields

#### `prepare_samples_with_config`

Full preparation of samples with configuration applied.

```python
prepare_samples_with_config(
    dataframe: pd.DataFrame, 
    config: Dict[str, Any]
) -> pd.DataFrame
```

**Returns:**
- DataFrame ready for upload with all validations and transformations applied

#### `get_existing_identifiers`

Get all existing sample identifiers from the table.

```python
get_existing_identifiers() -> List[str]
```

**Returns:**
- List of identifiers for ease of use

#### `load_dataframe`

Load DataFrame into BigQuery table using load jobs.

```python
load_dataframe(
    dataframe: pd.DataFrame,
    schema: Optional[List[SchemaField]] = None,
    write_disposition: str = "WRITE_APPEND",
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]
```

**Returns:**
- Dictionary with load results and status

#### `append_dataframe`

Append DataFrame to existing table.

```python
append_dataframe(
    dataframe: pd.DataFrame, 
    schema: Optional[List[SchemaField]] = None
) -> Dict[str, Any]
```

**Returns:**
- Dictionary with operation results

#### `get_entity_id_mapping`

Get a mapping between BigQuery UUIDs and entity identifiers.

```python
get_entity_id_mapping() -> Dict[str, str]
```

**Returns:**
- Dictionary mapping BigQuery entity identifiers to UUIDs

#### `get_samples_by_timeframe`

Retrieves samples based on a configurable timeframe.

```python
get_samples_by_timeframe(
    timeframe: str = "today",
    days_back: int = None,
    hours_back: int = None,
    start_datetime: str = None, 
    end_datetime: str = None,
    uploaded_filter: str = "not_uploaded",
    submitted_filter: str = "not_submitted",
    config_id: str = None, 
    set_name: str = None
) -> pd.DataFrame
```

**Returns:**
- DataFrame containing the samples matching the timeframe criteria

#### `get_samples_created_today`

Retrieves all samples that were created today but have not been uploaded yet.

```python
get_samples_created_today() -> pd.DataFrame
```

**Returns:**
- DataFrame with today's samples

#### `get_recent_samples_by_hour`

Retrieves samples created within the last specified hours.

```python
get_recent_samples_by_hour(
    hours: int = 1, 
    uploaded_filter: str = "not_uploaded"
) -> pd.DataFrame
```

**Returns:**
- DataFrame containing the samples from the last specified hours

#### `bulk_update_samples`

Bulk update samples using a single query.

```python
bulk_update_samples(updates: List[Dict[str, Any]]) -> Dict[str, Any]
```

**Returns:**
- Dictionary with update results

#### `query_samples`

Execute a custom query against the samples table with flexible conditions.

```python
query_samples(
    conditions: List[str] = None,
    parameters: Dict[str, Any] = None,
    fields: List[str] = None,
    order_by: str = "created_at DESC",
    limit: int = None,
    return_as_df: bool = True
) -> Union[pd.DataFrame, List[Dict[str, Any]]]
```

**Returns:**
- Either pandas DataFrame or list of dictionaries with query results

#### `get_unique_submission_ids`

Get unique Terra submission IDs for samples associated with a configuration.

```python
get_unique_submission_ids(
    config_id: str,
    need_workflow_id: bool = True,
    days_back: int = 30
) -> List[str]
```

**Returns:**
- List of unique submission IDs

#### `get_samples_by_entity_names`

Get samples matching specific entity names for a configuration.

```python
get_samples_by_entity_names(
    config_id: str,
    entity_names: List[str]
) -> pd.DataFrame
```

**Returns:**
- DataFrame containing matched samples

#### `get_incomplete_workflow_samples`

Get samples with incomplete workflow states.

```python
get_incomplete_workflow_samples(
    config_id: str,
    days_back: int = 30,
    limit: int = 1000
) -> pd.DataFrame
```

**Returns:**
- DataFrame containing samples with incomplete workflow states

#### `get_workflow_state_summary`

Get a summary of workflow states for a configuration.

```python
get_workflow_state_summary(
    config_id: str
) -> Dict[str, int]
```

**Returns:**
- Dictionary mapping workflow states to counts

---

## Class: `BigQueryConfigOperations`

Operations for BigQuery tables containing configuration data.

### Constructor

```python
BigQueryConfigOperations(
    client: "BigQueryClient",
    table_name: str,
    config_schema_yaml: Optional[str] = None,
    config_schema: Optional[List[SchemaField]] = None,
    location: str = "us-central1"
)
```

### Methods

#### `get_prefix_fields`

Get the field name that is marked with use_as_prefix=True.

```python
get_prefix_fields() -> str
```

**Returns:**
- String with the name of the field to be used as prefix

#### `get_alerts_display_field`

Get the field name that is marked with display_for_alerts=True.

```python
get_alerts_display_field() -> str
```

**Returns:**
- String with the name of the field to be used as display for alerts

#### `create_config`

Create a new configuration.

```python
create_config(
    config_data: Union[Dict[str, Any], str, Path]
) -> Dict[str, Any]
```

**Returns:**
- Dictionary with created configuration including ID (uuid)

#### `create_configs_from_directory`

Create multiple configurations from JSON files in a directory.

```python
create_configs_from_directory(
    directory_path: Union[str, Path], 
    pattern: str = "*.json"
) -> List[Dict[str, Any]]
```

**Returns:**
- List of created configurations

#### `get_config`

Get a single configuration by ID.

```python
get_config(config_id: str) -> Optional[Dict[str, Any]]
```

**Returns:**
- Configuration dictionary or None if not found

#### `get_configs`

Get configurations with optional filters.

```python
get_configs(
    active_only: bool = False, 
    entity_type: Optional[str] = None,
    skip_transferred: bool = False,
) -> List[Dict[str, Any]]
```

**Returns:**
- List of configuration dictionaries

#### `update_config`

Update a configuration.

```python
update_config(
    config_id: str, 
    update_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]
```

**Returns:**
- Updated configuration or None if not found

#### `delete_config`

Delete a configuration.

```python
delete_config(config_id: str) -> bool
```

**Returns:**
- True if deleted successfully

#### `load_configs_dataframe`

Load DataFrame of configurations into BigQuery table.

```python
load_configs_dataframe(
    dataframe: pd.DataFrame,
    schema: Optional[List[SchemaField]] = None,
    write_disposition: str = "WRITE_APPEND"
) -> Dict[str, Any]
```

**Returns:**
- Dictionary with load results

#### `deactivate_configs`

Deactivate configurations matching filters.

```python
deactivate_configs(filters: Dict[str, Any]) -> Dict[str, Any]
```

**Returns:**
- Dictionary with deactivation results