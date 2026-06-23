import requests

from pydantic import validate_call
from typing import Literal, Optional
from .basespace_client import BaseSpaceClient
from .basespace_exceptions import (
  BaseSpaceServerError,
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

class BaseSpaceEndpoints:
    """
    This class contains the endpoints for the BaseSpace API.
    """

    def __init__(self, client: BaseSpaceClient):
        self.client = client


    @validate_call
    def search(
        self,
        scope: Literal[None, "runs", "projects", "genomes", "samples", "appresults", "sample_files", "appresult_files"] = None,
        query: SearchQuery = SearchQuery(),
        paging: Paging = Paging(),
        **extra_params,
    ) -> BaseSpaceResponse[SearchItem]:
        """
        Search BaseSpace within a scope for a single field/term.
        https://developer.basespace.illumina.com/docs/content/documentation/rest-api/search-api-reference#SearchQueryqueryOptions

        Args:
            scope: The scope of the search ("projects" or "runs")
            query_field: The field to match (e.g., "run.Name", "run.ExperimentName", "run.Id", "project.Name", "project.Id")
            query_value: The value to search for
        Returns:
            The parsed v2 search body, e.g. {"Items": [...], "Paging": {...}}
        """

        logger.info(f"Searching BaseSpace with: scope=`{scope}` & query=`{query}`")

        try:
            response = self.client.get(
                endpoint="search",
                params={
                    **({"scope": scope} if scope else {}),
                    **({"query": query.as_string} if query.as_string else {}),
                    **paging.model_dump(by_alias=True, exclude_none=True),
                    **extra_params,
                }
            )
        except BaseSpaceServerError:
            logger.error(
                f"BaseSpace returned a server error for query: `{query.as_string}`. "
                f"This can happen when the query contains invalid special characters."
            )
            raise

        return BaseSpaceResponse[SearchItem].model_validate(response.json())


    def datasets(
        self,
        project_id: Optional[str] = None,
        input_runs: Optional[str] = None,
        dataset_types: Optional[str] = None,
        paging: Paging = Paging(),
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
        logger.info(
            f"Fetching BaseSpace datasets "
            f"{'project_id=' + project_id if project_id else ''}, "
            f"{'input_runs=' + input_runs if input_runs else ''}, "
            f"{'dataset_types=' + dataset_types if dataset_types else ''}"
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

        displayed_count = response.json().get("Paging", {}).get("DisplayedCount", 0)
        total_count = response.json().get("Paging", {}).get("TotalCount", 0)
        offset = response.json().get("Paging", {}).get("Offset", 0)
        limit = response.json().get("Paging", {}).get("Limit", 0)

        logger.info(
            f"Fetched {displayed_count} dataset(s) from BaseSpace "
            f"(total_count={total_count}, offset={offset}, limit={limit})"
        )

        return BaseSpaceResponse[DatasetItem].model_validate(response.json())


    def datasets_files(
        self,
        dataset_id: str,
        filehrefcontentresolution: Optional[bool] = None,
        paging: Paging = Paging(),
        **extra_params,
    ) -> BaseSpaceResponse[DatasetFileItem]:
        """
        Get a list of files for a given dataset.
        https://developer.basespace.illumina.com/docs/content/documentation/rest-api/api-reference#operation--datasets--id--files-get

        Args:
            dataset_id: The `DatasetItem.id` to fetch files for.
            filehrefcontentresolution: Optional flag to include file href content resolution.
            paging: Optional paging parameters.
            **extra_params: Any additional query params passed through to the endpoint.
        Returns:
            The parsed `/datasets/{dataset_id}/files` body, with items typed as `DatasetFileItem`.
        """

        logger.info(f"Fetching BaseSpace files for dataset_id=`{dataset_id}`")

        response = self.client.get(
            endpoint=f"datasets/{dataset_id}/files",
            params = {
                **({"filehrefcontentresolution": filehrefcontentresolution} if filehrefcontentresolution else {}),
                **paging.model_dump(by_alias=True, exclude_none=True),
                **extra_params,
            }
        )

        return BaseSpaceResponse[DatasetFileItem].model_validate(response.json())


    def files_content(
        self,
        file_id: str,
        redirect: Optional[bool] = None,
        stream: bool = True,
    ) -> requests.Response:
        """
        Get the content of a file by its ID.
        https://developer.basespace.illumina.com/docs/content/documentation/rest-api/api-reference#operation--files--id--content-get

        Args:
            file_id: The `DatasetFileItem.id` to fetch content for.
            redirect: Optional flag to follow redirects.
            stream: Whether to stream the response content.
        Returns:
            The raw response from the BaseSpace API, which may be a redirect or the file content.
        """

        response = self.client.get(
            endpoint=f"files/{file_id}/content",
            params = {
                **({"redirect": redirect} if redirect is not None else {}),
            },
            stream=stream,
        )

        return response
