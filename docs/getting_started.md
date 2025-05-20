# Getting Started with bioforklift

This guide will help you install and set up bioforklift, and demonstrate basic usage.

## Prerequisites

Before using bioforklift, ensure you have:

1. Python 3.9 or higher
2. Access to Google Cloud Platform (GCP) and BigQuery
3. Access to Terra workspace(s)
4. Appropriate permissions for both platforms

## Installation

You can install bioforklift using pip:
```bash
pip install bioforklift
```

Or install from source:

```bash
git clone https://github.com/theiagen/bioforklift.git
cd bioforklift
pip install -e .
```

## Authentication

### Google Cloud Authentication

bioforklift requires authentication to access Google Cloud and Terra. There are two main methods for authentication:

1. **Using Application Default Credentials**:

```bash
gcloud auth application-default login
```

2. **Using a Service Account Key**:

```python
# You can provide a path to your service account JSON key file
google_credentials_json = "path/to/your/service-account-key.json"
```

### Terra Authentication

Authentication for Terra is handled through the same Google credentials used for BigQuery.

## Setup and Configuration

bioforklift uses YAML-based schema definitions to configure BigQuery tables. Below are examples of the two main schema types used in the system.

### 1. Create Schema Files

#### Sample Schema

This schema defines the structure of sample data, including genomic samples and their metadata.

???+ info "Schema Attributes (click to collapse)"
    For each field in the schema, you can define various attributes to control its behavior:

    | Field Name | Description |
    |------------|-------------|
    | `type` | **Required**; specifies the data type of the field (e.g., string, integer, boolean, datetime, etc.)[^1] |
    | `required` | Indicates whether the field is mandatory. If set to `true`, NULL values are not permitted. |
    | `description` | Provides a description of the field |
    | `primary_key` | Identifies the primary key field that will be auto-populated with a UUID |
    | `sample_identifier` | Identifies the field that contains the sample identifier in Terra[^2] |
    | `column_mappings` | If the field name in BigQuery is different from the column name in Terra, you can specify the mapping here[^3] |
    | `sequence_file` | This is typically used for read data (e.g., `read1` and `read2`)[^4] |
    | `system_value` | Indicates that this field is managed by bioforklift and are not uploaded to Terra. |
    | `inherit_from_config` | Indicates that this field should be inherited from the configuration schema |
    | `configuration_identifier` | Indicates that this field contains the configuration identifier |
    | `metadata` | Indicates the field contains sample metadata |
    | `sync_field` | Indicates that this field should be synchronized between BigQuery and Terra |

