# Getting Started with bioforklift

Please ensure you have installed bioforklift and provided the appropriate authentication credentials for Google Cloud and Terra before proceeding with the setup.

## Setup Schemas and Initialize Components

bioforklift uses YAML-based schema definitions to configure BigQuery tables. After the schemas are made, you must initialize the components by creating the BigQuery dataset and tables.

!!! tip "Why do we need schemas?"
    Schema definitions in YAML format define:

    - Field names, types, and attributes
    - System-generated fields
    - Field relationships and mappings
    - Special handling instructions

    Schemas are used to create and interact with BigQuery tables.

### A Note on System Values

bioforklift maintains several system-managed fields that track the status and history of each sample throughout its lifecycle. Understanding these fields is essential for monitoring your workflows and troubleshooting issues.

Here are some important notes regarding system values (indicated by the `system_value: true` attribute in the schema):

- **These fields are excluded when uploading data to Terra**
- **Never manually modify system values** unless you fully understand the implications
- **Avoid names that conflict with system fields** when creating custom fields

#### Core System Fields

These fields are automatically managed by bioforklift and should be marked with `system_value: true` in your schema definitions:

| Field Name | Type | Description |
|------------|------|-------------|
| `id` | string | Primary UUID for the record in BigQuery |
| `created_at` | datetime | When the record was first created and added to BigQuery |
| `updated_at` | datetime | The last time when any field in the record changed |
| `uploaded_at` | datetime | When the sample was uploaded to Terra |
| `submitted_at` | datetime | When the sample was submitted to a workflow |
| `upload_source` | string | Name of the Terra entity set created during upload |
| `terra_submission_id` | string | Terra submission ID for tracking workflows |
| `terra_workflow_id` | string | Terra workflow ID for specific executions |
| `workflow_state` | string | Current state of the workflow (Submitted, Succeeded, Failed, Aborted) |

### 1. Sample Schema

!!! tip "What is a sample schema for?"
  
    Sample data represents genomic samples and their metadata. In bioforklift:

    - Samples are downloaded from Terra to BigQuery
    - Sample metadata is tracked and updated
    - Samples are grouped into sets for processing
    - Workflow results update sample status

??? info "Available Schema Attributes (click to expand)"
    For each field in the schema, you can define various attributes to control its behavior:

    | Field Name | Description |
    |------------|-------------|
    | `type` | **Required**; specifies the data type of the field (e.g., string, integer, boolean, datetime, etc.)[^1]; see subsequent toggle for options |
    | `required` | Indicates whether the field is mandatory. If set to `true`, NULL values are not permitted. |
    | `description` | Provides a description of the field |
    | `primary_key` | Identifies the primary key field that will be auto-populated with a UUID |
    | `sample_identifier` | Identifies the field that contains the sample identifier in Terra[^2] |
    | `use_field_name` | If True, will use field name as is for sample identifiers **applies only to field where sample_identifier: true**. DO NOT USE WITH COLUMN_MAPPINGS. |
    | `column_mappings` | If the field name in BigQuery is different from the column name in Terra, you can specify the mapping here[^3] |
    | `sequence_file` | This is typically used for read data (e.g., `read1` and `read2`)[^4] |
    | `system_value` | Indicates that this field is managed by bioforklift and are not uploaded to Terra. |
    | `inherit_from_config` | Indicates that this field should be inherited from the configuration schema |
    | `configuration_identifier` | Indicates that this field contains the configuration identifier for the sample |
    | `metadata` | **No functional effects** Indicates the field contains sample metadata |
    | `sync_field` | Indicates that this field should be synchronized between BigQuery and Terra |
    | `accepted_pattern` | Regex pattern for validating field values (e.g., "^[A-Z0-9]+$") |
    | `date_format` | Date format specification for date validation and coercion (e.g., "ISO 8601", "YYYY-MM-DD") |

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

