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
    client.source_project = "test-source-project"
    client.source_workspace = "test-source-workspace"
    client.destination_project = "test-destination-project"
    client.destination_workspace = "test-destination-workspace"
    return client

@pytest.fixture
def terra_method_ops(mock_terra_client):
    return TerraMethods(mock_terra_client)

@pytest.fixture
def sample_method_config(mock_terra_client):
    """Create a sample method config for testing"""
    return MethodConfig(
        namespace=mock_terra_client.source_project,
        name="Test_Source_Workspace_Method_Config",
        rootEntityType="sample",
        methodRepoMethod=MethodRepoMethod(
            methodUri="dockstore://test-method/version"
        ),
        inputs={
            "example.terra_ref": "this.value",
            "example.workspace_ref": "workspace.value",
            "example.str": "test",
            "example.int": 5,
            "example.float": 3.14,
            "example.str_array": ["A", "B", "C"],
            "example.int_array": [10, 20, 30],
            "example.map": {"key1": "value1", "key2": 10},
            "example.bool": True,
        },
        outputs={"example.output": "this.result"},
        prerequisites={},
        methodConfigVersion=0,
        deleted=False
    )

class TestMethodRepoMethod:

    @pytest.mark.parametrize(
        "methodUri,sourceRepo,methodPath,methodVersion",
        [
            pytest.param("dockstore://test-method/version", "dockstore", "github.com/test/repo", "main", id="all"),
            pytest.param("dockstore://test-method/version", None, None, None, id="with_uri"),
            pytest.param(None, "dockstore", "github.com/test/repo", "main", id="without_uri"),
        ]
    )
    def test_methodrepomethod_pass(
        self,
        methodUri,
        sourceRepo,
        methodPath,
        methodVersion,
    ):
        """Test MethodRepoMethod validation success with required fields"""
        method_repo_method = MethodRepoMethod(
            methodUri=methodUri,
            sourceRepo=sourceRepo,
            methodPath=methodPath,
            methodVersion=methodVersion,
        )
        assert method_repo_method is not None


    @pytest.mark.parametrize(
        "methodUri,sourceRepo,methodPath,methodVersion",
        [
            pytest.param(None, "dockstore", "github.com/test/repo", None, id="missing_version"),
            pytest.param(None, "dockstore", None, "main", id="missing_path"),
            pytest.param(None, None, "github.com/test/repo", "main", id="missing_repo"),
            pytest.param(None, None, None, None, id="all_missing"),
        ]
    )
    def test_methodrepomethod_fail(
        self,
        methodUri,
        sourceRepo,
        methodPath,
        methodVersion,
    ):
        """Test MethodRepoMethod validation failure when required fields are missing"""
        with pytest.raises(
            ValueError,
            match="Either 'methodUri' or all of 'sourceRepo', 'methodPath', and 'methodVersion' must be provided."
        ):
            MethodRepoMethod(
                methodUri=methodUri,
                sourceRepo=sourceRepo,
                methodPath=methodPath,
                methodVersion=methodVersion,
            )

class TestMethodConfig:

    def test_method_config_encoding(self, sample_method_config):
        """Test MethodConfig encoding with other input types"""
        config = sample_method_config
        config = config.model_dump(exclude_none=True)  # Trigger any encoding logic

        assert config["inputs"]["example.str"] == '"test"'
        assert config["inputs"]["example.int"] == '5'
        assert config["inputs"]["example.float"] == '3.14'
        assert config["inputs"]["example.str_array"] == '["A", "B", "C"]'
        assert config["inputs"]["example.int_array"] == '[10, 20, 30]'
        assert config["inputs"]["example.map"] == '{"key1": "value1", "key2": 10}'
        assert config["inputs"]["example.bool"] == 'true'

        # This should not get converted; should remain as string reference
        assert config["inputs"]["example.terra_ref"] == "this.value"
        assert config["inputs"]["example.workspace_ref"] == "workspace.value"

    def test_method_config_validate_minimal(
        self,
        terra_method_ops,
        mock_terra_client,
        mock_response,
    ):
        """Test basic MethodConfig creation (no inputs/outputs) and validation"""
        minimal_config = MethodConfig(
            namespace="test-project",
            name="Test_Method_Config",
            rootEntityType="sample",
            methodRepoMethod=MethodRepoMethod(
                methodUri="dockstore://test-method/version"
            )
        )

        expected_response = {
            "methodConfiguration": {"name": minimal_config.name},
            "validInputs": [],
            "validOutputs": [],
            "invalidInputs": {},
            "invalidOutputs": {},
            "missingInputs": [],
            "extraInputs": []
        }
        mock_response.json.return_value = expected_response
        mock_terra_client.get.return_value = mock_response

        test_result = terra_method_ops.method_config_validate(minimal_config)

        mock_terra_client.get.assert_called_once_with(
            f"method_configs/{mock_terra_client.destination_project}/{minimal_config.name}/validate",
            use_destination=True
        )

        assert test_result == expected_response


    def test_method_config_validate_pass(
        self,
        terra_method_ops,
        mock_terra_client,
        mock_response,
        sample_method_config,
    ):
        """Test validation of a valid method configuration"""

        expected_response = {
            "methodConfiguration": {"name": sample_method_config.name},
            "validInputs": list(sample_method_config.inputs.keys()),
            "validOutputs": list(sample_method_config.outputs.keys()),
            "invalidInputs": {},
            "invalidOutputs": {},
            "missingInputs": [],
            "extraInputs": []
        }

        mock_response.json.return_value = expected_response
        mock_terra_client.get.return_value = mock_response

        test_result = terra_method_ops.method_config_validate(sample_method_config)

        mock_terra_client.get.assert_called_once_with(
            f"method_configs/{mock_terra_client.destination_project}/{sample_method_config.name}/validate",
            use_destination=True
        )

        assert test_result == expected_response


    @pytest.mark.parametrize(
        "invalidInputs,invalidOutputs,missingInputs,extraInputs",
        [
            pytest.param({"invalid_input": "Error"}, {}, [], [], id="invalid_inputs"),
            pytest.param({}, {"invalid_output": "Error"}, [], [], id="invalid_outputs"),
            pytest.param({}, {}, ["missing_input"], [], id="missing_inputs"),
            pytest.param({}, {}, [], ["extra_input"], id="extra_inputs"),
        ]
    )
    def test_method_config_validate_fail(
        self,
        terra_method_ops,
        mock_terra_client,
        mock_response,
        sample_method_config,
        invalidInputs,
        invalidOutputs,
        missingInputs,
        extraInputs,
    ):
        """Test validation failure when method config has invalid inputs"""

        expected_response = {
            "methodConfiguration": {"name": sample_method_config.name},
            "validInputs": [],
            "validOutputs": [],
            "invalidInputs": invalidInputs,
            "invalidOutputs": invalidOutputs,
            "missingInputs": missingInputs,
            "extraInputs": extraInputs
        }

        mock_response.json.return_value = expected_response
        mock_terra_client.get.return_value = mock_response

        with pytest.raises(ValueError, match="MethodConfig validation errors found"):
            terra_method_ops.method_config_validate(sample_method_config)

        mock_terra_client.get.assert_called_once_with(
            f"method_configs/{mock_terra_client.destination_project}/{sample_method_config.name}/validate",
            use_destination=True
        )


