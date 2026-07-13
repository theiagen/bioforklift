#! /usr/bin/env python3

"""
Bioforklift: Automation Data Movement and Integration

main script for command-line bioforklift tool
"""

import sys
import argparse
from pathlib import Path
from bioforklift import __version__
from bioforklift.scripts.launch import launch, launch_args
from bioforklift.scripts.upload import upload, upload_args
from bioforklift.scripts.download import download, download_args
from bioforklift.scripts.configure import configure, configure_args, CLIConfig
from bioforklift.forklift_logging import setup_logger


logger = setup_logger(__name__)


def bioforklift_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Define command-line arguments for bioforklift tool with subcommands"""
    subparsers = parser.add_subparsers(dest="command")

    # Configuration arguments
    config_parser_init = subparsers.add_parser(
        "configure", aliases=["c"], help="Configure bioforklift settings"
    )
    config_parser = configure_args(config_parser_init)

    # Download arguments
    download_parser = subparsers.add_parser(
        "download", aliases=["d"], help="Download data from Terra workspace"
    )
    download_parser = download_args(download_parser)

    # Add arguments from launch_args to the launch subparser
    launch_parser = subparsers.add_parser(
        "launch", aliases=["l"], help="Launch a workflow in Terra"
    )
    launch_parser = launch_args(launch_parser)

    # Upload arguments
    upload_parser = subparsers.add_parser(
        "upload", aliases=["u"], help="Upload data to Terra workspace"
    )
    upload_parser = upload_args(upload_parser)

    return parser


def run():
    """Main function to run bioforklift command-line tool"""
    init_parser = argparse.ArgumentParser(description="Bioforklift Command-Line Tool")
    init_parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser = bioforklift_args(init_parser)
    parser.add_argument("-b", "--bunkee", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.bunkee:
        logger.info("BioBunkee mode activated")
        sys.exit(0)

    # Load configuration
    config = CLIConfig()

    # Execute the appropriate subcommand
    if args.command in {"launch", "l"}:
        launch(args, config)
    elif args.command in {"configure", "c"}:
        configure(args, config)
    elif args.command in {"download", "d"}:
        download(args, config)
    elif args.command in {"upload", "u"}:
        upload(args, config)
    else:
        parser.print_help()


if __name__ == "__main__":
    run()
    sys.exit(0)
