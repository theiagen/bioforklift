import yaml
import argparse
from pathlib import Path
from datetime import datetime
from bioforklift.logging import setup_logger


logger = setup_logger(__name__)


class CLIConfig:
    """Configuration class for bioforklift CLI tool"""

    def __init__(
        self,
        values: dict = {},
        config_path: str = f"{Path.home()}/.config/bioforklift.cfg",
    ) -> None:
        self.repository = "github.com/theiagen/public_health_bioinformatics"
        self.workspace = None
        self.project = None
        self.branch = "main"
        self.call_cache = False
        self.ignore_empty = False
        self.config_path = config_path

        # Load existing configuration from file
        self._load(self.config_path)
        self.update(values, prefer_self=False)

    def update(self, updates: dict, prefer_self: bool = False) -> None:
        """Update configuration attributes from a dictionary"""
        for key, value in updates.items():
            if hasattr(self, key):
                if prefer_self and self.__dict__[key] is not None:
                    continue
                if value is not None:
                    setattr(self, key, value)

    def _load(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        self.config_path = config_path
        if Path(config_path).is_file():
            with open(config_path, "r") as file:
                config = yaml.safe_load(file)
                self.update(config)

    def write(self) -> None:
        """Write the current configuration to a YAML file"""
        current_date = datetime.now().strftime("%Y%m%d")
        Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as file:
            file.write(f"# bioforklift configuration - {current_date}\n\n")
            yaml.safe_dump(self.__dict__, file)


def configure_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Define command-line arguments for configure subcommand"""
    wf_parser = parser.add_argument_group("Workflow Launch Parameters")
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
    wf_parser.add_argument(
        "-cc",
        "--call_cache",
        action="store_true",
        help="Enable call caching for the workflow submission; DEFAULT: False",
    )
    wf_parser.add_argument(
        "-ie",
        "--ignore_empty",
        action="store_true",
        help="Ignore empty outputs in the workflow submission; DEFAULT: False",
    )

    ws_parser = parser.add_argument_group("Terra Workspace Parameters")
    ws_parser.add_argument("-ws", "--workspace", type=str, help="Terra workspace name")
    ws_parser.add_argument("-p", "--project", type=str, help="Terra project name")

    return parser


def configure(
    configure_args: argparse.Namespace, config: CLIConfig = CLIConfig()
) -> None:
    """Configure bioforklift settings and write to configuration file"""
    config.update(vars(configure_args), prefer_self=False)
    # Update with defaults
    config.write()
    logger.info(f"Configuration written to {config.config_path}")
