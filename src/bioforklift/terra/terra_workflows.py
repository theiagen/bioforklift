from typing import Dict, Any
from .models import WorkspaceMethodConfig
from .client import TerraClient
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class TerraWorkflows:
    """
    Class meant to handle Terra workflows and method configurations
    See https://github.com/broadinstitute/fiss/blob/b3fa2a0d888610e04f744f9e661fa32e46a5af95/firecloud/api.py#L650
    """


    def __init__(self, client: TerraClient):
        self.client = client

    def get_workspace_method_config(
        self,
        config_name: str,
    ) -> Dict[str, Any]:
        """
        Get a workspace method configuration by name.

        Args:
            config_name: Name of the method configuration to retrieve

        Returns:
            Dict containing the method configuration details
        """
        logger.info(f"Fetching workspace method configuration: {config_name}")
        response = self.client.get(
          f"method_configs/{self.client.destination_project}/{config_name}",
          use_destination=True,
        )
        return response.json()


    def overwrite_workspace_method_config(
        self,
        config: WorkspaceMethodConfig
    ) -> Dict[str, Any]:
        """
        Add or overwrite a new workspace method configuration. AKA create a new workflow in Terra with inputs/outputs defined.

        Args:
            config: WorkspaceMethodConfig containing all configuration details

        Returns:
            Dict containing the created method configuration details
        """

        logger.info(f"Uploading workspace method configuration: {config.name}")
        return self.client.put(
            f"method_configs/{self.client.destination_project}/{config.name}",
            data=config.model_dump(exclude_none=True),
            use_destination=True,
        ).json()


    def workspace_method_validate(
      self,
      config: WorkspaceMethodConfig
    ) -> Dict[str, Any]:
        """
        Validate a workspace method configuration.

        Args:
            config: WorkspaceMethodConfig containing all configuration details

        Returns:
            Dict containing the validation results
        """
        logger.info(f"Validating workspace method configuration: {config.name}")
        response = self.client.get(
            f"method_configs/{self.client.destination_project}/{config.name}/validate",
            use_destination=True,
        )
        return response.json()
