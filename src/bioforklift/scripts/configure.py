import sys
import yaml
import argparse
from pathlib import Path
from datetime import datetime


class CLIConfig:
    """Configuration class for bioforklift CLI tool"""

    def __init__(
        self,
        config_path=None,
        repository=None,
        workspace=None,
        project=None,
        branch=None,
        call_cache=None,
        ignore_empty=None,
    ):
        self.repository = repository
        self.workspace = workspace
        self.project = project
        self.branch = branch
        self.call_cache = call_cache
        self.ignore_empty = ignore_empty
        self.config_path = config_path

        if config_path:
            loaded_config = self._load_config(self.config_path)
            if self.repository is None:
                self.repository = loaded_config["repository"]
            if self.workspace is None:
                self.workspace = loaded_config["workspace"]
            if self.project is None:
                self.project = loaded_config["project"]
            if self.branch is None:
                self.branch = loaded_config["branch"]
            if self.call_cache is None:
                self.call_cache = loaded_config["call_cache"]
            if self.ignore_empty is None:
                self.ignore_empty = loaded_config["ignore_empty"]

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        self.config_path = config_path
        if Path(config_path).is_file():
            with open(config_path, "r") as file:
                config = yaml.safe_load(file)
            return config
        else:
            raise FileNotFoundError(f"Configuration file not found at {config_path}")

    def write_config(self) -> None:
        """Write the current configuration to a YAML file"""
        current_date = datetime.now().strftime("%Y%m%d")
        if not self.config_path:
            self.config_path = f"{Path.home()}/.config/bioforklift.cfg"
        Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as file:
            file.write(f"# Bioforklift Configuration - {current_date}\n\n")
            yaml.safe_dump(self.__dict__, file)


def configure_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Define command-line arguments for configure subcommand"""
    wf_parser = parser.add_argument_group("Workflow Launch Parameters")
    wf_parser.add_argument(
        "-r",
        "--repository",
        type=str,
        default="github.com/theiagen/public_health_bioinformatics",
        help="GitHub repository for workflow source; DEFAULT: github.com/theiagen/public_health_bioinformatics",
    )
    wf_parser.add_argument(
        "-b",
        "--branch",
        type=str,
        default="main",
        help="GitHub branch for workflow source; DEFAULT: main",
    )
    wf_parser.add_argument(
        "-cc",
        "--call_cache",
        action="store_true",
        default=False,
        help="Enable call caching for the workflow submission; DEFAULT: False",
    )
    wf_parser.add_argument(
        "-ie",
        "--ignore_empty",
        action="store_true",
        default=False,
        help="Ignore empty outputs in the workflow submission; DEFAULT: False",
    )

    ws_parser = parser.add_argument_group("Terra Workspace Parameters")
    ws_parser.add_argument("-ws", "--workspace", type=str, help="Terra workspace name")
    ws_parser.add_argument("-p", "--project", type=str, help="Terra project name")
    return parser


def configure(configure_args: argparse.Namespace) -> None:
    """Configure bioforklift settings and write to configuration file"""
    config = CLIConfig(
        repository=configure_args.repository,
        workspace=configure_args.workspace,
        project=configure_args.project,
        branch=configure_args.branch,
        call_cache=configure_args.call_cache,
        ignore_empty=configure_args.ignore_empty,
        config_path=configure_args.config_path,
    )
    config.write_config()
    logger.info(f"Configuration written to {config.config_path}")
