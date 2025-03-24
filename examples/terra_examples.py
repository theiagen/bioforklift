from forklift.terra import Terra, WorkflowConfig

terra = Terra(
    source_workspace="CDPH_Automation_Development",
    source_project="cdph-terrabio-taborda-manual",
    destination_workspace="Theiagen_Babinski_Sandbox",
    destination_project="theiagen-training-workspaces",
)

terra_entities = terra.entities.list_entity_types(include_attributes=False)
print(f"Found {len(terra_entities)} in the workspace")
# Data operations
df = terra.entities.download_table("data")
updated_df = terra.entities.upload_entities(data=df, target="target")
result = terra.entities.create_entity_set("test_example_set", "target", updated_df)
if result.ok:
    print("Entity set created successfully")

example = {
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

# # # Workflow operations
workflow_config = WorkflowConfig.model_validate(example)
submission = terra.submissions.submit_workflow(workflow_config)
print(submission)
status = terra.submissions.get_submission_status(submission["submissionId"])
print(status)


# Test update entity attributes is working
update_entity_attribute = {"abricate_flu_database": "tested"}
updated_response = terra.entities.update_entity_attributes(
    "target", "NTC23A", update_entity_attribute
)
print(updated_response)
