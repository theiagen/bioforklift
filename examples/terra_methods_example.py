from bioforklift.terra import Terra, WorkflowConfig
from datetime import datetime


terra = Terra(
    source_workspace="CDPH_Automation_Development",
    source_project="cdph-terrabio-taborda-manual",
    destination_workspace="CDPH_Automation_Development",
    destination_project="cdph-terrabio-taborda-manual",
)

current_time = datetime.now().strftime("%Y%m%d_%H%M%S")

# Download table and create entity set
table_name = "test_mtb"
input_df = terra.entities.download_table(table_name)
result = terra.entities.create_entity_set(f"{table_name}_set_{current_time}", table_name, input_df)
if result.ok:
    print("Entity set created successfully")

# Fetch existing method configuration
base_method_config_dict = terra.methods.get_method_config("TheiaProk_FASTA_PHB")

# Method config can be modified
base_method_config = terra.methods.dict_to_method_config(base_method_config_dict)
print(f"Base method config - name: {base_method_config.name}")
print(f"Base method config - version: {base_method_config.methodRepoMethod.methodVersion}")
print(f"Base method config  - rootEntityType (data table to use): {base_method_config.rootEntityType}")
print(f"Base method config - inputs: {base_method_config.inputs}")

mod_method_config = base_method_config
mod_method_config.name = f"Test_Bioforklift_TheiaProk_FASTA"

mod_method_config.rootEntityType = f"{table_name}"
mod_method_config.inputs = {
    "theiaprok_fasta.assembly_fasta": "this.assembly_fasta",
    "theiaprok_fasta.samplename": f"this.{table_name}_id"
}

print(f"Modified method config - name: {mod_method_config.name}")
print(f"Modified method config - version: {mod_method_config.methodRepoMethod.methodVersion}")
print(f"Modified method config - inputs: {mod_method_config.inputs}")
print(f"Modified method config - rootEntityType (data table to use): {mod_method_config.rootEntityType}")

# Adds or overwrites a new method configuration in the Terra workspace
terra.methods.overwrite_method_config(mod_method_config)

# Validate method configuration inputs and outputs
# Check out val['validInputs', 'validOutputs', 'invalidInputs', 'invalidOutputs', 'missingInputs', 'extraInputs']
val = terra.methods.method_config_validate(mod_method_config)


example = {
    "methodConfigurationNamespace": terra.client.destination_project,
    "methodConfigurationName": mod_method_config.name,
    "entityType": f"{table_name}_set", # entityType is name of set table
    "entityName": f"{table_name}_set_{current_time}", # entityName is name of specific row in table
    "expression": f"this.{table_name}s", # if rootEntityType is a set table, expression must be None. Otherwise, use this.{table_name}s format.
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