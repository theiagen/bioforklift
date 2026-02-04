# Bioforklift Command-Line Interface

## Terra
### Configuration
The `configure` subcommand stores default values for commonly used metadata in a YAML file. These include the workflow repository, branch, project/workspace name, and call_cache/ignore_empty_outputs execution parameters.

Executing the configure subcommand will overwrite the existing configuration, which is by default located at `$HOME/.config/bioforklift.cfg`. 

Command-line arguments take precedence when they conflict with configuration.

### Downloading and Uploading data
The `download` and `upload` subcommands download and upload Terra tables.

### Launching workflows
The `launch` subcommand will execute workflows.

Command-line arguments take precedence over JSON input values.