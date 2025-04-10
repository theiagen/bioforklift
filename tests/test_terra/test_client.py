import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, ANY
import requests
from google.auth.exceptions import DefaultCredentialsError, RefreshError
from bioforklift.terra import TerraClient
from bioforklift.terra.exceptions import (
    TerraAPIError,
    TerraAuthenticationError,
    TerraConnectionError,
    TerraBadRequestError,
    TerraNotFoundError,
    TerraPermissionError,
    TerraServerError,
)


@pytest.fixture
def terra_client():
    """Create a TerraClient with default test parameters"""
    with patch('bioforklift.terra.TerraClient._get_default_credentials') as mock_creds:
        mock_creds.return_value = MagicMock()
        client = TerraClient(
            source_workspace="test-workspace",
            source_project="test-project",
        )
        # Mock the token behavior
        client._token = "mock-token"
        client._token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        return client


@pytest.fixture
def mock_response():
    """Mock response object for requests"""
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.ok = True
    mock_resp.status_code = 200
    return mock_resp


class TestTerraClient:
    def test_init_with_defaults(self):
        """Test initialization with default parameters"""
        with patch('bioforklift.terra.TerraClient._get_default_credentials') as mock_creds:
            mock_creds.return_value = MagicMock()
            client = TerraClient(
                source_workspace="test-workspace",
                source_project="test-project",
            )
            
            assert client.source_workspace == "test-workspace"
            assert client.source_project == "test-project"
            assert client.destination_workspace == "test-workspace"
            assert client.destination_project == "test-project"
            assert client.api_url == "https://api.firecloud.org/api"
            assert client._token is None
            assert client._token_expiry is None
            mock_creds.assert_called_once()

    def test_init_with_all_params(self):
        """Test initialization with all parameters specified"""
        with patch('bioforklift.terra.TerraClient._get_credentials_from_json') as mock_creds:
            mock_creds.return_value = MagicMock()
            client = TerraClient(
                source_workspace="src-workspace",
                source_project="src-project",
                destination_workspace="dest-workspace",
                destination_project="dest-project",
                google_credentials_json="path/to/creds.json",
                firecloud_api_url="https://custom.api.org/api/",
                token_audience="https://custom.audience"
            )
            
            assert client.source_workspace == "src-workspace"
            assert client.source_project == "src-project"
            assert client.destination_workspace == "dest-workspace"
            assert client.destination_project == "dest-project"
            assert client.api_url == "https://custom.api.org/api"
            assert client.token_audience == "https://custom.audience"
            mock_creds.assert_called_once_with("path/to/creds.json")

    def test_get_token_cached(self, terra_client):
        """Test getting a cached token"""
        # Token is already set in the fixture
        token = terra_client._get_token()
        
        assert token == "mock-token"
        # Ensure refresh wasn't called
        terra_client._credentials.refresh.assert_not_called()

    def test_get_token_refresh(self):
        """Test refreshing an expired token"""
        with patch('bioforklift.terra.TerraClient._get_default_credentials') as mock_get_creds:
            mock_credentials = MagicMock()
            mock_credentials.id_token = "new-token"
            mock_credentials.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
            mock_get_creds.return_value = mock_credentials
            
            client = TerraClient(
                source_workspace="test-workspace",
                source_project="test-project",
            )
            
            # Force expiry
            client._token = "old-token"
            client._token_expiry = datetime.now(timezone.utc) - timedelta(minutes=5)
            
            token = client._get_token()
            
            assert token == "new-token"
            mock_credentials.refresh.assert_called_once()

    def test_get_token_refresh_failure(self):
        """Test failure during token refresh"""
        with patch('bioforklift.terra.TerraClient._get_default_credentials') as mock_get_creds:
            mock_credentials = MagicMock()
            mock_credentials.refresh.side_effect = RefreshError("Refresh failed")
            mock_get_creds.return_value = mock_credentials
            
            client = TerraClient(
                source_workspace="test-workspace",
                source_project="test-project",
            )
            
            with pytest.raises(TerraAuthenticationError) as exc_info:
                client._get_token()
            
            assert "Failed to refresh authentication token" in str(exc_info.value)

    def test_headers(self, terra_client):
        """Test header generation"""
        headers = terra_client._headers
        
        assert headers["Authorization"] == "Bearer mock-token"
        assert headers["Accept"] == "*/*"

    def test_build_firecloud_url_source(self, terra_client):
        """Test building API URL for source workspace"""
        url = terra_client._build_firecloud_url("entities")
        
        assert url == "https://api.firecloud.org/api/workspaces/test-project/test-workspace/entities"

    def test_build_firecloud_url_destination(self, terra_client):
        """Test building API URL for destination workspace"""
        # Set different destination
        terra_client.destination_workspace = "dest-workspace"
        terra_client.destination_project = "dest-project"
        
        url = terra_client._build_firecloud_url("entities", use_destination=True)
        
        assert url == "https://api.firecloud.org/api/workspaces/dest-project/dest-workspace/entities"

    def test_handle_response_error_json(self):
        """Test handling error response with JSON body"""
        with patch('bioforklift.terra.TerraClient._get_default_credentials') as mock_get_creds:
            mock_get_creds.return_value = MagicMock()
            client = TerraClient(
                source_workspace="test-workspace",
                source_project="test-project",
            )
            
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"message": "Resource not found"}
            
            with pytest.raises(TerraNotFoundError) as exc_info:
                client._handle_response_error(mock_response)
            
            assert "Resource not found" in str(exc_info.value)
            assert exc_info.value.status_code == 404

    def test_reset_auth_cache(self, terra_client):
        """Test resetting authentication cache"""
        # Token is set in fixture
        assert terra_client._token == "mock-token"
        assert terra_client._token_expiry is not None
        
        terra_client.reset_auth_cache()
        
        assert terra_client._token is None
        assert terra_client._token_expiry is None

    def test_get(self, terra_client, mock_response):
        """Test GET request wrapper"""
        with patch.object(terra_client, '_http_request') as mock_http_request:
            mock_http_request.return_value = mock_response
            
            response = terra_client.get(
                endpoint="entities",
                params={"page": 1},
                stream=True,
                use_destination=False,
            )
            
            assert response == mock_response
            mock_http_request.assert_called_once_with(
                "GET",
                "entities",
                params={"page": 1},
                stream=True,
                use_destination=False,
            )

    def test_post(self, terra_client, mock_response):
        """Test POST request wrapper"""
        with patch.object(terra_client, '_http_request') as mock_http_request:
            mock_http_request.return_value = mock_response
            
            data = {"name": "test-entity"}
            files = {"file": ("test.txt", b"content")}
            
            response = terra_client.post(
                endpoint="entities",
                data=data,
                files=files,
                params={"validate": True},
                use_destination=True,
            )
            
            assert response == mock_response
            mock_http_request.assert_called_once_with(
                "POST",
                "entities",
                data=data,
                files=files,
                params={"validate": True},
                use_destination=True,
            )
            
# Comment to trigger github actions