from typing import Dict, Any
from datetime import datetime, date
import pandas as pd
import yaml
from google.cloud.bigquery import SchemaField
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)

# Utils mostly for handling schema and data transformations between BigQuery / yaml / pandas
# This is a good place to put functions that don't fit into the main BigQueryClient class


def infer_bigquery_param_type(value: Any) -> str:
    """
    Infer BigQuery parameter type from Python runtime value.

    Used for building parameterized queries with proper type casting.

    Args:
        value: Python value to infer type from

    Returns:
        BigQuery parameter type string (e.g., "STRING", "INT64", "BOOL")
    """
    # Check boolean before int 
    if isinstance(value, bool):
        return "BOOL"
    elif isinstance(value, int):
        return "INT64"
    elif isinstance(value, float):
        return "FLOAT64"
    elif isinstance(value, (datetime, pd.Timestamp)):
        return "DATETIME"
    elif isinstance(value, date):
        return "DATE"
    elif isinstance(value, (list, tuple)):
        return "ARRAY"
    elif value is None:
        return "STRING"
    else:
        # Default to STRING for str and other types
        return "STRING"


def parse_field_type(field_type: str) -> str:
    """Convert YAML schema types to BigQuery types"""
    type_mapping = {
        "string": "STRING",
        "str": "STRING",
        "integer": "INTEGER",
        "int": "INTEGER",
        "float": "FLOAT",
        "boolean": "BOOLEAN",
        "bool": "BOOLEAN",
        "datetime": "DATETIME",
        "date": "DATE",
        "timestamp": "TIMESTAMP",
        "record": "RECORD",
        "array": "ARRAY",
        "object": "JSON",
        "json": "JSON",
    }
    return type_mapping.get(field_type.lower(), "STRING")


def parse_mode(required: bool) -> str:
    """Convert required flag to BigQuery field mode"""
    return "REQUIRED" if required else "NULLABLE"


def create_schema_field(name: str, field_def: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a BigQuery SchemaField from YAML field definition

    Args:
        name: Field name
        field_def: Field definition from YAML
            {
                type: str,
                description: str (optional),
                required: bool (optional),
                fields: list (optional, for RECORD type)
            }
    """
    logger.debug(f"Creating schema field: {name} - {field_def}")
    field_type = parse_field_type(field_def["type"])
    mode = parse_mode(field_def.get("required", False))
    description = field_def.get("description", "")

    # Handle nested records
    if field_type == "RECORD":
        logger.debug(f"Creating nested record: {name}")
        sub_fields = []
        for sub_name, sub_def in field_def.get("fields", {}).items():
            sub_fields.append(create_schema_field(sub_name, sub_def))
        return SchemaField(
            name=name,
            field_type=field_type,
            mode=mode,
            description=description,
            fields=tuple(sub_fields),
        )

    # Handle arrays - repeated mode for simple types, record mode for nested records
    # https://cloud.google.com/bigquery/docs/nested-repeated
    elif field_type == "ARRAY":
        logger.debug(f"Creating array field: {name}")
        if "items" not in field_def:
            logger.error(f"Array field '{name}' must specify 'items' type")
            raise ValueError(f"Array field '{name}' must specify 'items' type")

        item_def = field_def["items"]
        item_type = parse_field_type(item_def["type"])

        if item_type == "RECORD":
            sub_fields = []
            for sub_name, sub_def in item_def.get("fields", {}).items():
                sub_fields.append(create_schema_field(sub_name, sub_def))
            return SchemaField(
                name=name,
                field_type=field_type,
                mode=mode,
                description=description,
                fields=tuple(sub_fields),
            )
        else:
            return SchemaField(
                name=name,
                field_type=item_type,
                mode="REPEATED",
                description=description,
            )

    # Extract any custom tags or identifiers reserved for custom attributes
    custom_attributes = {}
    for key, value in field_def.items():
        if key not in ["type", "description", "required", "fields", "items"]:
            custom_attributes[key] = value

    schema_field = SchemaField(
        name=name, field_type=field_type, mode=mode, description=description
    )

    return {"field": schema_field, "custom_attributes": custom_attributes}


def load_schema_from_yaml(yaml_path: str) -> Dict[str, Any]:
    """
    Load BigQuery schema from YAML file

    Example YAML format:
    ```yaml
    fields:
      id:
        type: string
        required: true
        description: Primary key
      sequence_file:
        type: string
        required: true
      retry:
        type: integer
      metadata:
        type: record
        fields:
          created_at:
            type: datetime
            required: true
          updated_at:
            type: datetime
    ```
    """
    logger.info(f"Loading schema from yaml: {yaml_path}")

    with open(yaml_path) as f:
        schema_def = yaml.safe_load(f)

    schema = []
    field_attributes = {}

    for field_name, field_def in schema_def["fields"].items():
        result = create_schema_field(field_name, field_def)
        schema.append(result["field"])

        if result["custom_attributes"]:
            field_attributes[field_name] = result["custom_attributes"]

    # Return both the schema and custom attributes for downstream use
    return {"schema": schema, "field_attributes": field_attributes}