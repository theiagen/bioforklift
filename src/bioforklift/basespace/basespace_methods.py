from typing import List, Optional, Tuple
from .basespace_client import BaseSpaceClient
from .basespace_endpoints import BaseSpaceEndpoints
from .basespace_exceptions import (
  BaseSpaceCollectionIdError,
)
from .basespace_models import (
    BaseSpaceResponse,
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
            # `UnknownItem` (and any non-search item) has no `.data`; skip it.
            data = getattr(item, "data", None)
            if data is None:
                continue
            if all(getattr(data, field, None) == value for field, value in criteria.items()):
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
                matches[(item.type, item.data.id)] = item

        if not matches:
            raise BaseSpaceCollectionIdError(
                f"Could not resolve input collection ID `{collection_id}`: no project or "
                f"run exactly matches it by id or name."
            )
        if len(matches) > 1:
            described = ", ".join(
                f"{item.type} {item.data.id} ({item.data.name})"
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
        datasets_response: BaseSpaceResponse[DatasetItem],
        sample_list: List[str],
    ) -> List[DatasetItem]:


    def list_datasets(
        self,
        item_type: str,
        item_id: str,
        dataset_types: Optional[str] = "common.fastq",
        paging: Paging = Paging(limit=1000),
    ) -> list[str]:
        """
        Get a list of dataset IDs for a given project or run.

        Args:
            item_type: The resolved type of the item ("project" or "run").
            item_id: The resolved ID of the project or run.
            dataset_types: Optional comma-separated list of dataset types to filter by.
        Returns:
            A list of datasets associated with the specified project or run.
        """
        params = {}
        if item_type == "project":
            params["projectid"] = item_id
        if item_type == "run":
            params["inputruns"] = item_id

        response = self.endpoints.datasets(
            project_id=params.get("projectid"),
            input_runs=params.get("inputruns"),
            dataset_types=dataset_types,
            paging=paging
        )

        return [ds.id for ds in response.items]
