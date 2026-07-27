import re
import time
import requests
from pathlib import Path
from typing import List, Optional

from pydantic.alias_generators import to_pascal

from .basespace_dataset_operations import (
    filter_dataset_types,
    match_datasets_by_sample,
    validate_paired_end_datasets,
    concatenate_dataset_files,
    write_dataset_sample_sheet,
)
from .basespace_endpoints import (
    BaseSpaceEndpoints,
    fetch_all_items,
)
from .basespace_exceptions import (
    BaseSpaceCollectionIdError,
    BaseSpaceDatasetError,
    BaseSpaceForbiddenError,
)
from .basespace_file_operations import (
    stream_to_disk,
)
from .basespace_models import (
    DatasetFileItem,
    DatasetItem,
    ProjectItem,
    RunItem,
    SearchItem,
)
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class BaseSpaceMethods:
    """
    Contains endpoint-backed operations for interacting with the BaseSpace API
    """

    def __init__(self, endpoints: BaseSpaceEndpoints):
        self.endpoints = endpoints

    def get_search_items(
        self,
        query: str,
        scope: Optional[str] = None,
    ) -> List[SearchItem]:
        """
        Run one `/search` (paging through all results) and keep only project/run items.
        Unmodeled results (`OtherItem`) are dropped, so callers only ever see runs/projects.

        Args:
            scope: The search scope, e.g. "projects" or "runs".
            query: A Lucene query clause, or "" to match everything in the scope.

        Returns:
            The project/run items returned by this search.
        """

        search_items: List[SearchItem] = fetch_all_items(
            endpoint_method=self.endpoints.search,
            scope=scope,
            query=query,
        )
        return [item for item in search_items]

    def get_datasets(
        self,
        search_item: SearchItem,
    ) -> List[DatasetItem]:
        """
        Get every dataset for a given project or run, paging through all results.

        Args:
            search_item: The resolved SearchItem object ("project" or "run").

        Returns:
            A list of all datasets associated with the specified project or run.
        """

        if not isinstance(search_item, (RunItem, ProjectItem)):
            raise BaseSpaceCollectionIdError(
                f"Cannot list datasets for {type(search_item).__name__}; expected a run or project."
            )
        # Capture and validate DatasetItems from API response
        return fetch_all_items(
            self.endpoints.datasets,
            project_id=search_item.id if search_item.type == "project" else None,
            input_runs=search_item.id if search_item.type == "run" else None,
        )

    def get_dataset_files(
        self,
        ds_item: DatasetItem,
    ) -> List[DatasetFileItem]:
        """
        Get all files associated with an input DatasetItem

        Args:
            ds_item: `DatasetItem`

        Returns:
            List of `DatasetFileItem`s
        """

        return fetch_all_items(
            endpoint_method=self.endpoints.dataset_files,
            dataset_id=ds_item.id,
        )

    def get_dataset_file_content(
        self,
        ds_file: DatasetFileItem,
    ) -> requests.Response:
        """
        Open a streaming response for a dataset file's content.

        Args:
            ds_file: The file to fetch.

        Returns:
            A streaming `requests.Response`
        """
        return self.endpoints.file_content(
            file_id=ds_file.id,
            stream=True,
            redirect="true",
        )

    def download_dataset_file_content(
        self,
        ds_file: DatasetFileItem,
        dest_dir: Optional[Path] = None,
        dry_run: bool = False,
        progress: bool = True,
    ) -> None:
        """
        Stream a single dataset file to `dest_dir` under its original name.

        Args:
            ds_file: The file to download.
            dest_dir: Destination directory (defaults to the current working directory).
            dry_run: If True, log what would be downloaded without fetching or writing.
            progress: If True (default), draw the tqdm progress bar on a TTY.
        """

        # Resolve the default at call time so it reflects the current cwd, then
        # ensure the destination exists for real downloads.
        dest_dir = dest_dir or Path.cwd()
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        destination = dest_dir / ds_file.name

        if dry_run:
            logger.info(f"[dry-run] Would download dataset file: `{ds_file.name}`")
            return

        # Time the transfer so we can log a single persistent completion line.
        start = time.monotonic()

        # Stream the file straight to disk; `with` releases the connection even on a mid-stream error.
        with self.get_dataset_file_content(ds_file) as response:
            stream_to_disk(
                response=response,
                destination=destination,
                expected_size=ds_file.size,
                progress=progress,
            )

        elapsed = time.monotonic() - start
        size_str = (
            f"{ds_file.size / (1024 * 1024):.1f} MB"
            if ds_file.size is not None else "unknown size"
        )
        logger.info(
            f"Downloaded dataset file: `{ds_file.name}` ({size_str} in {elapsed:.1f}s)"
        )
        return

    def resolve_collection_id(
        self,
        collection_id: str
    ) -> SearchItem:
        """
        Resolve an input "collection_id" to its BaseSpace project/run `SearchItem`. A "collection_id"
        can be a project/run ID or a project/run name. If no resource matches, or if
        more than one does, the input was not specific enough to be resolved, and an error is raised.

        Args:
            collection_id: The user-provided identifier for a project or run, which may be an ID or a name.
        Returns:
            The matched project/run `SearchItem`.
        """

        logger.info(f"Resolving BaseSpace collection ID: `{collection_id}`")

        # "run.Name"           refers to `Run ID` in BaseSpace UI
        # "run.ExperimentName" refers to `Run Name` in BaseSpace UI
        # "run.Id"             refers to numerical ID found in the BaseSpace HTTP URL (ex https://basespace.illumina.com/run/315086826/details)
        # "project.Name"       refers to name under the Projects tab in BaseSpace UI
        # "project.Id"         refers to numerical ID found in the BaseSpace HTTP URL (ex https://basespace.illumina.com/projects/489069003/about)

        # Represents the scope and field (snake_case model attribute of a `SearchItem`).
        search_fields = [
            ("runs", "id"),
            ("runs", "name"),
            ("runs", "experiment_name"),
            ("projects", "id"),
            ("projects", "name"),
        ]

        exact_matches: List[SearchItem] = []

        for scope, field in search_fields:
            # Creates a Lucene query clause compatible with BaseSpace (e.g. "experiment_name" -> "ExperimentName";
            query_clause = f'{to_pascal(field)}:"{collection_id}"'

            search_items = self.get_search_items(
                scope=scope,
                query=query_clause
            )

            # Sometimes the BaseSpace search endpoint can return items that are close matches but not exact matches.
            # Filter out items whose attribute/field doesn't match the input `collection_id` exactly.
            hits = 0
            for search_item in search_items:
                if (
                    getattr(search_item, field, None) == collection_id and
                    search_item not in exact_matches
                  ):
                    exact_matches.append(search_item)
                    hits += 1

            if search_items:
                logger.info(f"Found {hits} hit(s) after exact match filtering. (Total returned: {len(search_items)})")

        if not exact_matches:
            raise BaseSpaceCollectionIdError(
                f"Could not resolve input collection ID `{collection_id}`: no project or run exactly matches it by id or name."
            )

        if len(exact_matches) > 1:
            raise BaseSpaceCollectionIdError(
                f"Input collection ID `{collection_id}` is ambiguous; it matches: "
                f"{exact_matches}. Provide a more specific id or name."
            )

        # Should be exactly one match at this point
        search_item = next(iter(exact_matches))
        logger.info(
            f"Input collection ID `{collection_id}` resolved to `{search_item.id}` ({search_item.type}.id)"
        )
        return search_item

    def fetch_sample_fastqs(
        self,
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
        progress: bool = True,
    ):
        """
        Resolve a collection_id, find the datasets for the given sample(s), download
        their per-lane FASTQ files, and optionally concatenate them across lanes.

        Args:
            collection_id: A project/run ID or name to resolve.
            samples: The sample name(s) to download. Each name resolves to an exact dataset
                match or, when `group_by_lane` is True, to its `{name}_L###` lane siblings.
            dest_dir: The directory to download files to (defaults to the current working directory).
            dataset_types: Dataset types to keep when filtering, defaults to ["common.fastq"].
            concatenate: If True, merge each dataset's FASTQ files into `{name}_R1/_R2.fastq.gz`.
            group_by_lane: If True, expands sample name matching to `{sample}_L###` and groups together
                sibling datasets so they concatenate together. Set False to require an exact match.
            validate_paired_end: If True (default), require each output to be a balanced paired-end
                dataset group before downloading. Set False to skip the check.
            validate_lane_naming: If True, verify that all FASTQ files being concatenated
                share the same lane-stripped filename (per `_LANE_PATTERN`) before merging.
            remove_sources: If True (default), delete the downloaded per-lane FASTQ files once they
                have been concatenated into a size-verified output. Only applies when `concatenate`
                is True, and sources are kept if the API did not report a `Size` for every file.
            dry_run: If True, log what would be downloaded/concatenated without fetching or writing any files.
            progress: If True (default), draw the tqdm progress bar on a TTY. Set False to disable.
        """

        # Fail fast on empty/duplicate samples before any network calls.
        if not samples:
            raise BaseSpaceDatasetError("No samples provided; nothing to fetch.")
        duplicates = sorted({name for name in samples if samples.count(name) > 1})
        if duplicates:
            raise BaseSpaceDatasetError(
                f"Duplicate sample name(s) provided: {', '.join(duplicates)}. Provide each sample once."
            )

        # Resolve the destination once so download and concatenate agree on where files land.
        dest_dir = dest_dir or Path.cwd()

        # Resolve the collection_id to a SearchItem (project/run)
        search_item = self.resolve_collection_id(collection_id)

        # List every dataset for the resolved project/run (all types)
        all_ds_items = self.get_datasets(search_item)

        # Optionally filter the requested dataset type(s) before matching on sample name
        filtered_ds_items = filter_dataset_types(all_ds_items, dataset_types)

        for sample in samples:
            matched_ds_items = match_datasets_by_sample(
                sample=sample,
                ds_items=filtered_ds_items,
                group_by_lane=group_by_lane,
            )

            # Gather every file across the group's dataset(s) into one output unit.
            ds_files: List[DatasetFileItem] = []
            for ds_item in matched_ds_items:
                ds_files.extend(self.get_dataset_files(ds_item))

            logger.info(f"Found {len(ds_files)} FASTQ files across {len(matched_ds_items)} matching datasets")

            if validate_paired_end:
                validate_paired_end_datasets(
                    ds_items=matched_ds_items,
                    ds_files=ds_files,
                )

            logger.info(f"Preparing to download {len(ds_files)} FASTQ files")

            # Download all dataset file items for each matching dataset (or log if dry_run).
            for ds_file in ds_files:
                self.download_dataset_file_content(
                    ds_file=ds_file,
                    dest_dir=dest_dir,
                    dry_run=dry_run,
                    progress=progress,
                )

            # Concatenate the per-lane files into clean {sample}_R1/_R2.fastq.gz outputs.
            if concatenate:
                concatenate_dataset_files(
                    samplename=sample,
                    ds_files=ds_files,
                    dest_dir=dest_dir,
                    dry_run=dry_run,
                    validate_lane_naming=validate_lane_naming,
                    remove_sources=remove_sources,
                )

    def build_sample_sheet(
        self,
        collection_id: Optional[str] = None,
        dest_dir: Optional[Path] = None,
        dataset_types: Optional[List[str]] = ["common.fastq"],
    ) -> List[Path]:
        """
        Build a CSV describing every dataset available under a project/run, for
        exploring what's there without a predefined sample list. Writes one CSV per
        collection, named `{type}_{resolved name}.csv`.

        Unlike `fetch_sample_fastqs`, this takes no `samples` and never errors on
        single-end/unbalanced datasets: it lists every dataset and reports, per dataset,
        whether it would pass the download pipeline's validation (paired-end flag +
        balanced R1/R2). Testing utility only.

        Args:
            collection_id: A project/run ID or name to resolve. If None (default),
                survey the whole account: list every project and run and write a CSV for each.
            dest_dir: Directory to write the CSV(s) to (defaults to the current working directory).
            dataset_types: Restrict rows to these dataset type(s) (default
                `["common.fastq"]`); pass `None` to list every dataset regardless of type.

        Returns:
            The written CSV path(s), one per resolved project/run.
        """
        search_items: List[SearchItem] = []

        if collection_id is not None:
            search_items = [self.resolve_collection_id(collection_id)]
        else:
            for scope in ("projects", "runs"):
                search_items.extend(self.get_search_items(query="", scope=scope))

        dest_dir = dest_dir or Path.cwd()
        dest_dir.mkdir(parents=True, exist_ok=True)

        all_output_paths = []

        for search_item in search_items:
            # Name the file by the resolved SearchItem.name or ID
            resolved_name = (
                (search_item.experiment_name if isinstance(search_item, RunItem) else None)
                or search_item.name
                or search_item.id
            )
            filename = re.sub(r"[^\w.\-]+", "_", resolved_name)

            output_path = dest_dir / f"{search_item.type}_{filename}.csv"

            try:
                # List every dataset for the resolved project/run (all types)
                all_ds_items = self.get_datasets(search_item)
            except BaseSpaceForbiddenError:
                logger.info(f"Skipping SearchItem: ({search_item}); Unauthorized request.")
                continue

            # Filter the requested dataset type(s) before matching on sample name
            filtered_items = filter_dataset_types(all_ds_items, dataset_types)

            if len(filtered_items) == 0:
                logger.info(f"Skipping SearchItem: ({search_item}); Fetched 0 datasets.")
                continue

            grouped_datasets = []

            for ds_item in filtered_items:

                # Gather every file across the group's dataset(s) into one output unit.
                ds_files: List[DatasetFileItem] = []
                ds_files.extend(self.get_dataset_files(ds_item))

                grouped_datasets.append((ds_item, ds_files))

            sample_sheet = write_dataset_sample_sheet(
                grouped_datasets=grouped_datasets,
                output_path=output_path
            )

            all_output_paths.append(sample_sheet)

        logger.info(f"Wrote {len(all_output_paths)} sample sheet(s) to `{dest_dir}`")
        return all_output_paths