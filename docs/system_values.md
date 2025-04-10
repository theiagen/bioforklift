# System Values and Tracking Fields

bioforklift maintains several system-managed fields that track the status and history of each sample throughout its lifecycle. Understanding these fields is essential for monitoring your workflows and troubleshooting issues.

## Core System Fields

These fields are automatically managed by bioforklift and should be marked with `system_value: true` in your schema definitions:

| Field Name | Type | Description |
|------------|------|-------------|
| `id` | string | Primary UUID for the record in BigQuery |
| `created_at` | datetime | When the record was first created |
| `updated_at` | datetime | When the record was last updated |
| `uploaded_at` | datetime | When the sample was uploaded to Terra |
| `submitted_at` | datetime | When the sample was submitted to a workflow |
| `upload_source` | string | Name of the Terra entity set created during upload |
| `terra_submission_id` | string | Terra submission ID for tracking workflows |
| `terra_workflow_id` | string | Terra workflow ID for specific executions |
| `workflow_state` | string | Current state of the workflow (Submitted, Succeeded, Failed, Aborted) |

## Example Schema Definition

Here's how to properly configure these system fields in your sample schema YAML:

```yaml
fields:
  id:
    type: string
    required: true
    description: Unique identifier for the record
    primary_key: true
    system_value: true
  
  created_at:
    type: datetime
    required: true
    description: Record creation timestamp
    system_value: true
    
  updated_at:
    type: datetime
    description: Last update datetime
    system_value: true
    updated_datetime: true

  uploaded_at:
    type: datetime
    description: Date of sample upload to Terra
    system_value: true

  submitted_at:
    type: datetime
    description: Date of workflow submission
    system_value: true

  upload_source:
    type: string
    description: Source of sample upload (Terra entity set name)
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

## Lifecycle Tracking

The system values track a sample through its complete lifecycle:

1. **Creation**: `created_at` is set when the sample is first added to BigQuery
2. **Upload**: `uploaded_at` and `upload_source` are set when the sample is uploaded to Terra
3. **Submission**: `submitted_at` and `terra_submission_id` are set when a workflow is submitted
4. **Workflow**: `terra_workflow_id` and `workflow_state` are updated as the workflow progresses
5. **Updates**: `updated_at` is updated whenever any field in the record changes

## Querying System Values

You can use these system values to query sample status:

```python
# Get samples that have been uploaded but not submitted
pending_samples = samples_ops.get_samples_by_timeframe(
    timeframe="today", 
    uploaded_filter="uploaded",
    submitted_filter="not_submitted"
)

# Get samples with specific workflow states
failed_samples = samples_ops.query_samples(
    conditions=["workflow_state = @state"],
    parameters={"state": "Failed"}
)
```

## Workflow States

Common workflow states you'll see in the `workflow_state` field:

- **Submitted**: Workflow has been submitted but not yet started
- **Succeeded**: Workflow completed successfully
- **Failed**: Workflow encountered an error
- **Aborted**: Workflow was manually canceled

## Important Notes

- Fields marked with `system_value: true` are automatically excluded when uploading data to Terra
- Never manually modify system values unless you fully understand the implications
- System values are used by reporting and alerting functions to generate summaries
- When defining custom fields, avoid names that conflict with system fields