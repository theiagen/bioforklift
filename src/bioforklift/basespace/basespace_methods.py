import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import requests
from pydantic.alias_generators import to_pascal

from .basespace_endpoints import BaseSpaceEndpoints
from .basespace_exceptions import (
    BaseSpaceCollectionIdError,
    BaseSpaceDatasetError,
    BaseSpaceDownloadError,
    BaseSpaceMissingReadError,
)
from .basespace_models import (
    BaseSpaceResponse,
    DatasetFileItem,
    DatasetItem,
    DownloadedFileItem,
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

    def _matches_dataset_type(
        self,
        ds_item: DatasetItem,
        dataset_types: List[str]
    ) -> bool:
        """
        True if `ds_item` matches any requested dataset type, either directly by
        `DatasetType.Id` or by conformance (`ConformsToIds`). The conformance check
        catches typed variants like `illumina.fastq.v1.8`, which conform to
        `common.fastq` but do not match it by Id.
        """
        if ds_item.dataset_type is None:
            return False
        requested = set(dataset_types)
        return (
            ds_item.dataset_type.id in requested
            or bool(requested.intersection(ds_item.dataset_type.conforms_to_ids))
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

        The dataset-type filter is applied first (matching on `DatasetType.Id` or
        `ConformsToIds`, see `_matches_dataset_type`); the sample-name match then runs
        over that narrowed set.

        Args:
            samples: A list of sample names to filter by.
            ds_items: A list of DatasetItems to filter.
            dataset_types: Dataset types to keep, defaults to `["common.fastq"]`.

        Returns:
            A list of DatasetItems whose `DatasetItem.Name` is in the provided `samples`.
        """

        # Resolve the default here so this stays the single owner of the default dataset_types
        dataset_types = dataset_types or ["common.fastq"]

        all_items: List[DatasetItem] = []
        unmatched_samples = []

        # Reject duplicate sample names up front so we don't accidentally download the same dataset more than once.
        self._reject_duplicate_samples(samples)

        # Narrow to the requested dataset type(s) before matching on sample name, so
        # same-named datasets of other types can't trip the ambiguity check below.
        typed_items = [
            ds_item for ds_item in ds_items if self._matches_dataset_type(ds_item, dataset_types)
        ]

        logger.info(
            f"Filtering for {len(samples)} sample(s) against {len(typed_items)} dataset(s) "
            f"of type {dataset_types} (out of {len(ds_items)} total)"
        )

        for sample in samples:
            matches = [
                ds_item
                for ds_item in typed_items
                if ds_item.name == sample
            ]
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

        logger.info(f"Found {len(all_items)} dataset(s) matching the provided sample(s)")
        return all_items

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

        return self._fetch_all_items(
            self.endpoints.datasets,
            project_id=search_item.id if search_item.type == "project" else None,
            input_runs=search_item.id if search_item.type == "run" else None,
        )


    def _validate_paired_end(
        self,
        ds_item: DatasetItem,
        ds_files: List[DownloadedFileItem],
    ) -> bool:
        """
        Validate that a dataset's files form a balanced paired-end read set.

        Every file must be a standard Illumina read file carrying the `_R1_` / `_R2_`
        nomenclature, and the dataset must contain an equal, non-zero number of R1 and
        R2 files (nothing else is allowed).

        Args:
            ds_item: The dataset the fastq files belong to.
            ds_files: The files listed for the dataset.

        Returns:
            True if the files are a valid, balanced paired-end read set.

        Raises:
            BaseSpaceMissingReadError: If the dataset is not flagged paired-end, if any
                file breaks the `_R[1|2]_` naming convention, or the R1/R2 files are not
                balanced (no R1s or unequal R1/R2 counts).
        """

        # `attributes` is optional, so guard before reading the paired-end flag.
        is_paired_end = bool(ds_item.attributes and ds_item.attributes.is_paired_end)
        if not is_paired_end:
            raise BaseSpaceMissingReadError(
                f"DatasetItem `{ds_item.name}` is missing `paired_end` attribute; only paired-end datasets are supported."
            )

        # Expect an even file count that splits into matched R1/R2 reads (one R2 for
        # every R1, across lanes). Read number is parsed from the standard
        # `_R{read}_001.fastq` token in the file name. Every file must be an R1/R2
        # read; anything else fails loudly rather than being silently downloaded or missed.
        read1_files = [file for file in ds_files if file.is_valid_read1]
        read2_files = [file for file in ds_files if file.is_valid_read2]
        if (
            len(read1_files) == 0
            or len(read1_files) != len(read2_files)
            or len(read1_files) + len(read2_files) != len(ds_files)
        ):
            raise BaseSpaceMissingReadError(
                f"Dataset `{ds_item.name}` is paired-end but its files are not balanced "
                f"R1/R2 (R1={len(read1_files)}, R2={len(read2_files)}, total={len(ds_files)}). "
                f"Every file must be an R1 or R2 read."
            )

        return True

    def _stream_fastq_file(
        self,
        response: requests.Response,
        destination: Path,
        expected_size: Optional[int] = None,
        chunk_size: int = 8192,
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
        """

        # Create a temporary file in the same directory as the destination
        tmp_file = tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".tmp.{destination.name}.",
            delete=False,
        )
        tmp_path = Path(tmp_file.name)

        try:
            bytes_written = 0
            with tmp_file as outfile:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        outfile.write(chunk)
                        bytes_written += len(chunk)

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
        ds_items: List[DatasetItem],
        dest_dir: Optional[Path] = None,
        dry_run: bool = False,
        validate: bool = True,
    ) -> Dict[str, List[DownloadedFileItem]]:
        """
        Download the FASTQ files for a list of paired-end DatasetItems.

        Unless `validate` is False, each dataset is validated as a balanced paired-end
        read set (see `_validate_paired_end`) before anything is downloaded. Files are
        streamed to `dest_dir/{file.name}` under their original Illumina names and kept
        in place; `concatenate_read_sets` merges them across lanes afterwards.

        Args:
            ds_items: A list of DatasetItems to download files for.
            dest_dir: The directory to download files to (defaults to the current
                working directory).
            dry_run: If True, log what would be downloaded without fetching or
                writing any files.
            validate: If True (default), require each dataset to be a balanced
                paired-end read set before downloading. Set False to skip the check.
        Raises:
            BaseSpaceMissingReadError: If `validate` is True and a dataset's files are
                not a balanced set of R1/R2 reads (no R1s, unequal R1/R2 counts, or any
                non-R1/R2 file present).
        Returns:
            A dict mapping DatasetItem names to lists of DownloadedFileItems (each
            carrying its `local_path`) for the downloaded FASTQ files of each dataset.
        """

        # Resolve the default at call time so it reflects the current cwd, then
        # ensure the destination exists for real downloads.
        dest_dir = dest_dir or Path.cwd()
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        read_sets: Dict[str, List[DownloadedFileItem]] = {}

        for item in ds_items:
            ds_files: List[DatasetFileItem] = self._fetch_all_items(
                endpoint_method=self.endpoints.datasets_files,
                dataset_id=item.id,
            )

            # Wrap each raw API file in a DownloadedFileItem carrying its resolved local path
            downloaded_files = [
                DownloadedFileItem(
                    **file_item.model_dump(),
                    local_path=dest_dir / file_item.name
                ) for file_item in ds_files
            ]

            # Validate the dataset is a balanced paired-end read set before downloading
            if validate:
                self._validate_paired_end(item, downloaded_files)

            for file_item in downloaded_files:
                if dry_run:
                    logger.info(f"[dry-run] Would download `{file_item.name}` to `{file_item.local_path}`")
                    continue

                logger.info(f"Downloading FASTQ file `{file_item.name}` from dataset `{item.name}`")

                # Stream the file straight to disk; `with` releases the connection even on a mid-stream error.
                with self.endpoints.files_content(
                    file_id=file_item.id,
                    stream=True,
                    redirect="true",
                ) as response:
                    self._stream_fastq_file(
                        response=response,
                        destination=file_item.local_path,
                        expected_size=file_item.size,
                        chunk_size=(1024 * 1024),
                    )

            # Keep every file (each with its resolved `local_path`) so concatenation can group by read/lane.
            read_sets[item.name] = downloaded_files

        total_files = sum(len(files) for files in read_sets.values())
        logger.info(f"Downloaded {total_files} FASTQ file(s) from {len(ds_items)} dataset(s) to `{dest_dir}`")
        return read_sets


    def concatenate_read_sets(
        self,
        read_sets: Dict[str, List[DownloadedFileItem]],
        dry_run: bool = False,
    ) -> List[Tuple[str, Path]]:
        """
        Concatenate each read set's per-lane files into clean `{name}_R1.fastq.gz` /
        `{name}_R2.fastq.gz` outputs.

        The per-lane files produced by `download_dataset_files` are expected to already
        be on disk. For each read, the lane files are ordered by lane and joined at the
        byte level. Each output is written to a temp file first and renamed into place, so an
        interrupted concatenation never leaves a truncated file at the final path.

        Args:
            read_sets: A mapping of sample name -> its downloaded DownloadedFileItems (each
                carrying a `local_path`), as returned by `download_dataset_files`.
            dry_run: If True, log the outputs that would be written without reading or
                writing any files.

        Raises:
            BaseSpaceDownloadError: If a concatenated output's size does not match the
                combined `Size` of its source files.

        Returns:
            A list of ``(output_name, output_path)`` tuples for each concatenated read.
        """

        outputs: List[Tuple[str, Path]] = []

        for sample_name, ds_files in read_sets.items():
            read1_files = [file for file in ds_files if file.is_valid_read1]
            read2_files = [file for file in ds_files if file.is_valid_read2]

            for read_number, read_files in ((1, read1_files), (2, read2_files)):
                if not read_files:
                    continue

                # Lane ordering only matters for the concatenated output, so sort here.
                ordered_files = sorted(read_files, key=lambda file: file.lane or 0)
                source_paths = [file.local_path for file in ordered_files]
                output_path = source_paths[0].parent / f"{sample_name}_R{read_number}.fastq.gz"
                outputs.append((output_path.name, output_path))

                if dry_run:
                    logger.info(
                        f"[dry-run] Would concatenate {len(source_paths)} lane file(s) into `{output_path}`"
                    )
                    continue

                logger.info(f"Concatenating {len(source_paths)} lane file(s) into `{output_path.name}`")

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
                    sizes = [file.size for file in ordered_files]
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

        logger.info(f"Wrote {len(outputs)} concatenated FASTQ output(s)")
        return outputs

    def fetch_sample_fastqs(
        self,
        collection_id: str,
        samples: List[str],
        dest_dir: Optional[Path] = None,
        dataset_types: Optional[List[str]] = None,
        dry_run: bool = False,
        validate: bool = True,
        concatenate: bool = True,
    ) -> List[Tuple[str, Path]]:
        """
        Resolve a collection_id, find the datasets for the given sample(s), download
        their per-lane FASTQ files, and (by default) concatenate them across lanes.

        Args:
            collection_id: A project/run ID or name to resolve.
            samples: The sample name(s) to download; each must match exactly one dataset.
            dest_dir: The directory to download files to (defaults to the current working directory).
            dataset_types: Dataset types to keep when filtering, defaults to ["common.fastq"].
            dry_run: If True, log what would be downloaded/concatenated without fetching or writing any files.
            validate: If True (default), require each dataset to be a balanced paired-end
                read set before downloading. Set False to skip the check.
            concatenate: If True (default), merge each sample's lane files into
                ``{sample}_R1/_R2.fastq.gz``. If False, leave the per-lane files as-is.

        Returns:
            A list of ``(name, path)`` tuples: the concatenated ``{sample}_R1/_R2.fastq.gz``
            outputs when ``concatenate`` is True, otherwise the individual per-lane files.
            For a dry run these are the files/outputs that would have been written.
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
            dataset_types=dataset_types
        )

        # Download the per-lane files for the matched datasets (or log if dry_run).
        read_sets = self.download_dataset_files(
            matched_ds_items,
            dest_dir=dest_dir,
            dry_run=dry_run,
            validate=validate,
        )

        if not concatenate:
            # Return the individual per-lane files as (name, path) tuples.
            return [
                (file_item.name, file_item.local_path)
                for ds_files in read_sets.values()
                for file_item in ds_files
            ]

        # Concatenate the per-lane files into clean {sample}_R1/_R2.fastq.gz outputs.
        return self.concatenate_read_sets(read_sets, dry_run=dry_run)