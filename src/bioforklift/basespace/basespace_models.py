from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, computed_field
from pydantic.alias_generators import to_pascal


class BaseSpaceAPIModel(BaseModel):
    """Base class for BaseSpace API models."""

    model_config = ConfigDict(
        alias_generator=to_pascal,
        populate_by_name=True,
        extra="ignore",
    )


class Query(BaseModel):
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
    def from_lucene_query(cls, query_str: str) -> "Query":
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


class ProjectData(BaseSpaceAPIModel):
    """
    The `Project` key/dict nested inside a list of dict `Items` from the `/search?scope=projects` endpoint.
    """
    id: str
    name: Optional[str] = None


class RunItem(BaseSpaceAPIModel):
    """
    A single `Items` entry from the `/search?scope=runs` endpoint.
    The `Type` field on each item determines which of these nested objects is present.
    """

    type: Literal["run"]
    data: RunData = Field(alias="Run")


class ProjectItem(BaseSpaceAPIModel):
    """
    A single `Items` entry from the `/search?scope=projects` endpoint.
    The `Type` field on each item determines which of these nested objects is present.
    """
    type: Literal["project"]
    data: ProjectData = Field(alias="Project")


# Each `Item` has it's own unique structure but all share a `type` field that determines which one it is,
# so we can use that as a discriminator to parse them into distinct models.
Item = Annotated[
    Union[ProjectItem, RunItem],
    Field(discriminator="type"),
]

class SearchResponse(BaseSpaceAPIModel):
    """
    The full body of a `/search` endpoint call.
    """

    items: List[Item]
    paging: PagingResponse