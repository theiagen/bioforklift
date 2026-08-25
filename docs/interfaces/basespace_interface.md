# BaseSpace Classes, Methods, and Usage

## Module: `bioforklift.basespace`

Access these classes and operations using `from bioforklift.basespace import BaseSpace` as your import statement.

This module enables programmatic access to Illumina BaseSpace Sequence Hub's v2 REST API, allowing you to find sequencing data by project or run and pull FASTQ files down to local disk. It enables you to:

1. **Resolve Collections**: Turn a project/run ID or name into a single, unambiguous BaseSpace resource.
2. **Discover Datasets**: List every dataset under a project or run, and every file within a dataset.
3. **Download FASTQ Files**: Stream per-lane FASTQ files to disk with integrity verification.
4. **Concatenate Reads**: Merge per-lane files into clean `{sample}_R1.fastq.gz` / `{sample}_R2.fastq.gz` outputs.
5. **Survey Available Data**: Write CSV sample sheets describing what is available before committing to a download.

### Classes

- [BaseSpace](#class-basespace)
- [BaseSpaceClient](#class-basespaceclient)
- [BaseSpaceEndpoints](#class-basespaceendpoints)
- [BaseSpaceMethods](#class-basespacemethods)
- [RunItem](#class-runitem)
- [ProjectItem](#class-projectitem)
- [OtherItem](#class-otheritem)
- [SearchItem](#class-searchitem)
- [DatasetItem](#class-datasetitem)
- [DatasetType](#class-datasettype)
- [CommonFastqAttributes](#class-commonfastqattributes)
- [DatasetFileItem](#class-datasetfileitem)
- [Paging](#class-paging)
- [PagingResponse](#class-pagingresponse)
- [BaseSpaceResponse](#class-basespaceresponse)

### Module-level Functions

- [`fetch_all_items`](#fetch_all_items)
- [`stream_to_disk`](#stream_to_disk)
- [`concatenate_files`](#concatenate_files)
- [`read1_files` / `read2_files`](#read1_files-read2_files)
- [`filter_dataset_types`](#filter_dataset_types)
- [`match_datasets_by_sample`](#match_datasets_by_sample)
- [`validate_paired_end_datasets`](#validate_paired_end_datasets)
- [`concatenate_dataset_files`](#concatenate_dataset_files)
- [`write_dataset_sample_sheet`](#write_dataset_sample_sheet)

### Exception Classes

- [BaseSpaceError](#class-basespaceerror)
- [BaseSpaceConnectionError](#class-basespaceconnectionerror)
- [BaseSpaceTimeoutError](#class-basespacetimeouterror)
- [BaseSpaceInvalidResponseError](#class-basespaceinvalidresponseerror)
- [BaseSpaceCollectionIdError](#class-basespacecollectioniderror)
- [BaseSpaceDatasetError](#class-basespacedataseterror)
- [BaseSpaceMissingReadError](#class-basespacemissingreaderror)
- [BaseSpaceDownloadError](#class-basespacedownloaderror)
- [BaseSpaceAPIError](#class-basespaceapierror)
- [BaseSpaceBadRequestError](#class-basespacebadrequesterror)
- [BaseSpaceAuthenticationError](#class-basespaceauthenticationerror)
- [BaseSpaceForbiddenError](#class-basespaceforbiddenerror)
- [BaseSpaceNotFoundError](#class-basespacenotfounderror)
- [BaseSpaceServerError](#class-basespaceservererror)

---

## Important Notes

!!! info "Authentication"
    BaseSpace authentication does **not** use Google credentials, so the [Authentication](../index.md#authentication) section on the Home page does not apply to this module.

    Instead, BaseSpace uses a single **access token string**, passed as the first argument to `BaseSpace` (or `BaseSpaceClient`). It is sent on every request as the `x-access-token` header.

!!! info "Collections: projects vs. runs"
    A "collection" is either a BaseSpace **project** or a **run**. Both can hold datasets, and both are accepted anywhere a `collection_id` is expected — you can pass an ID *or* a name.

    The BaseSpace UI labels these fields differently than the API does, which is the most common source of confusion:

    - `run.Name` refers to `Run ID` in the BaseSpace UI
    - `run.ExperimentName` refers to `Run Name` in the BaseSpace UI
    - `run.Id` refers to the numerical ID found in the BaseSpace HTTP URL (e.g. `https://basespace.illumina.com/run/315086826/details`)
    - `project.Name` refers to the name under the Projects tab in the BaseSpace UI
    - `project.Id` refers to the numerical ID found in the BaseSpace HTTP URL (e.g. `https://basespace.illumina.com/projects/489069003/about`)

    The numerical ID from the URL is always the safest input, since names are not guaranteed to be unique.

!!! info "Download layout and disk space"
    Downloads land **flat** in `dest_dir` as `dest_dir / <original file name>` — there is no per-sample subdirectory. If two requested samples contain identically named files, they will collide at the same path. Use a separate `dest_dir` per collection if that is a risk.

    Concatenated outputs are written to the same directory as their sources. Because sources are only deleted *after* the merged output has been size-verified, plan for roughly **2× the final size** in peak disk usage when `remove_sources=True`.

---

## Class: `BaseSpace`

This class is the main interface for BaseSpace operations. It wires up the HTTP client, endpoints, and methods so that callers can reach the BaseSpace API through a single object. This is the main class you will use to interact with BaseSpace.

The most commonly used methods are found on [BaseSpaceMethods](#class-basespacemethods), reached as `basespace.methods.<method_name>(<parameters>)`. The two highest-level operations, [`fetch_sample_fastqs`](#fetch_sample_fastqs) and [`build_sample_sheet`](#build_sample_sheet), are also bound directly onto `BaseSpace` for convenience.

### Constructor

```python
BaseSpace(
    access_token: str,
    basespace_api_url: str = "https://api.basespace.illumina.com",
    basespace_api_version: str = "v2",
    max_retries: int = 3
)
```

#### Parameters

- **access_token** (str): The access token for authenticating with the BaseSpace API
- **basespace_api_url** (str): The base URL for the BaseSpace API (change only for non-US regions)
- **basespace_api_version** (str): The version of the BaseSpace API to use (do not change unless you know what you are doing)
- **max_retries** (int): Maximum number of automatic retries for transient failures

#### Example Construction

```python
import os
from bioforklift.basespace import BaseSpace

basespace = BaseSpace(
    access_token=os.environ["BASESPACE_ACCESS_TOKEN"]
)
```

### Properties

- **client** ([BaseSpaceClient](#class-basespaceclient)): The HTTP client handling authentication, retries, and error mapping
- **endpoints** ([BaseSpaceEndpoints](#class-basespaceendpoints)): Typed wrappers over the BaseSpace v2 REST endpoints
- **methods** ([BaseSpaceMethods](#class-basespacemethods)): The endpoint-backed operations you will call day to day
- **fetch_sample_fastqs**: Convenience alias bound to [`methods.fetch_sample_fastqs`](#fetch_sample_fastqs)
- **build_sample_sheet**: Convenience alias bound to [`methods.build_sample_sheet`](#build_sample_sheet)

### Methods

#### `from_client`

Creates a `BaseSpace` instance from an existing [BaseSpaceClient](#class-basespaceclient). Use this when you have already configured a client (custom API URL, custom retry count) and want to reuse it rather than have `BaseSpace` build a second one.

```python
from_client(
    client: BaseSpaceClient
) -> "BaseSpace"
```

---

## Class: `BaseSpaceClient`

The HTTP transport layer for BaseSpace. It attaches the `x-access-token` header, builds versioned URLs, applies the retry policy, and translates HTTP failures into the module's [exception classes](#exception-classes).

!!! tip "Advanced Topics"
    **This class is used internally** by the [BaseSpace](#class-basespace) class, which creates one for you. However, it is available for advanced users who need to configure transport behavior or share a single session across multiple `BaseSpace` instances via [`from_client`](#from_client).

### Constructor

```python
BaseSpaceClient(
    access_token: str,
    basespace_api_url: str = "https://api.basespace.illumina.com",
    basespace_api_version: str = "v2",
    max_retries: int = 3
)
```

#### Parameters

- **access_token** (str): The access token for authenticating with the BaseSpace API
- **basespace_api_url** (str): The base URL for the BaseSpace API (trailing slashes are stripped)
- **basespace_api_version** (str): The version of the BaseSpace API to use
- **max_retries** (int): Maximum number of automatic retries for transient failures

### Properties

- **access_token** (str): The token sent as the `x-access-token` header
- **base_url** (str): The API base URL, with any trailing slash removed
- **api_version** (str): The API version segment inserted into every request path
- **session** (requests.Session): The underlying session, with the retry policy mounted on both `http://` and `https://`

!!! info "Retry and timeout behavior"
    The retry policy is deliberately narrow: only **HTTP 429** (rate limited) is retried, and only for `GET` requests, with a `backoff_factor` of 0.5 and `Retry-After` honored. **5xx responses are not retried** — they surface immediately as [BaseSpaceServerError](#class-basespaceservererror) so a genuine outage or a malformed query fails fast rather than being retried three times.

    When a request does not specify a timeout, the default is `(30, 300)` — 30 seconds to connect, 300 seconds to read. The generous read timeout accommodates large FASTQ transfers.

### Methods

#### `get`

Makes a GET request to the BaseSpace API. The endpoint is a path fragment relative to the API version, e.g. `"datasets"` becomes `{base_url}/{api_version}/datasets`.

```python
get(
    endpoint: str,
    params: Optional[Dict] = None,
    timeout: Optional[tuple] = None,
    stream: bool = False
) -> requests.Response
```

---

## Class: `BaseSpaceEndpoints`

Thin, typed wrappers over the four BaseSpace v2 REST endpoints the module uses. Each method builds the query parameters, calls the client, and validates the response body into a [BaseSpaceResponse](#class-basespaceresponse).

!!! tip "Advanced Topics"
    **This class is used internally** by [BaseSpaceMethods](#class-basespacemethods), which handles pagination and orchestration for you. However, it is available for advanced users who need a single page of results, an endpoint parameter the higher-level methods do not expose, or explicit control over sort order.

!!! info "Validation errors are not BaseSpace errors"
    Every method on this class is decorated with pydantic's `@validate_call`. Passing an invalid `scope` or a wrong-typed argument raises `pydantic.ValidationError`, which is **not** a subclass of [BaseSpaceError](#class-basespaceerror). Code that catches only `BaseSpaceError` will not catch these.

### Constructor

```python
BaseSpaceEndpoints(
    client: BaseSpaceClient
)
```

#### Parameters

- **client** ([BaseSpaceClient](#class-basespaceclient)): The client used to issue requests

### Methods

#### `search`

Searches BaseSpace within a scope using a raw Lucene query clause. See the [BaseSpace search API reference](https://developer.basespace.illumina.com/docs/content/documentation/rest-api/search-api-reference#SearchQueryqueryOptions).

```python
search(
    query: str,
    scope: Literal["runs", "projects", "genomes", "samples", "appresults", "sample_files", "appresult_files", None] = None,
    paging: Optional[Paging] = None,
    **extra_params
) -> BaseSpaceResponse[SearchItem]
```

#### Parameters

- **query** (str): A raw Lucene query string, e.g. `project.Id:"489069003"` or `ExperimentName:"My Run"`. BaseSpace matches field names without case sensitivity; quote values that contain spaces
- **scope** (Literal): The scope of the search
- **paging** (Optional[[Paging](#class-paging)]): Optional paging parameters
- ****extra_params**: Any additional query params passed through to the endpoint

**Returns:**

- The parsed v2 `/search` body, with items typed as [SearchItem](#class-searchitem)

!!! info "Invalid query"
    A 500 response from this endpoint often means the query contains invalid or unescaped special characters rather than indicating a BaseSpace outage. The method logs that hint and re-raises [BaseSpaceServerError](#class-basespaceservererror).

</br>

#### `datasets`

Gets a list of datasets, optionally scoped to a project or run and filtered by type. See the [datasets API reference](https://developer.basespace.illumina.com/docs/content/documentation/rest-api/api-reference#operation--datasets-get).

```python
datasets(
    project_id: Optional[str] = None,
    input_runs: Optional[str] = None,
    dataset_types: Optional[str] = None,
    paging: Optional[Paging] = None,
    **extra_params
) -> BaseSpaceResponse[DatasetItem]
```

#### Parameters

- **project_id** (Optional[str]): Restrict to datasets in this project (accepts a comma-separated string of project IDs)
- **input_runs** (Optional[str]): Restrict to datasets produced by this run (accepts a comma-separated string of run IDs)
- **dataset_types** (Optional[str]): Restrict to these dataset types, e.g. `"common.fastq"` (accepts a comma-separated string of dataset types)
- **paging** (Optional[[Paging](#class-paging)]): Optional paging parameters
- ****extra_params**: Any additional query params passed through to the endpoint

**Returns:**

- The parsed `/datasets` body, with items typed as [DatasetItem](#class-datasetitem)

</br>

#### `dataset_files`

Gets a list of files for a given dataset. See the [dataset files API reference](https://developer.basespace.illumina.com/docs/content/documentation/rest-api/api-reference#operation--datasets--id--files-get).

```python
dataset_files(
    dataset_id: str,
    paging: Optional[Paging] = None,
    **extra_params
) -> BaseSpaceResponse[DatasetFileItem]
```

#### Parameters

- **dataset_id** (str): The `DatasetItem.id` to fetch files for
- **paging** (Optional[[Paging](#class-paging)]): Optional paging parameters
- ****extra_params**: Any additional query params passed through to the endpoint

**Returns:**

- The parsed `/datasets/{dataset_id}/files` body, with items typed as [DatasetFileItem](#class-datasetfileitem)

</br>

#### `file_content`

Gets the content of a file by its ID. See the [file content API reference](https://developer.basespace.illumina.com/docs/content/documentation/rest-api/api-reference#operation--files--id--content-get).

```python
file_content(
    file_id: str,
    stream: bool = True,
    redirect: Literal["true", "meta"] = "true"
) -> requests.Response
```

#### Parameters

- **file_id** (str): The `DatasetFileItem.id` to fetch content for
- **stream** (bool): Whether to stream the response content (True) or immediately download (False)
- **redirect** (Literal["true", "meta"]): Whether this method returns a standard 302 redirect, or a meta JSON response containing the `redirect_uri`

**Returns:**

- The raw `requests.Response`. Unlike the other endpoints, this returns the response object rather than a parsed model so the caller can stream the file bytes

---

## Class: `BaseSpaceMethods`

Contains the endpoint-backed operations for interacting with the BaseSpace API. This is where the day-to-day work happens, reached as `basespace.methods.<method_name>(<parameters>)`.

Every list-returning method on this class pages through the full result set automatically, so you always receive a complete list.

### Constructor

```python
BaseSpaceMethods(
    endpoints: BaseSpaceEndpoints
)
```

#### Parameters

- **endpoints** ([BaseSpaceEndpoints](#class-basespaceendpoints)): The endpoint wrappers used to issue requests

### Methods

#### `get_search_items`

Runs one `/search` request, paging through all results.

```python
get_search_items(
    query: str,
    scope: Optional[str] = None
) -> List[SearchItem]
```

#### Parameters

- **query** (str): A Lucene query clause, or `""` to match everything in the scope
- **scope** (Optional[str]): The search scope, e.g. `"projects"` or `"runs"`

**Returns:**

- The list of [SearchItem](#class-searchitem) objects returned by this search

</br>

#### `get_datasets`

Gets every dataset for a given project or run, paging through all results. The resolved item's type decides how it is queried: a project is passed as `project_id`, a run as `input_runs`.

```python
get_datasets(
    search_item: SearchItem
) -> List[DatasetItem]
```

#### Parameters

- **search_item** ([SearchItem](#class-searchitem)): The resolved SearchItem object (`"project"` or `"run"`)

**Returns:**

- A list of all [DatasetItem](#class-datasetitem) objects associated with the specified project or run

Passing anything other than a [RunItem](#class-runitem) or [ProjectItem](#class-projectitem) raises [BaseSpaceCollectionIdError](#class-basespacecollectioniderror).

</br>

#### `get_dataset_files`

Gets all files associated with an input [DatasetItem](#class-datasetitem).

```python
get_dataset_files(
    ds_item: DatasetItem
) -> List[DatasetFileItem]
```

#### Parameters

- **ds_item** ([DatasetItem](#class-datasetitem)): The dataset to list files for

**Returns:**

- A list of [DatasetFileItem](#class-datasetfileitem) objects

</br>

#### `get_dataset_file_content`

Opens a streaming response for a dataset file's content. The caller owns the response and is responsible for closing it — use a `with` block.

```python
get_dataset_file_content(
    ds_file: DatasetFileItem
) -> requests.Response
```

#### Parameters

- **ds_file** ([DatasetFileItem](#class-datasetfileitem)): The file to fetch

**Returns:**

- A streaming `requests.Response`

</br>

#### `download_dataset_file_content`

Streams a single dataset file to `dest_dir` under its original name. The file is written to a temporary path first and renamed into place, so an interrupted download never leaves a truncated file at the final path.

```python
download_dataset_file_content(
    ds_file: DatasetFileItem,
    dest_dir: Optional[Path] = None,
    dry_run: bool = False,
    progress: bool = True
) -> None
```

#### Parameters

- **ds_file** ([DatasetFileItem](#class-datasetfileitem)): The file to download
- **dest_dir** (Optional[Path]): Destination directory (defaults to the current working directory)
- **dry_run** (bool): If True, log what would be downloaded without fetching or writing
- **progress** (bool): If True (default), draw the tqdm progress bar on a TTY

If the API reported a `Size` for the file and the number of bytes written does not match it, [BaseSpaceDownloadError](#class-basespacedownloaderror) is raised and no file is left at the destination.

</br>

#### `resolve_collection_id`

Resolves an input `collection_id` to its BaseSpace project/run [SearchItem](#class-searchitem). A `collection_id` can be a project/run ID or a project/run name. If no resource matches, or if more than one does, the input was not specific enough to be resolved, and an error is raised.

```python
resolve_collection_id(
    collection_id: str
) -> SearchItem
```

#### Parameters

- **collection_id** (str): The user-provided identifier for a project or run, which may be an ID or a name

**Returns:**

- The matched project/run [SearchItem](#class-searchitem)

The method probes five scope/field combinations in order, building a Lucene clause for each:

1. `runs` by `Id`
2. `runs` by `Name`
3. `runs` by `ExperimentName`
4. `projects` by `Id`
5. `projects` by `Name`

BaseSpace's search endpoint can return close matches as well as exact ones, so results are then filtered down to items whose field value equals `collection_id` exactly. Zero exact matches or more than one both raise [BaseSpaceCollectionIdError](#class-basespacecollectioniderror) — see [Collections: projects vs. runs](#important-notes) for how these fields map to the BaseSpace UI.

_**Example**_

```python
# Resolve by numeric project ID from the browser URL
search_item = basespace.methods.resolve_collection_id("489069003")

print(search_item.type)  # "project"
print(search_item.id)    # "489069003"
```

</br>

#### `fetch_sample_fastqs`

Resolves a `collection_id`, finds the datasets for the given sample(s), downloads their per-lane FASTQ files, and optionally concatenates them across lanes. This is the primary entry point for the module.

```python
fetch_sample_fastqs(
    collection_id: str,
    samples: List[str],
    dest_dir: Optional[Path] = None,
    dataset_types: Optional[List[str]] = ["common.fastq"],
    concatenate: bool = True,
    remove_sources: bool = True,
    validate_paired_end: bool = True,
    validate_lane_naming: bool = False,
    group_by_lane: bool = False,
    dry_run: bool = False,
    progress: bool = True
) -> None
```

#### Parameters

- **collection_id** (str): A project/run ID or name to resolve
- **samples** (List[str]): The sample name(s) to download. Each name resolves to an exact dataset match or, when `group_by_lane` is True, to its `{name}_L###` lane siblings
- **dest_dir** (Optional[Path]): The directory to download files to (defaults to the current working directory)
- **dataset_types** (Optional[List[str]]): Dataset types to keep when filtering, defaults to `["common.fastq"]`
- **concatenate** (bool): If True, merge each dataset's FASTQ files into `{name}_R1/_R2.fastq.gz`
- **remove_sources** (bool): If True (default), delete the downloaded per-lane FASTQ files once they have been concatenated into a size-verified output. Only applies when `concatenate` is True, and sources are kept if the API did not report a `Size` for every file
- **validate_paired_end** (bool): If True (default), require each output to be a balanced paired-end dataset group before downloading. Set False to skip the check
- **validate_lane_naming** (bool): If True, verify that all FASTQ files being concatenated share the same lane-stripped filename before merging
- **group_by_lane** (bool): If True, expands sample name matching to `{sample}_L###` and groups together sibling datasets so they concatenate together. Set False to require an exact match
- **dry_run** (bool): If True, log what would be downloaded/concatenated without fetching or writing any files
- **progress** (bool): If True (default), draw the tqdm progress bar on a TTY. Set False to disable

**Returns:**

- Nothing. Files are the output — check `dest_dir`
- The output filenames are **always** built from the *requested* sample name (`{sample}_R1.fastq.gz`)

#### Execution Order

1. Reject an empty `samples` list, or one containing duplicate names, with [BaseSpaceDatasetError](#class-basespacedataseterror). Both guards run before any network call
2. Resolve `dest_dir` once, so download and concatenation agree on where files land
3. Resolve `collection_id` to a project/run via [`resolve_collection_id`](#resolve_collection_id)
4. List every dataset for that collection via [`get_datasets`](#get_datasets)
5. Filter to the requested `dataset_types` via [`filter_dataset_types`](#filter_dataset_types)
6. Then, for **each** requested sample: match datasets by name, gather every file across the matched group, optionally validate paired-end balance, download each file, and optionally concatenate

!!! info "Two mergers and two validators"
    The mergers:

    - **`concatenate`** (default **True**) is the *inner* merge: the per-lane files inside a matched dataset are joined into one R1/R2 pair. Set False to leave the raw per-lane files on disk untouched.
    - **`group_by_lane`** (default **False**) is the *outer* merge: a lane-less requested name is allowed to expand to its `{name}_L###` sibling **datasets** so they merge together. Set False to require an exact dataset-name match — a lane-less name that matches only siblings will raise rather than silently grouping.

    The validators:

    - **`validate_paired_end`** (default **True**) requires every dataset in the group to be flagged paired-end with balanced R1/R2 before anything downloads.
    - **`validate_lane_naming`** (default **False**) requires all files on one read side to share a single lane-stripped filename before merging.

!!! info "`dataset_types` is tri-state"
    `["common.fastq"]` (the default) keeps FASTQ datasets, including typed variants such as `illumina.fastq.v1.8` that declare conformance to `common.fastq`. `None` keeps **every** dataset type. An empty list `[]` matches nothing. Treat the default as read-only — it is a shared mutable default argument.

_**Examples**_

```python
from pathlib import Path

# Download three samples by exact dataset name and concatenate each
basespace.methods.fetch_sample_fastqs(
    collection_id="47639625",
    samples=[
        "E-coli_1ng_input-rep02_L001",
        "R-sphaeroides_100ng_input-rep18_L001",
        "R-sphaeroides_1ng_input-rep15_L001",
    ],
    dest_dir=Path("/data/fastqs"),
)
```

```python
# Lane-split data: "NA12878-3_4" exists only as NA12878-3_4_L001..L004 datasets.
# group_by_lane=True merges those four datasets into one R1/R2 pair.
basespace.methods.fetch_sample_fastqs(
    collection_id="25852834",
    samples=["NA12878-3_4"],
    dest_dir=Path("/data/fastqs"),
    group_by_lane=True,
    validate_lane_naming=True,
)
# Writes /data/fastqs/NA12878-3_4_R1.fastq.gz and NA12878-3_4_R2.fastq.gz
```

```python
# Preview the plan without writing anything to disk
basespace.methods.fetch_sample_fastqs(
    collection_id="MiSeq: Nextera DNA Flex",
    samples=["E-coli_1ng_input-rep02_L001"],
    dry_run=True,
)
```

!!! info "`dry_run` is a write dry-run, not a network dry-run"
    With `dry_run=True`, collection resolution, dataset listing, file listing, and paired-end validation **all still execute** and still hit the BaseSpace API. Only the byte download, the concatenation, and the source removal are skipped. This is deliberate: it lets a dry run surface the same resolution and validation errors a real run would hit.

</br>

#### `build_sample_sheet`

Builds a CSV describing every dataset available under a project/run, for exploring what is there without a predefined sample list. Writes one CSV per collection, named `{type}_{resolved name}.csv`.

Unlike [`fetch_sample_fastqs`](#fetch_sample_fastqs), this takes no `samples` and never errors on single-end or unbalanced datasets: it lists every dataset and reports, per dataset, whether it *would* pass the download pipeline's validation. This is a survey and testing utility — it never downloads or concatenates.

```python
build_sample_sheet(
    collection_id: Optional[str] = None,
    dest_dir: Optional[Path] = None,
    dataset_types: Optional[List[str]] = ["common.fastq"]
) -> List[Path]
```

#### Parameters

- **collection_id** (Optional[str]): A project/run ID or name to resolve. If None (default), survey the whole account: list every project and run and write a CSV for each
- **dest_dir** (Optional[Path]): Directory to write the CSV(s) to (defaults to the current working directory)
- **dataset_types** (Optional[List[str]]): Restrict rows to these dataset type(s) (default `["common.fastq"]`); pass `None` to list every dataset regardless of type

**Returns:**

- The written CSV path(s), one per resolved project/run

When surveying a whole account, collections the token cannot read raise [BaseSpaceForbiddenError](#class-basespaceforbiddenerror) internally; these are caught and skipped with a log line rather than aborting the survey. Collections with zero matching datasets are skipped too, so the returned list may be shorter than the number of collections in the account.

See [`write_dataset_sample_sheet`](#write_dataset_sample_sheet) for the CSV columns.

_**Example**_

```python
from pathlib import Path

# Survey one project
paths = basespace.methods.build_sample_sheet(
    collection_id="MiSeq: Nextera DNA Flex",
    dest_dir=Path("/data/sample_sheets"),
)
print(paths)  # [PosixPath('/data/sample_sheets/project_MiSeq__Nextera_DNA_Flex.csv')]

# Survey every project and run in the account
all_paths = basespace.methods.build_sample_sheet(
    dest_dir=Path("/data/sample_sheets"),
)
```

---

## Dataset Operations

Module: `bioforklift.basespace.basespace_dataset_operations`

These are pure functions that decide *what* to download and *how* to group it: read classification, dataset type filtering, sample-name matching, paired-end validation, and concatenation planning.

!!! tip "Advanced Topics"
    **These functions are used internally** by [BaseSpaceMethods](#class-basespacemethods). However, they are available for advanced users who need to build a custom pipeline — for example, to inspect what a sample name would match before downloading it.

    ```python
    from bioforklift.basespace.basespace_dataset_operations import (
        filter_dataset_types,
        match_datasets_by_sample,
        validate_paired_end_datasets,
        concatenate_dataset_files,
    )
    ```

!!! info "Filename patterns"
    Three case-insensitive regexes drive all filename logic in this module:

    - **Lane token**: `[_-]L\d{1,3}(?=[_-]R[12]|$)` — `_L` (or `-L`) plus **one to three digits**, so `_L1`, `_L01`, and `_L001` are all recognized as lanes. A lane token is only recognized in two places: at the **end of a dataset name** (`NA12878-3_4_L001`), or **directly before the read token** in a FASTQ filename (`Sample_S1_L001_R1_001.fastq.gz`). A mid-name `_L1` such as `CA-2024-001_L1_extra` is left alone
    - **Read 1**: `[_-]R1.*\.fastq\.gz$`
    - **Read 2**: `[_-]R2.*\.fastq\.gz$`

    Read classification is purely filename-based. Files named `.fq.gz`, or uncompressed FASTQ, match neither read pattern — and neither do `_I1_` index reads.

### `read1_files` / `read2_files`

Return the R1 (or R2) files among `ds_files` by filename pattern, **sorted by filename**.

```python
read1_files(ds_files: List[DatasetFileItem]) -> List[DatasetFileItem]
read2_files(ds_files: List[DatasetFileItem]) -> List[DatasetFileItem]
```

**Returns:**

- The matching [DatasetFileItem](#class-datasetfileitem) objects, in filename order

The sort is what guarantees correct paired-end output. The BaseSpace API does not promise a stable order across the two read sides, so concatenating in API order could interleave R1 and R2 lanes differently and silently misalign read pairs. Sorting both sides by filename makes the lane order consistent between R1 and R2 — the absolute order does not matter, only that the two sides agree.

### `filter_dataset_types`

Keeps datasets matching any requested type, by `DatasetType.Id` or by conformance (`ConformsToIds`).

```python
filter_dataset_types(
    ds_items: List[DatasetItem],
    dataset_types: Optional[List[str]] = None
) -> List[DatasetItem]
```

#### Parameters

- **ds_items** (List[[DatasetItem](#class-datasetitem)]): List of DatasetItems to filter from
- **dataset_types** (Optional[List[str]]): Dataset types to keep (e.g. `["common.fastq"]`); default `None` keeps all types

**Returns:**

- The list of [DatasetItem](#class-datasetitem) objects filtered by `dataset_types`

Checking conformance as well as the exact ID is what catches typed variants like `illumina.fastq.v1.8`, which declare that they conform to `common.fastq`. Note the asymmetry between the two falsy inputs: `None` keeps everything, an empty list keeps nothing.

### `match_datasets_by_sample`

Resolves one requested sample name to the dataset(s) that feed its output.

```python
match_datasets_by_sample(
    sample: str,
    ds_items: List[DatasetItem],
    group_by_lane: bool = False
) -> List[DatasetItem]
```

#### Parameters

- **sample** (str): The requested sample name to match
- **ds_items** (List[[DatasetItem](#class-datasetitem)]): DatasetItems to match against
- **group_by_lane** (bool): If True, group a lane-less sample name with its `{sample}_L###` siblings. Defaults to False (an exact match is required)

**Returns:**

- The matched [DatasetItem](#class-datasetitem) objects: a single-item list for an exact match, or the lane-sibling group when `group_by_lane` is True

Resolution follows a strict precedence:

- An exact `DatasetItem.Name` match **always wins**. If `{sample}_L###` siblings also exist, a **warning** is logged, because those lanes will *not* be grouped in. Watch for this warning — it is the one case where the function quietly returns less data than you might expect
- Otherwise, when `group_by_lane` is True, any `{sample}_L###` sibling datasets are returned together for downstream concatenation across lanes
- When `group_by_lane` is False, a name matching only `{sample}_L###` siblings raises rather than silently grouping

[BaseSpaceDatasetError](#class-basespacedataseterror) is raised if the sample matches multiple exact datasets, matches only lane siblings while `group_by_lane` is False, or matches nothing at all.

### `validate_paired_end_datasets`

Raises unless the datasets and their files form a balanced paired-end set.

```python
validate_paired_end_datasets(
    ds_items: List[DatasetItem],
    ds_files: List[DatasetFileItem]
) -> None
```

#### Parameters

- **ds_items** (List[[DatasetItem](#class-datasetitem)]): The dataset(s) feeding one output
- **ds_files** (List[[DatasetFileItem](#class-datasetfileitem)]): Every file across those dataset(s)

Two conditions must hold, and both raise [BaseSpaceMissingReadError](#class-basespacemissingreaderror) when violated:

1. **Every** dataset must be flagged paired-end via its [CommonFastqAttributes](#class-commonfastqattributes). A dataset with no `Attributes` block at all fails this check
2. The file set must be *balanced*: an equal, non-zero number of R1 and R2 files, **and nothing else present**. A dataset carrying index reads (`_I1_`) fails on that last condition even though its R1/R2 counts match

### `concatenate_dataset_files`

Concatenates one sample's per-lane files into clean `{samplename}_R1.fastq.gz` / `{samplename}_R2.fastq.gz` outputs under `dest_dir`.

```python
concatenate_dataset_files(
    samplename: str,
    ds_files: List[DatasetFileItem],
    dest_dir: Path,
    dry_run: bool = False,
    validate_lane_naming: bool = False,
    remove_sources: bool = True
) -> None
```

#### Parameters

- **samplename** (str): Names the output files (`{samplename}_R1/_R2.fastq.gz`)
- **ds_files** (List[[DatasetFileItem](#class-datasetfileitem)]): Every FASTQ file for the sample, already on disk under `dest_dir`
- **dest_dir** (Path): The directory the files were downloaded to
- **dry_run** (bool): If True, log the outputs that would be written without reading or writing files
- **validate_lane_naming** (bool): If True, verify that all FASTQ files being concatenated share the same lane-stripped filename before merging
- **remove_sources** (bool): If True (default), delete each output's per-lane source files once the concatenated output has been size-verified and written

Source paths are derived as `dest_dir / file.name` — the same deterministic location the files were downloaded to — so this step carries no state over from download. Files are joined at the **byte level** with no re-compression and no FASTQ parsing, which is valid for concatenating gzip members. A read side with no files is skipped, so single-end input (with `validate_paired_end=False` upstream) produces only an `_R1` output.

Size verification uses the combined `Size` the API reported, and only when **every** source file has one. [BaseSpaceDownloadError](#class-basespacedownloaderror) is raised on a mismatch; [BaseSpaceDatasetError](#class-basespacedataseterror) is raised when `validate_lane_naming` is set and a read's files do not share one lane-stripped name.

### `write_dataset_sample_sheet`

Writes a CSV summarizing each dataset and its files.

```python
write_dataset_sample_sheet(
    grouped_datasets: List[Tuple[DatasetItem, List[DatasetFileItem]]],
    output_path: Path
) -> Path
```

#### Parameters

- **grouped_datasets** (List[Tuple]): `(DatasetItem, [DatasetFileItem, ...])` pairs, one per dataset
- **output_path** (Path): Destination CSV path

**Returns:**

- The written CSV path

The columns, in order:

- **dataset_name**: The `DatasetItem.Name` — this is the value to pass in `samples`
- **dataset_id**: The `DatasetItem.Id`
- **read1_concat_size_mb**: Combined size of the R1 files, formatted e.g. `"512.00 MB"`
- **read2_concat_size_mb**: Combined size of the R2 files
- **num_files**: Total file count in the dataset
- **dataset_type**: The `DatasetType.Id`, or empty if the dataset has none
- **is_paired_end**: Whether the dataset is flagged paired-end
- **is_balanced**: Whether the R1/R2 counts are equal, non-zero, and account for every file

The last two columns together tell you whether the dataset would survive `validate_paired_end=True`.

---

## File Operations

Module: `bioforklift.basespace.basespace_file_operations`

The byte-level I/O layer: streaming a response to disk and concatenating files. Both write to a temporary file in the destination's directory and rename it into place.

!!! tip "Advanced Topics"
    **These functions are used internally** by [BaseSpaceMethods](#class-basespacemethods) and [Dataset Operations](#dataset-operations). However, they are available for advanced users who need direct control over file writes.

    They are **not** re-exported from `bioforklift.basespace`:

    ```python
    from bioforklift.basespace.basespace_file_operations import (
        stream_to_disk,
        concatenate_files,
    )
    ```

!!! info "Atomic writes"
    Both functions write to a `.tmp.{final_name}.XXXXXX` file in the **destination directory** — the same filesystem as the final path, so the rename is atomic — and only then rename it into place. Any failure, including `KeyboardInterrupt`, unlinks the temp file and re-raises.

    The guarantee: a disrupted transfer leaves only the temp file. It never leaves a truncated file at the final path that a later run might mistake for a complete download.

### `stream_to_disk`

Streams the content of an HTTP response body to a destination file.

```python
stream_to_disk(
    response: requests.Response,
    destination: Path,
    expected_size: Optional[int] = None,
    chunk_size: int = 1024 * 1024,
    progress: bool = True
) -> None
```

#### Parameters

- **response** (requests.Response): The response object to stream content from
- **destination** (Path): Path to save the streamed content
- **expected_size** (Optional[int]): Expected byte length (the file's `Size`); skipped if None
- **chunk_size** (int): The size of each chunk to read from the response
- **progress** (bool): If True (default), draw the tqdm progress bar on a TTY. Set False to disable

Raises [BaseSpaceDownloadError](#class-basespacedownloaderror) if `expected_size` is given and the bytes written do not match it.

The progress bar is drawn only when `progress` is True **and** stderr is a TTY. tqdm writes to stderr while the logger writes to stdout, so the bar and the log lines stay on separate streams and do not clobber each other.

### `concatenate_files`

Byte-concatenates `sources` into `destination`, in order.

```python
concatenate_files(
    sources: List[Path],
    destination: Path,
    expected_total_size: Optional[int] = None,
    remove_sources: bool = True
) -> None
```

#### Parameters

- **sources** (List[Path]): The files to concatenate, in output order
- **destination** (Path): Path to write the concatenated output to
- **expected_total_size** (Optional[int]): Combined byte length the output must match; skipped if None
- **remove_sources** (bool): If True (default), delete `sources` once the output has passed the size check and been renamed into place

Raises [BaseSpaceDownloadError](#class-basespacedownloaderror) if `expected_total_size` is given and the output does not match it.

!!! info "Source removal is gated on verification"
    `remove_sources` is deliberately conservative — it never deletes data that has not been proven redundant:

    - Deletion happens **only after** the output has been size-verified and renamed into place
    - When `expected_total_size` is None, verification was impossible, so **sources are kept** and a warning is logged
    - A source whose resolved path equals the destination is skipped, guarding against self-deletion when a source is already named `{sample}_R1.fastq.gz`
    - A source that cannot be deleted logs a warning rather than failing the call

### `fetch_all_items`

Module: `bioforklift.basespace.basespace_endpoints`

Pages through any paginated BaseSpace endpoint and returns every item.

```python
fetch_all_items(
    endpoint_method: Callable[..., BaseSpaceResponse[ItemType]],
    **kwargs
) -> List[ItemType]
```

#### Parameters

- **endpoint_method** (Callable): Any bound [BaseSpaceEndpoints](#class-basespaceendpoints) method returning a [BaseSpaceResponse](#class-basespaceresponse)
- ****kwargs**: Whatever query params that endpoint accepts, forwarded as-is

**Returns:**

- Every item across all pages, typed to the endpoint's item type (e.g. `List[SearchItem]` for `search`, `List[DatasetItem]` for `datasets`)

It requests pages of 1000 (the maximum for BaseSpace v2 endpoints), building a fresh [Paging](#class-paging) each iteration rather than mutating a shared instance, and stops when a page returns no items or the accumulated count reaches `total_count`.

!!! info "You cannot cap results through the high-level methods"
    Any `paging` value passed in `**kwargs` is **discarded**. Because [`get_search_items`](#get_search_items), [`get_datasets`](#get_datasets), and [`get_dataset_files`](#get_dataset_files) all route through this helper, they always return the complete result set. To fetch a single page or control sort order, call the [BaseSpaceEndpoints](#class-basespaceendpoints) method directly with an explicit `Paging`.

---

## Models

All models are pydantic models that parse BaseSpace API response bodies.

!!! info "PascalCase aliasing"
    BaseSpace returns PascalCase JSON keys (`ExperimentName`, `TotalCount`), while these models expose snake_case attributes (`experiment_name`, `total_count`). Every model inherits a shared base configured with `alias_generator=to_pascal`, `populate_by_name=True`, and `extra="ignore"`, so the mapping is automatic, models can be constructed by either name or alias, and unknown keys are dropped rather than raising.

    Two fields need explicit aliases because automatic conversion would produce the wrong casing: `total_clusters_pf` → `TotalClustersPF` and `total_reads_pf` → `TotalReadsPF`.

### Class: `RunItem`

A single entry in the `Items` list from the `/search?scope=runs` endpoint.

#### Attributes

- **type** (Literal["run"]): Always `"run"`; the discriminator value
- **id** (str): The run ID, read from the nested `Run.Id` path — the number in the run's browser URL
- **name** (Optional[str]): Read from `Run.Name`; this is what the BaseSpace UI calls **Run ID**
- **experiment_name** (Optional[str]): Read from `Run.ExperimentName`; this is what the BaseSpace UI calls **Run Name**

### Class: `ProjectItem`

A single entry in the `Items` list from the `/search?scope=projects` endpoint.

#### Attributes

- **type** (Literal["project"]): Always `"project"`; the discriminator value
- **id** (str): The project ID, read from the nested `Project.Id` path — the number in the project's browser URL
- **name** (Optional[str]): Read from `Project.Name`; the name shown under the Projects tab

### Class: `OtherItem`

Fallback for item shapes not yet modeled. It declares no fields and sets `extra="allow"`, so it keeps the raw payload instead of raising, meaning new or unmodeled search scopes do not break parsing.

An `OtherItem` cannot be used as a collection: [`get_datasets`](#get_datasets) raises [BaseSpaceCollectionIdError](#class-basespacecollectioniderror) for one, and [`resolve_collection_id`](#resolve_collection_id) will never return one, since it has no `id` or `name` attribute to match against.

### Class: `SearchItem`

A **type alias**, not a class. It is a discriminated union of [RunItem](#class-runitem), [ProjectItem](#class-projectitem), and [OtherItem](#class-otheritem), representing a single entry in the `Items` list returned by `/search`.

The discriminator inspects the raw dict: a payload with a `Project` key and `Type == "project"` becomes a `ProjectItem`, one with a `Run` key and `Type == "run"` becomes a `RunItem`, and anything else falls back to `OtherItem`. Use `isinstance(item, RunItem)` to narrow the type in your own code.

### Class: `DatasetItem`

A single entry in the `Items` list returned by the `/datasets` endpoint.

#### Attributes

- **id** (str): The dataset ID
- **name** (str): The dataset name — this is the value matched against a requested sample name
- **dataset_type** (Optional[[DatasetType](#class-datasettype)]): The dataset's type block
- **attributes** (Optional[[CommonFastqAttributes](#class-commonfastqattributes)]): Read from the nested `Attributes.common_fastq` path; None for datasets that are not FASTQ

### Class: `DatasetType`

Describes the type of a dataset, e.g. `common.fastq`.

#### Attributes

- **id** (str): The type identifier, e.g. `"common.fastq"` or `"illumina.fastq.v1.8"`
- **conforms_to_ids** (List[str]): Type identifiers this type conforms to; defaults to an empty list. This is what lets a typed variant match a request for `common.fastq`

### Class: `CommonFastqAttributes`

Maps to the `Attributes.common_fastq` block in a `DatasetItem`. Every field is optional and defaults to None.

#### Attributes

- **is_paired_end** (Optional[bool]): Whether the dataset is paired-end. [`validate_paired_end_datasets`](#validate_paired_end_datasets) requires this to be truthy
- **max_length_read1** (Optional[int]): Maximum read length for R1
- **max_length_read2** (Optional[int]): Maximum read length for R2
- **total_clusters_pf** (Optional[int]): Total clusters passing filter (alias `TotalClustersPF`)
- **total_clusters_raw** (Optional[int]): Total raw clusters
- **total_reads_pf** (Optional[int]): Total reads passing filter (alias `TotalReadsPF`)
- **total_reads_raw** (Optional[int]): Total raw reads

### Class: `DatasetFileItem`

A single entry in the `Items` list returned by the `/datasets/{dataset_id}/files` endpoint.

#### Attributes

- **id** (str): The file ID, used to fetch content
- **name** (str): The original filename; also determines the local download path and the R1/R2 classification
- **size** (Optional[int]): Size in bytes, used to verify a complete download. When the API does not report it, download and concatenation size verification are both skipped

### Class: `Paging`

The `Paging` block used by v2 list and search endpoints. All fields are optional and default to None; they are serialized to the query string by alias (`Offset`, `Limit`, `SortDir`, `SortBy`) with None values excluded.

#### Attributes

- **offset** (Optional[int]): Index of the first item to return
- **limit** (Optional[int]): Maximum items per page (1000 is the BaseSpace v2 maximum)
- **sort_dir** (Optional[Literal["Asc", "Desc"]]): Sort direction
- **sort_by** (Optional[str]): Field to sort by

### Class: `PagingResponse`

Extends [Paging](#class-paging) with the two counts BaseSpace returns on a response.

#### Attributes

- **displayed_count** (int): Number of items in this page
- **total_count** (int): Total number of items across all pages
- Plus every attribute from [Paging](#class-paging)

### Class: `BaseSpaceResponse`

A generic response model for BaseSpace list and search calls. The item type is specified per call, e.g. `BaseSpaceResponse[DatasetItem].model_validate(...)`.

#### Attributes

- **items** (List[ItemType]): The page of items, typed to whatever the endpoint returns
- **paging** ([PagingResponse](#class-pagingresponse)): The paging block for this response

---

## Exception Classes

Every exception in this module inherits from [BaseSpaceError](#class-basespaceerror), so a single `except BaseSpaceError` catches all of them. Two details are worth noting: `BaseSpaceTimeoutError` is a subclass of `BaseSpaceConnectionError` rather than of `BaseSpaceError` directly, and pydantic `ValidationError` from the [BaseSpaceEndpoints](#class-basespaceendpoints) layer is **not** part of this hierarchy.

```
BaseSpaceError
├── BaseSpaceConnectionError
│   └── BaseSpaceTimeoutError
├── BaseSpaceInvalidResponseError
├── BaseSpaceCollectionIdError
├── BaseSpaceDatasetError
├── BaseSpaceMissingReadError
├── BaseSpaceDownloadError
└── BaseSpaceAPIError
    ├── BaseSpaceBadRequestError      (400)
    ├── BaseSpaceAuthenticationError  (401)
    ├── BaseSpaceForbiddenError       (403)
    ├── BaseSpaceNotFoundError        (404)
    └── BaseSpaceServerError          (500)
```

### Class: `BaseSpaceError`

Base exception for BaseSpace-related errors.

### Class: `BaseSpaceConnectionError`

Raised when connection to BaseSpace fails. Also the catch-all for any other underlying `requests` transport failure.

### Class: `BaseSpaceTimeoutError`

Raised when a request to BaseSpace times out. Subclasses [BaseSpaceConnectionError](#class-basespaceconnectionerror).

### Class: `BaseSpaceInvalidResponseError`

Raised when a response body could not be parsed as expected JSON.

### Class: `BaseSpaceCollectionIdError`

Raised when a collection ID cannot be resolved to a single project/run — either nothing matched it exactly, or more than one thing did. Also raised when [`get_datasets`](#get_datasets) is handed something that is not a run or project.

### Class: `BaseSpaceDatasetError`

Raised when a sample resolves to no datasets, or to more than one (ambiguous). Also covers an empty or duplicated `samples` list, and a lane-naming mismatch during concatenation.

### Class: `BaseSpaceMissingReadError`

Raised when a dataset is not paired-end, or is paired-end but an unexpected number of reads are present.

### Class: `BaseSpaceDownloadError`

Raised when a downloaded or concatenated file fails an integrity check: the number of bytes written does not match the expected `Size`. The partial output is removed before the exception propagates.

### Class: `BaseSpaceAPIError`

Raised when the BaseSpace API returns an error. Any status code without a more specific subclass (for example 502) surfaces as this class.

#### Attributes

- **status_code** (int): HTTP status code returned by the API
- **response** (Optional[Any]): The parsed error body, usually a dict but occasionally a list
- **message** (str): Error message, taken from the body's `ResponseStatus.Message` when present

### Class: `BaseSpaceBadRequestError`

Raised when BaseSpace returns 400.

### Class: `BaseSpaceAuthenticationError`

Raised when BaseSpace returns 401. Usually an expired or malformed access token.

### Class: `BaseSpaceForbiddenError`

Raised when BaseSpace returns 403. The token is valid but lacks access to that resource. [`build_sample_sheet`](#build_sample_sheet) catches this internally to skip unauthorized collections during an account-wide survey.

### Class: `BaseSpaceNotFoundError`

Raised when BaseSpace returns 404.

### Class: `BaseSpaceServerError`

Raised when BaseSpace returns 500. From the `/search` endpoint, this often indicates an invalid or unescaped query rather than an outage. Note that 5xx responses are **not** retried automatically.

---

## Complete Workflow Example

The typical pattern: survey what is available, then fetch the samples you want.

```python
import os
from pathlib import Path

from bioforklift.basespace import BaseSpace, BaseSpaceError

basespace = BaseSpace(access_token=os.environ["BASESPACE_ACCESS_TOKEN"])

dest_dir = Path("/data/fastqs")

# Step 1: Survey the collection to see the real dataset names and whether
# each one would pass paired-end validation.
basespace.methods.build_sample_sheet(
    collection_id="47639625",
    dest_dir=dest_dir,
)

# Step 2: Fetch the samples you want, using dataset_name values from the CSV.
# Each sample's per-lane files are downloaded and merged into
# {sample}_R1.fastq.gz / {sample}_R2.fastq.gz, then the sources are removed.
try:
    basespace.methods.fetch_sample_fastqs(
        collection_id="47639625",
        samples=[
            "E-coli_1ng_input-rep02_L001",
            "R-sphaeroides_100ng_input-rep18_L001",
        ],
        dest_dir=dest_dir,
        concatenate=True,      # merge per-lane files into one R1/R2 pair
        remove_sources=True,   # delete per-lane files once the merge is verified
        validate_paired_end=True,
        dry_run=False,
    )
except BaseSpaceError as error:
    print(f"BaseSpace fetch failed: {error}")
```

---

## Troubleshooting

### Common Issues

Expand the sections below to see common issues and their solutions.

??? question "Could not resolve input collection ID"
    **Problem**: `BaseSpaceCollectionIdError: Could not resolve input collection ID ... no project or run exactly matches it by id or name.`

    **Solution**:

    - Prefer the **numeric ID from the browser URL** — it is unique and unambiguous. For `https://basespace.illumina.com/projects/489069003/about`, pass `"489069003"`
    - If you are using a name, check which field you actually have. What the UI calls **Run Name** is `ExperimentName` in the API, and what it calls **Run ID** is `Name`
    - Matching is exact after the search returns, so trailing spaces or a partial name will not resolve
    - If the error says the ID is **ambiguous**, the same name exists on more than one project or run. Use the numeric ID instead

??? question "No exact dataset match, or lane siblings will not be grouped"
    **Problem**: `BaseSpaceDatasetError: No exact dataset match for ... found.` or `Partial dataset match ... will not be grouped together (group_by_lane=False)`

    **Solution**:

    - Run [`build_sample_sheet`](#build_sample_sheet) first and use the `dataset_name` column — sample names in a sample sheet or LIMS often differ from BaseSpace dataset names
    - If the datasets are lane-split (`MySample_L001`, `MySample_L002`, ...) and you are requesting the lane-less name, pass `group_by_lane=True`
    - The lane pattern allows **one to three digits**, so `_L1`, `_L01`, and `_L001` are all recognized as lane tokens, but `_L0001` and `_L1234` are not. A name ending in a longer `_L####` is treated as an ordinary sample name and must be requested exactly as it appears
    - If you see a warning that siblings exist but will not be grouped, a dataset matched your name *exactly* while `_L###` siblings also exist. The exact match wins — request the lane-less name against a collection without the exact-match dataset, or request each lane individually

??? question "BaseSpaceMissingReadError on data that looks fine"
    **Problem**: `BaseSpaceMissingReadError: Unbalanced R1/R2 files ...` even though R1 and R2 both exist

    **Solution**:

    - Balance requires that **every** file in the group is an R1 or R2 read. A dataset that also carries index reads (`_I1_`, `_I2_`) fails, because those files count toward the total but match neither read pattern
    - Read classification is filename-based and only recognizes `*_R1*.fastq.gz` / `*_R2*.fastq.gz`. Files named `.fq.gz`, or uncompressed FASTQ, are invisible to it
    - The error can also come from the paired-end flag rather than the file counts: a dataset with no `Attributes` block at all is treated as not paired-end
    - To download anyway, pass `validate_paired_end=False`. Be aware that concatenation then merges whatever the read patterns do match, and a read side with no matches is silently skipped

??? question "Downloaded files overwrote each other, or the disk filled up"
    **Problem**: Files from two samples collided, or a large fetch ran out of space

    **Solution**:

    - Downloads land **flat** in `dest_dir` with no per-sample subdirectory. If two requested samples contain identically named files, the second overwrites the first. Use a separate `dest_dir` per collection or per sample
    - With `remove_sources=True`, sources and the concatenated output coexist until the size check passes, so plan for roughly **2× the final size** in peak disk usage
    - Temporary files are written in `dest_dir` itself (so the final rename is atomic), which means `dest_dir` must be writable and on a filesystem with room for the temp copy
    - If you see `Keeping source file(s) ... could not be size-verified`, the API did not report a `Size` for every source, so removal was skipped as a safety measure. Delete them manually after checking the output
