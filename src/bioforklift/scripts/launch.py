import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime
from bioforklift.terra.exceptions import TerraServerError
from bioforklift.scripts.configure import CLIConfig
from bioforklift.terra import Terra, WorkflowConfig


logger = logging.getLogger(__name__)


def launch_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Define command-line arguments for launch subcommand"""
    wf_parser = parser.add_argument_group("Workflow Submission Parameters")
    wf_parser.add_argument(
        "-wf", "--workflow_name", type=str, help="Terra workflow name to run"
    )
    wf_parser.add_argument(
        "-t", "--table", type=str, help="Terra entity table name for workflow"
    )
    wf_parser.add_argument(
        "-r",
        "--repository",
        type=str,
        help="GitHub repository for workflow source; DEFAULT: github.com/theiagen/public_health_bioinformatics",
    )
    wf_parser.add_argument(
        "-b",
        "--branch",
        type=str,
        help="GitHub branch for workflow source; DEFAULT: main",
    )

    launch_parser = parser.add_argument_group("Workflow Launch Parameters")
    launch_parser.add_argument(
        "-j", "--job_json", type=str, help="Path to workflow submission JSON file"
    )
    launch_parser.add_argument(
        "-s",
        "--sample_col",
        type=str,
        default="samplename",
        help="Column name in entity table for sample names; DEFAULT: samplename",
    )
    launch_parser.add_argument(
        "-i",
        "--input_json",
        type=str,
        help="Path to input JSON file for submission inputs",
    )
    launch_parser.add_argument(
        "-o",
        "--output_json",
        type=str,
        help="Path to output JSON file for submission outputs",
    )
    launch_parser.add_argument(
        "-cc",
        "--call_cache",
        action="store_true",
        help="Enable call caching for the workflow submission",
    )
    launch_parser.add_argument(
        "-c",
        "--comment",
        type=str,
        default="",
        help="User comment for the workflow submission",
    )
    launch_parser.add_argument(
        "-ie",
        "--ignore_empty",
        action="store_true",
        help="Ignore empty outputs in the workflow submission",
    )
    launch_parser.add_argument(
        "--sleep",
        type=int,
        default=1,
        help="Seconds to wait between launching multiple workflows; DEFAULT: 1",
    )

    ws_parser = parser.add_argument_group("Terra Workspace Parameters")
    ws_parser.add_argument("-ws", "--workspace", type=str, help="Terra workspace name")
    ws_parser.add_argument("-p", "--project", type=str, help="Terra project name")
    ws_parser.add_argument(
        "--preexisting_config",
        action="store_true",
        default=False,
        help="Use pre-existing method configuration in the workspace; DEFAULT: False",
    )

    run_parser = parser.add_argument_group("Runtime Parameters")
    run_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    return parser


def prepare_job_dict(args_dict: dict, config: CLIConfig) -> dict:
    """Extract workflow submission parameters from JSON file if provided

    Preference is given to command-line arguments over JSON file values."""

    # argument to requirement
    wf_args = {
        "workflow_name": True,
        "table": True,
        "input_json": True,
        "output_json": True,
        "sample_col": True,
        "comment": False,
        "branch": True,
        "call_cache": True,
        "ignore_empty": True,
        "preexisting_config": True,
    }

    job_dict = {}
    # parse JSON input
    if args_dict.get("job_json"):
        with open(args_dict["job_json"], "r") as json_file:
            json_data = json.load(json_file)
        # iterate through workflows in json file
        for wf, wf_data in json_data.items():
            job_dict[wf] = wf_data
            for arg, require in wf_args.items():
                # use the argument preferentially from command-line
                if args_dict.get(arg) is not None:
                    job_dict[wf][arg] = args_dict.get(arg)
                # else use from json if present
                elif wf_data.get(arg) is not None:
                    job_dict[wf][arg] = wf_data.get(arg)
                # else pull from config if required
                elif require:
                    if config.__dict__.get(arg) is not None:
                        job_dict[wf][arg] = config.__dict__.get(arg)
                    # raise error if still missing
                    else:
                        raise KeyError(
                            f"Missing required argument '{arg}' for workflow '{wf}'"
                        )
    else:
        # single workflow from command-line args
        wf = args_dict["workflow_name"]
        job_dict[wf] = {"workflow_name": wf}
        for arg, require in wf_args.items():
            # use from command-line args if present
            if args_dict.get(arg) is not None:
                if arg == "input_json" or arg == "output_json":
                    with open(args_dict.get(arg), "r") as io_file:
                        job_dict[wf][arg] = json.load(io_file)
                else:
                    job_dict[wf][arg] = args_dict.get(arg)
            # else pull from config if required
            elif require:
                if config.__dict__.get(arg) is not None:
                    job_dict[wf][arg] = config.__dict__.get(arg)
                # raise error if still missing
                else:
                    raise KeyError(
                        f"Missing required argument '{arg}' for workflow '{wf}'"
                    )
    return job_dict


def launch_job(job_data: dict, terra: Terra, config: CLIConfig) -> None:
    """Launch a workflow in Terra based on provided job data"""
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")

    # could implement a way to use local table
    try:
        new_table_df = terra.entities.download_table(
            job_data["table"], use_destination=True
        )
    except TerraServerError as e:
        raise TerraServerError(
            f"Error downloading table; does \"{job_data['table']}\" exist in the Terra workspace?"
        )
    result = terra.entities.create_entity_set(
        f"{job_data['table']}_set_{current_time}", job_data["table"], new_table_df
    )
    if not result.ok:
        logger.error(f"Failed to create {job_data['table']} entity set")
        raise TerraServerError(f"Entity set creation failed: {result.text}")

    logger.info(f"{job_data['table']} entity set created successfully")

    # get method config dictionary from existing workspace
    if job_data.get("preexisting_config"):
        base_method_config_dict = terra.methods.get_method_config(
            job_data["workflow_name"], use_destination=True
        )
        base_method_config = terra.methods.dict_to_method_config(base_method_config_dict)
    else:
        base_method_config = terra.methods.generate_method_config(
            config.repository,
            job_data["workflow_name"],
            job_data["table"],
            job_data["input_json"],
            job_data["output_json"],
            config.branch
        )

    mod_method_config = base_method_config.model_copy(deep=True)
    # modify method config for the new workspace
    mod_method_config.namespace = terra.client.destination_project
    mod_method_config.rootEntityType = f"{job_data['table']}"
    mod_method_config.methodRepoMethod.methodUri = None
    mod_method_config.methodRepoMethod.sourceRepo = "dockstore"
    mod_method_config.methodRepoMethod.methodPath = (
        f"{config.repository}/{job_data['workflow_name']}"
    )
    mod_method_config.methodRepoMethod.methodVersion = config.branch
    mod_method_config.methodConfigVersion = 0

    # set inputs from json file and dynamically set samplename based on table name
    mod_method_config.inputs = job_data["input_json"]
    mod_method_config.inputs[f"{job_data['table']}.{job_data['sample_col']}"] = (
        f"this.{job_data['table']}_id"
    )
    # set outputs from json file
    mod_method_config.outputs = job_data["output_json"]

    # Adds or overwrites the method configuration in the Terra workspace
    terra.methods.overwrite_method_config(mod_method_config, use_destination=True)

    # Validate the new method configuration we created in the Terra workspace
    val = terra.methods.method_config_validate(mod_method_config, use_destination=True)
    # raise error if invalid I/O detected
    if val["invalidInputs"] or val["invalidOutputs"]:
        if val["invalidInputs"]:
            logger.error(f"Invalid inputs detected: {val['invalidInputs']}")
        if val["invalidOutputs"]:
            logger.error(f"Invalid outputs detected: {val['invalidOutputs']}")
        raise KeyError("Invalid I/O")

    wf_config_params = {
        "methodConfigurationNamespace": terra.client.destination_project,
        "methodConfigurationName": mod_method_config.name,
        "entityType": f"{job_data['table']}_set",  # entityType is name of set table
        "entityName": f"{job_data['table']}_set_{current_time}",  # entityName is name of specific row in table
        "expression": f"this.{job_data['table']}s",  # if rootEntityType is a set table, expression must be None. Otherwise, use this.{table_name}s format.
        "useCallCache": config.call_cache,
        "deleteIntermediateOutputFiles": False,
        "useReferenceDisks": False,
        "memoryRetryMultiplier": 1.0,
        "workflowFailureMode": "NoNewCalls",
        "userComment": job_data.get("comment", ""),
        "ignoreEmptyOutputs": config.ignore_empty,
    }

    # Workflow operations
    workflow_config = WorkflowConfig.model_validate(wf_config_params)
    submission = terra.submissions.submit_workflow(workflow_config)
    logger.info(submission)
    status = terra.submissions.get_submission_status(submission["submissionId"])
    logger.debug(status)


def launch(args: argparse.Namespace, config: CLIConfig = CLIConfig()) -> None:
    """Prepare and manage launch execution of workflows in Terra"""

    if args.workflow_name and args.job_json:
        raise ValueError("--workflow and --job_json are mutually exclusive")
    elif not args.workflow_name and not args.job_json:
        raise ValueError("--workflow or --job_json are required")
    elif args.workflow_name and (
        not args.table or not args.input_json or not args.output_json
    ):
        raise ValueError(
            "--table, --input_json, and --output_json are required when using --workflow"
        )

    config.update(vars(args))
    job_dicts = prepare_job_dict(vars(args), config)

    terra = Terra(
        source_workspace=config.workspace,
        source_project=config.project,
        destination_workspace=config.workspace,
        destination_project=config.project,
    )

    for wf_name, job_data in job_dicts.items():
        logger.info(f"Launching workflow: {wf_name}")
        launch_job(job_data, terra, config)
        time.sleep(args.sleep)
