"""Data model for validated hierarchies and for the schemas describing them.

A *hierarchy* is a tree of `Collection` nodes: each node has a name, a list of
child collections and a list of leaf names (`data_objects`). Both the local
filesystem loader and the iRODS loader build this same model, so validation and
reporting are storage agnostic.
"""

import re
from datetime import datetime
from pathlib import PurePosixPath
from re import Pattern
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

IssueKind = Literal[
    "load_error",
    "name_mismatch",
    "missing_files",
    "too_many_files",
    "unexpected_files",
    "missing_collections",
    "too_many_collections",
    "unexpected_collections",
    "missing_metadata_keys",
]


class ValidationIssue(BaseModel):
    """A single problem found while validating a collection against a schema."""

    path: str
    kind: IssueKind
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    """The result of validating one collection tree against a schema."""

    path: str
    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class Collection(BaseModel):
    """A node in a hierarchy: sub-collections plus the leaf names it contains.

    `metadata` is only ever populated by the iRODS loader (AVUs); local
    directories carry none. The timestamps are informational — validation never
    reads them — and are whatever the backend reports: UTC-aware from the local
    loader, naive UTC from iRODS.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    name: str
    path: PurePosixPath
    metadata: dict[str, list[str]] = Field(default_factory=dict)
    collections: list['Collection'] = Field(default_factory=list)
    data_objects: list[str] = Field(default_factory=list)
    create_time: datetime | None = None
    modify_time: datetime | None = None


class NameRule(BaseModel):
    """A regex pattern plus how many entries are allowed to match it.

    `max: null` (or a missing `max`) means unbounded.
    """

    model_config = ConfigDict(extra="forbid")

    pattern: Pattern[str]
    min: int = 1
    max: int | None = None
    description: str | None = None

    @field_validator("pattern", mode="before")
    @classmethod
    def compile_pattern(cls, v):
        return re.compile(v) if isinstance(v, str) else v


class CollectionSchema(BaseModel):
    """The expected shape of one collection and, recursively, its children."""

    model_config = ConfigDict(extra="forbid")

    name: NameRule = Field(
        default_factory=lambda: NameRule(pattern=re.compile(r'.*'), min=1, max=None)
    )
    metadata_keys: set[str] = Field(default_factory=set)
    data_objects: list[NameRule] = Field(default_factory=list)
    collections: list['CollectionSchema'] = Field(default_factory=list)
    allow_extra_files: bool = False
    allow_extra_collections: bool = False
