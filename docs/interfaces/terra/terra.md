# Terra Subsystem

## Overview

The Terra subsystem provides a comprehensive interface for interacting with Terra, a scalable cloud platform for bioinformatics/biomedical researchers. This module enables programmatic access to Terra's APIs, allowing you to manage workspaces, data entities, and workflow submissions and transferring data between source and destination workspaces. 

## Purpose and Functionality

The Terra subsystem serves as the bridge between your application and the Terra platform, providing capabilities to do the following:

1. **Access Terra Data**: Download and query data tables from Terra workspaces
2. **Manage Data Entities**: Upload, update, and organize genomic data in Terra
3. **Execute Workflows**: Submit, monitor, and retrieve results from Terra workflows
4. **Track Execution**: Monitor the status of workflows and submissions
5. **Handle Authentication**: Securely authenticate with Google and Terra APIs

## Core Concepts

### Source vs. Destination Workspaces

A key concept in the Terra subsystem is the distinction between source and destination workspaces:

???+ info "Source vs. Destination"
    **Source Workspace**: The workspace from which data is read or downloaded. Normally this is where the data is originally uploaded to by analysts. 
    
    **Destination Workspace**: The workspace to which data is written, uploaded, or where workflows are executed. This is usually a master workspace containing all aggregated data for analysis. 

If no destination workspace is provided, all will be pulled and pushed to source workspace. 

