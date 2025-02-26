from forklift.bigquery import BigQuery

bq = BigQuery(
    project="general-theiagen",
    dataset="automation_test"
)

# Create table, commented out after first run
table_create_res =bq.create_table(
    table_name="configs",
    schema_yaml="example_config_schema.yaml"
)

table_exists = bq.table_exists("configs")
if table_exists:
    config_ops = bq.get_config_operations(
        table_name="configs",
        config_schema_yaml="example_config_schema.yaml"
    )
else:
    raise ValueError("Table does not exist")

# Create a new config
new_config = config_ops.create_config("example_configs/test_config.json")
print(f"Created new config with ID: {new_config.get('id')}")

# Get a config by ID
config_id = new_config.get('id')
retrieved_config = config_ops.get_config(config_id)
print(f"Retrieved config: {retrieved_config.get('name')}")

# Get all configs (optionally filtered)
all_configs = config_ops.get_configs()
print(f"Found {len(all_configs)} total configurations")

# Get only active configs
active_configs = config_ops.get_configs(active_only=True)
print(f"Found {len(active_configs)} active configurations")

# Get configs for a specific entity type
entity_configs = config_ops.get_configs(
    active_only=True,
    entity_type="illumina_specimen"
)
print(f"Found {len(entity_configs)} configs for entity type 'illumina_specimen'")

# Update created config
updated_config = config_ops.update_config(
    config_id=config_id,
    update_data={"config_version": "v1.1"}
)
print(f"Updated config version: {updated_config.get('config_version')}")

# Deactivate configs by filter
deactivation_result = config_ops.deactivate_configs({
    "entity_type": "illumina_specimen",
    "name": "Test Example"
})
print(f"Deactivated {deactivation_result.get('deactivated_count')} configs")

# Load multiple configs from a directory
try:
    bulk_configs = config_ops.create_configs_from_directory("example_configs/")
    print(f"Loaded {len(bulk_configs)} configurations from directory")
except Exception as e:
    print(f"Error loading configs from directory: {str(e)}")