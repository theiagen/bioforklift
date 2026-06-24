from pathlib import Path
from typing import List, Optional, Tuple

import requests
from .basespace_client import BaseSpaceClient
from .basespace_endpoints import BaseSpaceEndpoints
from .basespace_exceptions import (
  BaseSpaceCollectionIdError,
  BaseSpaceDatasetError,
)
from .basespace_models import (
    BaseSpaceResponse,
    DatasetFileItem,
    DatasetItem,
    Paging,
    SearchItem,
    SearchQuery,
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


    def filter_search_response(
        self,
        search_response: BaseSpaceResponse[SearchItem],
        criteria: dict,
    ) -> List[SearchItem]:
        """
        Filter a search response's items for those whose data matches all field==value pairs exactly.

        Args:
            search_response: The full body of a `/search` endpoint call.
            criteria: A dictionary of field==value pairs to filter by.
        Returns:
            The items whose data matches all field==value pairs exactly.
        """
        matches = []
        for item in search_response.items:
            if all(getattr(item, field) == value for field, value in criteria.items()):
                matches.append(item)
        return matches


    def resolve_collection_id(self, collection_id: str) -> Tuple[str, str]:
        """
        Resolve an input "collection_id" to its BaseSpace project/run. A "collection_id"
        can be a project/run ID or a project/run name. If no resource matches, or if
        more than one does, the input was not specific enough to be resolved, and an error is raised.

        Args:
            collection_id: The user-provided identifier for a project or run, which may be an ID or a name.
        Returns:
            A tuple containing the matched project/run's BaseSpace `type` and `id`.
        """
        logger.info(f"Resolving BaseSpace collection ID: `{collection_id}`")

        # Fields a collection_id could match, as (scope, field). Each `field` is
        # both the search field and the data attribute we re-check for an exact
        # match, since BaseSpace search is fuzzy and can return near-misses.

        # "run.Name"           refers to `Run ID` in BaseSpace UI
        # "run.ExperimentName" refers to `Run Name` in BaseSpace UI
        # "run.Id"             refers to numerical ID found in the BaseSpace HTTP URL (ex https://basespace.illumina.com/run/315086826/details)
        # "project.Name"       refers to name under the Projects tab in BaseSpace UI
        # "project.Id"         refers to numerical ID found in the BaseSpace HTTP URL (ex https://basespace.illumina.com/projects/489069003/about)

        search_fields = [
            ("runs", "id"),
            ("runs", "name"),
            ("runs", "experiment_name"),
            ("projects", "id"),
            ("projects", "name"),
        ]

        # Candidates keyed by (type, id) so one resource matched via several
        # fields collapses to a single entry, while genuinely different resources
        # stay separate and trip the ambiguity check below.
        matches = {}

        for scope, field in search_fields:
            response = self.endpoints.search(
                scope=scope,
                query=SearchQuery(field=field, value=collection_id),
            )

            exact_matches = self.filter_search_response(response, {field: collection_id})

            if response.items:
                logger.info(f"Found {len(exact_matches)} hit(s) after exact match filtering. (Total returned: {len(response.items)})")
                logger.debug(f"{response}")

            for item in exact_matches:
                matches[(item.type, item.id)] = item

        if not matches:
            raise BaseSpaceCollectionIdError(
                f"Could not resolve input collection ID `{collection_id}`: no project or "
                f"run exactly matches it by id or name."
            )
        if len(matches) > 1:
            described = ", ".join(
                f"{item.type} {item.id} ({item.name})"
                for item in matches.values()
            )
            raise BaseSpaceCollectionIdError(
                f"Input collection ID `{collection_id}` is ambiguous; it matches: "
                f"{described}. Provide a more specific id or name."
            )

        item = next(iter(matches.values()))
        logger.info(
            f"Input collection ID `{collection_id}` resolved to `{item.id}` ({item.type}.id)"
        )
        return (item.type, item.id)


    def filter_datasets_response(
        self,
        sample_list: List[str],
        ds_items: List[DatasetItem],
    ) -> List[DatasetItem]:
        """
        Filter a list of DatasetItems to those whose `DatasetItem.Name`
        has an exact match in the provided `sample_list`.

        Args:
            sample_list: A list of sample names to filter by.
            ds_items: A list of DatasetItems to filter.
        Returns:
            A list of DatasetItems whose `DatasetItem.Name` is in the provided `sample_list`.
        """
        all_items: list[DatasetItem] = []
        unmatched_samples = []

        for sample in sample_list:
            matches = [
                ds_item
                for ds_item in ds_items
                if ds_item.name == sample
            ]
            if not matches:
                unmatched_samples.append(sample)

            if len(matches) > 1:
                logger.warning(
                    f"Multiple datasets (n={len(matches)}) found for sample `{sample}`. "
                    f"Returning all matches."
                )

            all_items.extend(matches)

        if unmatched_samples:
            raise BaseSpaceDatasetError(f"No dataset match found for sample(s): {', '.join(unmatched_samples)}")

        return all_items


    def list_datasets(
        self,
        item_type: str,
        item_id: str,
        dataset_types: Optional[str] = "common.fastq",
        paging: Paging = Paging(),
    ) -> list[DatasetItem]:
        """
        Get a list of dataset IDs for a given project or run.

        Args:
            item_type: The resolved type of the item ("project" or "run").
            item_id: The resolved ID of the project or run.
            dataset_types: Optional comma-separated list of dataset types to filter by.
        Returns:
            A list of datasets associated with the specified project or run.
        """
        all_items: list[DatasetItem] = []

        params = {}
        if item_type == "project":
            params["projectid"] = item_id
        if item_type == "run":
            params["inputruns"] = item_id

        # Overwrite paging any `offset` or `limit` to ensure we don't miss any datasets
        paging.offset = 0
        paging.limit = 1000

        while True:
            paging.offset = len(all_items)

            ds = self.endpoints.datasets(
                project_id=params.get("projectid"),
                input_runs=params.get("inputruns"),
                dataset_types=dataset_types,
                paging=paging
            )

            all_items.extend(ds.items)

            if not ds.items or (ds.paging.displayed_count + ds.paging.offset) >= ds.paging.total_count:
                break

        return all_items


    def stream_fastq_file(
        self,
        response: requests.Response,
        destination: Optional[Path] = None,
        chunk_size: int = 8192,
    ) -> Optional[bytes]:
        """
        Stream the content of a FASTQ file to a destination file or return it as bytes.

        Args:
            response: The `requests.Response` object to stream content from.
            destination: Optional path to save the streamed content.
            chunk_size: The size of each chunk to read from the response.
        Returns:
            If `destination` is None, returns the content as bytes.
            Otherwise, saves to the specified file and returns None.
        """
        if destination:
            with open(destination, "wb") as outfile:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        outfile.write(chunk)
        else:
            content = bytearray()
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    content.extend(chunk)
            return bytes(content)



    def download_dataset_files(
        self,
        ds_items: List[DatasetItem],
        dest_dir: Path = Path.cwd(),
    ):
        """
        Download the files for a list of DatasetItems.

        Args:
            dest_dir: The directory to download files to.
            ds_items: A list of DatasetItems to download files for.
        Returns:
            A list of DatasetFileItems representing the downloaded files.
        """

        for item in ds_items:
            logger.info(f"Downloading FASTQ files for dataset `{item.name}`")

            ds_file = self.endpoints.datasets_files(
                dataset_id=item.id,
                filehrefcontentresolution=True,
                paging=Paging(limit=1000)
            )

            if item.attributes.is_paired_end and (
                len(ds_file.items) < 2 or
                len(ds_file.items) % 2 != 0
            ):
                logger.warning(f"Dataset `{item.name}` is paired-end but has an unexpected number of files.")

            for file_item in ds_file.items:
                logger.info(f"Downloading file `{file_item.name}` from dataset `{item.name}`")
                response = self.endpoints.files_content(
                    file_id=file_item.id,
                    redirect=True,
                    stream=True
                )

                dest_path = dest_dir / file_item.name
                self.stream_fastq_file(
                    response=response,
                    destination=dest_path,
                    chunk_size=(1024 * 1024)
                )
                logger.info(f"Saved file `{file_item.name}` to `{dest_path}`")
            break
        return
