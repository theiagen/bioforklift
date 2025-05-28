import pytest
import json
import uuid
import re
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from typing import Dict, List, Any, Optional
from bioforklift.terra2bq.config_builder import ConfigBuilder
from bioforklift.terra import Terra
from bioforklift.bigquery import BigQuery


@pytest.fixture
def mock_schema_yaml():
    """Mock schema YAML content."""
    return """
fields:
  id:
    type: string
    required: true
  entity_type:
    type: string
    required: true
  active:
    type: boolean
  transferred:
    type: boolean
  json_field:
    type: json
    """


@pytest.fixture
def config_builder(mock_schema_yaml):
    """Fixture for ConfigBuilder with mocked dependencies."""
    # Create a mock BigQuery instance with necessary methods
    mock_config_ops = MagicMock()
    mock_config_ops.field_attributes = {
        "id": {"type": "string", "required": True},
        "entity_type": {"type": "string", "required": True},
        "active": {"type": "boolean", "required": False},
        "transferred": {"type": "boolean", "required": False},
        "json_field": {"type": "json", "required": False}
    }
    
    mock_bigquery = MagicMock()
    mock_bigquery.get_config_operations.return_value = mock_config_ops
    
    # Create a mock Terra instance
    mock_terra = MagicMock()
    mock_terra.source_project = "test-project"
    mock_terra.source_workspace = "test-workspace"
    mock_terra.entities = MagicMock()
    mock_terra.entities.list_entity_types = MagicMock(return_value=["table1", "table2"])
    
    # Patch the dependencies
    with patch('bioforklift.bigquery.BigQuery', return_value=mock_bigquery), \
         patch('bioforklift.terra.Terra', return_value=mock_terra), \
         patch('builtins.open', mock_open(read_data=mock_schema_yaml)):
        
        # Create the ConfigBuilder instance
        builder = ConfigBuilder(
            bigquery_project="test-project",
            bigquery_dataset="test-dataset",
            bigquery_config_table_name="test_config_table",
            bigquery_config_schema_yaml="test_schema.yaml",
            terra_source_project="test-project",
            terra_source_workspace="test-workspace",
            template_config_path=None,
            default_values={"test_default": "value"}
        )
        
        # Set mocked config_ops directly
        builder.config_ops = mock_config_ops
        builder.bigquery = mock_bigquery
        builder.terra = mock_terra
        
        return builder


