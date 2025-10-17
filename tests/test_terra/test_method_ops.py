import pytest
from unittest.mock import Mock
import requests
from bioforklift.terra import TerraMethods
from bioforklift.terra import MethodConfig, MethodRepoMethod

@pytest.fixture
def mock_response():
    """Create a mock response with json method"""
    response = Mock(spec=requests.Response)
    response.ok = True
    return response


@pytest.fixture
def mock_terra_client():
    client = Mock()
    client.destination_project = "test-project"
    client.destination_workspace = "test-workspace"
    return client


@pytest.fixture
def method_ops(mock_terra_client):
    return TerraMethods(mock_terra_client)


@pytest.fixture
def sample_method_config(mock_terra_client):
    """Create a sample method config for testing"""
    return MethodConfig(
        namespace=mock_terra_client.destination_project,
        name="Test_Workspace_Method_Config",
        rootEntityType="sample",
        methodRepoMethod=MethodRepoMethod(
            methodUri="dockstore://test-method/version"
        ),
        inputs={"test.input": "this.value"},
        outputs={"test.output": "this.result"},
        prerequisites={},
        methodConfigVersion=0,
        deleted=False
    )


class TestGetMethodConfig:
    def test_get_method_config(self, method_ops, mock_terra_client, mock_response, sample_method_config):
        """Test getting a method configuration"""
        config_name = "Test_Workspace_Method_Config"

        mock_response.json.return_value = sample_method_config
        mock_terra_client.get.return_value = mock_response

        result = method_ops.get_method_config(config_name)

        mock_terra_client.get.assert_called_once_with(
            f"method_configs/{mock_terra_client.destination_project}/{config_name}",
            use_destination=True
        )
        assert result.name == config_name


class TestOverwriteMethodConfig:
    def test_overwrite_method_config(self, method_ops, mock_terra_client, mock_response, sample_method_config):
        """Test overwriting a method configuration"""

        mock_response.json.return_value = sample_method_config
        mock_terra_client.put.return_value = mock_response

        result = method_ops.overwrite_method_config(sample_method_config)

        mock_terra_client.put.assert_called_once_with(
            f"method_configs/{mock_terra_client.destination_project}/{sample_method_config.name}",
            data=sample_method_config.model_dump(exclude_none=True),
            use_destination=True
        )

        assert result == mock_response.json.return_value