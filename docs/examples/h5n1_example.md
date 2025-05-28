# Case Study: H5N1 USDA Dashboard Automation

This page describes how Sage automated scraping an NCBI BioProject for SRA data and checking relevant GenBank and BioSample records for metadata using bioforklift.

Theiagen organization members can see the full code in the cdph-automations _private_ GitHub repository.

The code is organized into three main types of functions:

1. miscellaneous functions to cleanse metadata, like turning dates into isoformat and various standardizations. These will not be described here, but you can see them in the code.
2. functions that interact with NCBI to scrape the BioProjects of interest.
3. the `main` function that uses bioforklift (and all the other functions)

## Scraping NCBI

Although the primary purpose of this page is to describe the bioforklift implementation, the NCBI scraping process is useful to understand.

The `requests` library is used to interact with NCBI using URL requests.

```python
import requests

def enable_retries():
    """
    This function creates a requests session with retries enabled 
    in case of connection errors and server-side errors.
    """

    session = requests.Session()
    retry = requests.adapters.Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504]) # retry on these status codes
    
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    session.timeout = 30
    return session
```

This implementation is fairly standard, and if you have questions I'd recommend you check out the requests documentation instead of asking me. 

### Finding SRA records from a bioproject

SRA records have the public-facing SRR#### IDs, but are internally indexed with UUIDs. The UUIDs are what is returned when searching BioProjects with entrez eutils.

```python
import requests

def find_records(start, batch_size, project, api_key):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=sra&term={}&retstart={}&retmax={}&api_key={}".format(project, start, batch_size, api_key)
    try:
        session = enable_retries()
        response = session.get(url)
        response.raise_for_status() # raise exceptions if request fails
        result = response.text
        
        pattern = r'<Id>(\d+)</Id>'
        ids = re.findall(pattern, result)
        return ids
    except requests.exceptions.RequestException as e:
        logger.error("Error executing request: {}".format(e))
        return []
```

This function returns a list of SRA UUIDs. The `start` and `batch_size` parameters are used to paginate through the results. The `project` parameter is the BioProject ID, and the `api_key` is your NCBI API key.

After UUIDs are found, the next step is to get the SRR#### and BioSample IDs. This is done by using the UUIDs to query the SRA database.

```python
import requests

def fetch_records(sra_id, api_key):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=sra&id={}&rettype=runinfo&retmode=text&api_key={}".format(sra_id, api_key)
    
    try:
        session = enable_retries()
        response = session.get(url)
        response.raise_for_status()
        result = response.text # CSV format
        
        lines = result.strip().split('\n')
        try:
            second_line = lines[1].split(',')
            accession = second_line[0] # return the first column of the second line -- this is the SRR ID
            biosample = second_line[25] # return the 25th column of the second line -- this is the biosample ID
            return (accession, biosample)
        except:
            return (None, None)
    
    except requests.exceptions.RequestException as e:
        logger.error("Error fetching record for SRA ID {}: {}".format(sra_id, e))
        return (None, None)
```

This function takes a UUID and returns the SRR#### ID and BioSample ID. The `rettype` parameter in the URL is set to `runinfo`, which returns the data in CSV format. The `retmode` parameter in the URL is set to `text`, which returns the data as plain text.

### Downloading SRA read data

SRA read data is then downloaded for the identified SRR#### ID. This is done as follows:

```python
import subprocess
import shutil 

def run_shell_command(cmd, check=True):
    """Run a shell command with proper exception handling."""
    try:
        result = subprocess.run(cmd, check=check, shell=True, text=True, 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print("Command ({}) failed with error: {}".format(cmd, e.stderr))
        if check:
            raise
        return None

def download_srr_reads(accession, output_directory, bioproject)::
    run_shell_command("prefetch {}".format(accession))
    run_shell_command("fasterq-dump '{}' --outdir {}/{}".format(accession, output_directory, project))
    shutil.rmtree(accession)
```

This command uses the `prefetch` and `fasterq-dump` commands from the SRA Toolkit to download the data. The `prefetch` command downloads the data, and the `fasterq-dump` command converts it to FASTQ format. The `shutil.rmtree` command is used to delete the downloaded prefetch files after they have been processed to save space. Commands are run through the `subprocess` library.

