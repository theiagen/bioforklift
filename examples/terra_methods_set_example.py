from bioforklift.terra import Terra, WorkflowConfig, MethodConfig, MethodRepoMethod
from datetime import datetime


terra = Terra(
    source_workspace="CDPH_Automation_Development",
    source_project="cdph-terrabio-taborda-manual",
    destination_workspace="CDPH_Automation_Development",
    destination_project="cdph-terrabio-taborda-manual",
)

current_time = datetime.now().strftime("%Y%m%d_%H%M%S")

table_name = "target"
input_df = terra.entities.download_table(table_name)
result = terra.entities.create_entity_set(f"{table_name}_set_{current_time}", table_name, input_df)
if result.ok:
    print("Entity set created successfully")

# Creating a new workflow method configuration with inputs/outputs defined.
method_config = MethodConfig(
    namespace=terra.client.destination_project,
    name="Test_Bioforklift_Concatenate_Column_Content",
    rootEntityType=f"{table_name}_set",
    inputs={
        "concatenate_column_content.concatenated_file_name": "concatenated_kraken_reports.txt",
        "concatenate_column_content.files_to_cat": f"this.{table_name}s.kraken_report",
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
#     "example.input_file_array": input_df["kraken_report"].tolist(),
#     "example.expected_genes": ["OXA"],
#     "example.downsampling_levels": [10, 20, 30, 40, 50],
#     "example.boolean_flag": True,
# }

# Adds or overwrites the method configuration in the Terra workspace
terra.methods.overwrite_method_config(method_config)

terra.methods.method_config_validate(method_config)

example = {
    "methodConfigurationNamespace": terra.client.destination_project,
    "methodConfigurationName": method_config.name,
    "entityType": f"{table_name}_set", # entityType is name of set table
    "entityName": f"{table_name}_set_{current_time}", # entityName is name of specific row in table
    "expression": None, # if rootEntityType is a set table, expression must be None. Otherwise, use this.{table_name}s format.
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