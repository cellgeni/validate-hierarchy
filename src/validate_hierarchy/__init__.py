"""validate-hierarchy: validate directory and iRODS collection trees.

A hierarchy is described declaratively in YAML — regex name patterns plus
min/max cardinalities for files and sub-collections at every level — and
checked against either the local filesystem or an iRODS zone.
"""

from importlib.metadata import PackageNotFoundError, version

from validate_hierarchy.flatten import flatten_schema
from validate_hierarchy.models import (
    Collection,
    CollectionSchema,
    NameRule,
    ValidationIssue,
    ValidationReport,
)
from validate_hierarchy.report import (
    any_failed,
    collect_extra_paths,
    log_validation_report,
    render_markdown_report,
    render_text_report,
    render_text_report_summarised,
)
from validate_hierarchy.schema import SchemaError, load_schema_from_file
from validate_hierarchy.sources.local import load_collection_from_dir
from validate_hierarchy.validate import validate_collection

try:
    __version__ = version("validate-hierarchy")
except PackageNotFoundError:  # pragma: no cover - not installed (e.g. run from src)
    __version__ = "unknown"

__all__ = [
    "Collection",
    "CollectionSchema",
    "NameRule",
    "SchemaError",
    "ValidationIssue",
    "ValidationReport",
    "__version__",
    "any_failed",
    "collect_extra_paths",
    "flatten_schema",
    "load_collection_from_dir",
    "load_schema_from_file",
    "log_validation_report",
    "render_markdown_report",
    "render_text_report",
    "render_text_report_summarised",
    "validate_collection",
]
