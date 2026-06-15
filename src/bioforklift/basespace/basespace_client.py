import requests
from typing import Optional, Dict
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class BaseSpaceClient:
    """Client for interacting with the BaseSpace API."""

    def __init__(
        self,
        access_token: str,
        basespace_api_url: str = "https://api.basespace.illumina.com",
        basespace_api_version: str = "v2", # optionally `v1pre3`
    ):
        self.access_token = access_token
        self.base_url = basespace_api_url.rstrip("/")
        self.api_version = basespace_api_version

    @property
    def _get_headers(self) -> Dict[str, str]:
        """Helper method to construct headers for API requests."""
        return {"x-access-token": self.access_token}

    def _build_url_path(
        self,
        endpoint: str,
    ) -> str:
        """Helper method to construct full URL for API requests."""
        logger.debug(f"Building BaseSpace URL for endpoint: {endpoint} with API version: {self.api_version}")
        return f"{self.base_url}/{self.api_version}/{endpoint.lstrip('/')}"

    def _http_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        stream: Optional[bool] = False,
        timeout: Optional[tuple] = None,
    ) -> requests.Response:
        """
        Helper method to make HTTP requests to the BaseSpace API

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Query parameters
            stream: Whether to stream the response
            timeout: Request timeout as (connect_timeout, read_timeout) in seconds

        Returns:
            Response object from the requests library
        """

        url = self._build_url_path(endpoint)
        logger.debug(f"BaseSpace URL constructed: {url}")

        # Default timeout: 30s to connect, 5min to read
        if timeout is None:
            timeout = (30, 300)

        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=self._get_headers,
                params=params,
                stream=stream,
                timeout=timeout,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"HTTP request failed: {e}")
            raise

    def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        timeout: Optional[tuple] = None,
        stream: Optional[bool] = False,
    ) -> requests.Response:
        """
        Make a GET request to the BaseSpace API.
        """
        return self._http_request(
            "GET",
            endpoint,
            params=params,
            timeout=timeout,
            stream=stream,
        )