from typing import Optional, Dict, Any


class TerraError(Exception):
    """Base exception for Terra API interactions"""

    pass


class TerraAPIError(TerraError):
    """Raised when Terra API returns an error"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response: Optional[Dict[str, Any]] = None,
    ):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class TerraConnectionError(TerraError):
    """Raised when connection to Terra fails"""

    pass


class TerraBadRequestError(TerraAPIError):
    """Raised when Terra returns 400"""

    pass


class TerraNotFoundError(TerraAPIError):
    """Raised when Terra returns 404"""

    pass


class TerraPermissionError(TerraAPIError):
    """Raised when Terra returns 403"""

    pass


class TerraServerError(TerraAPIError):
    """Raised when Terra returns 5xx"""

    pass


class TerraWorkspaceError(TerraError):
    """Raised for workspace-related errors"""

    pass


class TerraAuthenticationError(TerraAPIError):
    """Raised when authentication fails"""

    pass
