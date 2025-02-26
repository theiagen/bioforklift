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
        workspace: str,
        project: str,
        credentials: Optional[Credentials] = None,
        firecloud_api_url: str = "https://api.firecloud.org/api",
    ):
        """
        Initialize Terra interface

        Args:
            workspace: Terra workspace name
            project: Terra project name
            credentials: Optional Google credentials
            firecloud_api_url: Base URL for Terra API
        """
        self.client = TerraClient(
            workspace=workspace,
            project=project,
            credentials=credentials,
            firecloud_api_url=firecloud_api_url,
        )

        self.entities = TerraEntities(self.client)
        self.submissions = TerraSubmissions(self.client)