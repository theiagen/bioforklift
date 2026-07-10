from .basespace_client import BaseSpaceClient
from .basespace_endpoints import BaseSpaceEndpoints
from .basespace_methods import BaseSpaceMethods
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class BaseSpace:
    """
    Main interface for BaseSpace operations.

    Wires up the HTTP client, methods, and endpoints so callers can reach the
    BaseSpace API through `client`, `methods`, and `endpoints`.

    Contains links to top-level orchestrator functions for convenience, while still
    providing access to the lower-level building blocks.
    """

    def __init__(
        self,
        access_token: str,
        basespace_api_url: str,
        basespace_api_version: str,
        max_retries: int,
    ):
        """
        Initialize the BaseSpace interface.

        Args:
            access_token: The access token for authenticating with the BaseSpace API.
            basespace_api_url: The base URL for the BaseSpace API.
            basespace_api_version: The version of the BaseSpace API to use.
            max_retries: Maximum number of automatic retries for transient failures.
        """
        client = BaseSpaceClient(
            access_token,
            basespace_api_url,
            basespace_api_version,
            max_retries,
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
        """

        self.client = client
        self.endpoints = BaseSpaceEndpoints(self.client)
        self.methods = BaseSpaceMethods(self.endpoints)

        # include links to top-level orchestrator functions for convenience
        self.fetch_sample_fastqs = self.methods.fetch_sample_fastqs