from pathlib import Path
import re
from typing import Annotated, Any, Generic, List, Literal, Optional, TypeVar, Union

from pydantic import AliasPath, BaseModel, ConfigDict, Discriminator, Field, PrivateAttr, Tag, model_validator
from pydantic.alias_generators import to_pascal

from .basespace_exceptions import (
    BaseSpaceMissingReadError,
)

_R1_PATTERN = re.compile(r"[_-]R1.*\.fastq\.gz$", re.IGNORECASE)
_R2_PATTERN = re.compile(r"[_-]R2.*\.fastq\.gz$", re.IGNORECASE)
_LANE_PATTERN = re.compile(r"[_-]L(\d{3,})", re.IGNORECASE)

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
    name: str
    dataset_type: Optional[DatasetType] = None
    attributes: Optional[CommonFastqAttributes] = Field(
        default=None,
        validation_alias=AliasPath("Attributes", "common_fastq") # maps to the nested path ("Attributes": {"common_fastq": ...})
    )

    def matches_any_dataset_type(
        self,
        dataset_type_list: Optional[List[str]] = None
    ) -> bool:
        """
        True if `dataset_type_list` is None (match all types) or the dataset matches any
        requested type by `DatasetType.Id` or conformance (`ConformsToIds`). Conformance
        catches typed variants like `illumina.fastq.v1.8`, which conform to `common.fastq`
        without matching it by Id.
        """
        # `None` means "match every type"; an empty list matches nothing.
        if dataset_type_list is None:
            return True
        if self.dataset_type is None:
            return False
        requested = set(dataset_type_list)
        return (
            self.dataset_type.id in requested
            or bool(requested.intersection(self.dataset_type.conforms_to_ids))
        )


class DatasetFileItem(BaseSpaceAPIModel):
    """
    A single entry in the `Items` list returned by the `/datasets/{dataset_id}/files` endpoint when searching for dataset files.
    """

    id: str
    name: str
    size: Optional[int] = None  # bytes; used to verify a complete download

    # Set by `download_dataset_files` once the destination is known; None until then.
    _local_path: Optional[Path] = PrivateAttr(default=None)

    @property
    def is_valid_read1(self) -> bool:
        return bool(_R1_PATTERN.search(self.name))

    @property
    def is_valid_read2(self) -> bool:
        return bool(_R2_PATTERN.search(self.name))

    @property
    def lane(self) -> Optional[int]:
        match = _LANE_PATTERN.search(self.name)
        return int(match.group(1)) if match else None


class StagedDatasetFile(BaseModel):
    """
    A `DatasetItem` paired with its `DatasetFileItem`s, enriched for the download pipeline.
    """

    dataset_item: DatasetItem
    dataset_file_items: List[DatasetFileItem]

    @property
    def basename(self) -> str:
        # Dataset names can be lane-split (e.g. `..._rep02_L001`); strip the lane so those
        # datasets collapse into one `_R1/_R2` output during concatenation.
        match = _LANE_PATTERN.search(self.dataset_item.name)
        return self.dataset_item.name[:match.start()] if match else self.dataset_item.name

    def _output_filename(self, read_number: int) -> str:
        return f"{self.basename}_R{read_number}.fastq.gz"

    @property
    def read1_output_filename(self) -> str:
        return self._output_filename(1)

    @property
    def read2_output_filename(self) -> str:
        return self._output_filename(2)

    @property
    def read1_files(self) -> List[DatasetFileItem]:
        return [file for file in self.dataset_file_items if file.is_valid_read1]

    @property
    def read2_files(self) -> List[DatasetFileItem]:
        return [file for file in self.dataset_file_items if file.is_valid_read2]

    @model_validator(mode="after")
    def check_paired_end_flag(self) -> "StagedDatasetFile":
        """Require the dataset to be flagged paired-end (`attributes` is optional)."""
        is_paired_end = bool(self.dataset_item.attributes and self.dataset_item.attributes.is_paired_end)
        if not is_paired_end:
            raise BaseSpaceMissingReadError(
                f"DatasetItem `{self.dataset_item.name}` is not flagged paired-end; only paired-end datasets are supported."
            )
        return self

    @model_validator(mode="after")
    def check_balanced_reads(self) -> "StagedDatasetFile":
        """Require an equal, non-zero R1/R2 count with no other files present."""
        if (
            len(self.read1_files) == 0
            or len(self.read1_files) != len(self.read2_files)
            or len(self.read1_files) + len(self.read2_files) != len(self.dataset_file_items)
        ):
            raise BaseSpaceMissingReadError(
                f"Unbalanced R1/R2 files for `{self.dataset_item.name}` "
                f"(R1={len(self.read1_files)}, R2={len(self.read2_files)}, total={len(self.dataset_file_items)}). "
                f"Every file must be an R1 or R2 read."
            )
        return self


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