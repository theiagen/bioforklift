# BigQuery Classes, Methods, and Usage

## Module: `bioforklift.bigquery`

Access these classes and operations using `from bioforklift.bigquery import BigQuery` as your import statement.

This module serves as the bridge between your application and Google BigQuery, providing capabilities to:

1. **Define and Create Tables**: Create tables with schemas using YAML definitions
2. **Manage Sample Data**: Track and process genomic samples with specialized operations
3. **Manage Configurations**: Store and retrieve workflow configurations
4. **Query and Update Data**: Perform bulk queries and updates
5. **Track System Values**: Maintain consistent tracking of system fields for data provenance

### Classes

- [BigQuery](#class-bigquery)
- [BigQueryClient](#class-bigqueryclient)
- [BigQuerySampleOperations](#class-bigquerysampleoperations)
- [BigQueryConfigOperations](#class-bigqueryconfigoperations)

---

## Important Notes

!!! info "Table Types"
    **Sample Tables**: This table type stores genomic sample data, including metadata and system-generated fields, such as those that track workflow status.

    **Configuration Tables**: This table type stores pipeline configurations that define how samples are processed.

    Both table types are supported by dedicated operation classes that provide specialized funcationality based on that table's purpose.

!!! info "Pre-existing Dataset Required"
    In order to use the BigQuery interface, you must have a pre-existing dataset in your Google Cloud Platform project. The dataset must be created before using the `BigQuery` class, as it does not create datasets automatically. 

    You can create a dataset using the Google Cloud Console or the `bq mk` command in the bq command-line tool. [See here for more details](https://cloud.google.com/bigquery/docs/datasets).

## Class: `BigQuery`

This class is the main interface for BigQuery operationsm, and provides a single access point to table operations and data loading. This is the main class you will use to interact with BigQuery. Any subclasses will be inherited from this class.

### Constructor

```python
BigQuery(
    project: str,
    dataset: str,
    credentials: Optional[Dict] = None,
    location: str = "us-central1"
)
```

#### Parameters

- **project** (str): GCP project ID
- **dataset** (str): BigQuery dataset name
- **credentials** (Optional[Dict]): Optional service account credentials dict
- **location** (str): BigQuery dataset location - default is 'us-central1'

#### Example Construction

```python
from bioforklift.bigquery import BigQuery

bq = BigQuery(
    project="your-project-id",
    dataset="your-dataset-name"
)
```

### Properties

- **project** (str): Get project ID
- **dataset** (str): Get dataset name
- **location** (str): Get dataset location

### Methods

#### `create_table`

Creates a new table from a YAML schema definition. This requires creating a YAML file that defines the schema of the table; see the [Schema Setup](../getting_started.md#setup-schemas-and-initialize-components) section for more details on how to set up a schema file.

```python
create_table(
    table_name: str, 
    schema_yaml: str, 
    exists_ok: bool = True
) -> Dict[str, Any]
```

**Returns:**

- Dict containing table and field attributes

_**Example**_

```python
# Create a samples table
bq.create_table(
    table_name="samples",
    schema_yaml="path/to/sample_schema.yaml",
    exists_ok=True
)

# Create a configurations table
bq.create_table(
    table_name="configs",
    schema_yaml="path/to/config_schema.yaml",
    exists_ok=True
)
```

#### `table_exists`

Checks if a table exists.

```python
table_exists(table_name: str) -> bool
```

**Returns:**

- True if the table exists, False otherwise

_**Example**_

```python
# Check if the samples table exists, if not, create it
if not bq.table_exists("samples"):
    bq.create_table(
        table_name="samples",
        schema_yaml="path/to/sample_schema.yaml"
    )
```

#### `get_sample_operations`

Gets the sample operations interface for a specific table.

```python
get_sample_operations(
    table_name: str,
    sample_schema_yaml: str
) -> BigQuerySampleOperations
```

**Returns:**

- A [BigQuerySampleOperations](#class-bigquerysampleoperations) instance

_**Example**_

```python
# Get sample operations interface
sample_ops = bq.get_sample_operations(
    table_name="samples",
    sample_schema_yaml="path/to/sample_schema.yaml"
)
```

#### `get_config_operations`

Gets the config operations interface for a specific table.

```python
get_config_operations(
    table_name: str,
    config_schema_yaml: str
) -> BigQueryConfigOperations
```

**Returns:**

- A [BigQueryConfigOperations](#class-bigquerysampleoperations) instance

_**Example**_

```python
# Get config operations interface
config_ops = bq.get_config_operations(
    table_name="configs",
    config_schema_yaml="path/to/config_schema.yaml"
)
```

---

## Class: `BigQueryClient`

!!! tip "Advanced Topics"
    **This class is used internally** by the BigQuery class to manage interactions with BigQuery. It is not typically used directly by users.

    However, it is available for advanced users who need to manage API interactions directly.

This class provides the base connection to Google BigQuery.

### Constructor

```python
BigQueryClient(
    project: str,
    dataset: str,
    credentials: Optional[str] = None,
    location: str = "us-central1"
)
```

#### Parameters

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

- Dictionary containing table and field attributes

#### `table_exists`

Checks if a table exists (offers the same functionality as the `BigQuery` class).

```python
table_exists(table_name: str) -> bool
```

**Returns:**

- True if the table exists, False otherwise

#### `insert_rows`

Inserts rows into a table using load job for immediate availability.

```python
insert_rows(table: str, rows: list) -> None
```

---

## Class: `BigQuerySampleOperations`

This class offers specialized methods for working with BigQuery tables containing sample data. Its construction is managed by the `get_sample_operations` function of the `BigQuery` class.

These methods can be called with the following format, where `sample_ops` is an instance of this class. [See the `get_sample_operations` method in the `BigQuery` class](#get_sample_operations) on how to generate this instance.

```python
sample_ops.<method_name>(<parameters>)
```

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

This method prepares a sample DataFrame by filtering duplicates and adding system-generated values.

```python
prepare_samples_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame
```

**Returns:**

- The prepared DataFrame ready for loading into BigQuery

_**Example**_

```python
# Prepare samples dataframe for upload to bigquery from external source
prepared_df = sample_ops.prepare_samples_dataframe(raw_df)
```

#### `get_sample_identifier_field`

Gets the field name marked as the sample_identifier in the schema.

```python
get_sample_identifier_field() -> Optional[str]
```

**Returns:**

- The name of the field, or None if not found

_**Example**_

```python
# Get the sample identifier field name
sample_identifier = sample_ops.get_sample_identifier_field()
```

#### `get_config_identifier_field`

Gets the field name marked as the config_identifier in the schema.

```python
get_config_identifier_field() -> Optional[str]
```

**Returns:**

- The name of the field, or None if not found

_**Example**_

```python
# Get the config identifier field name
config_identifier = sample_ops.get_config_identifier_field()
```

#### `get_sequence_file_fields`

Gets a list of the field names that are marked as sequence files in the schema.

```python
get_sequence_file_fields() -> List[str]
```

**Returns:**

- A list of the field names

_**Example**_

```python
# Get sequence file fields from the schema
sequence_fields = sample_ops.get_sequence_file_fields()
```

#### `get_sync_fields`

Gets a list of the field names that are marked as sync_field in the schema.

```python
get_sync_fields() -> List[str]
```

**Returns:**

- A List of the field names

_**Example**_

```python
# Get sync fields from the schema
sync_fields = sample_ops.get_sync_fields()
```

#### `apply_configuration_sourced_fields`

Applies the configuration values to the fields marked as "inherit from config" in a DataFrame of samples.

```python
apply_configuration_sourced_fields(
    dataframe: pd.DataFrame, 
    config: Dict[str, Any]
) -> pd.DataFrame
```

**Returns:**

- A DataFrame with configuration values applied to inheritance fields

_**Example**_

```python
# Retrieve configuration data
config = config_ops.get_config("config-123")
# Apply configuration sourced fields to a DataFrame
updated_df = sample_ops.apply_configuration_sourced_fields(raw_df, config_data)
```

#### `prepare_samples_with_config`

Prepares the samples with configuration applie which allows for inheritence patterns

```python
prepare_samples_with_config(
    dataframe: pd.DataFrame, 
    config: Dict[str, Any]
) -> pd.DataFrame
```

**Returns:**

- A DataFrame ready for upload with all validations and transformations applied

_**Example**_

```python
# Prepare samples with configuration applied, this allows for inhertence patterns
config = config_ops.get_config("config-123") # Retrieve a configuration using the config operations class (see below)
prepared_df = sample_ops.prepare_samples_with_config(raw_df, config)
```

#### `get_existing_identifiers`

Gets all existing sample identifiers from the table.

```python
get_existing_identifiers() -> List[str]
```

**Returns:**

- A List of the sample identifiers
  
_**Example**_

```python
# Get existing sample identifiers from the table
existing_ids = sample_ops.get_existing_identifiers()
```

#### `load_dataframe`

Loads a DataFrame into BigQuery table using load jobs.

```python
load_dataframe(
    dataframe: pd.DataFrame,
    schema: Optional[List[SchemaField]] = None,
    write_disposition: str = "WRITE_APPEND",
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]
```

**Returns:**

- A Dictionary with load results and their status
  
_**Example**_

```python
# Load samples into BigQuery
result = sample_ops.load_dataframe(prepared_df)
print(f"Loaded {result['loaded']} samples, filtered {result['filtered']} samples")

# Load samples into BigQuery using an explicit configuration
result = sample_ops.load_dataframe(
    dataframe=prepared_df,
    config=config
)
```

#### `append_dataframe`

Appends a DataFrame to an existing table.

```python
append_dataframe(
    dataframe: pd.DataFrame, 
    schema: Optional[List[SchemaField]] = None
) -> Dict[str, Any]
```

**Returns:**

- A dictionary with operation results

_**Example**_

```python
# Append a DataFrame to the existing samples table
result = sample_ops.append_dataframe(prepared_df, schema=sample_schema)
print(f"Appended {result['loaded']} samples to the table.")
```

#### `get_entity_id_mapping`

Gets a dictionary that maps the BigQuery UUIDs to their respective entity identifiers.

```python
get_entity_id_mapping() -> Dict[str, str]
```

**Returns:**

- A dictionary mapping BigQuery entity identifiers to UUIDs

_**Example**_

```python
# Get entity ID mapping from the samples table
entity_id_mapping = sample_ops.get_entity_id_mapping()
```

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

- A DataFrame containing the samples matching the timeframe criteria

_**Example**_

```python
# Get samples by timeframe
samples = sample_ops.get_samples_by_timeframe(
    timeframe="today",  # Options: "today", "yesterday", "week", "month", "custom", "hourly"
    uploaded_filter="not_uploaded",  # Options: "not_uploaded", "uploaded", "all"
    submitted_filter="not_submitted"  # Options: "not_submitted", "submitted", "all"
)
```

#### `get_samples_created_today`

Retrieves all samples that were created today but have not been uploaded yet.

```python
get_samples_created_today() -> pd.DataFrame
```

**Returns:**

- A DataFrame with today's samples

_**Example**_

```python
# Get samples created today
today_samples = sample_ops.get_samples_created_today()
```

#### `get_recent_samples_by_hour`

Retrieves any samples created within the last specified hours.

```python
get_recent_samples_by_hour(
    hours: int = 1, 
    uploaded_filter: str = "not_uploaded"
) -> pd.DataFrame
```

**Returns:**

- A DataFrame containing the samples from the last specified hours

_**Example**_

```python
# Get recent samples by hour
recent_samples = sample_ops.get_recent_samples_by_hour(hours=2)
```

#### `query_samples`

Executes a custom query against the samples table with flexible conditions.

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

- Either a pandas DataFrame or a list of dictionaries with query results

_**Example**_

```python
# Custom query for things we can't generalize for
custom_samples = sample_ops.query_samples(
    conditions=["workflow_state = @state", "created_at >= @date"],
    parameters={
        "state": "Succeeded", 
        "date": "2023-01-01"
    },
    fields=["id", "entity_identifier", "workflow_state"],
    limit=100
)

# Query to return all samples with a field that is not null
custom_samples = sample_ops.query_samples(fields=['id', 'other_field', 'third_field'], conditions=["third_field IS NOT NULL"])
```

#### `bulk_update_samples`

Bulk updates samples using a single query. Note that an update operation scales exponentially with the number of samples and items in the updates dictionary; it is recommended to lower the batch size if you are running into timeouts. The UUID field (`id`) is required in each update dictionary.

```python
bulk_update_samples(
    updates: List[Dict[str, Any]],
    batch_size: int = 1000
) -> Dict[str, Any]
```

**Returns:**

- A dictionary with update results

_**Example**_

```python
# Bulk update samples
updates = [
    {"id": "sample-1", "workflow_state": "Succeeded", "terra_workflow_id": "workflow-123"},
    {"id": "sample-2", "workflow_state": "Failed", "terra_workflow_id": "workflow-456"}
]
result = sample_ops.bulk_update_samples(updates)
print(f"Updated {result['updated_count']} samples")

## This example shows how to create the updates list from a DataFrame and then splits it into chunks for extremely large updates (for example, if performing a backfill operation on a large number of samples).

# Create the updates list from a DataFrame
updates = []
for idx, row in updated_samples.iterrows():
    update_dict = {'id': row['id'], 'new_field': row['new_field']} 
    updates.append(update_dict)

# Update the samples in BigQuery using chunks and batch_size
chunk_size = 100
for i in range(0, len(updates), chunk_size):
    chunk = updates[i:i + chunk_size]
    
    print(f"Updating {len(chunk)} samples in BigQuery")
    update_result = bq_sample_ops.bulk_update_samples(chunk, batch_size=chunk_size)
    print(f"Updated {update_result.get('updated_count', 0)} samples with workflow information")
```

#### `get_unique_submission_ids`

Gets the unique Terra submission IDs for samples associated with a configuration; this is a helper function for updating workflow states and may be unlikely to use individually.

```python
get_unique_submission_ids(
    config_id: str,
    need_workflow_id: bool = True,
    days_back: int = 30
) -> List[str]
```

**Returns:**

- A list of unique submission IDs

_**Example**_

```python
# get unique submission IDs for a particular configuration
submission_ids = sample_ops.get_unique_submission_ids(
    config_id="config-123",
    need_workflow_id=True,
    days_back=30
)
```

#### `get_samples_by_entity_names`

Gets the samples that match specific entity names for a configuration, where entity_name refers to the source Terra table.

```python
get_samples_by_entity_names(
    config_id: str,
    entity_names: List[str]
) -> pd.DataFrame
```

**Returns:**

- A DataFrame containing matched samples

_**Example**_

```python
# Get samples by entity names
entity_samples = sample_ops.get_samples_by_entity_names(
    config_id="config-123",
    entity_names=["ENTITY1", "ENTITY2", "ENTITY3"]
)
```

#### `get_incomplete_workflow_samples`

Gets any samples with incomplete workflow states (where workflow state is not one of Succeeded, Failed, or Aborted)

```python
get_incomplete_workflow_samples(
    config_id: str,
    days_back: int = 30,
    limit: int = 1000
) -> pd.DataFrame
```

**Returns:**

- A DataFrame containing samples with incomplete workflow states

_**Example**_

```python
# Get incomplete workflow samples
incomplete = sample_ops.get_incomplete_workflow_samples(
    config_id="config-123",
    days_back=7
)
```

#### `get_workflow_state_summary`

Gets a summary of all the workflow states for a configuration.

```python
get_workflow_state_summary(
    config_id: str
) -> Dict[str, int]
```

**Returns:**

- A Dictionary mapping workflow states to counts

_**Example**_

```python
# Get workflow state summary for a configuration
workflow_summary = sample_ops.get_workflow_state_summary(
    config_id="config-123"
)
print(workflow_summary)
# Succeeded: 100, Failed: 5, Aborted: 2, In Progress: 10
```

---

## Class: `BigQueryConfigOperations`

This class offers specialized methods for working with BigQuery tables containing configuration data. Its construction is managed by the `get_config_operations` function of the `BigQuery` class.

These methods can be called with the following format, where `config_ops` is an instance of this class. [See the `get_config_operations` method in the `BigQuery` class](#get_config_operations) on how to generate this instance.

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

Gets the field name that is marked with `use_as_prefix=True`.

```python
get_prefix_fields() -> str
```

**Returns:**

- A String with the name of the field to be used as prefix

_**Example**_

```python
# Get the field marked with use_as_prefix
prefix_field = config_ops.get_prefix_fields()
```

#### `get_alerts_display_field`

Gets the field name that is marked with `display_for_alerts=True`.

```python
get_alerts_display_field() -> str
```

**Returns:**

- A String with the name of the field to be used as display for alerts

_**Example**_

```python
# Get the field marked for display in alerts
display_field = config_ops.get_alerts_display_field()
```

#### `create_config`

Create a new configuration entry in the configurations table. This method can accept a JSON file path or a dictionary containing the configuration data. The configuration must include all required fields as defined in the configs table schema.

```python
create_config(
    config_data: Union[Dict[str, Any], str, Path]
) -> Dict[str, Any]
```

**Returns:**

- A Dictionary with created configuration including ID (uuid)

_**Example**_

```python
# Create a configuration from a dictionary
new_config = config_ops.create_config({
    "name": "Test Configuration",
    "state": "California",
    "prefix": "test_sample",
    "entity_type": "sample",
    "terra_source_project": "your-terra-project",
    "terra_source_workspace": "your-terra-workspace",
    "terra_destination_project": "your-terra-project",
    "terra_destination_workspace": "your-terra-workspace",
    "active": True,
    "terra_analysis_method": "Illumina_PE",
    "terra_method_config": json.dumps({
        "methodConfigurationNamespace": "namespace",
        "methodConfigurationName": "name",
        "entityType": "sample_set",
        "entityName": "template",
        "expression": "this.samples",
        "useCallCache": True,
        "deleteIntermediateOutputFiles": True,
        "useReferenceDisks": True,
        "memoryRetryMultiplier": 1.0,
        "workflowFailureMode": "NoNewCalls",
        "userComment": "Automated submission"
    }),
    "config_url": "https://example.com/config",
    "config_version": "v1.0"
})

# Create a configuration from a JSON file
new_config = config_ops.create_config("path/to/config.json")
```

#### `create_configs_from_directory`

Creates multiple configurations from all matching JSON files in a directory.

```python
create_configs_from_directory(
    directory_path: Union[str, Path], 
    pattern: str = "*.json"
) -> List[Dict[str, Any]]
```

**Returns:**

- A list of created configurations

_**Example**_

```python
# Create configurations from all JSON files in a directory
configs = config_ops.create_configs_from_directory(
    directory_path="path/to/configs",
    pattern="*.json"
)
```

#### `get_config`

Gets a single configuration by its configuration_identifier ID.

```python
get_config(config_id: str) -> Optional[Dict[str, Any]]
```

**Returns:**

- The config's configuration dictionary, or None if not found

_**Example**_

```python

# Get a single configuration by ID
config = config_ops.get_config("config-123")
```

#### `get_configs`

Gets all configurations with optional filtration.

```python
get_configs(
    active_only: bool = False, 
    entity_type: Optional[str] = None,
    skip_transferred: bool = False,
) -> List[Dict[str, Any]]
```

**Returns:**

- A list of configuration dictionaries

_**Example**_

```python
# Get all configurations
all_configs = config_ops.get_configs()

# Get active configurations only
active_configs = config_ops.get_configs(active_only=True)

# Get configurations by entity type
entity_configs = config_ops.get_configs(
    active_only=True,
    entity_type="sample"
)
```

#### `update_config`

Updates an existing configuration.

```python
update_config(
    config_id: str, 
    update_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]
```

**Returns:**

- The updated configuration, or None if the config was not found

_**Example**_

```python
# Update a configuration
updated_config = config_ops.update_config(
    config_id="config-123",
    update_data={
        "config_version": "v1.1",
        "active": False
    }
)
```

#### `delete_config`

Deletes a configuration.

```python
delete_config(config_id: str) -> bool
```

**Returns:**

- True if deleted successfully, False if not

_**Example**_

```python
# Delete a configuration
deleted = config_ops.delete_config("config-123")
if deleted:
    print("Configuration deleted successfully.")
else:
    print("Configuration not found or could not be deleted.")
```

#### `load_configs_dataframe`

Loads a DataFrame of configurations into BigQuery table.

```python
load_configs_dataframe(
    dataframe: pd.DataFrame,
    schema: Optional[List[SchemaField]] = None,
    write_disposition: str = "WRITE_APPEND"
) -> Dict[str, Any]
```

**Returns:**

- A dictionary with load results

_**Example**_

```python
# example DataFrame for configurations
config_df = pd.DataFrame({
    "name": ["Test Config 1", "Test Config 2"],
    "state": ["California", "Texas"],
    "prefix": ["test1", "test2"],
    "entity_type": ["sample", "sample"],
    "terra_source_project": ["terra-project-1", "terra-project-2"],
    "terra_source_workspace": ["workspace-1", "workspace-2"],
    "terra_destination_project": ["terra-project-1", "terra-project-2"],
    "terra_destination_workspace": ["workspace-1", "workspace-2"],
    "active": [True, True],
    "terra_analysis_method": ["Illumina_PE", "Illumina_PE"],
    "terra_method_config": [json.dumps({"methodConfigurationNamespace": "namespace1", "methodConfigurationName": "name1", ...}), json.dumps({"methodConfigurationNamespace": "namespace2", "methodConfigurationName": "name2", ...})],
    "config_url": ["https://example.com/config1", "https://example.com/config2"],
    "config_version": ["v1.0", "v1.0"]
})
# Load configurations DataFrame into BigQuery
result = config_ops.load_configs_dataframe(
    dataframe=config_df,
    schema=config_schema
)
```

#### `deactivate_configs`

Deactivates any configurations that match the specific filters.

```python
deactivate_configs(filters: Dict[str, Any]) -> Dict[str, Any]
```

**Returns:**

- A dictionary with deactivation results

_**Example**_

```python
# Deactivate configurations by filter
result = config_ops.deactivate_configs(
    filters={
        "entity_type": "sample",
        "state": "California"
    }
)
print(f"Deactivated {result['deactivated_count']} configurations")
```

## Complete Workflow Example


```python
from bioforklift.bigquery import BigQuery
import pandas as pd

# Initialize BigQuery
bq = BigQuery(
    project="your-project-id",
    dataset="your-dataset-name"
)

# Get operation interfaces
sample_ops = bq.get_sample_operations(
    table_name="samples",
    sample_schema_yaml="path/to/sample_schema.yaml"
)
config_ops = bq.get_config_operations(
    table_name="configs",
    config_schema_yaml="path/to/config_schema.yaml"
)

# Create sample data
data = {
    "entity_identifier": ["SAMPLE1", "SAMPLE2", "SAMPLE3"],
    "read1": ["gs://bucket/sample1_R1.fastq", "gs://bucket/sample2_R1.fastq", "gs://bucket/sample3_R1.fastq"],
    "read2": ["gs://bucket/sample1_R2.fastq", "gs://bucket/sample2_R2.fastq", "gs://bucket/sample3_R2.fastq"],
    "upload_date": ["2023-03-15", "2023-03-15", "2023-03-15"]
}
df = pd.DataFrame(data)

# Get an active configuration
config = config_ops.get_configs(active_only=True)[0]

# Prepare and load samples
prepared_df = sample_ops.prepare_samples_with_config(df, config)
load_result = sample_ops.load_dataframe(prepared_df, config=config)
print(f"Loaded {load_result['loaded']} samples")

# Get samples that haven't been uploaded yet
not_uploaded = sample_ops.get_samples_by_timeframe(
    timeframe="today",
    uploaded_filter="not_uploaded",
    config_id=config["id"]
)
print(f"Found {len(not_uploaded)} samples ready for upload")
```

## Troubleshooting

### Common Issues

??? question "Schema Definition Errors"
    **Problem**: Errors when creating tables from schema

    **Solution**: 

    - Ensure your YAML file follows the correct format
    - Check for required fields 
    - Validate special attributes are used correctly
    - Look for syntax errors in the YAML file

??? question "Data Loading Failures"
    **Problem**: Unable to load data into BigQuery

    **Solution**:

    - Check that DataFrame columns match the schema definition
    - Ensure required fields have values
    - Look for type mismatches (can be common with ids being Int/Str coming from Terra)

??? question "Missing System Values"
    **Problem**: System tracking fields not being updated

    **Solution**:

    - Ensure fields are marked with `system_value: true` in schema
    - Use the `prepare_samples_dataframe` method before loading
    - Check if bulk updates include the correct ID field
    - Verify system fields are defined with correct types
    