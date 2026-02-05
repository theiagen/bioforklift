# bioforklift Command-Line Interface
The command-line interface comprises several subcommands, each with accessible help menus via `-h/--help`:

1. **configure**: Configure commonly referenced metadata
2. **download**: Download Terra entities
3. **upload**: Upload entities to Terra
4. **launch**: Launch workflow(s)

<br>

## Terra
### Configuration
The `configure` subcommand stores default values for commonly used metadata in a YAML file. These include the workflow repository, branch, project/workspace name, and call_cache/ignore_empty_outputs execution parameters.

Executing the `configure` subcommand write the configuration to `$HOME/.config/bioforklift.cfg`. Command-line arguments executed as part of other subcommands take precedence when they conflict with configuration.

e.g.: Configure a commonly used workspace with call-caching on a dev-branch:

```bash
bioforklift configure \
  -ws <WORKSPACE> \
  -p <PROJECT> \
  -b <BRANCH>
  -cc 
```

<br>

### Downloading and Uploading data
The `download` and `upload` subcommands download and upload Terra tables. These subcommands take a space-delimited list of inputs.

e.g. Download a table from Terra with `bioforklift` pre-configured:

```bash
bioforklift download <TABLE_NAME>
```

e.g. Upload a table from Terra with `bioforklift` pre-configured:
```bash
bioforklift upload \
  <INPUT_TABLE> \
  -t <TERRA_TABLE_NAME> \
  --overwrite # overwrite existing table
```

<br>

### Launching workflows
The `launch` subcommand will execute workflows. 

Command-line arguments take precedence over JSON (`--job_json`) workflow values.

e.g. Launch a workflow with command-line arguments (`-i/-o` are formatted in accord with JSONs downloaded from the Terra workflow):

```bash
bioforklift launch \
  -wf <TERRA_WF_NAME> \
  -t <TERRA_TABLE_NAME> \
  -i <INPUTS_JSON> \
  -o <OUTPUTS_JSON>
```

#### Workflow JSON

A workflow JSON can be provided as input with multiple workflows specified. Redundant execution commands are preferentially chosen based on the following hierarchy: command-line > JSON > bioforklift configuration.

A simple example workflow job JSON (please note workspace, project, branch, and repository are required inputs that can be specified in the backend via `bioforklift configure`):

```json
{
    <LOCAL_WF_NAME_1>: {
        "workflow_name": <TERRA_WF_NAME>,
        "table": <TERRA_TABLE>,
        "comment": <EXECUTION_COMMENT>,
        "input_json": <INPUTS_JSON>,
        "output_json": <OUTPUTS_JSON>
    },
    ...
    <LOCAL_WF_NAME_n>: {..}
}
```

e.g. Launch a job from a JSON with `bioforklift` pre-configured:

```bash
bioforklift launch -j <JOB_JSON>
```