class TestTerraMethods:

    def test_get_method_config(
        self,
        terra_method_ops,
        mock_terra_client,
        mock_response,
      ):
        """Test getting a method configuration from source/destination workspace"""

        config_name = "Test_Config"

        expected_response = {
            "namespace": mock_terra_client.source_project,
            "name": config_name,
        }

        mock_response.json.return_value = expected_response
        mock_terra_client.get.return_value = mock_response

        test_result = terra_method_ops.get_method_config(config_name, use_destination=False)

        mock_terra_client.get.assert_called_once_with(
            f"method_configs/{mock_terra_client.source_project}/{config_name}",
            use_destination=False
        )
        assert test_result == expected_response


    def test_overwrite_method_config(
        self,
        terra_method_ops,
        mock_terra_client,
        mock_response,
    ):
        """Test overwrite_method_config sends config to correct workspace"""

        new_config = MethodConfig(
            namespace=mock_terra_client.destination_project,
            name="Test_Overwrite_Config",
            rootEntityType="sample",
            methodRepoMethod=MethodRepoMethod(methodUri="dockstore://test-method/version"),
            inputs={
                "new_input": "this.new_input",
                "example.str": "new_test",
                "example.map": {"new_key1": "new_value1", "new_key2": 10},
            },
            outputs={"new_output": "this.new_output"}
        )

        # This will also test that inputs/outputs are properly encoded
        expected_response = {
            "namespace": mock_terra_client.destination_project,
            "name": "Test_Overwrite_Config",
            "rootEntityType": "sample",
            "methodRepoMethod": {"methodUri": "dockstore://test-method/version"},
            "inputs": {
                "new_input": "this.new_input",
                "example.str": '"new_test"',
                "example.map": '{"new_key1": "new_value1", "new_key2": 10}',
            },
            "outputs": {"new_output": "this.new_output"}

        }

        mock_response.json.return_value = expected_response
        mock_terra_client.put.return_value = mock_response

        test_result = terra_method_ops.overwrite_method_config(new_config, use_destination=True)

        mock_terra_client.put.assert_called_once_with(
            f"method_configs/{mock_terra_client.destination_project}/{new_config.name}",
            data=new_config.model_dump(exclude_none=True),
            use_destination=True
        )

        assert test_result == expected_response


    def test_dict_to_method_config(
        self,
        terra_method_ops
    ):
        """Test converting a dictionary to MethodConfig object"""

        config_dict = {
            "namespace": "test-namespace",
            "name": "TestConfig",
            "rootEntityType": "sample",
            "methodRepoMethod": {
                "methodUri": "dockstore://test/method"
            },
            "inputs": {
                "workflow.terra_ref": "this.input1",
                "workflow.string": "value2",
                "workflow.number": 42
            },
            "outputs": {
                "workflow.output1": "this.output1"
            }
        }

        test_result = terra_method_ops.dict_to_method_config(config_dict)

        assert isinstance(test_result, MethodConfig)
        assert test_result.name == "TestConfig"
        assert test_result.namespace == "test-namespace"
        assert test_result.rootEntityType == "sample"

        # Only encoded during serialization, so check raw inputs here
        assert test_result.inputs["workflow.terra_ref"] == "this.input1"
        assert test_result.inputs["workflow.string"] == "value2"
        assert test_result.inputs["workflow.number"] == 42