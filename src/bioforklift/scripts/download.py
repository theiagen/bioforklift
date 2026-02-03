import logging
from pathlib import Path
from bioforklift.scripts.configure import CLIConfig
from bioforklift.terra import Terra


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def download_args(parser):
    d_parser = parser.add_argument_group("Data Parameters")
    d_parser.add_argument("-t", "--table", type=str, help="Terra entity table name for workflow")

    ws_parser = parser.add_argument_group("Terra Workspace Parameters")
    ws_parser.add_argument("-ws", "--workspace", type=str, help="Terra workspace name")
    ws_parser.add_argument("-p", "--project", type=str, help="Terra project name")

    run_parser = parser.add_argument_group("Runtime Parameters")
    run_parser.add_argument("-o", "--output_path", type=str, help="Path to save downloaded data; DEFAULT: current directory")
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


def download(args, config=None):

    config = initialize_config(args, config)

    terra = Terra(
        source_workspace=config.workspace,
        source_project=config.project,
        destination_workspace=config.workspace,
        destination_project=config.project,
    )

    df = terra.entities.download_table(args.table, use_destination=True)
    output_path = Path(args.output_path) if args.output_path else Path(f"{args.table}.tsv")
    df.to_csv(output_path, index=False, sep='\t')
    logger.info(f"Downloaded table '{args.table}' to {output_path}")