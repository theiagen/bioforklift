import requests
import time
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone
from bioforklift.forklift_logging import setup_logger
from google.auth.transport import requests as google_requests
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account, id_token
from google.auth import default, transport
from google.auth.exceptions import DefaultCredentialsError, RefreshError
from .exceptions import (
    TerraAPIError,
    TerraAuthenticationError,
    TerraConnectionError,
    TerraBadRequestError,
    TerraNotFoundError,
    TerraPermissionError,
    TerraServerError,
)

logger = setup_logger("terra_client.py")


class TerraClient:
    """Base client for Terra Firecloud API interactions"""

    # These are the error classes we'll use to handle as I've ran into many of these, especially
    # 500 errors when the Terra API can't handle the load
    ERROR_MAPPING = {
        400: TerraBadRequestError,
        401: TerraAuthenticationError,
        403: TerraPermissionError,
        404: TerraNotFoundError,
        500: TerraServerError,
        502: TerraServerError,
        503: TerraServerError,
        504: TerraServerError,
    }

    def __init__(
        self,
        source_workspace: str,
        source_project: str,
        destination_workspace: Optional[str] = None,
        destination_project: Optional[str] = None,
        google_credentials_json: Optional[str] = None,
        firecloud_api_url: str = "https://api.firecloud.org/api",
        token_audience: str = "https://api.firecloud.org",
    ):
        self.source_workspace = source_workspace
        self.source_project = source_project
        self.destination_workspace = destination_workspace or source_workspace
        self.destination_project = destination_project or source_project
        self.api_url = firecloud_api_url.rstrip("/")
        self.token_audience = token_audience
        if google_credentials_json:
            self._credentials = self._get_credentials_from_json(google_credentials_json)
        else:
            self._credentials = self._get_default_credentials()
        # Set token explicitly to avoid refreshing on every request
        self._token = None
        self._token_expiry = None

    def _get_default_credentials(self) -> Credentials:
        """Get default Google Cloud credentials"""
        try:
            credentials, _ = default()
            logger.debug("Google Cloud Credentials Retrieved")
            return credentials
        except DefaultCredentialsError as error:
            logger.exception("Failed to get Google Cloud credentials")
            raise TerraAuthenticationError(
                "Failed to get Google Cloud credentials. "
                "Make sure you're authenticated with gcloud or provide credentials explicitly. "
                "Run 'gcloud auth application-default login'"
            ) from error

    def _get_credentials_from_json(self, json_path: str) -> Credentials:
        """Get Google Cloud credentials from a service account JSON file"""
        try:
            # Create credentials with appropriate scopes for Terra
            scopes = [
                "https://www.googleapis.com/auth/userinfo.profile",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/cloud-platform",
            ]

            credentials = service_account.Credentials.from_service_account_file(
                json_path, scopes=scopes
            )

            return credentials
        except Exception as error:
            raise TerraAuthenticationError(
                f"Failed to load credentials from JSON file: {str(error)}"
            ) from error

    def _get_token(self) -> str:
        """Get access token for Terra API, refreshing only if needed"""
        now = datetime.now(timezone.utc)

        # If we have a valid token that's not close to expiring, use it
        if (
            self._token
            and self._token_expiry
            and self._token_expiry > now + timedelta(minutes=3)
        ):
            logger.debug(f"Using cached token, expires at {self._token_expiry}")
            return self._token

        try:
            # First determine if this is a service account or user
            is_service_account = False
            if hasattr(self._credentials, "service_account_email"):
                is_service_account = bool(self._credentials.service_account_email)
                logger.debug(f"Detected service account: {is_service_account}")

            if is_service_account:
                try:
                    # For service accounts, use ID token
                    google_auth_request = transport.requests.Request()
                    self._token = id_token.fetch_id_token(
                        google_auth_request, self.token_audience
                    )
                    self._token_expiry = datetime.now(timezone.utc) + timedelta(
                        minutes=30
                    )
                    logger.info("Successfully fetched ID token for service account")
                    return self._token
                except Exception as id_token_error:
                    logger.debug(
                        f"Failed to fetch ID token for service account: {id_token_error}, falling back"
                    )

            # Regular credential flow for users or as fallback
            self._credentials.refresh(google_requests.Request())

            # For users, prefer access token over ID token
            if is_service_account and hasattr(self._credentials, "id_token"):
                self._token = self._credentials.id_token
            else:
                self._token = self._credentials.token

            self._token_expiry = (
                self._credentials.expiry.replace(tzinfo=timezone.utc)
                if self._credentials.expiry
                else datetime.now(timezone.utc) + timedelta(minutes=30)
            )
            logger.debug(
                f"Using {'service account' if is_service_account else 'user'} credentials, token expires at {self._token_expiry}"
            )
            return self._token

        except RefreshError as refresh_error:
            logger.exception("Failed to refresh authentication token")
            raise TerraAuthenticationError(
                "Failed to refresh authentication token"
            ) from refresh_error
        except Exception as error:
            logger.exception("Failed to get authentication token")
            raise TerraAuthenticationError(
                f"Failed to get authentication token: {str(error)}"
            ) from error

    @property
    def _headers(self) -> Dict[str, str]:
        """Get headers with fresh token"""
        return {"Authorization": f"Bearer {self._get_token()}", "Accept": "*/*"}

    def _build_firecloud_url(self, endpoint: str, use_destination: bool = False) -> str:
        """Helper function to build full API URL

        Args:
            endpoint: API endpoint to access
            use_destination: Whether to use destination workspace (True) or source workspace (False)
        """
        workspace = (
            self.destination_workspace if use_destination else self.source_workspace
        )
        project = self.destination_project if use_destination else self.source_project
        logger.debug(f"Building Firecloud URL for {project}/{workspace}/{endpoint}")
        # Now we can use project and workspace within function scope
        return f"{self.api_url}/workspaces/{project}/{workspace}/{endpoint}"

    def _handle_response_error(self, response: requests.Response) -> None:
        """Handle error responses from Terra API"""
        try:
            terra_error_data = response.json()
        except ValueError:
            logger.exception(
                "Failed to parse Terra Firecloud API error response, likely not JSON: \n{response.text}\n"
            )
            terra_error_data = {"message": response.text}

        error_class = self.ERROR_MAPPING.get(response.status_code, TerraAPIError)

        message = terra_error_data.get("message", str(terra_error_data))
        if error_class == TerraServerError:
            message = f"Terra Firecloud API server error: {message}"
        logger.error(f"Terra Firecloud API error: {message}")
        raise error_class(
            message=message, status_code=response.status_code, response=terra_error_data
        )

    def _http_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        files: Optional[Dict] = None,
        stream: Optional[bool] = False,
        use_destination: bool = False,
        timeout: Optional[tuple] = None,
        max_retries: int = 3,
    ) -> requests.Response:
        """
        Make HTTP request to Terra Firecloud API with dynamic method

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            files: Files to upload
            stream: Whether to stream the response
            use_destination: Whether to use destination workspace (True) or source workspace (False)
            timeout: Request timeout as (connect_timeout, read_timeout) in seconds
            max_retries: Maximum number of retries for transient server errors (502, 503, 504)
        """
        url = self._build_firecloud_url(endpoint, use_destination)
        logger.debug("FireCloud URL Built")

        # Default timeout: 30s to connect, 5min to read
        if timeout is None:
            timeout = (30, 300)

        last_exception = None
        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self._headers,
                    params=params,
                    json=data,
                    files=files,
                    stream=stream,
                    timeout=timeout,
                )

                if not response.ok:
                    # Check if this is a retryable server error
                    if response.status_code in (502, 503, 504) and attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.warning(
                            f"Request to {method} {response.url} failed with status {response.status_code}, "
                            f"retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue

                    logger.error(
                        f"Request to {method} {response.url} failed with status code {response.status_code}"
                    )
                    self._handle_response_error(response)

                logger.debug(f"{method} request to {response.url} successful")
                return response

            except requests.ConnectionError as connection_error:
                last_exception = TerraConnectionError(
                    f"Failed to connect to Terra Firecloud API: {str(connection_error)}"
                )
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Connection error, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                raise last_exception from connection_error
            except requests.Timeout as timeout_error:
                last_exception = TerraConnectionError(
                    f"Request to Terra Firecloud API timed out: {str(timeout_error)}"
                )
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Timeout error, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                raise last_exception from timeout_error
            except requests.RequestException as request_exception_error:
                raise TerraAPIError(
                    f"Request to Terra Firecloud API failed: {str(request_exception_error)}"
                ) from request_exception_error

        # If we exhausted all retries, raise the last exception
        if last_exception:
            raise last_exception

    def reset_auth_cache(self) -> None:
        """
        Reset authentication cache to force a new token on next request.
        """
        self._token = None
        self._token_expiry = None
        logger.debug("Reset authentication token cache")

    def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        stream: Optional[bool] = False,
        use_destination: bool = False,
    ) -> requests.Response:
        """Make GET request"""
        return self._http_request(
            "GET",
            endpoint,
            params=params,
            stream=stream,
            use_destination=use_destination,
        )

    def post(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        files: Optional[Dict] = None,
        params: Optional[Dict] = None,
        use_destination: bool = False,
    ) -> requests.Response:
        """Make POST request"""
        return self._http_request(
            "POST",
            endpoint,
            data=data,
            files=files,
            params=params,
            use_destination=use_destination,
        )

    def patch(
        self, endpoint: str, data: Dict, use_destination: bool = False
    ) -> requests.Response:
        """Make PATCH request"""
        return self._http_request(
            "PATCH", endpoint, data=data, use_destination=use_destination
        )
