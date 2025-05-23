# Terra Classes, Methods, and Usage

## Module: `bioforklift.terra`

Access these classes and operations using `from bioforklift.terra import Terra` as your import statement.

This module enables programmatic access to Terra's APIs, allowing you to manage workspaces, data entities, and workflow submissions and transferring data between source and destination workspaces. It enables you to:

1. **Access Terra Data**: Download and data tables from Terra workspaces.
2. **Manage Data Entities**: Upload and update data entities in Terra.
3. **Execute Workflows**: Submit workflows in Terra
4. **Track Execution**: Monitor the status of workflows
5. **Handle Authentication**: Manage authentication and API access with Google and Terra.

### Classes

- [Terra](#class-terra)
- [TerraClient](#class-terraclient)
- [TerraEntities](#class-terraentities)
- [TerraSubmissions](#class-terrasubmissions)
- [WorkflowConfig](#class-workflowconfig)
- [WorkflowMetadata](#class-workflowmetadata)
- [SubmissionInfo](#class-submissioninfo)

### Exception Classes

- [TerraError](#class-terraerror):
- [TerraAPIError](#class-terraapierror):
- [TerraAuthenticationError](#class-terraauthenticationerror):
- [TerraConnectionError](#class-terraconnectionerror)
- [TerraBadRequestError](#class-terrabadrequesterror)
- [TerraNotFoundError](#class-terranotfounderror)
- [TerraPermissionError](#class-terrapermissionerror)
- [TerraServerError](#class-terraservererror)

---

## Important Notes

!!! info "Source vs. Destination"
    **Source**: The workspace, table, and project from which data is read or downloaded. Typically, this is where data is originally stored and uploaded by analysts.

    **Destination**: The workspace, table, and project to which data is uploaded, or where workflows are executed. This is typically where data is transferred for analysis or reporting.

    If no destination workspace is provided, the source workspace is assumed to be the destination.

!!! info "Authentication"
    See the [Authentication](../index.md#authentication) section on the Home page for more details on how to authenticate with the Terra API.

## Class: `Terra`

This class is the main interface for Terra operations, and provides a single access point to data and workflow operations. This is the main class you will use to interact with Terra.

The most commonly used methods are found in subclasses [TerraEntities](#class-terraentities) and [TerraSubmissions](#class-terrasubmissions). These classes are used to manage data entities and workflow submissions, respectively.

### Constructor

```python
Terra(
    source_workspace: str,
    source_project: str,
    destination_workspace: Optional[str] = None,
    destination_project: Optional[str] = None,
    credentials: Optional[Credentials] = None,
    firecloud_api_url: str = "https://api.firecloud.org/api"
)
```

#### Parameters

- **source_workspace** (str): Source Terra workspace name
- **source_project** (str): Source Terra project name
- **destination_workspace** (Optional[str]): Optional target Terra workspace name (defaults to source_workspace)
- **destination_project** (Optional[str]): Optional target Terra project name (defaults to source_project)
- **credentials** (Optional[Credentials]): Optional Google credentials (if authentication cannot be done automatically)
- **firecloud_api_url** (str): Base URL for Terra API (do not change unless you know what you are doing)

#### Example Construction

Here is an example construction where automatic authentication cannot be used:

```python
from bioforklift.terra import Terra

terra = Terra(
    source_workspace="my-source-workspace",
    source_project="my-source-project",
    destination_workspace="my-destination-workspace",
    destination_project="my-destination-project",
    credentials="path/to/service_acccount.json"
)
```

### Properties

- **source_workspace** (str): Get source workspace name
- **source_project** (str): Get source project name
- **destination_workspace** (str): Get destination workspace name
- **destination_project** (str): Get destination project name

### Methods

!!! tip "Advanced Topics"
    These methods are typically not used in day-to-day operations, but are available for advanced users who need to manage connections and workspaces dynamically.

    The Terra subsystem allows you to dynamically switch between workspaces. This may be useful if you need to be able to dynamically switch between workspaces between processes.

#### `update_source_workspace`

Updates the source workspace and optionally the source project.

```python
update_source_workspace(
    source_workspace: str, 
    source_project: Optional[str] = None
) -> None
```

#### `update_target_workspace`

Updates the destination workspace and optionally the destination project.

```python
update_target_workspace(
    destination_workspace: str, 
    destination_project: Optional[str] = None
) -> None
```

#### `verify_connection`

Verifies that the Terra client connection is working correctly.

```python
verify_connection() -> bool
```

**Returns:** _True_ if connection is valid; _TerraConnectionError_ if not

#### `close_connections`

Closes any open connections and resources.

```python
close_connections() -> None
```

---

## Class: `TerraClient`

!!! tip "Advanced Topics"
    **This class is used internally** by the Terra class to manage API interactions. It is not typically used directly by users.

    However, it is available for advanced users who need to manage API interactions directly.

This class is the base client for Terra Firecloud API interactions.

### Constructor

```python
TerraClient(
    source_workspace: str,
    source_project: str,
    destination_workspace: Optional[str] = None,
    destination_project: Optional[str] = None,
    google_credentials_json: Optional[str] = None,
    firecloud_api_url: str = "https://api.firecloud.org/api",
    token_audience: str = "https://api.firecloud.org"
)
```

### Methods

#### `reset_auth_cache`

Reset authentication cache to force a new token on next request.

```python
reset_auth_cache() -> None
```

#### `get`

Make GET request to Terra Firecloud API.

```python
get(
    endpoint: str,
    params: Optional[Dict] = None,
    stream: Optional[bool] = False,
    use_destination: bool = False
) -> requests.Response
```

#### `post`

Make POST request to Terra Firecloud API.

```python
post(
    endpoint: str,
    data: Optional[Dict] = None,
    files: Optional[Dict] = None,
    params: Optional[Dict] = None,
    use_destination: bool = False
) -> requests.Response
```

#### `patch`

Make PATCH request to Terra Firecloud API.

```python
patch(
    endpoint: str, 
    data: Dict, 
    use_destination: bool = False
) -> requests.Response
```

---

## Class: `TerraEntities`

This class provides operations for Terra data entities. Its construction is managed by `Terra` but the methods can be used directly. Please see the examples below for usage.

These methods can be called with the following format:

```python
terra.entities.<method_name>(<parameters>)
```

### Constructor

```python
TerraEntities(client: TerraClient)
```

### Methods

#### `list_entity_types`

Retrieves a list of entity types from the **source workspace**. Remember that "entity type" is another way of saying Terra data table names.

```python
list_entity_types(
    include_attributes: bool = False,
    use_destination: bool = False
) -> List[str] | Dict[str, Any]
```

**Returns:**

- If `include_attributes` is False, returns a list of entity type names (table names)
- If `include_attributes` is True, returns a dictionary with entity types (table names) and their attributes (columns)

_**Examples**_

```python
# Get all entity types in a workspace
entity_types = terra.entities.list_entity_types()

# Get entity types with their attributes
entity_info = terra.entities.list_entity_types(include_attributes=True)
```

#### `download_table`

Downloads the contents of a Terra data table from the **source workspace**.

```python
download_table(
    entity_type: str,
    destination: Optional[Path] = None,
    attributes: Optional[List[str]] = None,
    model: str = "flexible",
    chunk_size: int = 65553,
    use_destination: bool = False
) -> pd.DataFrame
```

**Returns:**

- pandas DataFrame with table data

_**Examples**_

```python
# Download a Terra data table (the "sample" table) as a pandas DataFrame
samples_df = terra.entities.download_table("sample")

# Only download specific columns from the "sample" table
columns_df = terra.entities.download_table(entity_type="sample", attributes=["sample_id", "sequencing_date"])
```

#### `upload_entities`

Uploads entities to the **destination workspace**. If `destination_workspace`/`destination_project` was not provided, the source workspace and project will be used. The input is a pandas DataFrame.

```python
upload_entities(
    data: pd.DataFrame,
    target: str,
    entity_identifier_column: str = None,
    model: str = "flexible",
    delete_empty: bool = False,
    use_destination: bool = True
) -> pd.DataFrame
```

**Returns:**

- DataFrame with uploaded entities

_**Examples**_

```python
# Upload data to Terra
result_df = terra.entities.upload_entities(
    data=processed_df, # Dataframe with data meant for destination upload
    target="processed_sample", # The name of the target datatable in workspace
    entity_identifier_column="sample_id" # The name of the current entity identifier column
)
```

#### `create_entity_set`

Creates a new entity set. This allows you to group entities for processing together.

```python
create_entity_set(
    set_name: str,
    entity_type: str,
    entities: pd.DataFrame | List[str],
    model: str = "flexible",
    use_destination: bool = True
) -> Dict[str, Any]
```

_**Examples**_

```python
# Create a set of samples
sample_ids = ['sample1', 'sample2', 'sample3']

terra.entities.create_entity_set(
    set_name="batch_march_2023", # the name of the set to create
    entity_type="sample", # the data table where the samples are found
    entities=sample_ids # the list of samples to add to the set
)
```

#### `update_entity_attributes`

Updates the attributes of an entity. You can use this to update metadata or other information for a specific entity.

```python
update_entity_attributes(
    entity_type: str,
    entity_id: str,
    attributes: Dict[str, Any],
    use_destination: bool = True
) -> Dict[str, Any]
```

_**Examples**_

```python
# Update attributes for a specific entity
terra.entities.update_entity_attributes(
    entity_type="sample", # the table name
    entity_id="SAMPLE1", # the sample name
    attributes={"quality_score": 95, "status": "passed_qc"} # the fields you want to update in dictionary format
)
```

---

## Class: `TerraSubmissions`

This class provides operations for Terra workflow submissions. Its construction is managed by `Terra` but the methods can be used directly. Please see the examples below for usage.

These methods can be called with the following format:

```python
terra.submissions.<method_name>(<parameters>)
```

When submitting workflows, a `WorkflowConfig` object must be created. This object contains the configuration for the workflow submission. It corresponds to the expected entity types and expressions needed to launch a Terra workflow in the target workspace. See the [WorkflowConfig](#class-workflowconfig) section for more details.

???+ info "Potential Workflow States (click to collapse)"
    Workflows in Terra transition through various states.

    - **Submitted**: The workflow has been submitted but not yet started.
    - **Running**: The workflow is currently running.
    - **Succeeded**: The workflow has completed successfully.
    - **Aborted**: The workflow was aborted by the user.
    - **Aborting**: The workflow is in the process of being aborted.
    - **Failed**: The workflow failed to complete successfully.

### Constructor

```python
TerraSubmissions(client: TerraClient)
```

### Methods

#### `submit_workflow`

!!! tip "Advanced Topics"
    Launching workflows individually like described here is not used as frequently. In automations, the Terra2BQ class can be used to launch workflows in bulk. See the [Terra2BQ](../terra2bq.md) documentation for more details.

Submits a workflow for execution. This method requires the creation of a [WorkflowConfig](#class-workflowconfig) object.

```python
submit_workflow(
    config: WorkflowConfig,
    use_destination: bool = True
) -> Dict[str, Any]
```

**Returns:**

- Dictionary containing submission response

_**Examples**_

```python
# Submit a workflow
submission = terra.submissions.submit_workflow(workflow_config)
submission_id = submission["submissionId"]
```

#### `get_submission_status`

Gets the status of a workflow submission. This requires knowing the submission ID. A submission is the overlay that groups mulitple sample- or set-level workflows that were submitted at the same time.

```python
get_submission_status(
    submission_id: str,
    use_destination: bool = True
) -> Dict[str, Any]
```

_**Examples**_

```python
# Get the status of a submission
status = terra.submissions.get_submission_status(submission_id)
```

#### `get_all_submissions`

Gets all submissions from workspace. This is commonly used to retrieve all workflow statuses in a workspace. From there, the submission IDs can be queried to get the status of each workflow. This is particularly useful for backfilling workflow metadata.

```python
get_all_submissions(
    skip_aborted: bool = True,
    use_destination: bool = True
) -> List[SubmissionInfo]
```

**Returns:**

- List of [SubmissionInfo](#class-submissioninfo) objects
  
_**Examples**_

```python
# Get all submissions in a workspace
workflows = terra.submissions.get_all_submissions()
```

#### `get_workflows_by_submission`

Gets all workflows for a submission. This can often be combined with the `get_all_submissions` method to get all workflows that were submitted in a workspace.

```python
get_workflows_by_submission(
    submission_id: str,
    skip_aborted: bool = True,
    use_destination: bool = False
) -> List[WorkflowMetadata]
```

**Returns:**

- List of [WorkflowMetadata](#class-workflowmetadata) objects

_**Examples**_

```python
# get workflow data for a specific submission
submission_id = "12345"
workflows = terra.submissions.get_workflows_by_submission(submission_id)

# iterate through all submissions in a workflow to get all workflow metadata
workflows = terra.submissions.get_all_submissions()
for submission in workflows:
    workflow_data = terra.submissions.get_workflows_by_submission(submission.submission_id)
    for workflow in workflow_data:
        print(workflow.entity_name, workflow.workflow_id, workflow.submission_date, workflow.status)
```

#### `get_workflows_by_entity`

Gets workflow metadata for specific entities (samples).

```python
get_workflows_by_entity(
    entity_names: List[str],
    skip_aborted: bool = True,
    use_destination: bool = False
) -> Dict[str, WorkflowMetadata]
```

**Returns:**

- Dictionary mapping entity names to their [WorkflowMetadata](#class-workflowmetadata) objects.

_**Examples**_

```python
entity_metadata = terra.submissions.get_workflows_by_entity(
    entity_names=["sample1", "sample2", "sample3"]
)
```

---

## Class: `WorkflowConfig`

Model for Terra workflow submission configuration.

### Attributes

- **methodConfigurationNamespace** (str): Namespace for the method configuration
- **methodConfigurationName** (str): Name of the method configuration
- **entityType** (str): Entity type to run workflow on
- **entityName** (str): Name of the entity or entity set
- **expression** (Optional[str]): Expression for selecting entities
- **useCallCache** (bool): Whether to use call caching (default: True)
- **deleteIntermediateOutputFiles** (bool): Whether to delete intermediate files (default: True)
- **useReferenceDisks** (bool): Whether to use reference disks (default: True)
- **memoryRetryMultiplier** (float): Multiplier for memory retries (default: 1.0)
- **workflowFailureMode** (str): Failure mode (default: "NoNewCalls")
- **userComment** (Optional[str]): User comment for the submission
- **ignoreEmptyOutputs** (bool): Whether to ignore empty outputs (default: False)

---

Example:

```json
{
    "methodConfigurationNamespace": "theiagen-training-workspaces",
    "methodConfigurationName": "TheiaCoV_Illumina_PE_PHB",
    "entityType": "target_set",
    "entityName": "test_example_set",
    "expression": "this.targets",
    "useCallCache": True,
    "deleteIntermediateOutputFiles": False,
    "useReferenceDisks": False,
    "memoryRetryMultiplier": 1.0,
    "workflowFailureMode": "NoNewCalls",
    "userComment": "Test example",
}

```

## Class: `WorkflowMetadata`

Model for workflow metadata.

### Attributes

- **workflow_id** (str): Unique identifier for the workflow
- **status** (str): Current status of the workflow
- **submission_id** (str): ID of the submission this workflow belongs to
- **entity_name** (Optional[str]): Name of the entity processed by this workflow
- **submission_date** (Optional[datetime]): Date when the workflow was submitted
- **upload_source** (Optional[str]): Source of the uploaded data

---

## Class: `SubmissionInfo`

Model for submission information.

### Attributes

- **submission_id** (str): Unique identifier for the submission
- **entity_name** (str): Name of the submitted entity
- **submission_date** (datetime): Date when the submission was created
- **status** (Optional[str]): Current status of the submission

---

## Exception Classes

### Class: `TerraError`

Base exception for Terra API interactions.

### Class: `TerraAPIError`

Raised when Terra API returns an error.

#### Attributes

- **status_code** (Optional[int]): HTTP status code
- **response** (Optional[Dict[str, Any]]): Response data from the API
- **message** (str): Error message

### Class: `TerraAuthenticationError`

Raised when authentication fails.

### Class: `TerraConnectionError`

Raised when connection to Terra fails.

### Class: `TerraBadRequestError`

Raised when Terra returns 400.

### Class: `TerraNotFoundError`

Raised when Terra returns 404.

### Class: `TerraPermissionError`

Raised when Terra returns 403.

### Class: `TerraServerError`

Raised when Terra returns 5xx.

---

## Complete Workflow Example

```python
from bioforklift.terra import Terra

# Initialize Terra client
terra = Terra(
    source_workspace="source_workspace_name",
    source_project="source_project_name",
    destination_workspace="destination_workspace_name",
    destination_project="destination_project_name"
)

# Verify connection
terra.verify_connection()

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

---

## Troubleshooting

### Common Issues

Expand the sections below to see common issues and their solutions.

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