[^1]:
    [These values correspond to specific datatypes that are accepted by BigQuery](https://cloud.google.com/bigquery/docs/schemas#standard_sql_data_types).
[^2]:
    This field is typically the sample name in Terra (e.g., `entity:data_id`). This field's name can be name after a single table (like "data_id") (if only one datatable is used) or a generic term (like "sample_identifier") if multiple datatables are used.
[^3]:
    This describes how the field is named in Terra; typically used to convert `entity:data_id` to `data_id` so the `entity:` prefix is not included in BigQuery.
[^4]:
    If this is indicated, any rows that do not have an associated file for this field will be ignored and filtered out of BigQuery.

??? example "Example Sample Schema (click to expand)"
    ```yaml
    # example_sample_schema.yaml
    fields:
      # SYSTEM VALUE; DO NOT MODIFY
      id:
        type: string
        required: true
        description: Unique identifier for the record
        primary_key: true  # This field will be auto-populated with UUID
        system_value: true

      # USER-PROVIDED FIELDS; MODIFY AS NEEDED
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
      
      # SYSTEM VALUES; DO NOT MODIFY      
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

### 2. Configuration Schema

!!! tip "What is a configuration schema for?"

    Configurations in bioforklift define how data should be processed. Each configuration includes:

    - Source and destination Terra workspace and project
    - Entity types for Terra tables
    - Workflow method configuration - _created in a separate JSON file_
    - Status tracking fields

    Configurations are stored in BigQuery and drive the automated processing.

??? info "Available Schema Attributes (click to expand)"
    For each field in the schema, you can define various attributes to control its behavior:

    | Field Name | Description |
    |------------|-------------|
    | `type` | **Required**; specifies the data type of the field (e.g., string, integer, boolean, datetime, etc.)[^1]; see relevant toggle in the previous section for options. |
    | `required` | Indicates whether the field is mandatory. If set to `true`, NULL values are not permitted. |
    | `description` | Provides a description of the field |
    | `primary_key` | Identifies the primary key field that will be auto-populated with a UUID |
    | `properties` | This is used to define nested fields within a JSON field; used primarily for `terra_method_config`, which is used when launching jobs in Terra |
    | `system_value` | Indicates that this field is managed by bioforklift and are not uploaded to Terra. |
    | `updated_datetime` | Indicates that this field will be updated automatically with the current datetime when the record is modified |
    | `use_as_prefix` | Indicates that this field should be used as a prefix for entity set names |
    | `display_for_alerts` | Indicates that this field should be used in alert messages |
    | `single_datatable` | Indicates if source and destination datatables are the same (skips upload step) |

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

??? example "Example Configuration Schema (click to expand)"
    Sage recommends copying the following schema and making any necessary modifications for your puposes to ensure all fields are included.

    ```yaml
    fields:
      # SYSTEM VALUE; DO NOT MODIFY
      id:
        type: string
        required: true
        description: Configuration ID
        primary_key: true
        system_value: true
    
      # USER-PROVIDED FIELDS; modification allowed but not recommended for basic usage
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
        description: Prefix for entity set names
        
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
    
      single_datatable:
        type: boolean
        default: false
        description: Describes if a single datatable is used for this configuration

      # set to be the same as the source project if single_datatable is true
      terra_destination_project:
        type: string
        required: true
        description: Terra project identifier
    
      # set to be the same as the source workspace if single_datatable is true
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
    
      # SYSTEM VALUES; DO NOT MODIFY
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

### 3. Initialize Components

Before you can use bioforklift in an automated way, you need to initialize the components by creating the BigQuery dataset (in the Google Cloud console) and creating their tables using your schemas.

After your dataset is created, you can initialize your tables by running the following Python script:

```python
from bioforklift.bigquery import BigQuery
from pathlib import Path
    
def main():    
    # Create a BigQuery instance
    bq = BigQuery(project="your-project-id", dataset="your-dataset-name")
    
    # check if the "configs" (for configurations) and "samples" 
    #  (for sample data) tables exist; these commands return true 
    #  if the table exists and false if they do not
    config_table_exists = bq.table_exists("configs")
    sample_table_exists = bq.table_exists("samples")
    
    # if the configuration table does not exist
    if not config_table_exists:
        # create the configuration table using the schema
        table_create_res = bq.create_table(table_name="configs",
                                            schema_yaml=Path("path/to/config_schema.yaml"))
        
        # get the configuration operations for the table in order
        #  to add your workflow JSON file 
        config_ops = bq.get_config_operations(table_name="configs",
                                              config_schema_yaml=Path("path/to/config/schema.yaml"))
        
        # add your workflow JSON file to the configuration table
        new_configs = config_ops.create_config(Path("path/to/workflow.json"))
    
    # if the sample table does not exist
    if not sample_table_exists:
        # create the sample table using the schema
        table_create_res = bq.create_table(table_name="samples", 
                                            schema_yaml=Path("../data/samples.yaml"))
    
if __name__ == "__main__":
    main()
```

You are now ready to use bioforklift!

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
