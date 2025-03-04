from pathlib import Path
from forklift.terra2bq import Terra2BQ


integrator = Terra2BQ(
        bigquery_project="general-theiagen",
        bigquery_dataset="automation_test",
        samples_table="samples",
        configs_table="configs",
        samples_schema_yaml=Path("example_sample_schema.yaml"),
        configs_schema_yaml=Path("example_config_schema.yaml"),
    )