### Extracting BioSample metadata

Using the previously identified BioSample ID, we can extract metadata from the BioSample database. This is done using the `efetch` command from the NCBI API.

```python
import xml.etree.ElementTree as ET
import requests

def fetch_biosample(biosample_accession, api_key):
  url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=biosample&id={}&retmode=xml&api_key={}".format(biosample_accession, api_key)
    
    try:
        session = enable_retries()
        response = session.get(url)
        response.raise_for_status()
        result = response.text
        
        xml = ET.fromstring(result)
        
        biosample_dictionary = {}
        for attribute in xml.findall(".//Attribute"):
            attribute_name = attribute.get("attribute_name")
            if attribute_name in LIST_OF_DESIRED_METADATA_FIELDS:
                biosample_dictionary[attribute_name] = attribute.text
        
        return biosample_dictionary
    except requests.exceptions.RequestException as e:
        return {}
```

This function returns a dictionary of BioSample metadata. The `LIST_OF_DESIRED_METADATA_FIELDS` variable is a list of the metadata fields that you want to extract from the BioSample record. The `biosample_accession` parameter is the BioSample ID, and the `api_key` is your NCBI API key.

### Parsing GenBank metadata

Extracting GenBank metadata rqeuires two steps: first, we need to get the GenBank ID from the BioSample ID, and then we can extract the metadata from the GenBank record.

```python
import requests
import json

def fetch_genbank(biosample_accession, api_key):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nuccore&term={}&api_key={}".format(biosample_accession, api_key)
    metadata_dictionary = {}
    
    try:
        session = enable_retries()
        response = session.get(url)
        response.raise_for_status()
        result = response.text # CSV format
        
        pattern = r'<Id>(\d+)</Id>'
        ids = re.findall(pattern, result)
        # find the metadata for the first ID in the list; sometimes there are multiple IDs
        metadata_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=nuccore&id={}&retmode=json&api_key={}".format(','.join(ids), api_key)
        response = session.get(metadata_url)
        response.raise_for_status()
        metadata = response.text # JSON format
        
        json_data = json.loads(metadata)

        list_for_field_of_interest = []
        for uid in ids:
            list_for_field_of_interest.append(json_data['result'][uid][FIELD_OF_INTEREST])
    
        metadata_dictionary[FIELD_OF_INTEREST] = list_for_field_of_interest

        return metadata_dictionary
    except requests.exceptions.RequestException as e:
        return None
```

This function takes a BioSample ID and returns a dictionary of GenBank metadata. The `FIELD_OF_INTEREST` variable is the metadata field that you want to extract from the GenBank record. The `biosample_accession` parameter is the BioSample ID, and the `api_key` is your NCBI API key. In this use case, multiple GenBank IDs are returned, so the function parses the field of interest for each ID and returns a list of the values and adds that to a dictionary. In different scenarios, the list approach would be unsuitable.

## bioforklift implementation

First, Terra2BQ is initialized.

```python
from bioforklift.terra2bq import Terra2BQ

terra2bq = Terra2BQ(bigquery_project=bq_project_id, 
                    bigquery_dataset=bq_dataset_id,
                    samples_table=bq_sample_table,
                    configs_table=bq_config_table,
                    samples_schema_yaml=sample_schema,
                    configs_schema_yaml=config_schema,
                    destination_workspace=terra_workspace,
                    destination_project=terra_project,
                    destination_datatable=terra_terra
                    )
```

### Updating workflow metadata

Before any processing occurs, the script will update the workflow statuses for any previously processed workflows from either the previous day, or if it is Monday, the prior three days (to account for the weekend). This is done to ensure that the workflow statuses are up to date before processing any new workflows.

```python
# if the day is Monday, the days_back is set to 3, otherwise it is set to 1
workflow_status = terra2bq.update_workflow_status(days_back=1, batch_size=100, update_bigquery=True)
sync_status = terra2bq.sync_metadata(days_back=1, update_bigquery=True, update_destination=True)

print("Metadata: {} records were updated in BigQuery, and {} entities were updated in Terra".format(sync_status["bq_updated_count"], sync_status["destination_updated_count"]))
print("Workflow Status: {} records were updated in BigQuery".format(workflow_status["updated_count"]))
```

