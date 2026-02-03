#! /usr/bin/env python3

"""
Bioforklift: Automation Data Movement and Integration

main script for command-line bioforklift tool
"""

import sys
import argparse
from pathlib import Path
from bioforklift.scripts.launch import launch, launch_args
from bioforklift.scripts.configure import configure, configure_args, CLIConfig



def bioforklift_args(parser):
    subparsers = parser.add_subparsers(dest="command")

    # Configuration arguments
    config_parser_init = subparsers.add_parser("configure", aliases=["c"], help="Configure bioforklift settings")
    config_parser = configure_args(config_parser_init)

    # Download arguments
    download_parser = subparsers.add_parser("download", aliases=["d"], help="Download data from Terra workspace")
#    download_parser = download_args(download_parser)

    # Add arguments from launch_args to the launch subparser
    launch_parser = subparsers.add_parser("launch", aliases=["l"], help="Launch a workflow in Terra")
    launch_parser = launch_args(launch_parser)

    # Upload arguments
    upload_parser = subparsers.add_parser("upload", aliases=["u"], help="Upload data to Terra workspace")
#    upload_parser = upload_args(upload_parser)

    parser.add_argument("-c", "--config_path", type=str, default=f"{Path.home()}/.config/bioforklift.cfg", help="Path to bioforklift configuration file; DEFAULT: ~/.config/bioforklift.cfg")

    return parser 


def cl_init():
    init_parser = argparse.ArgumentParser(description="Bioforklift Command-Line Tool")
    parser = bioforklift_args(init_parser)
    args = parser.parse_args()
    config = CLIConfig(args.config_path)
    if args.command in {"launch", "l"}:
        launch(args, config)
    elif args.command in {"configure", "c"}:
        configure(args)
#    elif args.command in {"download", "d"}:
#        download(args)
#    elif args.command in {"upload", "u"}:
#        upload(args)
    else:
        parser.print_help() 


if __name__ == "__main__":
    cl_init()
    sys.exit(0)