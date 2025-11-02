# Data Processing Classes Reference

## Overview

The data processing module provides classes for handling sample and configuration data transformation, validation, and schema management. These classes are responsible for preparing data for BigQuery operations and ensuring data integrity through schema-based validation.

## Key Components

### SampleDataProcessor

The `SampleDataProcessor` class handles the processing of sample metadata DataFrames according to a defined schema.

#### Constructor

```python
SampleDataProcessor(schema_yaml: str)
```

**Parameters:**
- **schema_yaml** (str): Path to YAML schema file defining sample fields and their attributes

#### Key Methods

##### `process_samples`

Complete sample processing pipeline that applies all validation and transformation steps.

```python
process_samples(
    dataframe: pd.DataFrame,
    existing_identifiers: Optional[Set[str]] = None,
    config: Optional[Dict[str, Any]] = None
) -> pd.DataFrame
```

**Parameters:**
- **dataframe** (pd.DataFrame): Raw input DataFrame
- **existing_identifiers** (Optional[Set[str]]): Set of existing sample IDs to filter out
- **config** (Optional[Dict[str, Any]]): Configuration dictionary for entity type mapping and field inheritance

**Returns:**
- Processed DataFrame ready for BigQuery upload

**Processing Pipeline:**
1. Entity type mapping (Terra column mapping)
2. Field name mapping using `column_mappings` attributes
3. Add missing schema columns
4. Apply config field inheritance
5. Filter columns to schema-defined fields only
6. Filter out existing samples
7. Validate sequence files presence
8. Validate field patterns using regex
9. Add system values (UUIDs, timestamps)
10. Process date formats
11. Coerce DataFrame types to match schema

##### `coerce_dict_types`

Coerce values in a dictionary to match schema field types.

```python
coerce_dict_types(data: Dict[str, Any]) -> Dict[str, Any]
```

**Parameters:**
- **data** (Dict[str, Any]): Dictionary with field names as keys

**Returns:**
- Dictionary with coerced values ready for BigQuery

#### Schema Attribute Methods

##### `get_sample_identifier_field`

```python
get_sample_identifier_field() -> Optional[str]
```

Returns the field marked as `sample_identifier` in the schema.

##### `get_sequence_file_fields`

```python
get_sequence_file_fields() -> List[str]
```

Returns fields marked as `sequence_file` in the schema.

##### `get_config_source_fields`

```python
get_config_source_fields() -> Dict[str, str]
```

Returns mapping of fields that inherit values from configuration using `inherit_from_config` attribute.

##### `get_sync_fields`

```python
get_sync_fields() -> List[str]
```

Returns fields marked as `sync_field` for Terra synchronization.

---

### ConfigProcessor

The `ConfigProcessor` class handles configuration data processing for BigQuery insertion.

#### Constructor

```python
ConfigProcessor(schema_yaml: str)
```

**Parameters:**
- **schema_yaml** (str): Path to YAML schema file defining configuration fields and their attributes

#### Key Methods

##### `prepare_config_for_insert`

Prepare a configuration for insertion by adding system values and serializing JSON.

```python
prepare_config_for_insert(config_data: Dict[str, Any]) -> Dict[str, Any]
```

**Parameters:**
- **config_data** (Dict[str, Any]): Raw configuration data

**Returns:**
- Processed configuration ready for BigQuery insertion

##### `prepare_configs_from_directory`

Process multiple configuration files from a directory.

```python
prepare_configs_from_directory(
    config_dir: Path,
    file_pattern: str = "*.json"
) -> List[Dict[str, Any]]
```

**Parameters:**
- **config_dir** (Path): Directory containing configuration files
- **file_pattern** (str): File pattern to match (default: "*.json")

**Returns:**
- List of processed configurations

##### `process_configs_dataframe`

Process a DataFrame of configurations.

```python
process_configs_dataframe(
    dataframe: pd.DataFrame,
    schema: Optional[List[SchemaField]] = None
) -> pd.DataFrame
```

**Parameters:**
- **dataframe** (pd.DataFrame): DataFrame containing configuration data
- **schema** (Optional[List[SchemaField]]): Optional schema override

**Returns:**
- Processed DataFrame ready for BigQuery upload

#### Schema Attribute Methods

##### `get_prefix_field`

```python
get_prefix_field() -> Optional[str]
```

Returns the field marked with `use_as_prefix=True` for naming entity sets.

##### `get_alerts_display_field`

```python
get_alerts_display_field() -> Optional[str]
```

Returns the field marked with `display_for_alerts=True` for alert notifications.

---

## Schema Models

### FieldAttributes

Base model for field attributes in schema definitions.

