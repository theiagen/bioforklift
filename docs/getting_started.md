# Getting Started with Forklift

This guide will help you install and set up Forklift, and demonstrate basic usage.

## Prerequisites

Before using Forklift, ensure you have:

1. Python 3.9 or higher
2. Access to Google Cloud Platform (GCP) and BigQuery
3. Access to Terra workspace(s)
4. Appropriate permissions for both platforms

## Installation

You can install Forklift using pip:
(To come, still haven't published the package)
```bash
pip install forklift
```

Or install from source:

```bash
git clone https://github.com/theiagen/forklift.git
cd forklift
pip install -e .
```

## Authentication

### Google Cloud Authentication

Forklift requires authentication to access Google Cloud and Terra. There are two main methods for authentication:

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

## Basic Configuration

### 1. Set up Schema Files

Forklift uses YAML-based schema definitions to configure BigQuery tables. Below are examples of the two main schema types used in the system.

This schema defines the structure of sample data, including genomic samples and their metadata.

#### Sample Schema

??? example "Sample Schema (click to expand)"
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
      # System fields that need to be dropped before submission to terra 
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

### Key Field Attributes

- `primary_key`: Identifies the primary key field that will be auto-populated with a UUID
- `sample_identifier`: Identifies the field that contains the sample identifier for Terra
- `sequence_file`: Marks fields containing paths to sequence files
- `system_value`: Marks fields that are managed by the system and not uploaded to Terra

#### Configuration Schema

This schema defines the structure of configuration data that controls how workflows are processed.

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

### Key Field Attributes

- `primary_key`: Identifies the primary key field
- `display_for_alerts`: Identifies the field to use in alert messages
- `use_as_prefix`: Identifies the field to use as a prefix for entity set names
- `system_value`: Marks fields that are managed by the system


### 2. Initialize Components

```python
from forklift.bigquery import BigQuery
from forklift.terra import Terra
from forklift.terra2bq import Terra2BQ

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
```
