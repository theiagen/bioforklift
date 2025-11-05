from typing import Dict, Any, List, Type, Union
from google.cloud.bigquery import SchemaField

from .schema_models import (
    FieldAttributes,
    SampleFieldAttributes,
    ConfigFieldAttributes,
    FieldDefinition,
    SchemaDefinition
)
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


def convert_field_attributes(
    raw_attrs: Dict[str, Any],
    attr_class: Type[FieldAttributes] = FieldAttributes
) -> FieldAttributes:
    """
    Convert raw attribute dictionary to FieldAttributes model.

    Args:
        raw_attrs: Dictionary of raw field attributes from YAML
        attr_class: Attribute class to use (FieldAttributes, SampleFieldAttributes, or ConfigFieldAttributes)

    Returns:
        Typed FieldAttributes model
    """
    # Filter to only include known fields for this attribute class
    known_fields = attr_class.model_fields.keys()
    filtered_attrs = {
        key: value
        for key, value in raw_attrs.items()
        if key in known_fields
    }

    try:
        return attr_class(**filtered_attrs)
    except Exception as e:
        logger.warning(f"Error converting field attributes: {e}. Using defaults.")
        return attr_class()


def convert_to_schema_definition(
    schema: List[SchemaField],
    field_attributes: Dict[str, Dict[str, Any]],
    attr_class: Type[FieldAttributes] = SampleFieldAttributes
) -> SchemaDefinition:
    """
    Convert BigQuery schema and field attributes to SchemaDefinition model.

    Args:
        schema: List of BigQuery SchemaField objects
        field_attributes: Dictionary of field attributes from YAML
        attr_class: Attribute class to use (SampleFieldAttributes or ConfigFieldAttributes)

    Returns:
        Typed SchemaDefinition model
    """
    field_definitions = []

    for bq_field in schema:
        # Get attributes for this field, or empty dict if not present
        raw_attrs = field_attributes.get(bq_field.name, {})

        # Convert to typed attributes using the specified class
        attributes = convert_field_attributes(raw_attrs, attr_class)

        # Create field definition
        field_def = FieldDefinition(
            name=bq_field.name,
            field_type=bq_field.field_type,
            mode=bq_field.mode,
            description=bq_field.description or "",
            attributes=attributes
        )

        field_definitions.append(field_def)

    return SchemaDefinition(fields=field_definitions)


def extract_field_attributes_dict(schema_def: SchemaDefinition) -> Dict[str, Dict[str, Any]]:
    """
    Extract field attributes as raw dictionary (for backward compatibility).

    Args:
        schema_def: Typed SchemaDefinition

    Returns:
        Dictionary of field attributes
    """
    return {
        field.name: field.attributes.model_dump(exclude_none=True)
        for field in schema_def.fields
    }
