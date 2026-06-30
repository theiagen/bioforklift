import re
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import requests
from pydantic.alias_generators import to_pascal

from .basespace_client import BaseSpaceClient
from .basespace_endpoints import BaseSpaceEndpoints
from .basespace_exceptions import (
    BaseSpaceCollectionIdError,
    BaseSpaceDatasetError,
    BaseSpaceMissingReadError,
)
from .basespace_models import (
    BaseSpaceResponse,
    DatasetFileItem,
    DatasetItem,
    ItemType,
    Paging,
    SearchItem,
)
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class BaseSpaceMethods:
    """
    Class meant to handle BaseSpace API interactions for BioForklift
    """

    def __init__(self, client: BaseSpaceClient):
        self.client = client
        self.endpoints = BaseSpaceEndpoints(client)

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
                paging=Paging(offset=offset, limit=1000),
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

    def filter_datasets(
        self,
        samples: List[str],
        ds_items: List[DatasetItem],
    ) -> List[DatasetItem]:
        """
        Filter a list of DatasetItems to those whose `DatasetItem.Name`
        has an exact match in the provided input `samples`.

        Args:
            samples: A list of sample names to filter by.
            ds_items: A list of DatasetItems to filter.

        Returns:
            A list of DatasetItems whose `DatasetItem.Name` is in the provided `samples`.
        """

        all_items: List[DatasetItem] = []
        unmatched_samples = []

        for sample in samples:
            matches = [
                ds_item
                for ds_item in ds_items
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
        return all_items

    def list_datasets(
        self,
        search_item: SearchItem,
        dataset_types: Optional[str] = "common.fastq",
    ) -> List[DatasetItem]:
        """
        Get every dataset for a given project or run, paging through all results.

        Args:
            search_item: The resolved SearchItem object ("project" or "run").
            dataset_types: Optional comma-separated list of dataset types to filter by.

        Returns:
            A list of all datasets associated with the specified project or run.
        """

        return self._fetch_all_items(
            self.endpoints.datasets,
            project_id=search_item.id if search_item.type == "project" else None,
            input_runs=search_item.id if search_item.type == "run" else None,
            dataset_types=dataset_types,
        )

    def _stream_fastq_file(
        self,
        response: requests.Response,
        destination: Path,
        chunk_size: int = 8192,
    ) -> None:
        """
        Stream the content of a FASTQ file to a destination file.

        Args:
            response: The `requests.Response` object to stream content from.
            destination: Path to save the streamed content.
            chunk_size: The size of each chunk to read from the response.
        """

        with open(destination, "wb") as outfile:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    outfile.write(chunk)

    def download_dataset_files(
        self,
        ds_items: List[DatasetItem],
        dest_dir: Optional[Path] = None,
        dry_run: bool = False,
    ) -> List[Tuple[str, Path]]:
        """
        Download the files for a list of DatasetItems.

        Args:
            ds_items: A list of DatasetItems to download files for.
            dest_dir: The directory to download files to (defaults to the current
                working directory).
            dry_run: If True, log what would be downloaded without fetching or
                writing any files.
        Returns:
            A list of ``(file_name, dest_path)`` tuples that were (or, for a dry
            run, would be) downloaded.
        """

        # Resolve the default at call time so it reflects the current cwd, then
        # ensure the destination exists for real downloads.
        dest_dir = dest_dir or Path.cwd()
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        download_files: List[Tuple[str, Path]] = []

        for item in ds_items:
            ds_files: List[DatasetFileItem] = self._fetch_all_items(
                endpoint_method=self.endpoints.datasets_files,
                dataset_id=item.id,
            )

            # `attributes` is optional, so guard before reading the paired-end flag.
            is_paired_end = bool(item.attributes and item.attributes.is_paired_end)

            # If the dataset is paired-end, expect an even file count that splits into
            # matched R1/R2 reads (one R2 for every R1, across lanes). Read number is
            # parsed from the standard `_R{read}_001.fastq` token in the file name.
            if is_paired_end:
                read1_files = [file for file in ds_files if re.search(r"_R1_\d+\.fastq", file.name)]
                read2_files = [file for file in ds_files if re.search(r"_R2_\d+\.fastq", file.name)]
                if (
                    len(ds_files) < 2
                    or len(ds_files) % 2 != 0
                    or len(read1_files) != len(read2_files)
                    or len(read1_files) == 0
                ):
                    raise BaseSpaceMissingReadError(
                        f"Dataset `{item.name}` is paired-end but its files are not balanced "
                        f"R1/R2 (R1={len(read1_files)}, R2={len(read2_files)}, total={len(ds_files)})."
                    )

            for file_item in ds_files:
                dest_path = dest_dir / file_item.name
                download_files.append((file_item.name, dest_path))

                if dry_run:
                    logger.info(f"[dry-run] Would download `{file_item.name}` to `{dest_path}`")
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
                        destination=dest_path,
                        chunk_size=(1024 * 1024)
                    )
        logger.info(f"Downloaded {len(download_files)} FASTQ file(s) from {len(ds_items)} dataset(s) to `{dest_dir}`")
        return download_files

    def fetch_sample_fastqs(
        self,
        collection_id: str,
        samples: List[str],
        dest_dir: Optional[Path] = None,
        dataset_types: str = "common.fastq",
        dry_run: bool = False,
    ) -> List[Tuple[str, Path]]:
        """
        Resolve a collection_id, find the datasets for the given sample(s), and
        download their FASTQ files.

        Args:
            collection_id: A project/run ID or name to resolve.
            samples: The sample name(s) to download; each must match exactly one dataset.
            dest_dir: The directory to download files to (defaults to the current working directory).
            dataset_types: Comma-separated dataset types to list, defaults to "common.fastq".
            dry_run: If True, log what would be downloaded without fetching or writing any files.

        Returns:
            A list of ``(file_name, dest_path)`` tuples that were (or, for a dry
            run, would be) downloaded.
        """

        if not samples:
            raise BaseSpaceDatasetError("No samples provided; nothing to fetch.")

        # Resolve the collection_id to a SearchItem (project/run)
        search_item = self.resolve_collection_id(collection_id)

        # List all datasets for the resolved project/run, filtering by dataset_types if provided.
        all_ds_items = self.list_datasets(
            search_item,
            dataset_types=dataset_types
        )

        # Filter the datasets to those that match the provided sample names, error if any sample is unmatched or ambiguous.
        matched_ds_items = self.filter_datasets(samples, all_ds_items)

        # Download the files for the matched datasets, streaming them to disk (or logging if dry_run).
        return self.download_dataset_files(
            matched_ds_items,
            dest_dir=dest_dir,
            dry_run=dry_run,
        )