??? example "Use Case Example"
    A common scenario is to:
    
    1. Pull raw sequencing data or a clearlabs assembly from a **source workspace** ("lab_sars-cov-2")
    2. Process and filter this data by expected metadata fields and expected sequencing files
    3. Upload the processed data to a **destination workspace** ("Master_Workspace") / or same workspace as source, but different table. 
    4. Run [public_health_bioinformatics](https://github.com/theiagen/public_health_bioinformatics) analysis workflows on that data in it's destination table.

### Authentication Flow

The Terra subsystem uses Google Cloud authentication to access Terra's [Firecloud API](https://api.firecloud.org/#/):

1. **Credentials**: Authenticate with Google using application default credentials or a service account
2. **Token Management**: The system handles token refresh and expiration

## Terra Entities

The `TerraEntities` class provides methods for working with data entities in Terra.
More inforamation on this core concept of Terra entity types can be found [here](https://support.terra.bio/hc/en-us/articles/360033913771-Overview-Entity-types-and-the-standard-genomic-data-model)

### Key Operations

#### Setting Up Interface to Terra Client

The constructor will be set up using this a `source_workspace` and `source_project`
If you expect to upload and submit data to a target workspace, provide `destination_workspace` and `destination_project`.

```python
from forklift.terra import Terra

terra = Terra(
    source_workspace="my-source-workspace",
    source_project="my-source-project",
    destination_workspace="my-destination-workspace", # Optional, defualts to source_workspace
    destination_project="my-destination-project", # Optional, defualts to source_project
)

```

If you can not automatically authenticate, you can also pass in the service account json:

```

terra = Terra(
    source_workspace="my-source-workspace",
    source_project="my-source-project",
    destination_workspace="my-destination-workspace", # Optional, defualts to source_workspace
    destination_project="my-destination-project", # Optional, defualts to source_project
    credentials="path/to/service_acccount.json"
)


```

#### Listing Entity Types

```python
# Get all entity types in a workspace
entity_types = terra.entities.list_entity_types()

# Get entity types with their attributes
entity_info = terra.entities.list_entity_types(include_attributes=True)
```

#### Downloading Data Tables

```python
# Download a Terra data table as a pandas DataFrame
samples_df = terra.entities.download_table("sample")

# Download specific columns only
columns_df = terra.entities.download_table("sample", attributes=["sample_id", "sequencing_date"])
```

#### Uploading Entities

If `destination_workspace` / `destination_project` was set in the `Terra` constructor, then this method will automatically upload data to the destination, otherwise it will default to the source.

```python
# Upload data to Terra
result_df = terra.entities.upload_entities(
    data=processed_df, # Dataframe with data meant for destination upload
    target="processed_sample", # The name of the target datatable in workspace
    entity_identifier_column="sample_id" # The name of the current entity identifier column
)
```

#### Creating Entity Sets

Entity sets allow you to group entities for processing together, if you are pushing to you `sample` table in Terra, then the following code will create the set found in the `sample_set` data table in your workspace:

```python
# Create a set of samples

sample_ids = ['sample1', 'sample2', 'sample3']

terra.entities.create_entity_set(
    set_name="batch_march_2023",
    entity_type="sample",
    entities=sample_ids #List of entitites to add to set
)
```

#### Updating Entity Attributes

Here is an example of updating the values for an entity `SAMPLE1` in table name `sample`. This will either update the values for `quality_score` and `status` or append them. 

```python
# Update attributes for a specific entity
terra.entities.update_entity_attributes(
    entity_type="sample",
    entity_id="SAMPLE1",
    attributes={"quality_score": 95, "status": "passed_qc"}
)
```

## Terra Submissions

The `TerraSubmissions` class provides methods for executing and monitoring workflows in Terra.

### Workflow Configuration

Before submitting a workflow, you need to define its configuration, this corresponds to the expected entity types and expressions needed to luanch a terra submission in the target workspace, refer to the schema on the submission request body for more [info](https://api.firecloud.org/#/Submissions/createSubmission):

```python
from forklift.terra.models import WorkflowConfig

workflow_config = WorkflowConfig(
    methodConfigurationNamespace="namespace",
    methodConfigurationName="workflow_name",
    entityType="sample_set",
    entityName="my_sample_set",
    expression="this.samples",
    useCallCache=True,
    deleteIntermediateOutputFiles=True,
    workflowFailureMode="NoNewCalls"
)
```

### Key Operations

#### Submitting Workflows

This will submit a workflow as configured in the workflow configuration above to the destination workspace if specified, else it will defualt to the source workspace. 

```python
# Submit a workflow
submission = terra.submissions.submit_workflow(workflow_config)
submission_id = submission["submissionId"]
```

#### Checking Submission Status

From the `submission_id`, you can check the submissions status of your terra submission. Reminder that submission is the top level submission for all entities, which if not a set level workflow, will set off worklfows for each sample (sample level workflow).

```python
# Get the status of a submission
status = terra.submissions.get_submission_status(submission_id)
```

#### Retrieving Workflow Results

Here from the submission we can get the workflow status by submission id for each workflow.
```python
# Get all workflows for a submission
workflows = terra.submissions.get_workflows_by_submission(submission_id)

```

### Workflow States

Workflows in Terra transition through various states:

???+ info "Workflow States"
    | State | Description |
    |-------|-------------|
    | Submitted | Workflow has been submitted |
    | Running | Workflow is actively running |
    | Aborting | Workflow is being aborted |
    | Aborted | Workflow was manually aborted |
    | Succeeded | Workflow completed successfully |
    | Failed | Workflow encountered an error |

### Error Handling

The Terra subsystem provides specialized exceptions for handling various error scenarios:

- **TerraAPIError**: Base exception for Terra API errors
- **TerraAuthenticationError**: Authentication failures
- **TerraConnectionError**: Network connectivity issues
- **TerraBadRequestError**: Invalid requests (HTTP 400)
- **TerraNotFoundError**: Resource not found (HTTP 404)
- **TerraPermissionError**: Permission denied (HTTP 403)
- **TerraServerError**: Server-side errors (HTTP 5xx)

## Implementation Examples

### Basic Setup

```python
from forklift.terra import Terra

# Initialize Terra client
terra = Terra(
    source_workspace="source_workspace_name",
    source_project="source_project_name",
    destination_workspace="destination_workspace_name",
    destination_project="destination_project_name"
)

# Verify connection
terra.verify_connection()
```

### Complete Workflow Example

```python
# Download data from source workspace
samples_df = terra.entities.download_table("sample")

# Process data (application-specific logic)
processed_df = process_samples(samples_df)

# Upload processed data to destination workspace
result_df = terra.entities.upload_entities(
    data=processed_df,
    target="processed_sample",
    entity_identifier_column="sample_id"
)

# Create an entity set
terra.entities.create_entity_set(
    set_name="batch_001",
    entity_type="processed_sample",
    entities=result_df
)

# Configure workflow
workflow_config = WorkflowConfig(
    methodConfigurationNamespace="my_namespace",
    methodConfigurationName="my_workflow",
    entityType="processed_sample_set",
    entityName="batch_001",
    expression="this.processed_samples",
    useCallCache=True
)

# Submit workflow
submission = terra.submissions.submit_workflow(workflow_config)

# Monitor status
status = terra.submissions.get_submission_status(submission["submissionId"])
```

## Advanced Topics

### Managing Multiple Workspaces

The Terra subsystem allows you to dynamically switch between workspaces, this might be useful if you need to be able to dynamically switch between workspaces between processes. 

```python
# Update source workspace
terra.update_source_workspace(
    source_workspace="new_source_workspace",
    source_project="new_source_project"
)

# Update destination workspace
terra.update_target_workspace(
    destination_workspace="new_destination_workspace",
    destination_project="new_destination_project"
)
```

### Connection Management

For long-running processes, you may need to reset connections:

```python
# Reset authentication cache to force a new token on next request
terra.client.reset_auth_cache()

# Close all connections
terra.close_connections()
```

## Architecture Details

The Terra subsystem consists of the following components:

1. **Terra**: Main interface class that coordinates other components
2. **TerraClient**: Base client for API requests
3. **TerraEntities**: Handles data entity operations
4. **TerraSubmissions**: Manages workflow submissions
5. **Models**: Data models for configurations and responses
6. **Exceptions**: Specialized error handling

## Integration with Other Modules

The Terra subsystem is designed to integrate seamlessly with other components of the Forklift library:

- **BigQuery Module**: For data storage and retrieval
- **Terra2BQ Module**: For coordinated operations between Terra and BigQuery
- **Alerting Module**: For monitoring and notifications

## Troubleshooting

### Common Issues

??? question "Authentication Failures"
    **Problem**: Unable to authenticate with Terra
    
    **Solution**: 
    - Ensure Google credentials are properly configured
    - Check that the service account has appropriate permissions
    - Try running `gcloud auth application-default login` to refresh credentials

??? question "Workspace Not Found"
    **Problem**: Terra workspace not found
    
    **Solution**:
    - Verify workspace names and project names
    - Check permissions on the workspace
    - Ensure the workspace exists in the specified project

??? question "Submission Failures"
    **Problem**: Workflow submissions fail
    
    **Solution**:
    - Verify workflow configuration parameters
    - Check that the entity set exists
    - Ensure all required inputs for the workflow are present
    - Review Terra workspace logs for detailed error messages