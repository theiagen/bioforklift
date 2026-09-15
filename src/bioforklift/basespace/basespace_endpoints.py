from typing import Callable, List, Literal, Optional

import requests
from pydantic import validate_call

from .basespace_client import BaseSpaceClient
from .basespace_exceptions import BaseSpaceServerError
from .basespace_models import (
    BaseSpaceResponse,
    DatasetFileItem,
    DatasetItem,
    Paging,
    SearchItem,
    ItemType,
)
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


def fetch_all_items(
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


class BaseSpaceEndpoints:
    """
    This class contains the endpoints for the BaseSpace API.
    """

    def __init__(self, client: BaseSpaceClient):
        self.client = client

    @validate_call
    def search(
        self,
        query: str,
        scope: Literal["runs", "projects", "genomes", "samples", "appresults", "sample_files", "appresult_files", None] = None,
        paging: Optional[Paging] = None,
        **extra_params,
    ) -> BaseSpaceResponse[SearchItem]:
        """
        Search BaseSpace within a scope using a raw Lucene query clause.
        https://developer.basespace.illumina.com/docs/content/documentation/rest-api/search-api-reference#SearchQueryqueryOptions

        Args:
            scope: The scope of the search ("projects", "runs", "genomes", "samples", "appresults", "sample_files", "appresult_files").
            query: A raw Lucene query string, e.g. `project.Id:"489069003"` or `ExperimentName:"My Run"`.
                BaseSpace matches field names without case sensitivity; quote values that contain spaces.
            paging: Optional paging parameters.
            **extra_params: Any additional query params passed through to the endpoint.
        Returns:
            The parsed v2 `/search` body, with items typed as `SearchItem`.
        """

        paging = paging or Paging()

        logger.info(f"Searching BaseSpace with: scope=`{scope}` & query=`{query}`")

        try:
            response = self.client.get(
                endpoint="search",
                params={
                    "scope": scope,
                    "query": query,
                    **paging.model_dump(by_alias=True, exclude_none=True),
                    **extra_params,
                }
            )
        except BaseSpaceServerError:
            # A 500 response here could be an indication of an invalid/unescaped query rather than an outage.
            logger.error(
                f"BaseSpace returned a server error for query: `{query}`. "
                f"This can happen when the query contains invalid special characters."
            )
            raise
        return BaseSpaceResponse[SearchItem].model_validate(response.json())

    @validate_call
    def datasets(
        self,
        project_id: Optional[str] = None,
        input_runs: Optional[str] = None,
        dataset_types: Optional[str] = None,
        paging: Optional[Paging] = None,
        **extra_params,
    ) -> BaseSpaceResponse[DatasetItem]:
        """
        Get a list of datasets, optionally scoped to a project or run and filtered by type.
        https://developer.basespace.illumina.com/docs/content/documentation/rest-api/api-reference#operation--datasets-get

        Args:
            project_id: Restrict to datasets in this project (can accept comma-separated str of project IDs).
            input_runs: Restrict to datasets produced by this run (can accept comma-separated str of run IDs).
            dataset_types: Restrict to these dataset types, e.g. "common.fastq" (can accept comma-separated str of dataset types).
            paging: Optional paging parameters.
            **extra_params: Any additional query params passed through to the endpoint.
        Returns:
            The parsed `/datasets` body, with items typed as `DatasetItem`.
        """

        paging = paging or Paging()

        logger.info(
            f"Fetching BaseSpace datasets with: "
            f"{'project_id=' + project_id + ' ' if project_id else ''}"
            f"{'input_runs=' + input_runs + ' ' if input_runs else ''}"
            f"{'dataset_types=' + dataset_types + ' ' if dataset_types else ''}"
        )

        response = self.client.get(
            endpoint="datasets",
            params = {
                **({"projectid": project_id} if project_id else {}),
                **({"inputruns": input_runs} if input_runs else {}),
                **({"datasettypes": dataset_types} if dataset_types else {}),
                **paging.model_dump(by_alias=True, exclude_none=True),
                **extra_params,
            }
        )

        body = response.json()
        paging_info = body.get("Paging", {})
        logger.info(
            f"Fetched {paging_info.get('DisplayedCount', 0)} dataset(s) from BaseSpace "
            f"(total_count={paging_info.get('TotalCount', 0)}, "
            f"offset={paging_info.get('Offset', 0)}, limit={paging_info.get('Limit', 0)})"
        )
        return BaseSpaceResponse[DatasetItem].model_validate(body)

    @validate_call
    def dataset_files(
        self,
        dataset_id: str,
        paging: Optional[Paging] = None,
        **extra_params,
    ) -> BaseSpaceResponse[DatasetFileItem]:
        """
        Get a list of files for a given dataset.
        https://developer.basespace.illumina.com/docs/content/documentation/rest-api/api-reference#operation--datasets--id--files-get

        Args:
            dataset_id: The `DatasetItem.id` to fetch files for.
            paging: Optional paging parameters.
            **extra_params: Any additional query params passed through to the endpoint.
        Returns:
            The parsed `/datasets/{dataset_id}/files` body, with items typed as `DatasetFileItem`.
        """

        paging = paging or Paging()

        logger.debug(f"Fetching BaseSpace dataset files for dataset_id=`{dataset_id}`")

        response = self.client.get(
            endpoint=f"datasets/{dataset_id}/files",
            params = {
                **paging.model_dump(by_alias=True, exclude_none=True),
                **extra_params,
            }
        )
        return BaseSpaceResponse[DatasetFileItem].model_validate(response.json())

    @validate_call
    def file_content(
        self,
        file_id: str,
        stream: bool = True,
        redirect: Literal["true", "meta"] = "true",
    ) -> requests.Response:
        """
        Get the content of a file by its ID.
        https://developer.basespace.illumina.com/docs/content/documentation/rest-api/api-reference#operation--files--id--content-get

        Args:
            file_id: The `DatasetFileItem.id` to fetch content for.
            stream: Whether to stream the response content (True) or immediately download (False).
            redirect: Whether this method should return a standard 302 redirect or
                a meta JSON response containing the redirect_uri.

        Returns:
            The raw `requests.Response`. Unlike the other endpoints, this returns
            the response object (not a parsed model) so the caller can stream the
            file bytes.
        """

        logger.debug(f"Fetching BaseSpace file content for file_id=`{file_id}`")

        response = self.client.get(
            endpoint=f"files/{file_id}/content",
            params = {
                "redirect": redirect,
            },
            stream=stream,
        )
        return response
