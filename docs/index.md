# Forklift

**Forklift** is a Python library meant for seamlessly integrating data transfer between Biguery and Terra bioinformatics platform. Our goal is to simplify data automation for large scale sample processing worklfows for pathogen detection. 

<div style="text-align: center;">
  <img src="assets/forklift_py.png" alt="Forklift.py" width="450" height="450" style="border-radius: 15px;">
</div>


## Overview

Forklift provides a comprehensive solution for managing the flow of genomic sequening data and metadata between Terra workspaces and BigQuery databases. It offers a set of tools to:

- Download data from Terra to BigQuery
- Upload data from BigQuery to Terra
- Submit and monitor Terra workflows
- Synchronize metadata between platforms
- Generate alerts and reports

## Key Features

- **Bidirectional Integration**: Move data seamlessly between Terra and BigQuery
- **Workflow Management**: Submit, track, and monitor Terra workflows
- **Metadata Synchronization**: Keep your metadata in sync across workspaces and datatables
- **Configurable Operations**: Use YAML-based configuration for flexible setup
- **Alerting System**: Get notifications about workflow status through Slack

## Modules

They key modules for Forkflift include the following:

- **Terra2BQ**: Integration layer that combines BigQuery and Terra operations
- **BigQuery**: Interface with Google BigQuery for data storage and retrieval, generalizing common retrieval patterns
- **Terra**: Connect to Terra for bioinformatics workflow execution
- **Alerting**: Send notifications and reports to Slack

The goal is to make sure we can expand and integrate other data stores or alerting systems as needed to have a complete ecosystem for large scale bioinformatics data flows. 

## Getting Started

See the [Getting Started](getting_started.md) guide to begin using Forklift.


## License
GNU GENERAL PUBLIC LICENSE