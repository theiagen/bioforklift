from typing import Optional, List, Union, Dict, Any
from pydantic import BaseModel, Field, field_validator
import re


class FieldAttributes(BaseModel):
    """
    Base model for field attributes in schema definitions.

    Contains common attributes shared by both sample and config schemas.
    """

    # Field identification and classification
    primary_key: bool = Field(default=False, description="Field is a primary key (auto-generated UUID)")

    # Data processing attributes
    column_mappings: Optional[List[str]] = Field(
        default=None,
        description="Source column names to map to this field"
    )
    use_field_name: bool = Field(
        default=False,
        description="Use the field name as-is without mapping"
    )

    # Validation attributes
    accepted_pattern: Optional[str] = Field(
        default=None,
        description="Regex pattern for field value validation"
    )
    required: bool = Field(
        default=False,
        description="Field is required"
    )

    # System fields
    system_value: bool = Field(
        default=False,
        description="System-generated value (should be dropped before Terra upload)"
    )

    # Display and formatting
    use_as_prefix: bool = Field(
        default=False,
        description="Use this field value as a prefix"
    )
    display_for_alerts: bool = Field(
        default=False,
        description="Display this field in alerts"
    )
    date_format: Optional[str] = Field(
        default=None,
        description="Date format specification for date/string coercion (e.g., 'ISO 8601')"
    )

    @field_validator('accepted_pattern')
    @classmethod
    def validate_pattern(cls, v: Optional[str]) -> Optional[str]:
        """Validate that pattern is a valid regex."""
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")
        return v

    @field_validator('column_mappings')
    @classmethod
    def normalize_column_mappings(cls, v: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
        """Normalize column_mappings to always be a list."""
        if v is None:
            return None
        if isinstance(v, str):
            return [v]
        return v

    @field_validator('date_format')
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate that date_format is a recognized format."""
        if v is None:
            return None

        # Define supported date format identifiers - can be expanded as needed, but these are knowns
        # from our lab partners
        supported_formats = {
            'ISO 8601',
            'ISO8601',
            'RFC 3339',
            'RFC3339',
            'YYYY-MM-DD',
            'MM/DD/YYYY',
            'DD/MM/YYYY',
            'YYYY/MM/DD',
        }

        # Allow either exact match or strftime format strings
        if v in supported_formats or '%' in v:
            return v

        raise ValueError(
            f"Unsupported date format: {v}. "
            f"Supported formats: {', '.join(sorted(supported_formats))} "
            f"or a valid strftime format string (containing '%')"
        )

    def is_identifier_field(self) -> bool:
        """Check if this field is any type of identifier."""
        return self.primary_key

    def is_system_field(self) -> bool:
        """Check if this is a system-managed field."""
        return self.system_value or self.primary_key


class SampleFieldAttributes(FieldAttributes):
    """
    Extended attributes specific to sample fields.

    Adds sample-specific validation and processing attributes.
    """

    # Sample identification
    sample_identifier: bool = Field(
        default=False,
        description="Field uniquely identifies samples"
    )

    # Metadata and synchronization
    metadata: bool = Field(
        default=False,
        description="Field contains metadata"
    )
    sync_field: bool = Field(
        default=False,
        description="Field should be synchronized to Terra"
    )

    # File and sequence attributes
    sequence_file: bool = Field(
        default=False,
        description="Field contains sequence file path"
    )

    # Configuration inheritance
    inherit_from_config: Optional[str] = Field(
        default=None,
        description="Configuration field to inherit value from"
    )
    
    # Configuration identification for samples
    configuration_identifier: bool = Field(
        default=False,
        description="Field uniquely identifies configurations"
    )

    def is_identifier_field(self) -> bool:
        """Check if this field is any type of identifier."""
        return self.primary_key or self.sample_identifier or self.configuration_identifier

    def should_sync(self) -> bool:
        """Check if this field should be synchronized to Terra."""
        return self.sync_field or self.metadata


class ConfigFieldAttributes(FieldAttributes):
    """
    Extended attributes specific to configuration fields.

    Adds config-specific validation and processing attributes.
    """

    terra_method_config: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None,
        description="Field is part of Terra method configuration (JSON string or dict)"
    )
    single_datatable: bool = Field(
        default=False,
        description="Indicates if source and destination datatables are the same (skips upload step)"
    )


class FieldDefinition(BaseModel):
    """
    Complete field definition including schema and custom attributes.
    """

    name: str = Field(description="Field name")
    field_type: str = Field(description="BigQuery field type (STRING, INTEGER, etc.)")
    mode: str = Field(default="NULLABLE", description="Field mode (REQUIRED, NULLABLE, REPEATED)")
    description: Optional[str] = Field(default=None, description="Field description")

    # Custom attributes
    attributes: FieldAttributes = Field(
        default_factory=FieldAttributes,
        description="Custom processing attributes"
    )

    def has_pattern(self) -> bool:
        """Check if field has a validation pattern."""
        return self.attributes.pattern is not None

    def is_required(self) -> bool:
        """Check if field is required."""
        return self.mode == "REQUIRED" or self.attributes.required

    def get_source_columns(self) -> List[str]:
        """Get list of possible source column names."""
        if self.attributes.column_mappings:
            return self.attributes.column_mappings
        if self.attributes.use_field_name:
            return [self.name]
        return []


class SchemaDefinition(BaseModel):
    """
    Complete schema definition with all fields.
    """

    fields: List[FieldDefinition] = Field(description="List of field definitions")

    def get_field(self, name: str) -> Optional[FieldDefinition]:
        """Get field definition by name."""
        for field in self.fields:
            if field.name == name:
                return field
        return None

    def get_identifier_fields(self) -> List[FieldDefinition]:
        """Get all identifier fields."""
        return [
            field for field in self.fields
            if field.attributes.is_identifier_field()
        ]

    def get_pattern_fields(self) -> List[FieldDefinition]:
        """Get all fields with validation patterns."""
        return [
            field for field in self.fields
            if field.has_pattern()
        ]

    def get_sync_fields(self) -> List[FieldDefinition]:
        """Get all fields that should be synchronized."""
        return [
            field for field in self.fields
            if field.attributes.should_sync()
        ]

    def get_system_fields(self) -> List[FieldDefinition]:
        """Get all system-managed fields."""
        return [
            field for field in self.fields
            if field.attributes.is_system_field()
        ]
