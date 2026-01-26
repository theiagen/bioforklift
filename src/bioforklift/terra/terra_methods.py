from typing import Dict, Any
from .models import MethodConfig
from .client import TerraClient
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class TerraMethods:
    """
    Class meant to handle Terra workflows and method configurations
    See https://github.com/broadinstitute/fiss/blob/b3fa2a0d888610e04f744f9e661fa32e46a5af95/firecloud/api.py#L650
    """


    def __init__(self, client: TerraClient):
        self.client = client


    def get_method_config(
        self,
        config_name: str,
        use_destination: bool = False,
    ) -> Dict[str, Any]:
        """
        Get a workspace method configuration by name. By default pulls from source workspace.

        Args:
            config_name: Name of the method configuration to retrieve

        Returns:
            Dict containing the method configuration details
        """
        client_project = self.client.destination_project if use_destination else self.client.source_project

        logger.info(f"Fetching workspace method configuration: {config_name} from project: {client_project}")
        response = self.client.get(
          f"method_configs/{client_project}/{config_name}",
          use_destination=use_destination,
        )
        return response.json()


    def overwrite_method_config(
        self,
        config: MethodConfig,
        use_destination: bool = True,
    ) -> Dict[str, Any]:
        """
        Add or overwrite a new workspace method configuration. AKA create a new workflow in Terra with inputs/outputs defined.
        By default pulls from destination workspace.

        Args:
            config: MethodConfig containing all configuration details

        Returns:
            Dict containing the created method configuration details
        """
        client_project = self.client.destination_project if use_destination else self.client.source_project

        logger.info(f"Uploading workspace method configuration: {config.name} to project: {client_project}")
        return self.client.put(
            f"method_configs/{client_project}/{config.name}",
            data=config.model_dump(exclude_none=True),
            use_destination=use_destination,
        ).json()


    def method_config_validate(
      self,
      config: MethodConfig,
      use_destination: bool = True,
    ) -> Dict[str, Any]:
        """
        Validate a workspace method configuration. Note that this can only validate existing configurations in the workspace.
        Meaning you must first call `overwrite_method_config` before validating a new configuration.
        Args:
            config: MethodConfig containing all configuration details

        Returns:
            Dict containing the validation results
        """
        client_project = self.client.destination_project if use_destination else self.client.source_project

        logger.info(f"Validating workspace method configuration: {config.name} from project: {client_project}")
        response = self.client.get(
            f"method_configs/{client_project}/{config.name}/validate",
            use_destination=use_destination,
        ).json()

        # Check for invalid inputs/outputs and raise error if found
        invalid_fields = {}
        for key in ["invalidInputs", "invalidOutputs", "missingInputs", "extraInputs"]:
            if response[key]:
                invalid_fields[key] = response[key]

        if invalid_fields:
            msg = "MethodConfig validation errors found:\n" + "\n".join(
                f"- {key}: {val}" for key, val in invalid_fields.items()
            )
            logger.error(msg)
            raise ValueError(msg)

        return response


    def dict_to_method_config(
        self,
        config_dict: Dict[str, Any]
    ) -> MethodConfig:
        """
        Convert a dictionary to a MethodConfig object without making an API call.
        Useful for modifying existing configurations.

        Args:
            config_dict: Dict containing method configuration details

        Returns:
            MethodConfig object constructed from the dictionary
        """
        return MethodConfig.model_validate(config_dict)