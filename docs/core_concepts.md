# Core Concepts

## System Architecture

bioforklift consists of three main components:

1. **BigQuery Interface**: Interacts with Google BigQuery and controls Sample and Config Operations
2. **Terra Interface**: Interacts with Terra bioinformatics platform, specifically Entity and Submission methods
3. **Terra2BQ Integration Layer**: Coordinates operations between BigQuery and Terra for common automation pipelines

![bioforklift Architecture Diagram](assets/Forklift_Base_Architecture.png)

## Key Components

### BigQuery

The BigQuery module provides classes for:

- **BigQueryClient**: Base client for BigQuery operations
- **BigQuerySampleOperations**: Operations for sample data tables
- **BigQueryConfigOperations**: Operations for configuration data tables

### Terra

The Terra module provides classes for:

- **TerraClient**: Base client for Terra API interactions
- **TerraEntities**: Operations for Terra data entities
- **TerraSubmissions**: Operations for Terra workflow submissions
- **TerraToTerraTransfer**: Transfer samples between Terra workspaces with deduplication

### BaseSpace

The BaseSpace module provides classes for:

- **BaseSpaceClient**: Base client for BaseSpace API interactions
- **BaseSpaceEndpoints**: Typed wrappers over the BaseSpace v2 REST endpoints
- **BaseSpaceMethods**: Collection resolution, dataset discovery, and FASTQ download/concatenation

### Data Processing

The Data Processing module provides classes for:

- **SampleDataProcessor**: Processes sample metadata DataFrames with schema-based validation
- **ConfigProcessor**: Processes configuration data for BigQuery insertion
- **Schema Models**: Typed models for field attributes and schema definitions (FieldAttributes, SampleFieldAttributes, ConfigFieldAttributes, FieldDefinition, SchemaDefinition)
- **Schema Converters**: Functions for converting between schema formats and types

### Terra2BQ

The Terra2BQ integration layer:

- Coordinates data flow between Terra and BigQuery
- Manages configurations for different data processing pipelines
- Tracks workflow status and metadata
- Uses data processing classes for validation and transformation

### Alerting

The Alerting module:

- Sends notifications to Slack
- Generates summary reports for operations
- Monitors workflow status

## Key Concepts

### Configurations

Configurations in bioforklift define how data should be processed. Each configuration includes:

- Source and destination Terra workspace and project
- Entity types for Terra tables
- Workflow method configuration
- Status tracking fields

Configurations are stored in BigQuery and drive the automated processing.

### Sample Data

Sample data represents genomic samples and their metadata. In bioforklift:

- Samples are downloaded from Terra to BigQuery
- Sample metadata is tracked and updated
- Samples are grouped into sets for processing
- Workflow results update sample status

### Entity Sets

Entity sets in Terra group samples for workflow processing:

- Sets are created when samples are uploaded to Terra
- Sets are named based on configuration prefix and timestamp
- Sets are submitted to Terra workflows
- Set membership is tracked in BigQuery

### Time-based Operations

bioforklift operations are often time-based:

- Daily processing of new samples
- Hourly status updates
- Lookback periods for synchronization of metadata fields (where `sync_field` is `true`)

## Common Data Flows

These are high-level data flows that are available in bioforklift:

### Adding Data to BigQuery with Processing

Terra Data Table → Terra Entities → **SampleDataProcessor** → BigQuery Sample Operations → BigQuery Table

**Data Processing Steps:**
1. **Schema Validation**: Fields validated against schema patterns and requirements
2. **Field Mapping**: Terra column names mapped to BigQuery schema fields
3. **Type Coercion**: Data types converted to match BigQuery schema
4. **System Values**: UUIDs and timestamps automatically generated
5. **Deduplication**: Existing samples filtered out based on identifiers

### Downloading Sequencing Data from BaseSpace

BaseSpace Project/Run → **resolve_collection_id** → Datasets → Dataset Files → Local FASTQ → **Concatenated `{sample}_R1/_R2.fastq.gz`**

**Processing Steps:**
1. **Collection Resolution**: A run experiment name or project name is resolved to exactly one BaseSpace collection. Both scopes are searched, and a `priority` selects one when a run and a project share the name
2. **Dataset Filtering**: Datasets are filtered by type (`common.fastq`, including conforming variants)
3. **Sample Matching**: Each requested sample name resolves to an exact dataset, or to its `_L###` lane siblings
4. **Validation**: Datasets are checked for the paired-end flag and balanced R1/R2 files before any transfer
5. **Download**: Files stream to disk atomically and are size-verified against the API's reported `Size`
6. **Concatenation**: Per-lane files merge into one R1/R2 pair per sample, in matching lane order

### Configuration Processing

Configuration Files/Data → **ConfigProcessor** → BigQuery Config Operations → BigQuery Table

**Processing Steps:**
1. **JSON Serialization**: Complex objects serialized for BigQuery storage
2. **System Values**: Primary keys and timestamps generated
3. **Validation**: Required fields and data types validated

### Data Upload and Workflow Submission

BigQuery Table → BigQuery Sample Operations → **Data Processing** → Terra Entities → Terra Submission → Terra Workflow

**Processing Steps:**
1. **System Column Removal**: Auto-generated fields excluded from Terra upload
2. **Field Mapping**: BigQuery fields mapped back to Terra column names
3. **Type Conversion**: Data prepared for Terra API format

### Updating Workflow Status

Terra Submissions → Terra Workflow Status → **Type Coercion** → BigQuery Sample Updates

### Synchronizing Metadata

Terra Data → **SampleDataProcessor** → BigQuery Updates → **Data Processing** → Terra Destination Updates

**Sync Processing:**
1. **Field Filtering**: Only `sync_field` marked fields synchronized
2. **Date Formatting**: Dates validated and formatted consistently
3. **Bidirectional Updates**: Changes propagated to both BigQuery and Terra

### Terra-to-Terra Data Promotion

Source Terra Workspace → **TerraToTerraTransfer** → Destination Terra Workspace → **Terra2BQ** → BigQuery

This flow supports "data promotion" workflows where analyzed samples move from a working workspace to a production workspace:

1. **Deduplication**: Only new samples (not already in destination) are transferred
2. **Schema-less Transfer**: All columns from source are preserved in destination
3. **BigQuery Sync**: Transferred samples can then be synced to BigQuery with a curated schema

```python
from bioforklift.terra import TerraToTerraTransfer, TerraClient, TransferStatus
from bioforklift.terra2bq import Terra2BQ

# Step 1: Create client and transfer to destination workspace
client = TerraClient(
    source_workspace="analysis-workspace",
    source_project="source-billing-project",
    destination_workspace="production-workspace",
    destination_project="dest-billing-project",
)
transfer = TerraToTerraTransfer(
    client=client,
    source_table_name="analyzed_sample",
    destination_table_name="sample",
)  # identifier columns default to {table_name}_id
result = transfer.transfer()

# Step 2: Sync to BigQuery
if result.status == TransferStatus.SUCCESS:
    terra2bq = Terra2BQ(...)
    terra2bq.download_from_terra_to_bigquery()
```
