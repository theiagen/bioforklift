import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
from bioforklift.terra import Terra
from bioforklift.bigquery import BigQuery
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)

class ConfigBuilder:
    """
    Utility class for building and managing Terra configs
    """
    
    def __init__(self, 
                bigquery: BigQuery,
                config_table_name: str,
                config_schema_yaml: str,
                template_config_path: Optional[Union[str, Path]] = None,
                defualt_values: Optional[Dict[str, Any]] = None,
                ):
        """
        Initializes the ConfigBuilder with the provided parameters.
        
        Args:
            bigquery (BigQuery): The BigQuery instance to use for database operations.
            config_table_name (str): The name of the configuration table.
            config_schema_yaml (str): The path to the YAML schema file for the configuration.
            template_config_path (Optional[Union[str, Path]]): The path to the template config file (JSON).
            defualt_values (Optional[Dict[str, Any]]): Optional dictionary of default values to use for the configuration.
        """
        
        self.bigquery = bigquery
        self.config_table_name = config_table_name
        self.config_schema_yaml = config_schema_yaml
        self.template_config_path = Path(template_config_path) if template_config_path else None
        self.defualt_values = defualt_values if defualt_values else {}
        
        self.config_ops = bigquery.get_config_operations(
            config_table_name=self.config_table_name,
            config_schema_yaml=self.config_schema_yaml
        )
        
        self.template_config = {}
        if self.template_config_path and self.template_config_path.exists():
            with open(self.template_config_path, 'r') as json_file:
                self.template_config = json.load(json_file)
                
                
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate config dictionary against the schema.
        Args:
            config (Dict[str, Any]): The configuration dictionary to validate.
            
        Raises:
            ValueError: If the config does not match the schema.
        """
        
        missing_fields = []
        
        field_attributes = self.config_ops.field_attributes
        
        for field, attributes in field_attributes.items():
            if attributes.get('required') and field not in config:
                missing_fields.append(field)
                
        if missing_fields:
            raise ValueError(f"Missing required fields in config: {', '.join(missing_fields)}")
        
        # Handle JSON fields
        for fields_name, value in config.items():
            if fields_name in field_attributes and field_attributes[fields_name].get('type') == 'json':
                if isinstance(value, dict) or isinstance(value, list):
                    config[fields_name] = json.dumps(value)
    
    def list_terra_datatables(self,
                            terra_client: Terra,
                            include_attributes: bool = False
                            ) -> List[str] | Dict[str, Any]:
        """
        Lists all the datatables in the Terra workspace.
        
        Args:
            terra_client (Terra): The Terra client instance to use for fetching datatables.
            include_attributes (bool): Whether to include attributes in the output.
            
        Returns:
            List[str] | Dict[str, Any]: A list of datatable names or a dictionary with datatable names and their attributes.
        
        """
        
        try:
            
            logger.info(f"Fetching datatables from Terra workspace: {terra_client.source_project}/{terra_client.source_workspace}")
            
            entity_types = terra_client.entities.list_entity_types(include_attributes=include_attributes)
            
            logger.info(f"Datatables fetched successfully: {entity_types}")
            
            return entity_types
            
        except Exception as exc:
            logger.error(f"Error fetching datatables: {exc}")
            raise RuntimeError(f"Error fetching datatables: {exc}")
        
        
    def get_existing_entity_types(self) -> List[str]:
        """
        Get list of existing entity types in the BigQuery config table.
        
        Returns:
            List[str]: A list of existing entity types.
        """
        
        try:
            
            configs = self.config_ops.get_configs()
            
            entity_types = list(set(config.get('entity_type') for config in configs if config.get('entity_type')))
            
            logger.info(f"Existing entity types fetched successfully: {len(entity_types)}")
            
            return entity_types
            
        except Exception as exc:
            logger.error(f"Error fetching existing entity types: {exc}")
            raise RuntimeError(f"Error fetching existing entity types: {exc}")
        
    def get_new_entity_types(self,
                            terra_client: Terra,
                            ) -> List[str]:
        """
        Get list of new entity types in the Terra workspace.
        
        Args:
            terra_client (Terra): The Terra client instance to use for fetching datatables.
            include_attributes (bool): Whether to include attributes in the output.
            
        Returns:
            List[str]: A list of new entity types.
        """
        
        try:
            # Fetch new entity types from the Terra workspace
            new_entity_types = self.list_terra_datatables(terra_client)
            
            # Get existing entity types from the BigQuery config table
            existing_entity_types = self.get_existing_entity_types()
            
            # Filter out existing entity types
            new_entity_types = [entity for entity in new_entity_types if entity not in existing_entity_types]
            
            logger.info(f"New entity types fetched successfully: {len(new_entity_types)}")
            
            return new_entity_types
            
        except Exception as exc:
            logger.error(f"Error fetching new entity types: {exc}")
            raise RuntimeError(f"Error fetching new entity types: {exc}")
        
        
    def create_config_from_template(
        self,
        entity_type: str,
        terra_client: Terra,
        override_values: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
        
        """
        Create a configuration dictionary from a template.
        Args:
            entity_type (str): The entity type for which to create the configuration.
            terra_client (Terra): The Terra client instance to use for fetching datatables.
            override_values (Optional[Dict[str, Any]]): Optional dictionary of values to override in the template.
        Returns:
            Dict[str, Any]: The configuration dictionary.
        """
    
        try:
            
            config = self.template_config.copy() if self.template_config else {}
            
            # We need to apply defult values to the config
            
            for key, value in self.defualt_values.items():
                if key not in config:
                    config[key] = value
                    
            config.update({
                "id": str(uuid.uuid4()),
                "entity_type": entity_type,
                "active": True,
                "transferred": False,
                "terra_source_workspace": terra_client.source_workspace,
                "terra_source_project": terra_client.source_project,
            })
            
            if override_values:
                config.update(override_values)
                
            # Validate the config against the schema
            self._validate_config(config)
            
            # Create config
            new_config = self.config_ops.create_config(config)
            
            logger.info(f"Config created successfully from template: {config}")
            
            return new_config                
            
                    
        except Exception as exc:
            logger.error(f"Error creating config from template: {exc}")
            raise RuntimeError(f"Error creating config from template: {exc}")
        
        
    def build_new_configs(
        self,
        terra_client: Terra,
        override_values: Optional[Dict[str, Any]] = None,
        ) -> List[Dict[str, Any]]:
        
        """
        Build new configurations for the new entity types in the Terra workspace.
        
        Args:
            terra_client (Terra): The Terra client instance to use for fetching datatables.
            override_values (Optional[Dict[str, Any]]): Optional dictionary of values to override in the template.
            
        Returns:
            List[Dict[str, Any]]: A list of new configuration dictionaries.
        """
        
        try:
            # Grab new entities from the Terra workspace
            new_entity_types = self.get_new_entity_types(terra_client)
            
            if not new_entity_types:
                logger.info("No new entity types found, no configurations created")
                return []
            
            # Create configurations for each new entity type added to the workspace
            created_configs = []
            for entity_type in new_entity_types:
                config = self.create_config_from_template(
                    entity_type=entity_type,
                    terra_client=terra_client,
                    override_values=override_values
                )
                created_configs.append(config)
            
            logger.info(f"Created {len(created_configs)} new configurations")
            return created_configs
            
        except Exception as exc:
            logger.error(f"Error building missing configurations: {str(exc)}")
            raise RuntimeError(f"Failed to build missing configurations: {str(exc)}")
        
        
    def load_config_template(template_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Load configuration template from JSON file
        
        Args:
            template_path: Path to template JSON file
            
        Returns:
            Template configuration dictionary
        """
        path = Path(template_path) if isinstance(template_path, str) else template_path
        
        if not path.exists():
            raise FileNotFoundError(f"Template file not found: {path}")
        
        with open(path, 'r') as f:
            template = json.load(f)
        
        return template
        
        
    