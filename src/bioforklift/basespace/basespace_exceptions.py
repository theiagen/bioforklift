from typing import Dict, Optional, Type

class BaseSpaceError(Exception):
    """Base exception for BaseSpace-related errors."""
    pass


class BaseSpaceConnectionError(BaseSpaceError):
    """Raised when connection to BaseSpace fails."""
    pass


class BaseSpaceTimeoutError(BaseSpaceConnectionError):
    """Raised when a request to BaseSpace times out."""
    pass


class BaseSpaceInvalidResponseError(BaseSpaceError):
    """Raised when a response body could not be parsed as expected JSON."""
    pass


class BaseSpaceCollectionIdError(BaseSpaceError):
    """Raised when a collection ID cannot be resolved to a single project/run."""
    pass


class BaseSpaceDatasetError(BaseSpaceError):
    """Raised when a sample resolves to no datasets, or to more than one (ambiguous)."""
    pass


class BaseSpaceMissingReadError(BaseSpaceError):
    """Raised when a dataset is paired-end but no R2 files are present."""
    pass


class BaseSpaceAPIError(BaseSpaceError):
    """Raised when BaseSpace API returns an error."""

    def __init__(
        self,
        message: str,
        status_code: int,
        response: Optional[Dict],
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class BaseSpaceBadRequestError(BaseSpaceAPIError):
    """Raised when BaseSpace returns 400."""
    pass


class BaseSpaceAuthenticationError(BaseSpaceAPIError):
    """Raised when BaseSpace returns 401."""
    pass


class BaseSpaceForbiddenError(BaseSpaceAPIError):
    """Raised when BaseSpace returns 403."""
    pass


class BaseSpaceNotFoundError(BaseSpaceAPIError):
    """Raised when BaseSpace returns 404."""
    pass

class BaseSpaceServerError(BaseSpaceAPIError):
    """Raised when BaseSpace returns 500."""
    pass

# Maps HTTP status codes to their most specific exception class. Any status
# not listed falls back to the generic BaseSpaceAPIError.
_ERROR_MAPPING: Dict[int, Type[BaseSpaceAPIError]] = {
    400: BaseSpaceBadRequestError,
    401: BaseSpaceAuthenticationError,
    403: BaseSpaceForbiddenError,
    404: BaseSpaceNotFoundError,
    500: BaseSpaceServerError,
}


def api_error_for_status(
    message: str,
    status_code: int,
    response: Optional[Dict] = None,
) -> BaseSpaceAPIError:
    """
    Return specific BaseSpaceAPIError for a given HTTP status code.

    Args:
        status_code: HTTP status code returned by the API.
        message: error/message from the response body
        response: The parsed error status as a dict, attached for inspection.

    Returns:
        An instance of the matching BaseSpaceAPIError subclass, or
        BaseSpaceAPIError itself if the status code is not specifically mapped.
    """
    exception_class = _ERROR_MAPPING.get(status_code, BaseSpaceAPIError)
    return exception_class(message, status_code=status_code, response=response)
