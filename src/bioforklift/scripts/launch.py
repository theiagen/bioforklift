import json
import time
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
from bioforklift.terra.exceptions import TerraServerError, TerraNotFoundError
from bioforklift.scripts.configure import CLIConfig
from bioforklift.scripts.download import extract_samples, filter_df
from bioforklift.terra import Terra, WorkflowConfig, MethodConfig
from bioforklift.forklift_logging import setup_logger


logger = setup_logger(__name__)


def launch_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Define command-line arguments for launch subcommand"""
    wf_parser = parser.add_argument_group("Workflow Parameters")
    wf_parser.add_argument(
        "-wf", "--workflow_name", type=str, help="Terra workflow name to run"
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

    tbl_parser = parser.add_argument_group("Table Parameters")
    tbl_parser.add_argument(
        "-t", "--table", type=str, help="Terra entity table name for workflow"
    )
    tbl_parser.add_argument(
        "--entity_name",
        type=str,
        help="Terra entity (set) name for workflow; DEFAULT: table name with timestamp",
    )
    tbl_parser.add_argument(
        "-rs",
        "--reuse_set",
        action="store_true",
        default=False,
        help="Reuse set defined by '--entity_name' - overrides '--samples'; DEFAULT: append current time to existing set",
    )
    tbl_parser.add_argument(
        "-s", "--samples", nargs="+", help="Sample name(s) to filter rows upon"
    )
    tbl_parser.add_argument(
        "-f", "--filter", type=str, nargs="+", help="Strings to filter rows upon"
    )
    tbl_parser.add_argument(
        "-fc",
        "--filter_column",
        type=str,
        nargs="+",
        help="Column name(s) to apply filter(s) to; DEFAULT: all",
    )
    tbl_parser.add_argument(
        "-M",
        "--exact_match",
        action="store_true",
        help="Require exact match rather than substring match for filter(s)",
    )
    tbl_parser.add_argument(
        "-e",
        "--exclusion_filter",
        action="store_true",
        help="Exclude rows matching the filter(s)",
    )
    tbl_parser.add_argument(
        "-x",
        "--max_rows",
        type=int,
        help="Maximum number of rows to include per filter; DEFAULT: all rows",
    )
    tbl_parser.add_argument(
        "-R",
        "--randomize",
        action="store_true",
        help="Randomize extraction of filtered rows",
    )

    launch_parser = parser.add_argument_group("Launch Parameters")
    launch_parser.add_argument(
        "-cc",
        "--call_cache",
        action="store_true",
        help="Enable call caching",
    )
    launch_parser.add_argument(
        "-C",
        "--comment",
        type=str,
        help="Submission comment",
    )
    launch_parser.add_argument(
        "-ie",
        "--ignore_empty",
        action="store_true",
        help="Ignore empty outputs",
    )
    launch_parser.add_argument(
        "--sleep",
        type=int,
        default=5,
        help="Seconds to wait between launching multiple workflows; DEFAULT: 5",
    )

    io_parser = parser.add_argument_group("Input/Output Parameters")
    io_parser.add_argument(
        "-j",
        "--job_json",
        nargs="+",
        type=str,
        help="Path(s) to workflow submission JSON(s)",
    )
    io_parser.add_argument(
        "-i",
        "--input_json",
        type=str,
        help="Path to input JSON file for workflow input mapping",
    )
    io_parser.add_argument(
        "-o",
        "--output_json",
        type=str,
        help="Path to output JSON file for workflow output mapping",
    )
    io_parser.add_argument(
        "-n",
        "--input_variables",
        type=str,
        nargs="+",
        help="Input variable(s) (prepended with WDL workflow name, will overwrite JSON variables)",
    )
    io_parser.add_argument(
        "-nv",
        "--input_values",
        type=str,
        nargs="+",
        help="Input value(s) (ordered with --input_variables)",
    )
    io_parser.add_argument(
        "-ww",
        "--wdl_workflow",
        type=str,
        help="WDL workflow name to prepend --input_variables; DEFAULT: workflow name",
    )

    ws_parser = parser.add_argument_group("Terra Parameters")
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


def arg_handling(args: argparse.Namespace) -> None:
    """Handle argument validation and error handling for workflow submission"""
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
    elif args.job_json and (args.table or args.input_json or args.output_json):
        raise ValueError(
            "--table, --input_json, and --output_json cannot be used with --job_json"
        )
    elif (args.input_variables and not args.input_values) or (
        not args.input_variables and args.input_values
    ):
        raise ValueError("--input_variables and --input_values must be used together")
    elif args.input_variables and args.input_values:
        if len(args.input_variables) != len(args.input_values):
            raise ValueError(
                "The number of --input_variables and --input_values values must be the same"
            )


def check_entity_exists(terra: Terra, entity_name: Str, table_name: Str) -> bool:
    """Check if a specific entity (set) exists in the Terra workspace"""
    entity_type = f"{table_name.removesuffix("_set")}_set"  # entity type is always the set table, even if the user is referencing an existing non-set table
    try:
        entity = terra.entities.get_entity(
            entity_type=entity_type,
            entity_name=entity_name,
            use_destination=True,
        )
        return entity is not None
    except TerraNotFoundError:
        return False
    except TerraServerError as e:
        logger.error(f"Error checking for entity existence: {e}")
        raise e


def prepare_entity_name(
    terra: Terra, entity_name: Str, table_name: Str, reuse_set: bool
) -> Str:

    # Create a default entity name and update `job_data` with it if the user hasn't provided an --entity_name
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Raise an error if the user tries to create a set that already exists
    # Otherwise create the new set with either the default timestammped name or the user-provided --entity_name
    if entity_name:
        logger.info(f"Checking if entity '{entity_name}' exists")
        entity_exists = check_entity_exists(terra, entity_name, table_name)

        if entity_exists:
            if reuse_set:
                logger.info(f"Entity '{entity_name}' exists and will be reused")
                return entity_exists
            else:
                new_entity_name = f"{entity_name}_{current_time}"
                logger.warning(
                    f"Entity '{entity_name}' exists and new entity will be named {new_entity_name}"
                )
                return new_entity_name
    else:
        return f"{table_name}_set_{current_time}"


def prepare_job_dicts(args_dict: dict, config: CLIConfig) -> dict:
    """Extract workflow submission parameters from JSON file if provided

    Preference is given to command-line arguments over JSON file values."""

    # argument to requirement
    wf_args = {
        "workflow_name": True,
        "table": True,
        "reuse_set": False,
        "input_json": True,
        "output_json": True,
        "comment": False,
        "branch": True,
        "call_cache": True,
        "ignore_empty": True,
        "preexisting_config": True,
        "filter": False,
        "filter_column": False,
        "exact_match": False,
        "randomize": False,
        "exclusion_filter": False,
        "max_rows": False,
        "samples": False,
    }

    job_dict = {}
    # parse JSON input
    if args_dict.get("job_json"):
        for job_json_path in args_dict["job_json"]:
            with open(job_json_path, "r") as json_file:
                json_data = json.load(json_file)
            # iterate through workflows in json file
            for wf, entity_dict in json_data.items():
                job_dict[wf] = {}
                for entity, wf_data in entity_dict.items():
                    job_dict[wf][entity] = wf_data
                    for arg, require in wf_args.items():
                        # use the argument preferentially from command-line
                        if args_dict.get(arg) is not None:
                            job_dict[wf][entity][arg] = args_dict.get(arg)
                        # else use from json if present
                        elif wf_data.get(arg) is not None:
                            job_dict[wf][entity][arg] = wf_data.get(arg)
                        # else pull from config if required
                        elif require:
                            if config.__dict__.get(arg) is not None:
                                job_dict[wf][entity][arg] = config.__dict__.get(arg)
                            # raise error if still missing
                            else:
                                raise KeyError(
                                    f"Missing required argument '{arg}' for workflow '{wf}'"
                                )
    else:
        # single workflow from command-line args
        wf = args_dict["workflow_name"]
        entity = args_dict["entity_name"]
        job_dict[wf] = {entity: {"workflow_name": wf}}
        for arg, require in wf_args.items():
            # use from command-line args if present
            if args_dict.get(arg) is not None:
                if arg == "input_json" or arg == "output_json":
                    with open(args_dict.get(arg), "r") as io_file:
                        job_dict[wf][entity][arg] = json.load(io_file)
                else:
                    job_dict[wf][entity][arg] = args_dict.get(arg)
            # else pull from config if required
            elif require:
                if config.__dict__.get(arg) is not None:
                    job_dict[wf][entity][arg] = config.__dict__.get(arg)
                # raise error if still missing
                else:
                    raise KeyError(
                        f"Missing required argument '{arg}' for workflow '{wf}'"
                    )

    # update with command line input_variabless if required
    if args_dict.get("input_variables"):
        modified_io = {
            mod: val
            for mod, val in zip(
                args_dict.get("input_variables"), args_dict.get("input_values")
            )
        }
        for wf, entity_dict in job_dict.items():
            for entity, wf_data in wf_dict.items():
                # prepend workflow name to added keys
                wf_io = {}
                for k, v in modified_io.items():
                    if args_dict.get("wdl_workflow"):
                        wf_io[f"{args_dict.get('wdl_workflow')}.{k}"] = v
                    else:
                        wf_io[f"{wf}.{k}"] = v
                job_dict[wf][entity]["input_json"] = {
                    **job_dict[wf][entity]["input_json"],
                    **wf_io,
                }

    return job_dict


def prepare_entity_set(
    terra: Terra, table_name: str, job_data: dict, entity_name=None
) -> str:
    """Prepare a table in the Terra workspace for workflow submission by creating an entity set based on the input table"""
    # cannot download set tables, so we must download the base and then create the set
    # could implement a way to use local table
    try:
        new_table_df = terra.entities.download_table(table_name, use_destination=True)
    except TerraServerError as e:
        raise TerraServerError(
            f'Error downloading table; does "{table_name}" exist in the Terra workspace?'
        )
    # filter if requested
    if (
        job_data.get("samples")
        or job_data.get("filter")
        or job_data.get("randomize")
        or job_data.get("max_rows")
    ):
        logger.info(f"Filtering table {table_name}")
        samples = filter_mngr(new_table_df, job_data, terra)
        logger.info(
            f"Samples filtered for submission:\n\t{'\n\t'.join(sorted(samples))}"
        )
        result = terra.entities.create_entity_set(entity_name, table_name, samples)
    else:
        result = terra.entities.create_entity_set(entity_name, table_name, new_table_df)

    if not result.ok:
        logger.error(f"Failed to create {entity_name} entity set")
        raise TerraServerError(f"Entity set creation failed: {result.text}")

    logger.info(f"{entity_name} entity set created successfully")
    return entity_name  # return name of entity set created for use in workflow config


def prepare_method_config(
    mod_method_config: MethodConfig,
    job_data: dict,
    terra: Terra,
    config: CLIConfig,
    source_repo: str = "dockstore",
    method_uri: str = None,
    method_config_version: int = 0,
) -> MethodConfig:
    """Prepare a method configuration for workflow submission by incorporating metadata"""
    # modify method config for the new workspace
    mod_method_config.namespace = terra.client.destination_project
    mod_method_config.rootEntityType = f"{job_data['table']}"
    mod_method_config.methodRepoMethod.methodUri = method_uri
    mod_method_config.methodRepoMethod.sourceRepo = source_repo
    mod_method_config.methodRepoMethod.methodPath = (
        f"{config.repository}/{job_data['workflow_name']}"
    )
    mod_method_config.methodRepoMethod.methodVersion = job_data["branch"]
    mod_method_config.methodConfigVersion = method_config_version

    # set inputs from json file and dynamically set samplename based on table name
    mod_method_config.inputs = job_data["input_json"]
    # set outputs from json file
    mod_method_config.outputs = job_data["output_json"]
    return mod_method_config


def validate_method_config(mod_method_config: MethodConfig, terra: Terra) -> dict:
    """Validate the method configuration in the Terra workspace and raise error if invalid I/O detected"""
    # Validate the new method configuration we created in the Terra workspace
    val = terra.methods.method_config_validate(mod_method_config, use_destination=True)
    # raise error if invalid I/O detected
    if val["invalidInputs"] or val["invalidOutputs"]:
        if val["invalidInputs"]:
            logger.error(f"Invalid inputs detected: {val['invalidInputs']}")
        if val["invalidOutputs"]:
            logger.error(f"Invalid outputs detected: {val['invalidOutputs']}")
        raise KeyError("Invalid I/O")
    return val


def prepare_workflow_config(
    terra: Terra,
    mod_method_config: MethodConfig,
    job_data: dict,
    entity_name: str,
    config: CLIConfig,
) -> WorkflowConfig:
    """Prepare a workflow configuration for workflow submission by incorporating metadata"""
    set_mode = job_data["table"].endswith("_set")
    wf_config_params = {
        "methodConfigurationNamespace": terra.client.destination_project,
        "methodConfigurationName": mod_method_config.name,
        "entityType": f"{job_data['table'].removesuffix("_set")}_set",  # entityType will always be the name of the set table
        "entityName": f"{entity_name}",  # entityName is name of specific row in table
        "expression": (
            None if set_mode else f"this.{job_data['table']}s"
        ),  # if rootEntityType is a set table, expression must be None. Otherwise, use this.{table_name}s format.
        "useCallCache": config.call_cache,
        "deleteIntermediateOutputFiles": False,
        "useReferenceDisks": False,
        "memoryRetryMultiplier": 1.0,
        "workflowFailureMode": "NoNewCalls",
        "userComment": job_data.get("comment", job_data.get("branch", "")),
        "ignoreEmptyOutputs": config.ignore_empty,
    }

    # Workflow operations
    workflow_config = WorkflowConfig.model_validate(wf_config_params)
    return workflow_config


def launch_job(
    entity_name: str, job_data: dict, terra: Terra, config: CLIConfig
) -> None:
    """Launch a workflow in Terra based on provided job data"""

    # get method config dictionary from existing workspace
    if job_data.get("preexisting_config"):
        base_method_config_dict = terra.methods.get_method_config(
            job_data["workflow_name"], use_destination=True
        )
        base_method_config = terra.methods.dict_to_method_config(
            base_method_config_dict
        )
    # generate method config dictionary
    else:
        base_method_config = terra.methods.generate_method_config(
            config.repository,
            job_data["workflow_name"],
            job_data["table"],
            job_data["input_json"],
            job_data["output_json"],
            job_data["branch"],
        )

    mod_method_config = base_method_config.model_copy(deep=True)
    mod_method_config = prepare_method_config(
        mod_method_config, job_data, terra, config
    )

    # Adds or overwrites the method configuration in the Terra workspace
    terra.methods.overwrite_method_config(mod_method_config, use_destination=True)
    validate_method_config(mod_method_config, terra)

    # Prepare and submit the workflow configuration for execution in Terra
    workflow_config = prepare_workflow_config(
        terra, mod_method_config, job_data, entity_name, config
    )
    submission = terra.submissions.submit_workflow(workflow_config)
    logger.info(submission)
    status = terra.submissions.get_submission_status(submission["submissionId"])
    # this is perhaps a suboptimal way of doing this due to hard-coding the Terra link
    submission_prefix = f"https://app.terra.bio/#workspaces/{config.project}/{config.workspace}/submission_history/"
    submission_url = f"{submission_prefix}{submission['submissionId']}"
    logger.info(f"Submission URL: {submission_url}")
    logger.debug(status)


def filter_mngr(df: pd.DataFrame, job_data: dict, terra: Terra) -> list:
    """Extract sample list from filters"""
    sample_col = df.columns[0]
    if job_data.get("samples"):
        logger.debug(f"Extracting samples: {job_data.get('samples')}")
        df = extract_samples(df, samples=job_data.get("samples"), sample_col=sample_col)
    filtered_df = filter_df(
        df,
        filters=job_data.get("filter"),
        filter_columns=job_data.get("filter_column"),
        match=job_data.get("exact_match", False),
        exclude=job_data.get("exclusion_filter", False),
        max_rows=job_data.get("max_rows"),
        randomize=job_data.get("randomize", False),
    )
    return filtered_df[sample_col].tolist()


def launch(args: argparse.Namespace, config: CLIConfig = CLIConfig()) -> None:
    """Prepare and manage launch execution of workflows in Terra"""

    # Validate and handle arguments
    arg_handling(args)

    # Update configuration with command-line arguments
    config.update(vars(args))

    # Prepare job dictionary from command-line arguments and/or JSON file input

    job_dicts = prepare_job_dicts(vars(args), config)

    # Initialize Terra client
    terra = Terra(
        source_workspace=config.workspace,
        source_project=config.project,
        destination_workspace=config.workspace,
        destination_project=config.project,
    )

    # Submit workflows for each job in the job dictionary
    first = True
    for wf_name, entity_dict in job_dicts.items():
        for entity_name, job_data in entity_dict.items():
            if not first:
                time.sleep(args.sleep)
            first = False
            logger.info(f"Launching workflow: {wf_name}")

            clean_table_name = job_data["table"].removesuffix("_set")
            clean_entity_name = prepare_entity_name(
                terra, entity_name, clean_table_name, job_data["reuse_set"]
            )
            prepare_entity_set(terra, clean_table_name, job_data, clean_entity_name)

            launch_job(clean_entity_name, job_data, terra, config)