class TestConfigBuilder:
    """Test suite for ConfigBuilder class."""

    def test_init(self, config_builder):
        """Test initialization of ConfigBuilder."""
        assert config_builder.config_table_name == "test_config_table"
        assert config_builder.config_schema_yaml == "test_schema.yaml"
        assert config_builder.default_values == {"test_default": "value"}
        assert config_builder.template_config == {}

    def test_init_with_template(self, mock_schema_yaml):
        """Test initialization with a template config file."""
        mock_template = {"template_key": "template_value"}
        
        # Patch dependencies
        with patch('bioforklift.bigquery.BigQuery') as mock_bigquery_class, \
             patch('bioforklift.terra.Terra') as mock_terra_class, \
             patch('pathlib.Path.exists', return_value=True), \
             patch('builtins.open') as mock_open_func:
            
            # Configure mocks
            mock_bigquery = mock_bigquery_class.return_value
            mock_config_ops = MagicMock()
            mock_bigquery.get_config_operations.return_value = mock_config_ops
            
            mock_terra = mock_terra_class.return_value
            
            # Configure mock_open to return different content based on file path
            def side_effect(file_path, *args, **kwargs):
                if str(file_path) == "test_template.json":
                    file_mock = mock_open(read_data=json.dumps(mock_template)).return_value
                else:
                    file_mock = mock_open(read_data=mock_schema_yaml).return_value
                return file_mock
            
            mock_open_func.side_effect = side_effect
            
            # Create the builder
            builder = ConfigBuilder(
                bigquery_project="test-project",
                bigquery_dataset="test-dataset",
                bigquery_config_table_name="test_config_table",
                bigquery_config_schema_yaml="test_schema.yaml",
                terra_source_project="test-project",
                terra_source_workspace="test-workspace",
                template_config_path="test_template.json",
                default_values={"test_default": "value"}
            )
            
            # Verify template was loaded
            assert builder.template_config == mock_template

    def test_validate_config_success(self, config_builder):
        """Test successful config validation."""
        # Test valid config
        valid_config = {
            "id": "test-id",
            "entity_type": "test-entity",
            "json_field": {"key": "value"}
        }
        
        # This should not raise an exception
        config_builder._validate_config(valid_config)
        
        # Check if JSON field was converted to string
        assert isinstance(valid_config["json_field"], str)
        assert json.loads(valid_config["json_field"]) == {"key": "value"}

    def test_validate_config_missing_required(self, config_builder):
        """Test config validation with missing required fields."""
        # Test invalid config
        invalid_config = {
            "id": "test-id" 
        }
        
        with pytest.raises(ValueError) as exc:
            config_builder._validate_config(invalid_config)
        
        assert "Missing required fields in config" in str(exc.value)
        assert "entity_type" in str(exc.value)

    def test_list_terra_datatables(self, config_builder):
        """Test listing Terra datatables."""
        
        config_builder.terra.entities.list_entity_types.return_value = ["table1", "table2"]
        
        result = config_builder.list_terra_datatables()
        
        assert result == ["table1", "table2"]
        config_builder.terra.entities.list_entity_types.assert_called_once_with(include_attributes=False)

    def test_get_existing_entity_types(self, config_builder):
        """Test getting existing entity types."""
        
        mock_configs = [
            {"entity_type": "table1"},
            {"entity_type": "table2"},
            {"entity_type": "table1"}  # Duplicate to test set conversion
        ]
        config_builder.config_ops.get_configs = MagicMock(return_value=mock_configs)
        
        result = config_builder.get_existing_entity_types()
        
        assert set(result) == {"table1", "table2"}
        config_builder.config_ops.get_configs.assert_called_once()

    def test_get_new_entity_types_no_pattern(self, config_builder):
        """Test getting new entity types without pattern."""
        
        with patch.object(config_builder, 'list_terra_datatables', return_value=["table1", "table2", "table3"]), \
             patch.object(config_builder, 'get_existing_entity_types', return_value=["table1"]):
            
            result = config_builder.get_new_entity_types()
            
            assert set(result) == {"table2", "table3"}

    def test_get_new_entity_types_with_pattern(self, config_builder):
        """Test getting new entity types with pattern."""
        
        with patch.object(config_builder, 'list_terra_datatables', return_value=["table1", "table2", "table3"]), \
             patch.object(config_builder, 'get_existing_entity_types', return_value=["table1"]):
            
            result = config_builder.get_new_entity_types(table_pattern="table2")
            
            assert result == ["table2"]

    def test_create_config_from_template(self, config_builder):
        """Test creating config from template."""
        
        config_builder.template_config = {"template_key": "template_value"}
        expected_config = {
            "id": "test-uuid",
            "entity_type": "test_entity",
            "active": True,
            "transferred": False,
            "terra_source_workspace": "test-workspace",
            "terra_source_project": "test-project",
            "template_key": "template_value",
            "test_default": "value"
        }
        
        config_builder.config_ops.create_config = MagicMock(return_value=expected_config)
        
        mock_uuid = MagicMock()
        mock_uuid.__str__.return_value = "test-uuid"
        with patch('uuid.uuid4', return_value=mock_uuid):
            
            result = config_builder.create_config_from_template("test_entity")
            
            assert result == expected_config
            
            # Check that create_config was called with the right parameters
            # Get the actual config passed to create_config
            actual_config = config_builder.config_ops.create_config.call_args[0][0]
            assert actual_config["entity_type"] == "test_entity"
            assert actual_config["template_key"] == "template_value"
            assert actual_config["active"] is True
            assert actual_config["transferred"] is False

    def test_build_new_configs(self, config_builder):
        """Test building new configs."""
        
        mock_entity_types = ["table2", "table3"]
        mock_configs = [
            {"id": "id1", "entity_type": "table2"},
            {"id": "id2", "entity_type": "table3"}
        ]
        
        with patch.object(config_builder, 'get_new_entity_types', return_value=mock_entity_types), \
             patch.object(config_builder, 'create_config_from_template', side_effect=mock_configs):
            
            result = config_builder.build_new_configs()
            
            assert result == mock_configs
            assert config_builder.create_config_from_template.call_count == 2

    def test_build_new_configs_empty(self, config_builder):
        """Test building new configs with no new entities."""
        
        with patch.object(config_builder, 'get_new_entity_types', return_value=[]):
            result = config_builder.build_new_configs()
            
            assert result == []

    def test_build_new_configs_with_override(self, config_builder):
        """Test building new configs with override values."""
        
        mock_entity_types = ["table2"]
        mock_config = {"id": "id1", "entity_type": "table2", "override_key": "override_value"}
        
        with patch.object(config_builder, 'get_new_entity_types', return_value=mock_entity_types), \
             patch.object(config_builder, 'create_config_from_template', return_value=mock_config) as mock_create:
            
            override_values = {"override_key": "override_value"}
            result = config_builder.build_new_configs(override_values=override_values)
            
            assert result == [mock_config]
            
            # Check that create_config_from_template was called with the right parameters
            mock_create.assert_called_once_with(
                entity_type="table2",
                override_values=override_values
            )