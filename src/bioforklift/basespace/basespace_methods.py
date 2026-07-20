import os
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, List, Optional

import requests
from pydantic.alias_generators import to_pascal
from tqdm import tqdm

from .basespace_endpoints import BaseSpaceEndpoints
from .basespace_exceptions import (
    BaseSpaceCollectionIdError,
    BaseSpaceDatasetError,
    BaseSpaceDownloadError,
)
from .basespace_models import (
    BaseSpaceResponse,
    DatasetFileItem,
    DatasetItem,
    StagedDatasetFile,
    ItemType,
    Paging,
    ProjectItem,
    RunItem,
    SearchItem,
)
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class BaseSpaceMethods:
    """
    Class meant to handle BaseSpace API interactions for BioForklift
    """

    def __init__(self, endpoints: BaseSpaceEndpoints):
        self.endpoints = endpoints

    def _fetch_all_items(
        self,
        endpoint_method: Callable[..., BaseSpaceResponse[ItemType]],
        **kwargs,
    ) -> List[ItemType]:
        """
        Page through any paginated BaseSpace endpoint and return every item.
        Ensures that the caller receives a complete list of items, regardless of
        how many pages the endpoint returns.

        Endpoint-agnostic: works with any `BaseSpaceEndpoints` method that accepts a
        `paging` kwarg and returns a `BaseSpaceResponse` (`.items` + `.paging`) -
        e.g. `search`, `datasets`, `datasets_files`, or any future paginated
        endpoint. The item type of the returned list is inferred from whichever
        endpoint is passed. Any `paging` passed in `**kwargs` is ignored.

        Args:
            endpoint_method: Any bound `BaseSpaceEndpoints` method returning a `BaseSpaceResponse`
            **kwargs: Whatever query params that endpoint accepts, forwarded as-is

        Returns:
            Every item across all pages, typed to the endpoint's item type
            (e.g. `List[SearchItem]` for `search`, `List[DatasetItem]` for `datasets`).
        """

        # Ignore caller-supplied value
        kwargs.pop("paging", None)

        all_items: List[ItemType] = []
        offset = 0

        while True:
            # Build a fresh Paging each iteration; never mutate a shared instance.
            response = endpoint_method(
                paging=Paging(offset=offset, limit=1000), # Max limit is 1000 for BaseSpace v2 endpoints
                **kwargs,
            )

            all_items.extend(response.items)

            # Same as checking the `displayed_count` + `offset` in the PagingResponse
            # Stop iterating if the endpoint returned no items, or if we've already fetched all items.
            if not response.items or len(all_items) >= response.paging.total_count:
                break

            offset = len(all_items)
        return all_items

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

            all_search_items: List[SearchItem] = self._fetch_all_items(
                endpoint_method=self.endpoints.search,
                scope=scope,
                query=query_clause,
            )

            # Sometimes the BaseSpace search endpoint can return items that are close matches but not exact matches.
            # Filter out `SearchItem`s whose attribute/field doesn't match the input `collection_id` exactly.
            hits = 0
            for search_item in all_search_items:
                if (
                    getattr(search_item, field, None) == collection_id and
                    search_item not in exact_matches
                  ):
                    exact_matches.append(search_item)
                    hits += 1

            if all_search_items:
                logger.info(f"Found {hits} hit(s) after exact match filtering. (Total returned: {len(all_search_items)})")

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
        search_item: SearchItem = next(iter(exact_matches))
        logger.info(
            f"Input collection ID `{collection_id}` resolved to `{search_item.id}` ({search_item.type}.id)"
        )
        return search_item

    def list_datasets(
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
        return self._fetch_all_items(
            self.endpoints.datasets,
            project_id=search_item.id if search_item.type == "project" else None,
            input_runs=search_item.id if search_item.type == "run" else None,
        )

    def _reject_duplicate_samples(self, samples: List[str]) -> None:
        """
        Raise if any sample name appears more than once, so we never accidentally
        download the same dataset twice.
        """

        duplicates = sorted({name for name in samples if samples.count(name) > 1})
        if duplicates:
            raise BaseSpaceDatasetError(
                f"Duplicate sample name(s) provided: {', '.join(duplicates)}. Provide each sample once."
            )

    def filter_datasets(
        self,
        samples: List[str],
        ds_items: List[DatasetItem],
        dataset_types: Optional[List[str]] = ["common.fastq"],
    ) -> List[DatasetItem]:
        """
        Filter a list of DatasetItems down to those of the requested dataset type(s)
        whose `DatasetItem.Name` has an exact match in the provided input `samples`.

        Args:
            samples: A list of sample names to filter by.
            ds_items: A list of DatasetItems to filter.
            dataset_types: Dataset types to keep (default `["common.fastq"]`); pass `None` to keep all types.

        Returns:
            A list of DatasetItems whose `DatasetItem.Name` is in the provided `samples`.
        """
        all_items: List[DatasetItem] = []
        unmatched_samples = []

        # Reject duplicate sample names up front so we don't accidentally download the same dataset more than once.
        self._reject_duplicate_samples(samples)

        # Narrow to the requested dataset type(s) before matching on sample name, so
        # same-named datasets of other types can't trip the ambiguity check below.
        typed_items = [
            ds_item for ds_item in ds_items if ds_item.matches_any_dataset_type(dataset_types)
        ]

        logger.info(
            f"Attempting to match {len(samples)} sample(s) to {len(typed_items)} dataset(s) "
            f"of type {dataset_types} (out of {len(ds_items)} total)"
        )

        # Check if any sample names match in the list of filtered DatasetItem(s)
        for sample in samples:
            matches = [ds_item for ds_item in typed_items if ds_item.name == sample]

            if not matches:
                unmatched_samples.append(sample)

            if len(matches) > 1:
                raise BaseSpaceDatasetError(
                    f"Multiple datasets (n={len(matches)}) found for sample `{sample}`. Provide a more specific sample name."
                )

            all_items.extend(matches)

        if unmatched_samples:
            raise BaseSpaceDatasetError(
                f"No dataset match found for sample(s): {', '.join(unmatched_samples)}"
            )

        logger.info(f"Matched {len(samples)} samples to {len(all_items)} dataset(s)")
        return all_items

    def prepare_dataset_files(
        self,
        ds_items: List[DatasetItem],
        validate: bool = True,
    ) -> List[StagedDatasetFile]:
        """
        Fetch each DatasetItem's files and pair them into StagedDatasetFiles.

        When `validate` is True, each pairing runs the paired-end model validators;
        `validate=False` uses `model_construct` to skip them.
        """
        all_staged_files: List[StagedDatasetFile] = []

        logger.info("Preparing dataset files for download")

        for item in ds_items:
            ds_files: List[DatasetFileItem] = self._fetch_all_items(
                endpoint_method=self.endpoints.datasets_files,
                dataset_id=item.id,
            )

            if validate:
                sdf = StagedDatasetFile(dataset_item=item, dataset_file_items=ds_files)
            else:
                sdf = StagedDatasetFile.model_construct(dataset_item=item, dataset_file_items=ds_files)

            logger.info(
                f"{'Validated' if validate else 'Unvalidated'} "
                f"dataset: `{item.name}` with {len(ds_files)} file(s) available for download"
            )

            all_staged_files.append(sdf)
        return all_staged_files

    def _stream_fastq_file(
        self,
        response: requests.Response,
        destination: Path,
        expected_size: Optional[int] = None,
        chunk_size: int = 8192,
        progress: bool = True,
    ) -> None:
        """
        Stream the content of a FASTQ file to a destination file.
        First, streams to a temporary file in the destination's directory, then
        renames it into place once the full body is written. A disrupted
        stream will only ever leave the temp file (which will get cleaned up).
        It will never leave a truncated file at the final path.

        Args:
            response: The `requests.Response` object to stream content from.
            destination: Path to save the streamed content.
            expected_size: Expected byte length (the file's `Size`); skipped if None.
            chunk_size: The size of each chunk to read from the response.
            progress: If True (default), draw the tqdm progress bar on a TTY. Set False to disable.
        """

        # Only draw the animated bar on a real terminal; tqdm defaults to stderr, so the
        # bar and the stdout log handler stay on separate streams and don't clobber each other.
        show_bar = progress and sys.stderr.isatty()

        # Create a temporary file in the same directory as the destination
        tmp_file = tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".tmp.{destination.name}.",
            delete=False,
        )
        tmp_path = Path(tmp_file.name)

        try:
            bytes_written = 0
            bar = tqdm(
                total=expected_size,
                desc=destination.name,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                disable=not show_bar,
                leave=False,
            )
            with tmp_file as outfile, bar:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        outfile.write(chunk)
                        bytes_written += len(chunk)
                        bar.update(len(chunk))

            if expected_size is not None and bytes_written != expected_size:
                raise BaseSpaceDownloadError(
                    f"Incomplete download for `{destination.name}`: wrote {bytes_written} byte(s), "
                    f"expected {expected_size}."
                )

            os.replace(tmp_path, destination)
        except BaseException:
            # Clean up the partial temp file on any failure (including interrupts).
            tmp_path.unlink(missing_ok=True)
            raise

    def download_dataset_files(
        self,
        staged_dataset_files: List[StagedDatasetFile],
        dest_dir: Optional[Path] = None,
        dry_run: bool = False,
        progress: bool = True,
    ) -> List[StagedDatasetFile]:
        """
        Stream each staged file's FASTQs to `dest_dir` under their original Illumina names,
        setting each `DatasetFileItem._local_path` so `concatenate_read_sets` can find them.

        Args:
            staged_dataset_files: The StagedDatasetFiles to download, from `prepare_dataset_files`.
            dest_dir: Destination directory (defaults to the current working directory).
            dry_run: If True, log what would be downloaded without fetching or writing anything.
            progress: If True (default), draw the tqdm progress bar on a TTY. Set False to disable.

        Returns:
            The same StagedDatasetFiles, with `_local_path` set on each file.
        """
        # Resolve the default at call time so it reflects the current cwd, then
        # ensure the destination exists for real downloads.
        dest_dir = dest_dir or Path.cwd()
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        for sdf in staged_dataset_files:
            ds_item_name = sdf.dataset_item.name
            ds_file_items: List[DatasetFileItem] = sdf.dataset_file_items

            # For each `DatasetItem.id` present, download all fastq files (`DatasetFileItem.id`)
            for file_item in ds_file_items:

                # Create and assign _local_path to `DatasetFileItem` for download/concatenation
                local_path = dest_dir / file_item.name
                file_item._local_path = local_path

                if dry_run:
                    logger.info(f"[dry-run] Would download FASTQ file `{file_item.name}` from dataset `{ds_item_name}`")
                    continue

                # Time the transfer so we can log a single persistent completion line.
                start = time.monotonic()

                # Stream the file straight to disk; `with` releases the connection even on a mid-stream error.
                with self.endpoints.files_content(
                    file_id=file_item.id,
                    stream=True,
                    redirect="true",
                ) as response:
                    self._stream_fastq_file(
                        response=response,
                        destination=file_item._local_path,
                        expected_size=file_item.size,
                        chunk_size=(1024 * 1024),
                        progress=progress,
                    )

                elapsed = time.monotonic() - start
                size_str = (
                    f"{file_item.size / (1024 * 1024):.1f} MB"
                    if file_item.size is not None else "unknown size"
                )
                logger.info(
                    f"Downloaded FASTQ file `{file_item.name}` from dataset `{ds_item_name}` "
                    f"({size_str} in {elapsed:.1f}s)"
                )

        total_files = sum(len(sdf.dataset_file_items) for sdf in staged_dataset_files)
        verb = "Would download" if dry_run else "Downloaded"
        logger.info(f"{verb} {total_files} FASTQ file(s) from {len(staged_dataset_files)} dataset(s) to `{dest_dir}`")
        return staged_dataset_files

    def concatenate_read_sets(
        self,
        staged_dataset_files: List[StagedDatasetFile],
        dry_run: bool = False,
    ) -> None:
        """
        Concatenate each read set's per-lane files into clean `{name}_R1.fastq.gz` /
        `{name}_R2.fastq.gz` outputs.

        Requires a prior `download_dataset_files` (or dry-run) pass: it reads each file's
        `_local_path`, which that step sets. For each read, the lane files are ordered by
        lane and joined at the byte level. Each output is written to a temp file first and
        renamed into place, so an interrupted concatenation never leaves a truncated file
        at the final path.

        Args:
            staged_dataset_files: The StagedDatasetFiles whose files are already on disk
                (each `DatasetFileItem._local_path` set by `download_dataset_files`).
            dry_run: If True, log the outputs that would be written without reading or
                writing any files.

        Raises:
            BaseSpaceDownloadError: If a concatenated output's size does not match the
                combined `Size` of its source files.
        """
        merged_dataset_files = defaultdict(list)

        # Combine/merge the read files of datasets with the same basename
        for sdf in staged_dataset_files:
            merged_dataset_files[sdf.read1_output_filename].extend(sdf.read1_files)
            merged_dataset_files[sdf.read2_output_filename].extend(sdf.read2_files)

        # Track only outputs we actually process (past both guards) so the summary
        # reflects real writes rather than every merged key.
        output_count = 0
        source_file_count = 0

        # Concatenate read files with the same basename
        for output_filename, read_files in merged_dataset_files.items():
            if not read_files:
                continue

            # Sort and filter for "laned" (`_LANE_PATTERN`) fastq files
            laned_files = sorted(
                (file_item for file_item in read_files if file_item.lane is not None),
                key=lambda file_item: file_item.lane or 0,
            )
            # Without lane tokens the files can't be ordered, so concatenation is skipped.
            # Warn rather than skip silently: these reads passed validation and were downloaded,
            # so a missing `{output_filename}` output would otherwise be invisible.
            if not laned_files:
                logger.warning(
                    f"No laned FASTQ files found for `{output_filename}` "
                    f"({len(read_files)} non-laned read file(s)); skipping concatenation for this output."
                )
                continue

            source_paths = [file_item._local_path for file_item in laned_files]
            output_path = source_paths[0].parent / output_filename

            output_count += 1
            source_file_count += len(source_paths)

            if dry_run:
                logger.info(
                    f"[dry-run] Would concatenate {len(source_paths)} laned FASTQ file(s) into `{output_path}`"
                )
                continue

            logger.info(f"Concatenating {len(source_paths)} laned FASTQ file(s) into `{output_path.name}`")

            # Write to a temp file in the destination dir, then atomically rename.
            tmp_file = tempfile.NamedTemporaryFile(
                dir=output_path.parent,
                prefix=f".tmp.{output_path.name}.",
                delete=False,
            )
            tmp_path = Path(tmp_file.name)

            try:
                with tmp_file as outfile:
                    for source_path in source_paths:
                        with open(source_path, "rb") as infile:
                            shutil.copyfileobj(infile, outfile, 1024 * 1024)

                # Verify the concatenated output matches the combined size the API
                # reported (skipped if any source is missing a Size).
                sizes = [file_item.size for file_item in laned_files]
                if all(size is not None for size in sizes):
                    bytes_written = tmp_path.stat().st_size
                    if bytes_written != sum(sizes):
                        raise BaseSpaceDownloadError(
                            f"Concatenated size mismatch for `{output_path.name}`: wrote {bytes_written} "
                            f"byte(s), expected {sum(sizes)}."
                        )

                os.replace(tmp_path, output_path)
            except BaseException:
                # Clean up the partial temp file on any failure (including interrupts).
                tmp_path.unlink(missing_ok=True)
                raise

        verb = "Would write" if dry_run else "Wrote"
        logger.info(
            f"{verb} {output_count} concatenated FASTQ output(s) "
            f"from {source_file_count} total FASTQ file(s)"
        )

    def fetch_sample_fastqs(
        self,
        collection_id: str,
        samples: List[str],
        dest_dir: Optional[Path] = None,
        dataset_types: Optional[List[str]] = ["common.fastq"],
        dry_run: bool = False,
        validate: bool = True,
        concatenate: bool = False,
        progress: bool = True,
    ):
        """
        Resolve a collection_id, find the datasets for the given sample(s), download
        their per-lane FASTQ files, and optionally concatenate them across lanes.

        Args:
            collection_id: A project/run ID or name to resolve.
            samples: The sample name(s) to download; each must match exactly one dataset.
            dest_dir: The directory to download files to (defaults to the current working directory).
            dataset_types: Dataset types to keep when filtering, defaults to ["common.fastq"].
            dry_run: If True, log what would be downloaded/concatenated without fetching or writing any files.
            validate: If True (default), require each dataset to be a balanced paired-end
                read set before downloading. Set False to skip the check.
            concatenate: If True, merge each sample's lane files into
                ``{sample}_R1/_R2.fastq.gz``. Defaults to False, leaving the per-lane files as-is.
            progress: If True (default), draw the tqdm progress bar on a TTY. Set False to disable.
        """

        if not samples:
            raise BaseSpaceDatasetError("No samples provided; nothing to fetch.")

        # Fail fast on duplicates before any network calls (also enforced in filter_datasets).
        self._reject_duplicate_samples(samples)

        # Resolve the collection_id to a SearchItem (project/run)
        search_item = self.resolve_collection_id(collection_id)

        # List every dataset for the resolved project/run (all types)
        all_ds_items = self.list_datasets(search_item)

        # Filter the datasets to the requested type(s) and provided sample names, error if any sample is unmatched or ambiguous.
        matched_ds_items = self.filter_datasets(
            samples=samples,
            ds_items=all_ds_items,
            dataset_types=dataset_types,
        )

        # Prepare datasets for download by validating/linking DatasetItem(s) and DatasetFileItem(s)
        # into a list of corresponding StagedDatasetFile(s)
        staged_ds_files = self.prepare_dataset_files(
            ds_items=matched_ds_items,
            validate=validate,
        )

        # Download the per-lane files for the matched datasets (or log if dry_run).
        self.download_dataset_files(
            staged_dataset_files=staged_ds_files,
            dest_dir=dest_dir,
            dry_run=dry_run,
            progress=progress,
        )

        # Concatenate the per-lane files into clean {sample}_R1/_R2.fastq.gz outputs.
        if concatenate:
            self.concatenate_read_sets(
                staged_dataset_files=staged_ds_files,
                dry_run=dry_run,
            )