from .basespace_client import BaseSpaceClient
from .basespace_methods import BaseSpaceMethods
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class BaseSpace:
    """
    Main interface for BaseSpace operations.

    Wires up the HTTP client, methods, and endpoints so callers can reach the
    BaseSpace API through `client`, `methods`, and `endpoints`.
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
        client = BaseSpaceClient(
            access_token,
            basespace_api_url,
            basespace_api_version,
        )
        self._wire(client)

    @classmethod
    def from_client(cls, client: BaseSpaceClient) -> "BaseSpace":
        """
        Create a BaseSpace instance from an existing BaseSpaceClient.

        Args:
            client: An instance of BaseSpaceClient.

        Returns:
            A BaseSpace instance that reuses the provided client.
        """

        instance = cls.__new__(cls)
        instance._wire(client)
        return instance

    def _wire(self, client: BaseSpaceClient) -> None:
        """
        Wire up the client, methods, and endpoints from a single client instance.

        `endpoints` is shared with `methods` so exactly one `BaseSpaceEndpoints`
        instance exists per `BaseSpace`.
        """

        self.client = client
        self.methods = BaseSpaceMethods(client)
        self.endpoints = self.methods.endpoints
