from .basespace_client import BaseSpaceClient
from .basespace_methods import BaseSpaceMethods
from .basespace_endpoints import BaseSpaceEndpoints
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class BaseSpace:
    """
    Main interface for BaseSpace operations.

    Wires up the HTTP client and methods, and exposes a single entry point for
    downloading a sample's paired-end FASTQs.
    """

    def __init__(
        self,
        access_token: str,
        basespace_api_url: str = "https://api.basespace.illumina.com",
        basespace_api_version: str = "v2",
    ):
        """
        Initialize the BaseSpace interface.

        Args:
            access_token: The access token for authenticating with the BaseSpace API.
            basespace_api_url: The base URL for the BaseSpace API.
            basespace_api_version: The version of the BaseSpace API to use.
        """
        self.client = BaseSpaceClient(
            access_token,
            basespace_api_url,
            basespace_api_version
        )
        self.methods = BaseSpaceMethods(self.client)
        self.endpoints = BaseSpaceEndpoints(self.client)

    @classmethod
    def from_client(cls, client: BaseSpaceClient) -> "BaseSpace":
        """
        Create a BaseSpace instance from an existing BaseSpaceClient.

        Args:
            client: An instance of BaseSpaceClient.

        Returns:
            A BaseSpace instance initialized with the provided client.
        """

        return cls(
            access_token=client.access_token,
            basespace_api_url=client.base_url,
            basespace_api_version=client.api_version
        )