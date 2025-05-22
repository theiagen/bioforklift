from bioforklift.terra2bq import Terra2BQ
from bioforklift.bigquery import BigQuery
from bioforklift.terra import Terra
from pathlib import Path
from google.cloud import bigquery

terra2bq = Terra2BQ(bigquery_project="h5n1-looker", 
                    bigquery_dataset="h5n1_data",
                    samples_schema_yaml="data/samples.yaml",
                    configs_schema_yaml="data/config.yaml",
                    destination_workspace="dataAnalysis_VRDL_H5N1_USDA",
                    destination_project="cdph-terrabio-taborda-manual",
                    destination_datatable="h5n1_specimen"
                    )




sync_status = terra2bq.sync_metadata(days_back=1, update_bigquery=True, update_destination=True, batch_size=300)