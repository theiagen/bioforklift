from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import Mock, patch
import requests
from google.auth.exceptions import (
    DefaultCredentialsError,
    RefreshError,
)
from forklift.terra.client import TerraClient
from forklift.terra.exceptions import (
    TerraBadRequestError,
    TerraServerError,
    TerraConnectionError,
    TerraAuthenticationError,
)


@pytest.fixture
def mock_credentials():
    """Fixture for mocked credentials"""
    credentials = Mock()
    credentials.token = "test-token"
    credentials.refresh = Mock()
    return credentials


@pytest.fixture
def mock_request(monkeypatch):
    """Mock the requests.request function"""
    mock = Mock()
    monkeypatch.setattr("requests.request", mock)
    return mock


@pytest.fixture
def terra_client(mock_credentials):
    return TerraClient(
        source_workspace="test-workspace",
        source_project="test-project",
        credentials=mock_credentials,
    )


class TestTerraClientInit:
    def test_successful_init(self, mock_credentials):
        client = TerraClient(
            source_workspace="test-workspace",
            source_project="test-project",
            credentials=mock_credentials,
        )
        assert client.source_workspace == "test-workspace"
        assert client.source_project == "test-project"
        assert client.api_url == "https://api.firecloud.org/api"


class TestTerraClientURLBuilding:
    def test_build_firecloud_url(self, terra_client):
        url = terra_client._build_firecloud_url("entities")
        expected = "https://api.firecloud.org/api/workspaces/test-project/test-workspace/entities"
        assert url == expected


class TestTerraClientRequests:
    @patch("requests.request")
    def test_successful_get_request(self, mock_request, terra_client):
        """Test GET request returns raw response"""
        # Setup mock response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"entity": "SRR123456"}
        mock_request.return_value = mock_response

        # Make request
        result = terra_client.get("entities")

        # Verify request was made correctly
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        assert kwargs["method"] == "GET"
        assert "Authorization" in kwargs["headers"]
        assert kwargs["timeout"] == 10

        # Verify we get back the raw response object
        assert result == mock_response

    @patch("requests.request")
    def test_request_timeout(self, mock_request, terra_client):
        mock_request.side_effect = requests.Timeout()

        with pytest.raises(TerraConnectionError) as exc:
            terra_client.get("entities")
        assert "timed out" in str(exc.value)


class TestTerraClientErrors:
    @patch("requests.request")
    def test_400_error(self, mock_request, terra_client):
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Bad request"}
        mock_request.return_value = mock_response

        with pytest.raises(TerraBadRequestError) as exc:
            terra_client.get("entities")
        assert "Bad request" in str(exc.value)

    @patch("requests.request")
    def test_500_error(self, mock_request, terra_client):
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Server error"}
        mock_request.return_value = mock_response

        with pytest.raises(TerraServerError) as exc:
            terra_client.get("entities")
        assert "Terra Firecloud API server error" in str(exc.value)

    @patch("requests.request")
    def test_connection_error(self, mock_request, terra_client):
        mock_request.side_effect = requests.ConnectionError()

        with pytest.raises(TerraConnectionError) as exc:
            terra_client.get("entities")
        assert "Failed to connect" in str(exc.value)


class TestTerraClientAuthentication:
    def test_auth_error_on_init_default_credentials(self):
        """Test authentication error when default credentials can't be obtained"""
        with patch("forklift.terra.client.default") as mock_default:
            mock_default.side_effect = DefaultCredentialsError("No credentials found")

            with pytest.raises(TerraAuthenticationError) as exc:
                TerraClient(
                    source_workspace="test-workspace", source_project="test-project"
                )
            assert "Failed to get Google Cloud credentials" in str(exc.value)
            assert "Run 'gcloud auth application-default login'" in str(exc.value)

    def test_auth_error_on_token_refresh(self, mock_credentials):
        """Test authentication error when token refresh fails"""
        mock_credentials.refresh.side_effect = RefreshError("Token refresh failed")

        client = TerraClient(
            source_workspace="test-workspace",
            source_project="test-project",
            credentials=mock_credentials,
        )

        with pytest.raises(TerraAuthenticationError) as exc:
            client.get("entities")
        assert "Failed to refresh authentication token" in str(exc.value)

    def test_token_caching(self, mock_credentials):
        """Test that tokens are properly cached"""
        # Setup mock credentials
        mock_credentials.token = "test-token"

        client = TerraClient(
            source_workspace="test-workspace",
            source_project="test-project",
            credentials=mock_credentials,
        )

        # Mock successful response
        with patch("requests.request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.return_value = {"success": True}
            mock_request.return_value = mock_response

            # First call should refresh
            client.get("entities")
            assert mock_credentials.refresh.call_count == 1

            # Second call within expiry window should not refresh
            client.get("entities")
            assert mock_credentials.refresh.call_count == 1

    def test_token_refresh_near_expiry(self, mock_credentials):
        """Test that tokens are refreshed when near expiry"""
        mock_credentials.token = "test-token"

        client = TerraClient(
            source_workspace="test-workspace",
            source_project="test-project",
            credentials=mock_credentials,
        )

        # Mock successful response
        with patch("requests.request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.return_value = {"success": True}
            mock_request.return_value = mock_response

            # First call sets token
            client.get("entities")
            assert mock_credentials.refresh.call_count == 1

            # Manually set expiry to near future
            client._token_expiry = datetime.now(timezone.utc) + timedelta(minutes=2)

            # Next call should refresh due to imminent expiry
            client.get("entities")
            assert mock_credentials.refresh.call_count == 2

    def test_auth_error_on_credential_error(self, mock_credentials):
        """Test authentication error when credentials encounter error"""
        mock_credentials.refresh.side_effect = Exception("Unexpected credential error")

        client = TerraClient(
            source_workspace="test-workspace",
            source_project="test-project",
            credentials=mock_credentials,
        )

        with pytest.raises(TerraAuthenticationError) as exc:
            client.get("entities")
        assert "Failed to get authentication token" in str(exc.value)
