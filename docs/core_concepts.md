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

### Terra2BQ

The Terra2BQ integration layer:

- Coordinates data flow between Terra and BigQuery
- Manages configurations for different data processing pipelines
- Tracks workflow status and metadata

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

### Adding Data to BigQuery

Terra Data Table → Terra Entities → BigQuery Sample Operations → BigQuery Table

### Data Upload and Workflow Submission

BigQuery Table → BigQuery Sample Operations → Terra Entities → Terra Submission → Terra Workflow

### Updating Workflow Status

Terra Submissions → Terra Workflow Status → BigQuery Sample Updates

### Synchronizing Metadata

Terra Data → BigQuery Updates → Terra Destination Updates
