# Core Concepts

Here we will cover core concepts that drive the architecture and development of Forklift, a domain specific library for data automations

## System Architecture

Forklift consists of three main components:

1. **BigQuery Interface**: Interacts with Google BigQuery and controls Sample and Config Operations
2. **Terra Interface**: Interacts with Terra bioinformatics platform, specifically Entity and Submission methods
3. **Terra2BQ Integration Layer**: Coordinates operations between BigQuery and Terra for common automation pipelines

![Forklift Architecture Diagram](assets/Forklift_Base_Architecture.png)

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

## Core Workflows

### 1. Data Download Flow

```
Terra Data Table → Terra Entities → BigQuery Sample Operations → BigQuery Table
```

### 2. Data Upload and Workflow Submission Flow

```
BigQuery Table → BigQuery Sample Operations → Terra Entities → Terra Submission → Terra Workflow
```

### 3. Workflow Status Tracking Flow

```
Terra Submissions → Terra Workflow Status → BigQuery Sample Updates
```

### 4. Metadata Synchronization Flow

```
Terra Data → BigQuery Updates → Terra Destination Updates
```

## Key Concepts

### Configurations

Configurations in Forklift define how data should be processed. Each configuration includes:

- Source and destination Terra workspace and project
- Entity types for Terra tables
- Workflow method configuration
- Status tracking fields

Configurations are stored in BigQuery and drive the automated processing.

### Sample Data

Sample data represents genomic samples and their metadata. In Forklift:

- Samples are downloaded from Terra to BigQuery
- Sample metadata is tracked and updated
- Samples are grouped into sets for processing
- Workflow results update sample status

### Schema Definitions

Schema definitions in YAML format define:

- Field names, types, and attributes
- System-generated fields
- Field relationships and mappings
- Special handling instructions

Schemas are used to create and interact with BigQuery tables.

### Entity Sets

Entity sets in Terra group samples for workflow processing:

- Sets are created when samples are uploaded to Terra
- Sets are named based on configuration prefix and timestamp
- Sets are submitted to Terra workflows
- Set membership is tracked in BigQuery

### Time-based Operations

Forklift operations are often time-based:

- Daily processing of new samples
- Hourly status updates
- Lookback periods for synchronization of metadata fields
- Time-tracking for all operations

## Configuration Attributes

Special field attributes in schema definitions control behavior:

- `primary_key`: Indicates primary key fields
- `system_value`: Fields managed by the system
- `sample_identifier`: Field that identifies sample entities
- `config_identifier`: Field that links samples to configurations
- `sequence_file`: Fields containing sequence file paths
- `sync_field`: Fields to synchronize between Terra and BigQuery
- `column_mappings`: Map between Terra and BigQuery field names
- `inherit_from_config`: Fields that inherit values from configuration

[forkliftArchitectureDiagram]: ../assets/diagrams/Forklift_Base_Architecture.png