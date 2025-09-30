"""
Tests for ConfigDataProcessor class.
"""

import pytest
import pandas as pd
import tempfile
import yaml
import json
from pathlib import Path
from bioforklift.data_processing import ConfigDataProcessor


@pytest.fixture
def config_schema_yaml():
    """Create a temporary YAML schema file for testing"""
    schema_content = {
        "fields": {
            "id": {
                "type": "string",
                "required": True,
                "primary_key": True
            },
            "name": {
                "type": "string",
                "required": True,
                "use_as_prefix": True
            },
            "description": {
                "type": "string",
                "display_for_alerts": True
            },
            "settings": {
                "type": "object"
            },
            "parameters": {
                "type": "JSON"
            },
            "workflow_config": {
                "type": "string",
                "configuration_identifier": True
            },
            "created_at": {
                "type": "datetime"
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(schema_content, f)
        return f.name


@pytest.fixture
def config_processor(config_schema_yaml):
    """Create a ConfigDataProcessor instance for testing"""
    return ConfigDataProcessor(config_schema_yaml)


@pytest.fixture
def sample_config():
    """Sample configuration data for testing"""
    return {
        "name": "test_config",
        "description": "Test configuration",
        "settings": {"option1": "value1", "option2": 42},
        "parameters": [{"param1": "value1"}, {"param2": "value2"}],
        "workflow_config": "workflow_123"
    }


@pytest.fixture
def config_directory(tmp_path):
    """Create a temporary directory with config files"""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()

    # Create multiple config files
    configs = [
        {"name": "config1", "description": "First config", "settings": {"key": "value1"}},
        {"name": "config2", "description": "Second config", "settings": {"key": "value2"}},
        {"name": "config3", "description": "Third config", "settings": {"key": "value3"}}
    ]

    for i, config in enumerate(configs, 1):
        config_file = config_dir / f"config{i}.json"
        with open(config_file, 'w') as f:
            json.dump(config, f)

    return config_dir


class TestConfigDataProcessor:
    """Test the ConfigDataProcessor class"""

    def test_initialization(self, config_processor):
        """Test processor initialization"""
        assert config_processor is not None
        assert len(config_processor.schema) > 0
        assert len(config_processor.field_attributes) > 0

    def test_get_prefix_field(self, config_processor):
        """Test getting prefix field"""
        prefix_field = config_processor.get_prefix_field()
        assert prefix_field == "name"

    def test_get_alerts_display_field(self, config_processor):
        """Test getting alerts display field"""
        display_field = config_processor.get_alerts_display_field()
        assert display_field == "description"

    def test_get_configuration_identifier_fields(self, config_processor):
        """Test getting configuration identifier fields"""
        identifier_fields = config_processor.get_configuration_identifier_fields()
        assert "workflow_config" in identifier_fields

    def test_prepare_config_for_insert(self, config_processor, sample_config):
        """Test preparing a single config for insertion"""
        prepared_config = config_processor.prepare_config_for_insert(sample_config)

        # Should have generated UUID for id field
        assert "id" in prepared_config
        assert len(prepared_config["id"]) == 36  # UUID format

        # Should have added created_at timestamp
        assert "created_at" in prepared_config

        # Should have serialized JSON fields
        assert isinstance(prepared_config["settings"], str)  # Serialized from dict
        assert isinstance(prepared_config["parameters"], str)  # Serialized from list

        # Original data should be preserved
        assert prepared_config["name"] == sample_config["name"]
        assert prepared_config["description"] == sample_config["description"]

    def test_prepare_config_preserves_existing_values(self, config_processor):
        """Test that existing ID and timestamp values are preserved"""
        config_with_values = {
            "id": "existing-uuid",
            "name": "test_config",
            "created_at": "2023-01-01 12:00:00",
            "settings": {"key": "value"}
        }

        prepared_config = config_processor.prepare_config_for_insert(config_with_values)

        # Should preserve existing values
        assert prepared_config["id"] == "existing-uuid"
        assert prepared_config["created_at"] == "2023-01-01 12:00:00"

    def test_json_serialization(self, config_processor):
        """Test JSON field serialization"""
        config = {
            "name": "test",
            "settings": {"nested": {"key": "value"}},  # Object type
            "parameters": [{"item1": "value1"}, {"item2": "value2"}],  # JSON type
            "simple_string": "not_serialized"
        }

        processed = config_processor.prepare_config_for_insert(config)

        # Should serialize dict and list fields
        assert isinstance(processed["settings"], str)
        assert isinstance(processed["parameters"], str)

        # Should not modify string fields
        assert processed["simple_string"] == "not_serialized"

        # Should be valid JSON
        assert json.loads(processed["settings"]) == {"nested": {"key": "value"}}
        assert json.loads(processed["parameters"]) == [{"item1": "value1"}, {"item2": "value2"}]

    def test_prepare_configs_from_directory(self, config_processor, config_directory):
        """Test processing multiple configs from directory"""
        configs = config_processor.prepare_configs_from_directory(config_directory)

        assert len(configs) == 3

        # All configs should have system values
        for config in configs:
            assert "id" in config
            assert "created_at" in config

        # Should preserve original data
        names = [config["name"] for config in configs]
        assert "config1" in names
        assert "config2" in names
        assert "config3" in names

    def test_prepare_configs_from_nonexistent_directory(self, config_processor):
        """Test handling of nonexistent directory"""
        with pytest.raises(FileNotFoundError):
            config_processor.prepare_configs_from_directory(Path("/nonexistent/path"))

    def test_process_configs_dataframe(self, config_processor):
        """Test processing DataFrame of configurations"""
        df = pd.DataFrame([
            {"name": "config1", "description": "First config", "settings": {"key": "value1"}},
            {"name": "config2", "description": "Second config", "parameters": [{"param": "value"}]},
            {"name": "config3", "description": "Third config"}
        ])

        processed_df = config_processor.process_configs_dataframe(df)

        assert len(processed_df) == 3

        # Should have system fields
        assert "id" in processed_df.columns
        assert "created_at" in processed_df.columns

        # All IDs should be unique
        ids = processed_df["id"].tolist()
        assert len(set(ids)) == len(ids)

        # JSON fields should be serialized
        settings_with_data = processed_df[processed_df["settings"].notna()]
        if len(settings_with_data) > 0:
            # Should be serialized strings
            assert all(isinstance(val, str) for val in settings_with_data["settings"])

    def test_process_empty_dataframe(self, config_processor):
        """Test processing empty DataFrame"""
        empty_df = pd.DataFrame()
        result = config_processor.process_configs_dataframe(empty_df)

        assert len(result) == 0
        assert result.equals(empty_df)

    def test_get_schema_fields(self, config_processor):
        """Test getting schema field names"""
        fields = config_processor.get_schema_fields()

        expected_fields = ["id", "name", "description", "settings", "parameters", "workflow_config", "created_at"]
        for field in expected_fields:
            assert field in fields