### Determine which samples need to be processed

In order to determine which samples to process from the BioProjects, I extract the SRR UIDs from BigQuery.

```python
bq = BigQuery(project=bq_project_id, dataset=bq_dataset_id)
bq_sample_ops = bq.get_sample_operations(table_name=bq_sample_table, sample_schema_yaml=sample_schema)
try:
    processed_srrs_df = bq_sample_ops.query_samples(fields=['srr_uid'], conditions=["srr_uid IS NOT NULL"]) # returns dataframe with all srr_uid
    if len(processed_srrs_df) > 0:
        processed_srr_ids = processed_srrs_df['srr_uid'].tolist()
    else:
        processed_srr_ids = []
except:
    processed_srr_ids = []
```

### Scrape NCBI and update Terra

Then, the script with iterate through the BioProjects of interest and use the `find_records` function to identify all SRA UUIDs associated with the BioProject. The two lists of SRR UUIDs are the compared to identify any which have not been processed. If so, the script will process the SRR UUIDs in a `process_srr_id` function by:

1. identifying the SRR#### ID and the BioSample ID using the `fetch_records` function
2. downloading the SRA read data using the `download_srr_reads` function
3. extracting the BioSample metadata using the `fetch_biosample` function

The final return value of the `process_srr_id` function is a dictionary containing the metadata, read data, and identifiers for the SRR UUID. After the `process_srr_id` function is run on all unprocessed SRR UUIDs, the dictionaries for all the SRR UUIDs are added to a single `pandas.DataFrame`.

The final DataFrame is then uploaded to Terra.

```python
terra = Terra(source_workspace=terra_workspace,
                source_project=terra_project)
terra.entities.upload_entities(data=new_table, target="h5n1_specimen", entity_identifier_column="accession")
```

### Process all new samples

The `upload_entities` function will automatically create a new table in the target workspace if it does not already exist. The `entity_identifier_column` parameter is used to specify the column that contains the unique identifiers for the entities -- that is, what column in the pd.DataFrame provided to the `data` input variable that will fill the `entity:<target>_id` column in Terra.

After the upload is complete, the script will then run the `terra2bq.process_all_configs()` function to process all samples that were just added using the associated configuration in the BigQuery configs table. This will (a) launch the associated Terra workflow, (b) update the BigQuery configs table with the new workflow ID, and (c) update the BigQuery samples table with the new sample IDs and any relevant fields.

```python
terra2bq.process_all_configs()
```

### Checking for GenBank metadata updates

If the day of the week is Monday, Wednesday, or Friday, the script will also search for updates to the metadata in GenBank. 

First, several fields are extracted from BigQuery to help with this process.

```python
biosample_accessions = bq_sample_ops.query_samples(fields=['h5n1_id', 'biosample_accession', 'genbank_last_update_date', 'genbank_last_checked_date'], 
                                                conditions=["biosample_accession IS NOT NULL"]) # returns dataframe with all biosample_accession
```

For any samples that were not checked (with the `genbank_last_checked_date` field) in the last seven days, the script will call the `fetch_genbank` function to extract the metadata from GenBank. The script will then update the BigQuery samples table with the new metadata and update the `genbank_last_checked_date` field to the current date.

```python
terra.entities.upload_entities(data=additional_metadata, target="h5n1_specimen", entity_identifier_column="h5n1_id")
terra2bq.sync_metadata(days_back=1, update_bigquery=True, update_destination=False)
```

In this scenario, the `entity_identifier_column` is the `h5n1_id` column, which is the unique identifier for the samples in the BigQuery samples table. This field has a column_mapping that connects it to the `entity:h5n1_specimen_id` column in the Terra table. The `sync_metadata` function will then update the BigQuery samples table with the new metadata and update the `genbank_last_checked_date` field to the current date as well.

I am still not sure if the sync_metadata function is the most appropriate here. I will probably let you know soon.
