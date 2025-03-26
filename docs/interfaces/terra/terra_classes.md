# Terra Classes and Methods

## Module: `forklift.terra`

### Classes

- [Terra](#class-terra)
- [TerraClient](#class-terraclient)
- [TerraEntities](#class-terraentities)
- [TerraSubmissions](#class-terrasubmissions)
- [WorkflowConfig](#class-workflowconfig)
- [WorkflowMetadata](#class-workflowmetadata)
- [SubmissionInfo](#class-submissioninfo)

## Exception Classes

- [TerraError](#class-terraerror)
- [TerraAPIError](#class-terraapierror)
- [TerraAuthenticationError](#class-terraauthenticationerror)
- [TerraConnectionError](#class-terraconnectionerror)
- [TerraBadRequestError](#class-terrabadrequesterror)
- [TerraNotFoundError](#class-terranotfounderror)
- [TerraPermissionError](#class-terrapermissionerror)
- [TerraServerError](#class-terraservererror)

---

## Class: `Terra`

Main interface for Terra operations. Provides a single access point to data and workflow operations.

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

#### Parameters:
- **source_workspace** (str): Source Terra workspace name
- **source_project** (str): Source Terra project name
- **destination_workspace** (Optional[str]): Optional target Terra workspace name (defaults to source_workspace)
- **destination_project** (Optional[str]): Optional target Terra project name (defaults to source_project)
- **credentials** (Optional[Credentials]): Optional Google credentials
- **firecloud_api_url** (str): Base URL for Terra API

### Properties

- **source_workspace** (str): Get source workspace name
- **source_project** (str): Get source project name
- **destination_workspace** (str): Get destination workspace name
- **destination_project** (str): Get destination project name

### Methods

#### `update_source_workspace`

Update the source workspace and optionally the source project.

```python
update_source_workspace(
    source_workspace: str, 
    source_project: Optional[str] = None
) -> None
```

#### `update_target_workspace`

Update the destination workspace and optionally the destination project.

```python
update_target_workspace(
    destination_workspace: str, 
    destination_project: Optional[str] = None
) -> None
```

#### `verify_connection`

Verify that the Terra client connection is working correctly.

```python
verify_connection() -> bool
```

**Returns:**
- True if connection is valid, raises an exception otherwise

#### `close_connections`

Close any open connections and resources.

```python
close_connections() -> None
```

---

## Class: `TerraClient`

Base client for Terra Firecloud API interactions.

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

Operations for Terra data entities.

### Constructor

```python
TerraEntities(client: TerraClient)
```

### Methods

#### `list_entity_types`

Retrieve a list of entity types from the workspace.

```python
list_entity_types(
    include_attributes: bool = False,
    use_destination: bool = False
) -> List[str] | Dict[str, Any]
```

**Returns:**
- If include_attributes is False, returns a list of entity type names
- If include_attributes is True, returns a dictionary with entity types and their attributes

#### `download_table`

Download table from Terra workspace.

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

#### `upload_entities`

Upload entities to Terra.

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

#### `create_entity_set`

Create a new entity set.

```python
create_entity_set(
    set_name: str,
    entity_type: str,
    entities: pd.DataFrame | List[str],
    model: str = "flexible",
    use_destination: bool = True
) -> Dict[str, Any]
```

#### `update_entity_attributes`

Update attributes of an entity.

```python
update_entity_attributes(
    entity_type: str,
    entity_id: str,
    attributes: Dict[str, Any],
    use_destination: bool = True
) -> Dict[str, Any]
```

---

## Class: `TerraSubmissions`

Operations for Terra workflow submissions.

### Constructor

```python
TerraSubmissions(client: TerraClient)
```

### Methods

#### `submit_workflow`

Submit a workflow for execution.

```python
submit_workflow(
    config: WorkflowConfig,
    use_destination: bool = True
) -> Dict[str, Any]
```

**Returns:**
- Dict containing submission response

#### `get_submission_status`

Get status of a workflow submission.

```python
get_submission_status(
    submission_id: str,
    use_destination: bool = True
) -> Dict[str, Any]
```

#### `get_all_submissions`

Get all submissions from workspace.

```python
get_all_submissions(
    skip_aborted: bool = True,
    use_destination: bool = True
) -> List[SubmissionInfo]
```

**Returns:**
- List of submission information

#### `get_workflows_by_submission`

Get all workflows for a submission.

```python
get_workflows_by_submission(
    submission_id: str,
    skip_aborted: bool = True,
    use_destination: bool = False
) -> List[WorkflowMetadata]
```

**Returns:**
- List of workflow metadata

#### `get_workflows_by_entity`

Get workflow metadata for specific entities.

```python
get_workflows_by_entity(
    entity_names: List[str],
    skip_aborted: bool = True,
    use_destination: bool = False
) -> Dict[str, WorkflowMetadata]
```

**Returns:**
- Dict mapping entity names to their workflow metadata

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

```
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

## Class: `TerraError`

Base exception for Terra API interactions.

## Class: `TerraAPIError`

Raised when Terra API returns an error.

### Attributes

- **status_code** (Optional[int]): HTTP status code
- **response** (Optional[Dict[str, Any]]): Response data from the API
- **message** (str): Error message

## Class: `TerraAuthenticationError`

Raised when authentication fails.

## Class: `TerraConnectionError`

Raised when connection to Terra fails.

## Class: `TerraBadRequestError`

Raised when Terra returns 400.

## Class: `TerraNotFoundError`

Raised when Terra returns 404.

## Class: `TerraPermissionError`

Raised when Terra returns 403.

## Class: `TerraServerError`

Raised when Terra returns 5xx.