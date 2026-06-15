from typing import Dict, Optional

class BaseSpaceError(Exception):
    """Base exception for BaseSpace-related errors."""
    pass

class BaseSpaceAPIError(BaseSpaceError):
    """Raised when BaseSpace API returns an error."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response: Optional[Dict] = None,
    ):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class BaseSpaceBadRequestError(BaseSpaceAPIError):
    """Raised when BaseSpace returns 400."""
    pass

class BaseSpaceConnectionError(BaseSpaceError):
    """Raised when connection to BaseSpace fails."""
    pass

class BaseSpaceNotFoundError(BaseSpaceAPIError):
    """Raised when BaseSpace returns 404."""
    pass