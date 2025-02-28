import requests
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from google.auth import default
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
        credentials: Optional[Credentials] = None,
        firecloud_api_url: str = "https://api.firecloud.org/api",
        token_audience: str = "https://api.firecloud.org",
    ):
        self.source_workspace = source_workspace
        self.source_project = source_project
        self.destination_workspace = destination_workspace or source_workspace
        self.destination_project = destination_project or source_project
        self.api_url = firecloud_api_url.rstrip("/")
        self.token_audience = token_audience
        self._credentials = credentials or self._get_default_credentials()
        # Set token explicitly to avoid refreshing on every request
        self._token = None
        self._token_expiry = None

    def _get_default_credentials(self) -> Credentials:
        """Get default Google Cloud credentials"""
        try:
            credentials, _ = default()
            return credentials
        except DefaultCredentialsError as error:
            raise TerraAuthenticationError(
                "Failed to get Google Cloud credentials. "
                "Make sure you're authenticated with gcloud or provide credentials explicitly. "
                "Run 'gcloud auth application-default login'"
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
            return self._token
        try:
            self._credentials.refresh(google_requests.Request())
            self._token = self._credentials.token
            # Google auth token good for one hour
            self._token_expiry = now + timedelta(hours=1)
            return self._token
        except RefreshError as refresh_error:
            raise TerraAuthenticationError(
                "Failed to refresh authentication token"
            ) from refresh_error
        except Exception as error:
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
        # Now we can use project and workdpace within function scope
        return f"{self.api_url}/workspaces/{project}/{workspace}/{endpoint}"

    def _handle_response_error(self, response: requests.Response) -> None:
        """Handle error responses from Terra API"""
        try:
            terra_error_data = response.json()
            print(terra_error_data)
        except ValueError:
            terra_error_data = {"message": response.text}

        error_class = self.ERROR_MAPPING.get(response.status_code, TerraAPIError)

        message = terra_error_data.get("message", str(terra_error_data))
        if error_class == TerraServerError:
            message = f"Terra Firecloud API server error: {message}"

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
        """
        url = self._build_firecloud_url(endpoint, use_destination)

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._headers,
                params=params,
                json=data,
                files=files,
                stream=stream,
                timeout=10,  # This is a good default timeout from previous experience
            )

            if not response.ok:
                self._handle_response_error(response)

            return response

        except requests.ConnectionError as connection_error:
            raise TerraConnectionError(
                f"Failed to connect to Terra Firecloud API: {str(connection_error)}"
            ) from connection_error
        except requests.Timeout as timeout_error:
            raise TerraConnectionError(
                f"Request to Terra Firecloud API timed out: {str(timeout_error)}"
            ) from timeout_error
        except requests.RequestException as request_exception_error:
            raise TerraAPIError(
                f"Request to Terra Firecloud API failed: {str(request_exception_error)}"
            ) from request_exception_error

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
