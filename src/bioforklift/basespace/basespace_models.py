from typing import Annotated, Any, Generic, List, Literal, Optional, TypeVar, Union

from pydantic import AliasPath, BaseModel, ConfigDict, Discriminator, Field, Tag
from pydantic.alias_generators import to_pascal


class BaseSpaceAPIModel(BaseModel):
    """
    Base class for BaseSpace API models.
    """

    # Automatically convert snake_case field names to PascalCase for BaseSpace API compatibility.
    model_config = ConfigDict(
        alias_generator=to_pascal,
        populate_by_name=True,
        extra="ignore",
    )


# =========================================================================
# Models for `/search` endpoint
# =========================================================================


class RunItem(BaseSpaceAPIModel):
    """
    A single entry in the `Items` list from the `/search?scope=runs` endpoint.
    """

    type: Literal["run"]
    id: str = Field(validation_alias=AliasPath("Run", "Id")) # maps to the nested path ("Run": {"Id": ...})
    name: Optional[str] = Field(default=None, validation_alias=AliasPath("Run", "Name"))
    experiment_name: Optional[str] = Field(default=None, validation_alias=AliasPath("Run", "ExperimentName"))


class ProjectItem(BaseSpaceAPIModel):
    """
    A single entry in the `Items` list from the `/search?scope=projects` endpoint.
    """

    type: Literal["project"]
    id: str = Field(validation_alias=AliasPath("Project", "Id")) # maps to the nested path ("Project": {"Id": ...})
    name: Optional[str] = Field(default=None, validation_alias=AliasPath("Project", "Name"))


class OtherItem(BaseSpaceAPIModel):
    """
    Fallback for item shapes not yet modeled. Keeps the raw payload (extra='allow')
    instead of raising an error, so new scopes don't break.
    """

    model_config = ConfigDict(
        alias_generator=to_pascal,
        populate_by_name=True,
        extra="allow"
    )


def _search_item_type(value: Any) -> str:
    """
    Discriminator for a `SearchItem`. Serves as a map to model and distinguish raw `/search`
    result dicts to their corresponding model instances. Includes a fallback to `OtherItem`.
    """
    if isinstance(value, BaseModel):
        return {
            RunItem: "run",
            ProjectItem: "project",
            OtherItem: "other",
        }.get(type(value), "other")

    if isinstance(value, dict):
        if "Project" in value and value.get("Type", "").lower() == "project":
            return "project"
        if "Run" in value and value.get("Type", "").lower() == "run":
            return "run"
    return "other"


# Type alias representing a single entry in the `Items` list returned by the `/search` endpoint
# Pydantic resolves which model applies via the `_search_item_type` discriminator function
SearchItem = Annotated[
    Union[
        Annotated[RunItem, Tag("run")],
        Annotated[ProjectItem, Tag("project")],
        Annotated[OtherItem, Tag("other")],
    ],
    Discriminator(_search_item_type),
]


# =========================================================================
# Models for `/datasets` endpoint
# =========================================================================


class CommonFastqAttributes(BaseSpaceAPIModel):
    """
    Maps to the `Attributes.common_fastq` block in a single `DatasetItem` entry.
    Describes attributes returned by the `/datasets` endpoint for datasets of type `common.fastq`.
    """

    is_paired_end: Optional[bool] = None
    max_length_read1: Optional[int] = None
    max_length_read2: Optional[int] = None
    total_clusters_pf: Optional[int] = Field(default=None, alias="TotalClustersPF") # explicit alias to match BaseSpace API
    total_clusters_raw: Optional[int] = None
    total_reads_pf: Optional[int] = Field(default=None, alias="TotalReadsPF") # explicit alias to match BaseSpace API
    total_reads_raw: Optional[int] = None


class DatasetType(BaseSpaceAPIModel):
    """
    Maps to the `DatasetType` block in a single `DatasetItem` entry.
    Describes the type of dataset, e.g. `common.fastq` returned by the `/datasets` endpoint.
    """

    id: str
    conforms_to_ids: List[str] = Field(default_factory=list)


class DatasetItem(BaseSpaceAPIModel):
    """
    A single entry in the `Items` list returned by the `/datasets` endpoint when searching for datasets.
    """

    id: str
    name: Optional[str] = None
    dataset_type: Optional[DatasetType] = None
    attributes: Optional[CommonFastqAttributes] = Field(
        default=None,
        validation_alias=AliasPath("Attributes", "common_fastq") # maps to the nested path ("Attributes": {"common_fastq": ...})
    )


class DatasetFileItem(BaseSpaceAPIModel):
    """
    A single entry in the `Items` list returned by the `/datasets/{dataset_id}/files` endpoint when searching for dataset files.
    """

    id: str
    name: str
    size: Optional[int] = None  # bytes; used to verify a complete download


# =========================================================================
# Models for all endpoints
# =========================================================================


class Paging(BaseSpaceAPIModel):
    """
    The `Paging` block returned by v2 list/search endpoints.
    """

    offset: Optional[int] = None
    limit: Optional[int] = None
    sort_dir: Optional[Literal["Asc", "Desc"]] = None
    sort_by: Optional[str] = None


class PagingResponse(Paging):
    """
    The full body of a paginated response.
    """

    displayed_count: int
    total_count: int


ItemType = TypeVar("ItemType")


class BaseSpaceResponse(BaseSpaceAPIModel, Generic[ItemType]):
    """
    A generic response model for all BaseSpace API calls, containing a list of `Items`
    and a `Paging` block. The expected item type is specified per call, e.g.
    ``BaseSpaceResponse[DatasetItem].model_validate(...)``.
    """

    items: List[ItemType]
    paging: PagingResponse