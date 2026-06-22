from pydantic import validate_call
from typing import List, Literal

from .basespace_client import BaseSpaceClient

from .basespace_exceptions import (
  BaseSpaceCollectionIdError,
  BaseSpaceServerError,
)
from .basespace_models import (
    Item,
    Paging,
    Query,
    SearchResponse,
)
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)

class BaseSpaceMethods:
    """
    Class meant to handle BaseSpace API interactions for BioForklift
    """

    def __init__(self, client: BaseSpaceClient):
        self.client = client


    @validate_call
    def search(
        self,
        scope: Literal[None, "runs", "projects", "genomes", "samples", "appresults", "sample_files", "appresult_files"] = None,
        query: Query = Query(),
        paging: Paging = Paging(),
    ) -> SearchResponse:
        """
        Search BaseSpace within a scope for a single field/term.

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
                    **paging.model_dump(by_alias=True, exclude_none=True)
                }
            )
        except BaseSpaceServerError:
            logger.error(
                f"BaseSpace returned a server error for query: `{query.as_string}`. "
                f"This can happen when the query contains invalid special characters."
            )
            raise

        return SearchResponse.model_validate(response.json())


    def filter_search_response(
        self,
        search_response: SearchResponse,
        criteria: dict,
    ) -> List[Item]:
        """
        Filter a search response's items for those whose data matches all field==value pairs exactly.

        Args:
            search_response: The full body of a `/search` endpoint call.
            criteria: A dictionary of field==value pairs to filter by.
        Returns:
            The items whose data matches all field==value pairs exactly.
        """
        return [
            item for item in search_response.items
            if all(
                getattr(item.data, field, None) == value
                for field, value in criteria.items()
            )
        ]


    def resolve_collection_id(self, collection_id: str) -> str:
        """
        Resolve an input "collection_id" to its BaseSpace project/run. A "collection_id"
        can be a project/run ID or a project/run name. If no resource matches, or if
        more than one does, the input was not specific enough to be resolved, and an error is raised.

        Args:
            collection_id: The user-provided identifier for a project or run, which may be an ID or a name.
        Returns:
            The matched project/run's BaseSpace `Id`.
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
            response = self.search(
                scope=scope,
                query=Query(field=field, value=collection_id),
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
            f"Input collection ID `{collection_id}` resolved to `{item.data.id}` ({item.type}.id)"
        )
        return item.data.id