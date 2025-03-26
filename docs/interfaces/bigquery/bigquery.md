# BigQuery Subsystem

## Overview

The BigQuery subsystem provides a guideline based approach to interacting with and managing data and data schemas for data being stored in bigquery. 

## Purpose and Functionality

The BigQuery subsystem serves as the bridge between your application and Google BigQuery, providing capabilities to:

1. **Define and Create Tables**: Create tables with schemas using YAML definitions
2. **Manage Sample Data**: Track and process genomic samples with specialized operations
3. **Manage Configurations**: Store and retrieve workflow configurations
4. **Query and Update Data**: Perform bulk queries and updates
5. **Track System Values**: Maintain consistent tracking of system fields for data provenance

## Core Concepts

### Tables and Operations

The BigQuery subsystem is built around two primary table types, each with specialized operations:

???+ info "Table Types"
    **Sample Tables**: Store genomic sample data with tracking fields for workflow status
    
    **Configuration Tables**: Store pipeline configurations that define how samples are processed

Both table types are supported by dedicated operation classes that provide specialized functionality based on the table's purpose.

??? example "Use Case Example"
    A common scenario is to:
    
    1. Create tables for samples and configurations
    2. Load sample data from a data source (i.e. Terra)
    3. Prepare samples by filtering out duplicates and adding system values
    4. Apply configuration settings to samples
    5. Track sample processing status with system fields

### Schema Definitions

The BigQuery class uses YAML-based schema definitions to create tables with specialized field attributes:

```yaml
fields:
  id:
    type: string
    required: true
    description: Unique identifier for the record
    primary_key: true
    system_value: true
  
  entity_identifier:
    type: string
    required: true
    column_mappings: ["entity:data_id"]
    description: External entity identifier
    sample_identifier: true
```

These schema definitions support special attributes that control behavior:

- `primary_key`: Indicates primary key fields (system generates UUID for items going into a BQ table)
- `system_value`: Fields managed by the BigQuery system, but are not desired outside of BigQuery (i.e. created_at, updated_at, etc)
- `sample_identifier`: Unifying field that identifies sample entities (from Terra could come from many entity types)
- `config_identifier`: Field that links samples to configurations, meant for data provenence
- `sequence_file`: Fields containing sequence file gs uri paths (gs:/path/to/fastq)
- `sync_field`: Fields to synchronize between source and destination, for example metadata that might later be uploaded to the source workspace like gisaid upload_date and submission_id
- `column_mappings`: Map between BigQuery column names source data naming, for example coming from Terra a column maybe be sample_id, but in our internal database falls under `entity_identifier`
- `inherit_from_config`: Fields that inherit values from configuration

## BigQuery Client

The `BigQueryClient` class provides the base connection to Google BigQuery.

### Key Operations

#### Setting Up Interface to BigQuery

The constructor will be set up using a GCP `project` and `dataset` name. If you're using a service account, provide the credentials.

```python
from forklift.bigquery import BigQuery

bq = BigQuery(
    project="your-project-id",
    dataset="your-dataset-name",
    location="us-central1"  # Optional, defaults to us-central1
)
```

If you need to use service account credentials:

```python
import json

# Load credentials from file
with open("path/to/service-account.json", "r") as f:
    credentials = json.load(f)

bq = BigQuery(
    project="your-project-id",
    dataset="your-dataset-name",
    credentials=credentials
)
```

#### Creating Tables

Tables are created using YAML schema definitions:

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

#### Checking if Tables Exist

```python
# Check if a table exists before creating it
if not bq.table_exists("samples"):
    bq.create_table(
        table_name="samples",
        schema_yaml="path/to/sample_schema.yaml"
    )
```

#### Getting Operation Interfaces

```python
# Get sample operations interface
sample_ops = bq.get_sample_operations(
    table_name="samples",
    sample_schema_yaml="path/to/sample_schema.yaml"
)

# Get config operations interface
config_ops = bq.get_config_operations(
    table_name="configs",
    config_schema_yaml="path/to/config_schema.yaml"
)
```

## Sample Operations

The `BigQuerySampleOperations` class provides specialized methods for working with sample data.

### Key Operations

#### Preparing Sample Data

```python
# Prepare samples dataframe for upload to bigquery from external source
prepared_df = sample_ops.prepare_samples_dataframe(raw_df)

# Prepare samples with configuration applied, this allows for inhertence patterns
config = config_ops.get_config("config-123")
prepared_df = sample_ops.prepare_samples_with_config(raw_df, config)
```

#### Loading Samples

