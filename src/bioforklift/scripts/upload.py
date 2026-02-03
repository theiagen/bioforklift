import logging
import pandas as pd
from pathlib import Path
from bioforklift.scripts.configure import CLIConfig
from bioforklift.terra import Terra


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def upload_args(parser):
    d_parser = parser.add_argument_group("Data Parameters")
    d_parser.add_argument("-i", "--input_path", type=str, help="Path to input data file in Terra workspace")
    d_parser.add_argument("-t", "--table", type=str, help="Terra entity table name for workflow")

    ws_parser = parser.add_argument_group("Terra Workspace Parameters")
    ws_parser.add_argument("-ws", "--workspace", type=str, help="Terra workspace name")
    ws_parser.add_argument("-p", "--project", type=str, help="Terra project name")
    return parser


def initialize_config(args, config):
    if not config:
        config = CLIConfig(
            workspace=args.workspace,
            project=args.project,
        )
    else:
        # Override config values with command-line arguments if provided
        if args.workspace is not None:
            config.workspace = args.workspace
        if args.project is not None:
            config.project = args.project
    return config


def upload(args, config=None):

    config = initialize_config(args, config)

    terra = Terra(
        source_workspace=config.workspace,
        source_project=config.project,
        destination_workspace=config.workspace,
        destination_project=config.project,
    )

    if args.input_path.endswith(".tsv"):
        sep = '\t'
    else:
        sep = ','
    if args.table:
        table_name = args.table
    else:
        table_name = Path(args.input_path).stem
    df = pd.read_csv(args.input_path, sep=sep)
    terra.entities.upload_entities(data=df, target=table_name)
    logger.info(f"Uploaded data from '{args.input_path}' to table '{table_name}' in workspace '{config.project}/{config.workspace}'")
