from typing import Annotated, Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, Tag, Discriminator, computed_field
from pydantic.alias_generators import to_pascal


class BaseSpaceAPIModel(BaseModel):
    """Base class for BaseSpace API models."""

    model_config = ConfigDict(
        alias_generator=to_pascal,
        populate_by_name=True,
        extra="ignore",
    )


class SearchQuery(BaseModel):
    """Defines a search query for BaseSpace"""
    field: Optional[str] = None
    value: Optional[str] = None
    # Allows us to support (field + value) queries as well as (from_lucene_query) literal strings for more complex queries.
    _raw: Optional[str] = None

    @computed_field
    @property
    def as_string(self) -> str:
        """Construct the query string for this search scope."""
        field = f"{self.field}:" if self.field else ""
        value = f'"{self.value}"' if (self.field and self.value) else ""
        if self._raw is not None:
            return f"{self._raw}"
        return f'{field}{value}'

    @classmethod
    def from_lucene_query(cls, query_str: str) -> "SearchQuery":
        """
        Wrap a raw Lucene query string verbatim (no parsing/validation).
        See: https://lucene.apache.org/core/2_9_4/queryparsersyntax.html
        """
        return cls(_raw=query_str)

    def __str__(self) -> str:
        return self.as_string


class Paging(BaseSpaceAPIModel):
    """The ``Paging`` block returned by v2 list/search endpoints."""

    offset: Optional[int] = None
    limit: Optional[int] = None
    sort_dir: Optional[Literal["Asc", "Desc"]] = None
    sort_by: Optional[str] = None


class PagingResponse(Paging):
    """The full body of a paginated response"""
    displayed_count: int
    total_count: int


class RunData(BaseSpaceAPIModel):
    """
    The `Run` key/dict nested inside a list of dict `Items` from the `/search?scope=runs` endpoint.
    """

    id: str
    name: Optional[str] = None
    experiment_name: Optional[str] = None


class RunItem(BaseSpaceAPIModel):
    """
    A single `Items` entry from the `/search?scope=runs` endpoint.
    The `Type` field on each item determines which of these nested objects is present.
    """

    type: Literal["run"]
    data: RunData = Field(alias="Run")


class ProjectData(BaseSpaceAPIModel):
    """
    The `Project` key/dict nested inside a list of dict `Items` from the `/search?scope=projects` endpoint.
    """
    id: str
    name: Optional[str] = None


class ProjectItem(BaseSpaceAPIModel):
    """
    A single `Items` entry from the `/search?scope=projects` endpoint.
    The `Type` field on each item determines which of these nested objects is present.
    """
    type: Literal["project"]
    data: ProjectData = Field(alias="Project")


class DatasetType(BaseSpaceAPIModel):
    """
    The `DatasetType` key/dict nested inside a list of dict `Items` from the `/datasets` endpoint when searching for datasets.
    """
    id: str
    name: Optional[str] = None
    conforms_to_ids: List[str] = Field(default_factory=list)


class CommonFastqAttributes(BaseSpaceAPIModel):
    is_paired_end: Optional[bool] = None
    max_length_read1: Optional[int] = None
    max_length_read2: Optional[int] = None
    # to_pascal turns "..._pf" into "...Pf", so the PF fields need explicit aliases.
    total_clusters_pf: Optional[int] = Field(default=None, alias="TotalClustersPF")
    total_clusters_raw: Optional[int] = None
    total_reads_pf: Optional[int] = Field(default=None, alias="TotalReadsPF")
    total_reads_raw: Optional[int] = None


class DatasetAttributes(BaseSpaceAPIModel):
    common_fastq: Optional[CommonFastqAttributes] = Field(default=None, alias="common_fastq")


class DatasetItem(BaseSpaceAPIModel):
    """
    A single `Items` entry from the `/datasets` endpoint when searching for datasets.
    """
    id: str
    name: Optional[str] = None
    dataset_type: Optional[DatasetType] = None
    attributes: Optional[DatasetAttributes] = None


class UnknownItem(BaseSpaceAPIModel):
    """
    Fallback for item shapes not yet modeled. Keeps the raw payload (extra='allow')
    instead of raising an error, so new scopes don't break.
    """
    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True, extra="allow")



def _item_type(value: Any) -> str:
    if isinstance(value, BaseModel):
        return {
            RunItem: "run",
            ProjectItem: "project",
            DatasetItem: "dataset",
            UnknownItem: "unknown"
        }.get(type(value), "unknown")

    if isinstance(value, dict):
        if (
            "Project" in value and
            value.get("Type", "").lower() == "project"
        ):
            return "project"
        if (
            "Run" in value and
            value.get("Type", "").lower() == "run"
        ):
            return "run"
        if (
            value.get("Id", "").startswith("ds.")
        ):
            return "dataset"
    return "unknown"


# Each `Item` has it's own unique structure and are discriminated by the
# _item_type function, which looks for the presence of certain keys and values
# to parse responses/results into distinct models.
Item = Annotated[
    Union[
        Annotated[RunItem, Tag("run")],
        Annotated[ProjectItem, Tag("project")],
        Annotated[DatasetItem, Tag("dataset")],
        Annotated[UnknownItem, Tag("unknown")],
    ],
    Discriminator(_item_type),
]


# Items returned by the `/search` endpoint: projects and runs, with anything from other
# scopes (samples, genomes, appresults, ...) falling through to `UnknownItem`.
SearchItem = Annotated[
    Union[
        Annotated[RunItem, Tag("run")],
        Annotated[ProjectItem, Tag("project")],
        Annotated[UnknownItem, Tag("unknown")],
    ],
    Discriminator(_item_type),
]


class BaseSpaceResponse[ItemType](BaseSpaceAPIModel):
    """
    A generic response model for BaseSpace API calls, containing a list of `Items`
    and a `Paging` block. The expected item type is specified per call, e.g.
    ``BaseSpaceResponse[DatasetItem].model_validate(...)``.
    """

    items: List[ItemType]
    paging: PagingResponse