```python
# Load samples into BigQuery
result = sample_ops.load_dataframe(prepared_df)
print(f"Loaded {result['loaded']} samples, filtered {result['filtered']}")

# Load with explicit configuration
result = sample_ops.load_dataframe(
    dataframe=prepared_df,
    config=config
)
```

#### Querying Samples

```python
# Get samples created today
today_samples = sample_ops.get_samples_created_today()

# Get samples by timeframe
samples = sample_ops.get_samples_by_timeframe(
    timeframe="today",  # Options: "today", "yesterday", "week", "month", "custom", "hourly"
    uploaded_filter="not_uploaded",  # Options: "not_uploaded", "uploaded", "all"
    submitted_filter="not_submitted"  # Options: "not_submitted", "submitted", "all"
)

# Get recent samples by hour
recent_samples = sample_ops.get_recent_samples_by_hour(hours=2)

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
```

#### Updating Samples

```python
# Bulk update samples
updates = [
    {"id": "sample-1", "workflow_state": "Succeeded", "terra_workflow_id": "workflow-123"},
    {"id": "sample-2", "workflow_state": "Failed", "terra_workflow_id": "workflow-456"}
]
result = sample_ops.bulk_update_samples(updates)
print(f"Updated {result['updated_count']} samples")
```

#### Working with Workflows

```python
# Get unique submission IDs, helper function for when updating workflow states
submission_ids = sample_ops.get_unique_submission_ids(
    config_id="config-123",
    need_workflow_id=True,
    days_back=30
)

# Get samples by entity names
entity_samples = sample_ops.get_samples_by_entity_names(
    config_id="config-123",
    entity_names=["ENTITY1", "ENTITY2", "ENTITY3"]
)

# Get incomplete workflow samples (where workflow state is not one of Succeeded,Failed,Aborted)
incomplete = sample_ops.get_incomplete_workflow_samples(
    config_id="config-123",
    days_back=7
)

```

## Configuration Operations

The `BigQueryConfigOperations` class provides specialized methods for working with configuration data.

### Key Operations

#### Creating Configurations

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

# Create configurations from a directory
configs = config_ops.create_configs_from_directory(
    directory_path="path/to/configs",
    pattern="*.json"
)
```

#### Retrieving Configurations

```python
# Get a single configuration by ID
config = config_ops.get_config("config-123")

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

#### Updating Configurations

```python
# Update a configuration
updated_config = config_ops.update_config(
    config_id="config-123",
    update_data={
        "config_version": "v1.1",
        "active": False
    }
)

# Deactivate configurations by filter
result = config_ops.deactivate_configs(
    filters={
        "entity_type": "sample",
        "state": "California"
    }
)
print(f"Deactivated {result['deactivated_count']} configurations")
```

#### Special Field Getters

```python
# Get the field marked with use_as_prefix
prefix_field = config_ops.get_prefix_fields()

# Get the field marked for display in alerts
display_field = config_ops.get_alerts_display_field()
```

## System Values

The BigQuery subsystem maintains several system-managed fields that track the status and history of each sample:

???+ info "System Fields"
    | Field Name | Description |
    |------------|-------------|
    | `id` | Primary UUID for the record in BigQuery |
    | `created_at` | When the record was first created |
    | `updated_at` | When the record was last updated |
    | `uploaded_at` | When the sample was uploaded to external system |
    | `submitted_at` | When the sample was submitted to a workflow |
    | `upload_source` | Source of the upload (e.g., entity set name) |
    | `terra_submission_id` | External submission ID |
    | `terra_workflow_id` | External workflow ID |
    | `workflow_state` | Current state of the workflow |

These system fields are automatically managed by the BigQuerySampleOperations class and should be marked with `system_value: true` in your schema definitions.

## Architecture Details

The BigQuery subsystem consists of the following components:

1. **BigQuery**: Main interface class that constructs BigQueryClient, Sample, and Config operations
2. **BigQueryClient**: Base client for API requests to BigQuery
3. **BigQuerySampleOperations**: Handles sample data operations
4. **BigQueryConfigOperations**: Handles configuration operations
5. **Utils**: Utility functions for schema management and data transformations


## Complete Workflow Example

```python
from forklift.bigquery import BigQuery
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
    - Look for type mismatches

??? question "Missing System Values"
    **Problem**: System tracking fields not being updated
    
    **Solution**:
    - Ensure fields are marked with `system_value: true` in schema
    - Use the `prepare_samples_dataframe` method before loading
    - Check if bulk updates include the correct ID field
    - Verify system fields are defined with correct types