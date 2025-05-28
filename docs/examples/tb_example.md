# Case Study: CalTB-Net Automation

This page descrives how Sage automated the transfer of data from the CDPH clinical workspace to a CalTB-Net workspace using bioforklift.

Theiagen organization members can see the full code in the `cdph-automations` _private_ GitHub respository.

Of note, this automation required creating new configurations based on the presence of new data tables in the CDPH clinical workspace. bioforklift has built-in functionality to create new configurations, using the `ConfigBuilder` class, by performing regular expression searches on the workspace's data entities. In order to create new configurations, a template configuration was needed to model any new configurations.

The following code is used to:

1. search for new data tables in the CDPH clinical workspace
2. copy the read data from those tables to a new `WGSDST_combined` table in the CDPH clinical workspace
3. process the new configurations

```python
from bioforklift.terra import Terra
from bioforklift.terra2bq import Terra2BQ, ConfigBuilder

# a function to create new configurations by searching for the new data tables using a regex pattern
def find_tables_in_workspace(config_builder, regex_pattern):
    print("\nBuilding configurations for matching WGS datasets...")
    created_configs = config_builder.build_new_configs(
        table_pattern=regex_pattern
    )
    print("New configurations created: {}".format(len(created_configs)))
    return created_configs  
      
config_builder = ConfigBuilder(
        bigquery_project=bq_project_id,
        bigquery_dataset=bq_dataset_id,
        bigquery_config_table_name=bq_config_table,
        bigquery_config_schema_yaml=config_schema,
        template_config_path=template_config_schema,
        terra_source_project=source_project,
        terra_source_workspace=source_workspace
    )

new_configurations = []
# search for new tables that match the regex patterns: WGSDST_YYYYMMDD_[XX] or WGSDST_YYYY-MM-DD_[XX]
for pattern in [r"^WGSDST_\d{4}\d{2}\d{2}_[A-Z]{2}$", r"^WGSDST_\d{4}-\d{2}-\d{2}_[A-Z]{2}$"]:
    created_configs = find_tables_in_workspace(config_builder, pattern, logger)
    if created_configs:
        new_configurations.extend(created_configs)

# read data from the new configurations will be uploaded to the WGS_combined table in the SOURCE workspace -- special request for this case study
for config in new_configurations:
    entity_id = "entity:{}_id".format(config['entity_type'])

    # create a Terra object for handling data transfer
    terra = Terra(source_project=source_project, source_workspace=source_workspace)
    downloaded_data = terra.entities.download_table(entity_name, attributes=[entity_id, 'read1', 'read2'])

    if len(downloaded_data) > 0:
        downloaded_data['upload_date'] = today_date # indicate the date of upload
        terra.entities.upload_entities(data=downloaded_data, target="WGSDST_combined", entity_identifier_column=entity_id)

terra2bq = Terra2BQ(
        bigquery_project=bq_project_id,
        bigquery_dataset=bq_dataset_id,
        samples_table=bq_sample_table,
        configs_table=bq_config_table,
        samples_schema_yaml=sample_schema,
        configs_schema_yaml=config_schema,
        metadata_cleanup_fn=filter_samples,
    )

print("Processing all configurations")
processed_result = terra2bq.process_all_configs(batch_size=3, destination_bucket=terra_bucket, skip_transferred=True)
```
