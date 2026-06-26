from typing import Dict, Optional

import requests

from .basespace_exceptions import (
    BaseSpaceConnectionError,
    BaseSpaceInvalidResponseError,
    BaseSpaceTimeoutError,
    api_error_for_status,
)
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class BaseSpaceClient:
    """
    Client for interacting with the BaseSpace API.
    """

    def __init__(
        self,
        access_token: str,
        basespace_api_url: str = "https://api.basespace.illumina.com",
        basespace_api_version: str = "v2",
    ):
        self.access_token = access_token
        self.base_url = basespace_api_url.rstrip("/")
        self.api_version = basespace_api_version

    @property
    def _headers(self) -> Dict[str, str]:
        """
        Helper property to construct headers for API requests.
        """

        return {"x-access-token": self.access_token}

    def _build_url_path(
        self,
        endpoint: str,
    ) -> str:
        """
        Helper method to construct full URL for API requests.
        """

        return f"{self.base_url}/{self.api_version}/{endpoint.strip('/')}"

    def _http_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        stream: bool = False,
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

        # Default timeout: 30s to connect, 5min to read
        if timeout is None:
            timeout = (30, 300)

        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=self._headers,
                params=params,
                stream=stream,
                timeout=timeout,
            )
            logger.debug(f"BaseSpace URL constructed: {response.url}")
            response.raise_for_status()
            return response
        except requests.Timeout as e:
            logger.error(f"Request to {url} timed out: {e}")
            raise BaseSpaceTimeoutError(f"Request to {url} timed out") from e
        except requests.ConnectionError as e:
            logger.error(f"Could not connect to {url}: {e}")
            raise BaseSpaceConnectionError(f"Could not connect to {url}") from e
        except requests.HTTPError as e:
            # Attempt to parse error response body for more details, first check for invalid JSON or unexpected formats.
            try:
                body = e.response.json()
            except ValueError as json_error:
                raise BaseSpaceInvalidResponseError("Response body was not valid JSON") from json_error

            source = body.get("ResponseStatus") or body
            message = source.get("Message") or str(e)
            raise api_error_for_status(
                message, e.response.status_code, response=body,
            ) from e

        except requests.RequestException as e:
            logger.error(f"HTTP request failed: {e}")
            raise BaseSpaceConnectionError(str(e)) from e

    def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        timeout: Optional[tuple] = None,
        stream: bool = False,
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