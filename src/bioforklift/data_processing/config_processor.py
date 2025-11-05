import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import pandas as pd
from google.cloud.bigquery import SchemaField
from .utils import load_schema_from_yaml
from bioforklift.forklift_logging import setup_logger
from .schema_models import SchemaDefinition, ConfigFieldAttributes
from .schema_converter import convert_to_schema_definition

logger = setup_logger(__name__)


class ConfigProcessor:

    def __init__(self, schema_yaml: str):
        """
        Initialize the processor with schema information.

        Args:
            schema_yaml: Path to YAML schema file
        """
        schema_info = load_schema_from_yaml(schema_yaml)
        self.schema = schema_info["schema"]
        self.field_attributes = schema_info["field_attributes"]

        # Add typed schema definition for type-safe attribute access
        self.schema_definition: SchemaDefinition = convert_to_schema_definition(
            self.schema,
            self.field_attributes,
            ConfigFieldAttributes
        )

        logger.info(f"ConfigDataProcessor initialized with schema: {schema_yaml}")

    def prepare_config_for_insert(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare a configuration for insertion by adding system values and serializing JSON.

        Args:
            config_data: Raw configuration data

        Returns:
            Processed configuration ready for BigQuery insertion
        """
        logger.debug("Preparing config for insertion")

        # Create a copy to avoid modifying the original
        config = config_data.copy()

        # Generate system values
        config = self._add_system_values_to_config(config)

        # Serialize JSON fields
        config = self._serialize_json_fields(config)

        return config

    def prepare_configs_from_directory(
        self,
        config_dir: Path,
        file_pattern: str = "*.json"
    ) -> List[Dict[str, Any]]:
        """
        Process multiple configuration files from a directory.

        Args:
            config_dir: Directory containing configuration files
            file_pattern: File pattern to match (default: *.json)

        Returns:
            List of processed configurations
        """
        logger.info(f"Processing configs from directory: {config_dir}")

        if not config_dir.exists():
            raise FileNotFoundError(f"Config directory not found: {config_dir}")

        config_files = list(config_dir.glob(file_pattern))
        if not config_files:
            logger.warning(f"No config files found matching pattern: {file_pattern}")
            return []

        configs = []
        for config_file in config_files:
            try:
                logger.debug(f"Processing config file: {config_file}")
                with open(config_file, 'r') as f:
                    config_data = json.load(f)

                processed_config = self.prepare_config_for_insert(config_data)
                configs.append(processed_config)

            except Exception as e:
                logger.error(f"Error processing config file {config_file}: {e}")
                continue

        logger.info(f"Successfully processed {len(configs)} configuration files")
        return configs

    def process_configs_dataframe(
        self,
        dataframe: pd.DataFrame,
        schema: Optional[List[SchemaField]] = None
    ) -> pd.DataFrame:
        """
        Process a DataFrame of configurations.

        Args:
            dataframe: DataFrame containing configuration data
            schema: Optional schema override

        Returns:
            Processed DataFrame ready for BigQuery upload
        """
        logger.info(f"Processing DataFrame with {len(dataframe)} configurations")

        if dataframe.empty:
            return dataframe

        processed_df = dataframe.copy()

        # Add system values for each row
        processed_df = self._add_system_values_to_dataframe(processed_df)

        # Serialize JSON fields in DataFrame
        processed_df = self._serialize_json_fields_dataframe(processed_df)

        logger.info(f"DataFrame processing complete: {len(processed_df)} configs ready")
        return processed_df

    def _add_system_values_to_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Add system-generated values to a single configuration"""
        # Generate UUID for primary key fields if not provided
        for field_name, attrs in self.field_attributes.items():
            if attrs.get("primary_key") and field_name not in config:
                config[field_name] = str(uuid.uuid4())
                logger.debug(f"Generated UUID for field '{field_name}': {config[field_name]}")

        # Set created_at datetime if not provided
        for field_name, attrs in self.field_attributes.items():
            if field_name == "created_at" and field_name not in config:
                config[field_name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.debug(f"Set created_at timestamp: {config[field_name]}")

        return config

    def _add_system_values_to_dataframe(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Add system-generated values to a DataFrame of configurations"""
        df = dataframe.copy()

        # Generate UUIDs for primary key fields
        for field_name, attrs in self.field_attributes.items():
            if attrs.get("primary_key") and (field_name not in df.columns or df[field_name].isna().any()):
                if field_name not in df.columns:
                    df[field_name] = None

                # Fill missing values with UUIDs
                null_mask = df[field_name].isna()
                df.loc[null_mask, field_name] = [str(uuid.uuid4()) for _ in range(null_mask.sum())]
                logger.debug(f"Generated {null_mask.sum()} UUIDs for field '{field_name}'")

        # Set created_at for missing timestamps
        for field_name, attrs in self.field_attributes.items():
            if field_name == "created_at":
                if field_name not in df.columns:
                    df[field_name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    null_mask = df[field_name].isna()
                    df.loc[null_mask, field_name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return df

    def _serialize_json_fields(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize JSON fields in a single configuration"""
        # Serialize based on schema field types
        for field in self.schema:
            field_name = field.name
            if field.field_type.upper() == "JSON" and field_name in config:
                if isinstance(config[field_name], (dict, list)):
                    config[field_name] = json.dumps(config[field_name])
                    logger.debug(f"Serialized JSON field '{field_name}'")

        # Serialize based on field attributes (backup approach)
        for field_name, attrs in self.field_attributes.items():
            if attrs.get("type", "").lower() == "object" and field_name in config:
                if isinstance(config[field_name], (dict, list)):
                    config[field_name] = json.dumps(config[field_name])
                    logger.debug(f"Serialized object field '{field_name}' from attributes")

        return config

    def _serialize_json_fields_dataframe(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Serialize JSON fields in a DataFrame"""
        df = dataframe.copy()

        # Serialize based on schema field types
        for field in self.schema:
            field_name = field.name
            if field.field_type.upper() == "JSON" and field_name in df.columns:
                # Apply JSON serialization to dict/list values
                df[field_name] = df[field_name].apply(
                    lambda x: json.dumps(x) if isinstance(x, (dict, list)) else x
                )
                logger.debug(f"Serialized JSON field '{field_name}' in DataFrame")

        # Serialize based on field attributes
        for field_name, attrs in self.field_attributes.items():
            if attrs.get("type", "").lower() == "object" and field_name in df.columns:
                df[field_name] = df[field_name].apply(
                    lambda x: json.dumps(x) if isinstance(x, (dict, list)) else x
                )
                logger.debug(f"Serialized object field '{field_name}' from attributes in DataFrame")

        return df

    def get_schema_fields(self) -> List[str]:
        """Get list of field names defined in the schema"""
        return [field.name for field in self.schema]

    def get_prefix_field(self) -> Optional[str]:
        """Get the field name that is marked with use_as_prefix=True"""
        return next(
            (
                field_name
                for field_name, attrs in self.field_attributes.items()
                if attrs.get("use_as_prefix")
            ),
            None,
        )

    def get_alerts_display_field(self) -> Optional[str]:
        """Get the field name that is marked with display_for_alerts=True"""
        return next(
            (
                field_name
                for field_name, attrs in self.field_attributes.items()
                if attrs.get("display_for_alerts")
            ),
            None,
        )

    def get_single_datatable_field(self) -> Optional[str]:
        """Get the field name 'single_datatable' if it exists in the schema"""
        return "single_datatable" if "single_datatable" in self.field_attributes else None