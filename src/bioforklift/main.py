#! /usr/bin/env python3

"""
Bioforklift: Automation Data Movement and Integration

main script for command-line bioforklift tool
"""

import sys
import argparse
from bioforklift.scripts.launcher import launcher, launcher_args


def bioforklift_args(parser):
    subparsers = parser.add_subparsers()

    # Configuration arguments
    config_parser = subparsers.add_parser("config", help="Configure bioforklift settings")
#    config_parser = config_args(config_parser)

    # Download arguments
    download_parser = subparsers.add_parser("download", help="Download data from Terra workspace")
#    download_parser = download_args(download_parser)

    # Add arguments from launcher_args to the launcher subparser
    launcher_parser = subparsers.add_parser("launch", help="Launch a workflow in Terra")
    launcher_parser = launcher_args(launcher_parser)

    # Upload arguments
    upload_parser = subparsers.add_parser("upload", help="Upload data to Terra workspace")
#    upload_parser = upload_args(upload_parser)

    return parser 

def cl_init():
    init_parser = argparse.ArgumentParser(description="Bioforklift Command-Line Tool")
    parser = bioforklift_args(init_parser)
    args = parser.parse_args()


if __name__ == "__main__":
    cl_init()
    sys.exit(0)