from bioforklift.terra import Terra, WorkflowConfig, WorkspaceMethodConfig, MethodRepoMethod
from datetime import datetime


terra = Terra(
    source_workspace="CDPH_Automation_Development",
    source_project="cdph-terrabio-taborda-manual",
    destination_workspace="CDPH_Automation_Development",
    destination_project="cdph-terrabio-taborda-manual",
)

current_time = datetime.now().strftime("%Y%m%d_%H%M%S")

input_df = terra.entities.download_table("target")
result = terra.entities.create_entity_set(f"test_example_set_{current_time}", "target", input_df)
if result.ok:
    print("Entity set created successfully")

# List of files
files_to_cat = input_df["kraken_report"].tolist()

# Creating a new workflow method configuration with inputs/outputs defined.
workspace_method_config = WorkspaceMethodConfig(
    namespace=terra.client.destination_project,
    name="Test_Bioforklift_Concatenate_Column_Content",
    rootEntityType=f"target_set",
    inputs={
        "concatenate_column_content.concatenated_file_name": "concatenated_kraken_reports.txt",
        "concatenate_column_content.files_to_cat": files_to_cat,
    },
    outputs={
        "concatenate_column_content.concatenate_column_content_analysis_date": "this.concatenate_column_content_analysis_date",
        "concatenate_column_content.concatenate_column_content_version": "this.concatenate_column_content_version",
        "concatenate_column_content.concatenated_files": "this.concatenated_files"
    },
    prerequisites={},
    methodRepoMethod=MethodRepoMethod(
        sourceRepo="dockstore",
        methodPath="github.com/theiagen/public_health_bioinformatics/Concatenate_Column_Content_PHB",
        methodVersion="main",
    ),
    methodConfigVersion=0,
    deleted=False
)

# Other example inputs for WorkspaceMethodConfig. Types are automatically converted to correct JSON types:
# rootEntityType="target_set" # rootEntityType is name of set table
# inputs={
#     "example.expected_genes": ["OXA"],
#     "example.downsampling_levels": [10, 20, 30, 40, 50],
#     "example.boolean_flag": True,
# }

# Adds or overwrites the method configuration in the Terra workspace
terra.workflows.overwrite_workspace_method_config(workspace_method_config)

example = {
    "methodConfigurationNamespace": terra.client.destination_project,
    "methodConfigurationName": workspace_method_config.name,
    "entityType": "target_set", # entityType is name of set table
    "entityName": f"test_example_set_{current_time}", # entityName is name of specific row in table
    "expression": "null", # name of column in set table containing all entities in this.{}s format
    "useCallCache": False,
    "deleteIntermediateOutputFiles": False,
    "useReferenceDisks": False,
    "memoryRetryMultiplier": 1.0,
    "workflowFailureMode": "NoNewCalls",
    "userComment": "Test example",
}

# # # Workflow operations
workflow_config = WorkflowConfig.model_validate(example)
submission = terra.submissions.submit_workflow(workflow_config)
print(submission)
status = terra.submissions.get_submission_status(submission["submissionId"])
print(status)