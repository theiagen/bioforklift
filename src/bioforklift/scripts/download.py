import logging
import argparse
from pathlib import Path
from bioforklift.scripts.configure import CLIConfig
from bioforklift.terra import Terra


logger = logging.getLogger(__name__)


def download_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Define command-line arguments for download subcommand"""
    d_parser = parser.add_argument_group("Data Parameters")
    d_parser.add_argument(
        "table", type=str, nargs="+",help="Terra entity table name(s) (space-delimited)"
    )

    ws_parser = parser.add_argument_group("Terra Workspace Parameters")
    ws_parser.add_argument("-ws", "--workspace", type=str, help="Terra workspace name")
    ws_parser.add_argument("-p", "--project", type=str, help="Terra project name")

    run_parser = parser.add_argument_group("Runtime Parameters")
    run_parser.add_argument(
        "-o",
        "--output_path",
        type=str,
        help="Path to save downloaded data; DEFAULT: current directory",
    )
    return parser


def download(args: argparse.Namespace, config: CLIConfig = CLIConfig()) -> None:
    """Download data from Terra workspace"""
    config.update(vars(args))

    terra = Terra(
        source_workspace=config.workspace,
        source_project=config.project,
        destination_workspace=config.workspace,
        destination_project=config.project,
    )

    # Create output directory if it doesn't exist
    if args.output_path:
        output_dir = Path(args.output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = Path.cwd()

    terra_entities = terra.entities.list_entity_types(include_attributes=False)
    for table in args.table:
        if table not in terra_entities:
            raise ValueError(f"Table '{table}' does not exist in the Terra workspace.")
        df = terra.entities.download_table(table, use_destination=True)
        # Save the downloaded table to defined output path or current directory
        output_path = output_dir / f"{table}.tsv"
        df.to_csv(output_path, index=False, sep="\t")
        logger.info(f"Downloaded table '{table}' to {output_path}")