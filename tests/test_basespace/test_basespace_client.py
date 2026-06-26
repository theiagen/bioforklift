import pytest
from unittest.mock import MagicMock, patch
import requests

from bioforklift.basespace import BaseSpaceClient
from bioforklift.basespace.basespace_exceptions import (
    BaseSpaceAPIError,
    BaseSpaceAuthenticationError,
    BaseSpaceBadRequestError,
    BaseSpaceConnectionError,
    BaseSpaceForbiddenError,
    BaseSpaceInvalidResponseError,
    BaseSpaceNotFoundError,
    BaseSpaceServerError,
    BaseSpaceTimeoutError,
)


@pytest.fixture
def client():
    """A BaseSpaceClient with default URL/version and a test token."""
    return BaseSpaceClient(access_token="67")


@pytest.fixture
def mock_response():
    """A mock requests.Response that succeeds by default."""
    response = MagicMock(spec=requests.Response)
    response.status_code = 200
    response.url = "https://api.basespace.illumina.com/v2/search"
    return response


class TestBaseSpaceClient:
    def test_client_init_with_defaults(self, client):
        # Grabbed from the fixture, which uses the default URL and version
        assert client.access_token == "67"
        assert client.base_url == "https://api.basespace.illumina.com"
        assert client.api_version == "v2"
        assert client._headers == {"x-access-token": "67"}

    def test_custom_client(self):
        client = BaseSpaceClient(
            access_token="abc",
            basespace_api_url="https://example.com",
            basespace_api_version="v1",
        )
        assert client.access_token == "abc"
        assert client.base_url == "https://example.com"
        assert client.api_version == "v1"

    def test_custom_client_trims_trailing_slash_url(self):
        client = BaseSpaceClient(
            access_token="abc",
            basespace_api_url="https://example.com/"
        )
        assert client.base_url == "https://example.com"

    def test_build_url_path(self, client):
        # The _build_url_path method should correctly construct the full URL for various endpoints, regardless of leading/trailing slashes.
        assert client._build_url_path("search") == "https://api.basespace.illumina.com/v2/search"
        assert client._build_url_path("/search/") == "https://api.basespace.illumina.com/v2/search"
        assert client._build_url_path("/datasets") == "https://api.basespace.illumina.com/v2/datasets"
        assert client._build_url_path("datasets/ds.1/files/") == "https://api.basespace.illumina.com/v2/datasets/ds.1/files"

    def test_get(self, client, mock_response):
        with patch.object(client, "_http_request") as mock_http_request:
            mock_http_request.return_value = mock_response

            response = client.get(
                endpoint="search",
                params={"scope": "projects"}
            )

        # Make sure the result is a valid response
        assert response == mock_response

        # Make sure the request was made with the correct default parameters
        mock_http_request.assert_called_once_with(
            "GET",
            "search",
            params={"scope": "projects"},
            stream=False,
            timeout=None,
        )

    def test_http_request_calls_raises_for_status(self, client, mock_response):
        with patch("requests.request") as mock_request:
            mock_request.return_value = mock_response
            client.get("search", params={"scope": "projects"})

        # Make sure raise_for_status was called to check for HTTP errors
        mock_response.raise_for_status.assert_called_once()

    def test_http_request_custom_args(self, client, mock_response):
        with patch("requests.request") as mock_request:
            mock_request.return_value = mock_response
            client.get("search", timeout=(5, 10), stream=True)

        assert mock_request.call_args.kwargs["timeout"] == (5, 10)
        assert mock_request.call_args.kwargs["stream"] == True


class TestBaseSpaceErrorMapping:
    def test_timeout_raises(self, client):
        with patch("requests.request", side_effect=requests.Timeout):
            with pytest.raises(BaseSpaceTimeoutError):
                client.get("search")

    def test_connection_error_raises(self, client):
        with patch("requests.request", side_effect=requests.ConnectionError):
            with pytest.raises(BaseSpaceConnectionError):
                client.get("search")

    def test_generic_requestexception_raises(self, client):
        with patch("requests.request", side_effect=requests.RequestException):
            with pytest.raises(BaseSpaceConnectionError):
                client.get("search")

    def test_http_error_with_invalid_json_raises(self, client, mock_response):
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("not valid json")

        http_error = requests.HTTPError("500 error")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error

        with patch("requests.request") as mock_request:
            mock_request.return_value = mock_response
            with pytest.raises(BaseSpaceInvalidResponseError):
                client.get("search")

    @pytest.mark.parametrize(
        "status_code, expected_class",
        [
            (400, BaseSpaceBadRequestError),
            (401, BaseSpaceAuthenticationError),
            (403, BaseSpaceForbiddenError),
            (404, BaseSpaceNotFoundError),
            (500, BaseSpaceServerError),
            (418, BaseSpaceAPIError),  # Unknown status code should fall back to generic API error
        ],
    )
    def test_http_error_maps_status_to_exception(self, client, mock_response, status_code, expected_class):
        mock_response.status_code = status_code
        mock_response.json.return_value = {"ResponseStatus": {"Message": "BAD"}}

        # raise_for_status() is what turns a 4xx/5xx into an HTTPError, so the
        # mock has to raise one carrying this same response.
        http_error = requests.HTTPError(f"{status_code} error")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error

        with patch("requests.request") as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(expected_class) as exc_info:
                client.get("search")

        assert type(exc_info.value) == expected_class
        assert exc_info.value.status_code == status_code
        assert "BAD" in str(exc_info.value)
        assert exc_info.value.response == {"ResponseStatus": {"Message": "BAD"}}
