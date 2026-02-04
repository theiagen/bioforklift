import logging
import argparse
import pandas as pd
from pathlib import Path
from bioforklift.scripts.configure import CLIConfig
from bioforklift.terra import Terra


logger = logging.getLogger(__name__)


def upload_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Command-line arguments for uploading data to Terra workspace"""
    d_parser = parser.add_argument_group("Data Parameters")
    d_parser.add_argument(
        "-i",
        "--input_path",
        type=str,
        help="Path to input data file in Terra workspace",
    )
    d_parser.add_argument(
        "-t", "--table", type=str, help="Terra entity table name for workflow"
    )
    d_parser.add_argument(
        "-o", "--overwrite", action="store_true", help="Overwrite existing entities"
    )

    ws_parser = parser.add_argument_group("Terra Workspace Parameters")
    ws_parser.add_argument("-ws", "--workspace", type=str, help="Terra workspace name")
    ws_parser.add_argument("-p", "--project", type=str, help="Terra project name")
    return parser


def upload(args: argparse.Namespace, config: CLIConfig = CLIConfig()) -> None:
    """Upload data to Terra workspace"""

    config.update(vars(args))

    terra = Terra(
        source_workspace=config.workspace,
        source_project=config.project,
        destination_workspace=config.workspace,
        destination_project=config.project,
    )

    # attempt to infer separator
    if args.input_path.endswith(".tsv"):
        sep = "\t"
    else:
        sep = ","

    # determine table name
    if args.table:
        table_name = args.table
    else:
        table_name = Path(args.input_path).stem

    # upload data
    df = pd.read_csv(args.input_path, sep=sep)
    terra_entities = terra.entities.list_entity_types(include_attributes=False)
    if not args.overwrite and table_name in terra_entities:
        raise ValueError(f"Table '{table_name}' already exists in workspace. Use --overwrite to replace it.")
    terra.entities.upload_entities(data=df, target=table_name)
    if logger:
        logger.info(
            f"Uploaded data from '{args.input_path}' to table '{table_name}' in workspace '{config.project}/{config.workspace}'"
        )