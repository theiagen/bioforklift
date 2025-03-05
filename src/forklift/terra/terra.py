from typing import Optional
from google.oauth2.credentials import Credentials
from .client import TerraClient
from .terra_entities import TerraEntities
from .terra_submissions import TerraSubmissions


class Terra:
    """
    Main interface for Terra operations.
    Provides single access point to data and workflow operations.
    """

    def __init__(
        self,
        source_workspace: str,
        source_project: str,
        destination_workspace: Optional[str] = None,
        destination_project: Optional[str] = None,
        credentials: Optional[Credentials] = None,
        firecloud_api_url: str = "https://api.firecloud.org/api",
    ):
        """
        Initialize Terra interface

        Args:
            source_workspace: Source Terra workspace name
            source_project: Source Terra project name
            target_workspace: Optional target Terra workspace name (defaults to source_workspace)
            target_project: Optional target Terra project name (defaults to source_project)
            credentials: Optional Google credentials
            firecloud_api_url: Base URL for Terra API
        """
        self.client = TerraClient(
            source_workspace=source_workspace,
            source_project=source_project,
            destination_workspace=destination_workspace,
            destination_project=destination_project,
            google_credentials_json=credentials,
            firecloud_api_url=firecloud_api_url,
        )

        self.entities = TerraEntities(self.client)
        self.submissions = TerraSubmissions(self.client)

    @property
    def source_workspace(self) -> str:
        """Get source workspace name"""
        return self.client.source_workspace

    @property
    def source_project(self) -> str:
        """Get source project name"""
        return self.client.source_project

    @property
    def destination_workspace(self) -> str:
        """Get destination workspace name"""
        return self.client.destination_workspace

    @property
    def destination_project(self) -> str:
        """Get destination project name"""
        return self.client.destination_project

    def update_source_workspace(
        self, source_workspace: str, source_project: Optional[str] = None
    ) -> None:
        """
        Update the source workspace and optionally the source project

        Args:
            source_workspace: New source workspace name
            source_project: Optional new source project name
        """
        self.client.source_workspace = source_workspace
        if source_project:
            self.client.source_project = source_project

    def update_target_workspace(
        self, destination_workspace: str, destination_project: Optional[str] = None
    ) -> None:
        """
        Update the destionation workspace and optionally the target project

        Args:
            destination_workspace: New destination workspace name
            destination_project: Optional new destination project name
        """
        # Nice little pivot utility to update the target workspace and optionally the target project
        self.client.destination_workspace = destination_workspace
        if destination_project:
            self.client.destination_project = destination_project