[^1]:
    [These values correspond to specific datatypes that are accepted by BigQuery](https://cloud.google.com/bigquery/docs/schemas#standard_sql_data_types).
[^2]:
    This field is typically the sample name in Terra (e.g., `entity:data_id`). This field can be the name of the specific data table, or a generic name depending on data sources (multi-tables vs singular)
[^3]:
    This describes how the field will be named when downloaded from Terra; typically used for `entity:data_id` to convert into `data_id` so the `entity:` prefix is not included in BigQuery.
[^4]:
    If this is indicated, any rows that do not have an associated file for this field will be ignored and filtered out of BigQuery.

??? tip "Accepted Data Types for the `type` field (click to expand)"
    | user-provided value for `type` | The associated BigQuery type |
    |------------------|--------------------------|
    | string           | STRING                   |
    | str              | STRING                   |
    | integer          | INTEGER                  |
    | int              | INTEGER                  |
    | float            | FLOAT                    |
    | boolean          | BOOLEAN                  |
    | bool             | BOOLEAN                  |
    | datetime         | DATETIME                 |
    | date             | DATE                     |
    | timestamp        | TIMESTAMP                |
    | record           | RECORD                   |
    | array            | ARRAY                    |
    | object           | JSON                     |
    | json             | JSON                     |

??? example "Example Sample Schema (click to expand)"
    ```yaml
    # example_sample_schema.yaml
    fields:
      id:
        type: string
        required: true
        description: Unique identifier for the record
        primary_key: true  # This field will be auto-populated with UUID
        system_value: true

      entity_identifier:
        type: string
        required: true
        column_mappings: ["entity:data_id"]
        description: External entity identifier
        sample_identifier: true
    
      config_id:
        type: string
        description: Configuration ID
        inherit_from_config: id
        configuration_identifier: true
        system_value: true
    
      read1:
        type: string
        description: Read 1 sequence
        sequence_file: true
    
      read2:
        type: string
        description: Read 2 sequence
        sequence_file: true
    
      upload_date:
        type: string
        description: Date of sample collection
        metadata: true
        sync_field: true
      
      # System fields that will not be included in Terra operations
      created_at:
        type: datetime
        required: true
        description: Record creation timestamp
        system_value: true
        
      updated_at:
        type: datetime
        description: Last update datetime
        system_value: true
    
      uploaded_at:
        type: datetime
        description: Date of sample upload
        system_value: true
    
      submitted_at:
        type: datetime
        description: Date of sample submission
        system_value: true
    
      upload_source:
        type: string
        description: Source of sample upload
        system_value: true
    
      terra_submission_id:
        type: string
        description: Terra submission ID
        system_value: true
    
      terra_workflow_id:
        type: string
        description: Terra workflow submission ID
        system_value: true
        
      workflow_state:
        type: string
        description: Current state of the workflow
        system_value: true
    ```

#### Configuration Schema

This schema defines the structure of configuration data that controls how workflows are processed.

???+ info "Schema Attributes (click to collapse)"
    For each field in the schema, you can define various attributes to control its behavior:

    | Field Name | Description |
    |------------|-------------|
    | `type` | **Required**; specifies the data type of the field (e.g., string, integer, boolean, datetime, etc.)[^1] |
    | `required` | Indicates whether the field is mandatory. If set to `true`, NULL values are not permitted. |
    | `description` | Provides a description of the field |
    | `primary_key` | Identifies the primary key field that will be auto-populated with a UUID |
    | `properties` | This is used to define nested fields within a JSON field; used primarily for `terra_method_config`, which is used when launching jobs in Terra |
    | `system_value` | Indicates that this field is managed by bioforklift and are not uploaded to Terra. |
    | `updated_datetime` | Indicates that this field will be updated automatically with the current datetime when the record is modified |
    | `use_as_prefix` | Indicates that this field should be used as a prefix for entity set names |
    | `display_for_alerts` | Indicates that this field should be used in alert messages |

??? tip "Creating a Terra Workflow configuration (click to expand)"
    To fill in the `terra_method_config` field, you will use a separate JSON file that contains the configuration for the workflow that will be fed into the `properties` field. See the following example:

    ```json

    {
      "name": "name-of-json",
      "prefix": "your-set-prefix",
      "state": "state",
      "entity_type": "name-of-terra-table",
      "terra_source_project": "terra-source-project",
      "terra_source_workspace": "terra-source-workspace",
      "terra_destination_project": "terra-destination-project", // if single_datatable true, set this to be the same as the source project
      "terra_destination_workspace": "terra-destination-workspace", // if single_datatable true, set this to be the same as the source workspace
      "active": true, // set to false if you do not want to run this configuration
      "single_datatable": true, // or false if multiple workspaces and tables are being combined
      "terra_analysis_method": "name-of-workflow",
      "terra_method_config": {
        "methodConfigurationNamespace": "name-of-terra-project",
        "methodConfigurationName": "name-of-workflow",
        "entityType": "<name-of-terra-table>_set",
        "entityName": "test-specimen-{date}", // this can differ based on how you name your sets
        "expression": "this.<name-of-terra-table>s",
        "useCallCache": false,
        "deleteIntermediateOutputFiles": false,
        "useReferenceDisks": false,
        "memoryRetryMultiplier": 1,
        "workflowFailureMode": "NoNewCalls",
        "userComment": "Test job automatically launched; test-{date}", // completely customizable
        "ignoreEmptyOutputs": true
      },
      "predecessor_id": null,
      "config_url": "url/to/config/on/github",
      "config_version": "v1.0"
    }
    ```

??? example "Configuration Schema (click to expand)"
    ```yaml
    fields:
      id:
        type: string
        required: true
        description: Configuration ID
        primary_key: true
        system_value: true
    
      name:
        type: string
        required: true
        description: Configuration name
        display_for_alerts: true
        
      state:
        type: string
        required: true
        description: State for project
        
      prefix:
        type: string
        required: true
        use_as_prefix: true
        description: Configuration prefix
        
      entity_type:
        type: string
        required: true
        description: Original entity from source table
        
      terra_source_project:
        type: string
        required: true
        description: Terra project identifier
    
      predecessor_id:
        type: string
        description: Predeccessor configuration ID
        
      terra_source_workspace:
        type: string
        required: true
        description: Terra workspace identifier
    
      terra_destination_project:
        type: string
        required: true
        description: Terra project identifier
    
      terra_destination_workspace:
        type: string
        required: true
        description: Terra workspace identifier
        
      active:
        type: boolean
        default: true
        description: Whether the configuration is active
        
      terra_analysis_method:
        type: string
        required: true
        description: Terra analysis method to use (workflow i.e TheiaCoV_Illumina_PE)
        
      terra_method_config:
        type: json
        description: Terra method configuration details
        properties:
          methodConfigurationNamespace:
            type: string
            required: true
            description: Method configuration namespace
          
          methodConfigurationName:
            type: string
            required: true
            description: Method configuration name
          
          entityType:
            type: string
            required: true
            description: Entity type for the method
          
          entityName:
            type: string
            required: true
            description: Template for entity names
          
          expression:
            type: string
            required: true
            description: Expression for the method
          
          useCallCache:
            type: boolean
            required: true
            description: Whether to use call cache
          
          deleteIntermediateOutputFiles:
            type: boolean
            required: true
            description: Whether to delete intermediate output files
          
          useReferenceDisks:
            type: boolean
            required: true
            description: Whether to use reference disks
          
          memoryRetryMultiplier:
            type: number
            required: true
            description: Memory retry multiplier
          
          workflowFailureMode:
            type: string
            required: true
            description: Workflow failure mode
          
          userComment:
            type: string
            required: true
            description: Template for user comments
      
      config_url:
        type: string
        required: true
        description: URL to the configuration
      
      config_version:
        type: string
        required: true
        description: Version of the configuration
    
      created_at:
          type: datetime
          required: true
          description: Record creation timestamp
          system_value: true
    
      updated_at:
          type: datetime
          description: Record update timestamp
          updated_datetime: true 
          system_value: true
    ```

### 2. Initialize Components

Before you can use bioforklift in an automated way, you need to initialize the components by creating the BigQuery dataset (must be done in the Google Cloud console) and creating their tables using your previously created schemas.

You can initialize your tables by running the following Python script:

```python
from bioforklift.bigquery import BigQuery
from pathlib import Path
    
def main():    
    bq = BigQuery(project="your-project-id", dataset="your-dataset-name")
    
    config_table_exists = bq.table_exists("configs")
    sample_table_exists = bq.table_exists("samples")
    
    if not config_table_exists:
        table_create_res = bq.create_table(table_name="configs",
                                            schema_yaml=Path("path/to/config_schema.yaml"))
        
        config_ops = bq.get_config_operations(table_name="configs",
                                              config_schema_yaml=Path("path/to/config/schema.yaml"))
        
        new_configs = config_ops.create_config(Path("path/to/workflow.json"))
    
    if not sample_table_exists:
        table_create_res = bq.create_table(table_name="samples", 
                                            schema_yaml=Path("../data/samples.yaml"))
    
if __name__ == "__main__":
    main()
```
<!-- 
```python
from bioforklift.bigquery import BigQuery
from bioforklift.terra import Terra
from bioforklift.terra2bq import Terra2BQ

# Initialize BigQuery
bq = BigQuery(
    project="your-project-id",
    dataset="your-dataset-name",
    credentials=google_credentials_json  # Optional
)

# Initialize Terra
terra = Terra(
    source_workspace="your-source-workspace",
    source_project="your-source-project",
    destination_workspace="your-destination-workspace",  # Optional
    destination_project="your-destination-project"      # Optional
)

# Initialize Terra2BQ
terra2bq = Terra2BQ(
    bigquery_project="your-project-id",
    bigquery_dataset="your-dataset-name",
    samples_table="samples",
    configs_table="configs",
    samples_schema_yaml="path/to/sample_schema.yaml",
    configs_schema_yaml="path/to/config_schema.yaml",
    source_workspace="your-source-workspace",  # Optional
    source_project="your-source-project"      # Optional
)
```

## Basic Usage Examples

### Download Data from Terra to BigQuery

```python
# Get active configurations
configs = terra2bq.get_active_configs()

# Process a single configuration
for config in configs:
    result = terra2bq.download_from_terra_to_bigquery(config)
    print(f"Downloaded {result.get('loaded_count')} samples")
```

### Upload Data from BigQuery to Terra

```python
# Get a configuration
config = terra2bq.config_ops.get_config("your-config-id")

# Get samples to upload
samples_df = terra2bq.samples_ops.get_samples_by_timeframe(
    timeframe="today",
    uploaded_filter="not_uploaded",
    config_id=config.get("id")
)

# Process upload and submit workflow
result = terra2bq.process_upload_and_submit(config)
print(f"Uploaded {result.get('uploaded_count')} samples")
print(f"Created entity set: {result.get('set_name')}")
print(f"Submitted workflow: {result.get('submission_id')}")
```

### Update Workflow Status

```python
# Update workflow status for all configurations
result = terra2bq.update_workflow_status(days_back=7)
print(f"Updated {result.get('updated_count')} workflow records")
``` -->
