import sys
import json
import argparse
import logging
from datetime import datetime
from bioforklift.terra import Terra, WorkflowConfig, MethodConfig, MethodRepoMethod


def cl_init():
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

    init_parser = argparse.ArgumentParser(description="Validate Terra workflow submission configurations.")
    parser = launcher_args(init_parser)
    run_parser = parser.add_argument_group("Runtime Parameters")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)
    return args


def launcher_args(parser):
    wf_parser = parser.add_argument_group("Workflow Submission Parameters")
    wf_parser.add_argument("-wf", "--workflow", type=str, help="Terra workflow name to run")
    wf_parser.add_argument("-b", "--branch", type=str, default="main", help="GitHub branch for workflow source; DEFAULT: main")

    launch_parser = parser.add_argument_group("Workflow Launch Parameters")
    launch_parser.add_argument("-s", "--sample_col", type=str, default="samplename", help="Column name in entity table for sample names; DEFAULT: samplename")
    # launch_parser.add_argument("--bioblueprint", type=str, help="Path to Bio-Blueprint JSON file for workflow inputs/outputs")
    launch_parser.add_argument("-i", "--input_json", type=str, help="Path to input JSON file for submission inputs")
    launch_parser.add_argument("-o", "--output_json", type=str, help="Path to output JSON file for submission outputs")
    launch_parser.add_argument("-cc", "--call_cache", action="store_true", default=False, help="Enable call caching for the workflow submission; DEFAULT: False")
    launch_parser.add_argument("-c", "--comment", type=str, default="", help="User comment for the workflow submission")
    launch_parser.add_argument("-ie", "--ignore_empty", action="store_true", default=False, help="Ignore empty outputs in the workflow submission; DEFAULT: False")

    ws_parser = parser.add_argument_group("Terra Workspace Parameters")
    ws_parser.add_argument("-ws", "--workspace", type=str, help="Terra workspace name")
    ws_parser.add_argument("-p", "--project", type=str, help="Terra project name")
    ws_parser.add_argument("-t", "--table", type=str, help="Terra entity table name for workflow")
    ws_parser.add_argument("--preexisting", action="store_true", default=False, help="Use pre-existing method configuration in the workspace; DEFAULT: False")

    return parser


def generate_method_config(terra, wf_name, table_name, inputs_dict, outputs_dict, branch):
    # to be removed when added natively
    method_config = MethodConfig(
        namespace=terra.client.destination_project,
        name=wf_name,
        rootEntityType=f"{table_name}_set",
        inputs=inputs_dict,
        outputs=outputs_dict,
        prerequisites={},
        methodRepoMethod=MethodRepoMethod(
            sourceRepo="dockstore",
            methodPath=f"github.com/theiagen/public_health_bioinformatics/{wf_name}",
            methodVersion=branch,
        ),
        methodConfigVersion=0,
        deleted=False
    )
    return method_config

def launcher(workspace, project, table, workflow, branch, sample_col, input_json, output_json, call_cache, comment, ignore_empty, preexisting, verbose):
    terra = Terra(
        source_workspace=workspace,
        source_project=project,
        destination_workspace=workspace,
        destination_project=project,
    )

    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")

    # get required terra task name and table name for each workflow
    wf_terra_task_name = workflow.replace("_PHB", "").lower()

    new_table_df = terra.entities.download_table(table, use_destination=True)
    result = terra.entities.create_entity_set(f"{table}_set_{current_time}", table, new_table_df)
    if result.ok:
        logger.info(f"{table} entity set created successfully")

        # get workflow input parameters from json file
        if isinstance(input_json, str):
            with open(input_json, 'r') as input_file:
                wf_inputs = json.load(input_file)
        else:
            wf_inputs = input_json

        # get workflow output parameters from json file
        if isinstance(output_json, str):
            with open(output_json, 'r') as output_file:
                wf_outputs = json.load(output_file)
        else:
            wf_outputs = output_json

        # get method config dictionary from existing workspace
        if preexisting:
            base_method_config_dict = terra.methods.get_method_config(workflow, use_destination=True)
        else:
            base_method_config_dict = generate_method_config(terra, workflow, table, wf_inputs, wf_outputs, branch)
        base_method_config = terra.methods.dict_to_method_config(base_method_config_dict)

        mod_method_config = base_method_config.model_copy(deep=True)
        # modify method config for the new workspace
        mod_method_config.namespace = terra.client.destination_project
        mod_method_config.rootEntityType = f"{table}"
        mod_method_config.methodRepoMethod.methodUri = None
        mod_method_config.methodRepoMethod.sourceRepo = "dockstore"
        mod_method_config.methodRepoMethod.methodPath = f"github.com/theiagen/public_health_bioinformatics/{workflow}"
        mod_method_config.methodRepoMethod.methodVersion = branch
        mod_method_config.methodConfigVersion = 0

        # set inputs from json file and dynamically set samplename based on table name
        mod_method_config.inputs = wf_inputs
        mod_method_config.inputs[f"{wf_terra_task_name}.{sample_col}"] = f"this.{table}_id"

        # set outputs from json file
        mod_method_config.outputs = wf_outputs

        # Adds or overwrites the method configuration in the Terra workspace
        terra.methods.overwrite_method_config(mod_method_config, use_destination=True)

        # Validate the new method configuration we created in the Terra workspace
        terra.methods.method_config_validate(mod_method_config, use_destination=True)

        wf_config_params = {
            "methodConfigurationNamespace": terra.client.destination_project,
            "methodConfigurationName": mod_method_config.name,
            "entityType": f"{table}_set", # entityType is name of set table
            "entityName": f"{table}_set_{current_time}", # entityName is name of specific row in table
            "expression": f"this.{table}s", # if rootEntityType is a set table, expression must be None. Otherwise, use this.{table_name}s format.
            "useCallCache": call_cache,
            "deleteIntermediateOutputFiles": False,
            "useReferenceDisks": False,
            "memoryRetryMultiplier": 1.0,
            "workflowFailureMode": "NoNewCalls",
            "userComment": comment,
            "ignoreEmptyOutputs": ignore_empty,
        }

        # Workflow operations
        workflow_config = WorkflowConfig.model_validate(wf_config_params)
        submission = terra.submissions.submit_workflow(workflow_config)
        logger.info(submission)
        status = terra.submissions.get_submission_status(submission["submissionId"])
        logger.info(status)

if __name__ == "__main__":
    args = cl_init()
    launcher(args.workspace, args.project, args.table, args.workflow, args.branch, args.sample_col, args.input_json, args.output_json, args.call_cache, args.comment, args.ignore_empty, args.preexisting, args.verbose)
    sys.exit(0)