```python
class FieldAttributes(BaseModel):
    primary_key: bool = False
    column_mappings: Optional[List[str]] = None
    use_field_name: bool = False
    accepted_pattern: Optional[str] = None
    required: bool = False
    system_value: bool = False
    use_as_prefix: bool = False
    display_for_alerts: bool = False
    date_format: Optional[str] = None
```

### SampleFieldAttributes

Extended attributes specific to sample fields.

```python
class SampleFieldAttributes(FieldAttributes):
    sample_identifier: bool = False
    metadata: bool = False
    sync_field: bool = False
    sequence_file: bool = False
    inherit_from_config: Optional[str] = None
    configuration_identifier: bool = False
```

### ConfigFieldAttributes

Extended attributes specific to configuration fields.

```python
class ConfigFieldAttributes(FieldAttributes):
    terra_method_config: Optional[Union[str, Dict[str, Any]]] = None
    single_datatable: bool = False
```

### FieldDefinition

Complete field definition including schema and custom attributes.

```python
class FieldDefinition(BaseModel):
    name: str
    field_type: str
    mode: str = "NULLABLE"
    description: Optional[str] = None
    attributes: FieldAttributes
```

### SchemaDefinition

Complete schema definition with all fields and typed access methods.

```python
class SchemaDefinition(BaseModel):
    fields: List[FieldDefinition]

    def get_field(self, name: str) -> Optional[FieldDefinition]
    def get_identifier_fields(self) -> List[FieldDefinition]
    def get_pattern_fields(self) -> List[FieldDefinition]
    def get_sync_fields(self) -> List[FieldDefinition]
    def get_system_fields(self) -> List[FieldDefinition]
```

## Schema Converter Functions

### convert_field_attributes

Convert raw attribute dictionary to typed FieldAttributes model.

```python
convert_field_attributes(
    raw_attrs: Dict[str, Any],
    attr_class: Type[FieldAttributes] = FieldAttributes
) -> FieldAttributes
```

### convert_to_schema_definition

Convert BigQuery schema and field attributes to SchemaDefinition model.

```python
convert_to_schema_definition(
    schema: List[SchemaField],
    field_attributes: Dict[str, Dict[str, Any]],
    attr_class: Type[FieldAttributes] = SampleFieldAttributes
) -> SchemaDefinition
```

## Common Field Attribute Patterns

### Sample Identification
- `sample_identifier: true` - Marks the field that uniquely identifies samples
- `primary_key: true` - Auto-generates UUID for this field
- `configuration_identifier: true` - Links sample to its configuration

### Data Validation
- `accepted_pattern: "regex_pattern"` - Validates field values against regex
- `required: true` - Marks field as required
- `sequence_file: true` - Validates presence of sequence files

### Data Mapping
- `column_mappings: ["source_col1", "source_col2"]` - Maps Terra columns to this field
- `use_field_name: true` - Uses field name as-is without mapping
- `inherit_from_config: "config_field"` - Inherits value from configuration

### Synchronization
- `sync_field: true` - Synchronizes field values back to Terra
- `metadata: true` - Marks field as metadata for synchronization
- `system_value: true` - Auto-generated field, excluded from Terra uploads

### Date Processing
- `date_format: "ISO 8601"` - Validates and formats date fields
- Supported formats: ISO 8601, YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY, or strftime patterns

## Usage Examples

### Sample Processing

```python
from bioforklift.data_processing import SampleDataProcessor

# Initialize processor with schema
processor = SampleDataProcessor("schemas/samples_schema.yaml")

# Process samples with validation and transformation
processed_df = processor.process_samples(
    dataframe=raw_samples_df,
    existing_identifiers=existing_sample_ids,
    config=config_dict
)

# Coerce individual record types
coerced_data = processor.coerce_dict_types(sample_dict)
```

### Configuration Processing

```python
from bioforklift.data_processing import ConfigProcessor

# Initialize processor with schema
processor = ConfigProcessor("schemas/configs_schema.yaml")

# Process single configuration
processed_config = processor.prepare_config_for_insert(config_data)

# Process directory of config files
configs = processor.prepare_configs_from_directory(
    config_dir=Path("configs/"),
    file_pattern="*.json"
)
```

### Schema Definition Usage

```python
from bioforklift.data_processing import convert_to_schema_definition
from bioforklift.data_processing import SampleFieldAttributes

# Convert to typed schema definition
schema_def = convert_to_schema_definition(
    schema=bigquery_schema,
    field_attributes=field_attrs_dict,
    attr_class=SampleFieldAttributes
)

# Type-safe access to field definitions
sample_id_field = schema_def.get_field("sample_id")
if sample_id_field and sample_id_field.attributes.sample_identifier:
    print(f"Sample identifier field: {sample_id_field.name}")
```