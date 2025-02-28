import pytest
from unittest.mock import Mock, patch
import requests
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
def terra_client_with_destination(mock_credentials):
    """Terra client fixture with both source and destination workspaces"""
    return TerraClient(
        source_workspace="source-workspace",
        source_project="source-project",
        destination_workspace="destination-workspace",
        destination_project="destination-project",
        credentials=mock_credentials,
    )


class TestTerraClientDestinationInit:
    def test_init_with_destination(self, mock_credentials):
        """Test initialization with destination workspace"""
        client = TerraClient(
            source_workspace="source-workspace",
            source_project="source-project",
            destination_workspace="destination-workspace",
            destination_project="destination-project",
            credentials=mock_credentials,
        )
        assert client.source_workspace == "source-workspace"
        assert client.source_project == "source-project"
        assert client.destination_workspace == "destination-workspace"
        assert client.destination_project == "destination-project"

    def test_init_with_destination_default_project(self, mock_credentials):
        """Test initialization with destination workspace but default project"""
        client = TerraClient(
            source_workspace="source-workspace",
            source_project="source-project",
            destination_workspace="destination-workspace",
            credentials=mock_credentials,
        )
        assert client.source_workspace == "source-workspace"
        assert client.source_project == "source-project"
        assert client.destination_workspace == "destination-workspace"
        assert (
            client.destination_project == "source-project"
        )  # Should default to source project


class TestTerraClientDestinationURLBuilding:
    def test_build_workspace_url_source(self, terra_client_with_destination):
        """Test URL building for source workspace"""
        url = terra_client_with_destination._build_firecloud_url(
            "entities", use_destination=False
        )
        expected = "https://api.firecloud.org/api/workspaces/source-project/source-workspace/entities"
        assert url == expected

    def test_build_workspace_url_destination(self, terra_client_with_destination):
        """Test URL building for destination workspace"""
        url = terra_client_with_destination._build_firecloud_url(
            "entities", use_destination=True
        )
        expected = "https://api.firecloud.org/api/workspaces/destination-project/destination-workspace/entities"
        assert url == expected


class TestTerraClientDestinationRequests:
    @patch("requests.request")
    def test_get_request_source(self, mock_request, terra_client_with_destination):
        """Test GET request to source workspace"""
        # Setup mock response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"entity": "source_entity"}
        mock_request.return_value = mock_response

        # Make request to source workspace (default)
        result = terra_client_with_destination.get("entities")

        # Verify request was made to source workspace
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        assert "source-workspace" in kwargs["url"]
        assert result == mock_response

    @patch("requests.request")
    def test_get_request_destination(self, mock_request, terra_client_with_destination):
        """Test GET request to destination workspace"""
        # Setup mock response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"entity": "destination_entity"}
        mock_request.return_value = mock_response

        # Make request to destination workspace
        result = terra_client_with_destination.get("entities", use_destination=True)

        # Verify request was made to destination workspace
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        assert "destination-workspace" in kwargs["url"]
        assert result == mock_response

    @patch("requests.request")
    def test_post_request_destination(
        self, mock_request, terra_client_with_destination
    ):
        """Test POST request to destination workspace"""
        # Setup mock response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"created": True}
        mock_request.return_value = mock_response

        # Make request to destination workspace
        data = {"name": "test_entity"}
        result = terra_client_with_destination.post(
            "entities", data=data, use_destination=True
        )

        # Verify request was made to destination workspace
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        assert "destination-workspace" in kwargs["url"]
        assert kwargs["json"] == data
        assert result == mock_response

    @patch("requests.request")
    def test_patch_request_destination(
        self, mock_request, terra_client_with_destination
    ):
        """Test PATCH request to destination workspace"""
        # Setup mock response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"updated": True}
        mock_request.return_value = mock_response

        # Make request to destination workspace
        data = {"status": "updated"}
        result = terra_client_with_destination.patch(
            "entities/sample1", data=data, use_destination=True
        )

        # Verify request was made to destination workspace
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        assert "destination-workspace" in kwargs["url"]
        assert kwargs["json"] == data
        assert result == mock_response


class TestTerraClientDestinationErrors:
    @patch("requests.request")
    def test_400_error_destination(self, mock_request, terra_client_with_destination):
        """Test handling 400 error from destination workspace"""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Bad request"}
        mock_request.return_value = mock_response

        with pytest.raises(TerraBadRequestError) as exc:
            terra_client_with_destination.get("entities", use_destination=True)
        assert "Bad request" in str(exc.value)

    @patch("requests.request")
    def test_500_error_destination(self, mock_request, terra_client_with_destination):
        """Test handling 500 error from destination workspace"""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Server error"}
        mock_request.return_value = mock_response

        with pytest.raises(TerraServerError) as exc:
            terra_client_with_destination.get("entities", use_destination=True)
        assert "Terra Firecloud API server error" in str(exc.value)

    @patch("requests.request")
    def test_connection_error_destination(
        self, mock_request, terra_client_with_destination
    ):
        """Test handling connection error when accessing destination workspace"""
        mock_request.side_effect = requests.ConnectionError()

        with pytest.raises(TerraConnectionError) as exc:
            terra_client_with_destination.get("entities", use_destination=True)
        assert "Failed to connect" in str(exc.value)
