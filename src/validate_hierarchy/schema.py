"""Loading and validating hierarchy schema files.

Schemas are YAML (JSON is accepted too, being a subset of YAML). Repeated
blocks can be factored out in **two interchangeable ways, both supported, and
usable together in the same schema**:

1. ``!include`` directives — split a schema over several files::

       data_objects: !include _dataset_files.yml

   Paths are resolved relative to the *including* file, and includes may nest.

2. YAML anchors and aliases — plain YAML, no custom tags, one self-contained
   file. Declare a block once with ``&name`` and reuse it with ``*name``::

       data_objects: &gene_files
         - pattern: '^Features\\.stats$'
           min: 1
           max: 1
       # ... elsewhere ...
       data_objects: *gene_files

   Mapping keys beginning with ``_`` or ``x-`` are ignored by the loader, so a
   schema may also carry a section that exists purely to host anchors::

       _definitions:
         gene_files: &gene_files
           - pattern: '^Features\\.stats$'
             min: 1
             max: 1

Anchors are resolved per file by the YAML parser, so an alias cannot refer to
an anchor declared in a different file; use ``!include`` to share across files
and anchors to share within one.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from validate_hierarchy.models import CollectionSchema

#: Mapping keys with these prefixes are dropped before schema validation, so a
#: schema can hold anchor-only sections that are not schema fields themselves.
ANCHOR_BLOCK_PREFIXES = ("_", "x-")


class SchemaError(Exception):
    """Raised when a schema file cannot be read or does not describe a schema."""


class IncludeLoader(yaml.SafeLoader):
    """YAML loader with ``!include`` support.

    Subclasses `SafeLoader`, so anchors, aliases and merge keys keep working as
    standard YAML alongside the custom ``!include`` tag.
    """

    def __init__(self, stream):
        self._root = Path(getattr(stream, "name", ".")).resolve().parent
        super().__init__(stream)


def _construct_include(loader: IncludeLoader, node: yaml.nodes.ScalarNode):
    """Resolve an ``!include <file>`` node relative to the including file."""
    filename = loader.construct_scalar(node)
    filepath = (loader._root / filename).resolve()
    try:
        with open(filepath, encoding="utf-8") as f:
            return yaml.load(f, IncludeLoader)
    except OSError as exc:
        raise SchemaError(f"Cannot read included schema file {filepath}: {exc}") from exc


IncludeLoader.add_constructor("!include", _construct_include)


def _is_anchor_block(key: Any) -> bool:
    return isinstance(key, str) and key.startswith(ANCHOR_BLOCK_PREFIXES)


def _strip_anchor_blocks(node: Any, _memo: dict[int, Any] | None = None) -> Any:
    """Return `node` with all anchor-only mapping keys removed.

    Aliased nodes are the *same* Python object in several places once PyYAML has
    parsed the document, so results are memoised by object identity. That keeps
    the sharing intact, avoids re-walking heavily aliased schemas, and makes
    self-referential anchors terminate instead of recursing forever.
    """
    if _memo is None:
        _memo = {}
    if not isinstance(node, (dict, list)):
        return node

    key = id(node)
    if key in _memo:
        return _memo[key]

    if isinstance(node, dict):
        stripped: dict[Any, Any] = {}
        _memo[key] = stripped
        for k, v in node.items():
            if _is_anchor_block(k):
                continue
            stripped[k] = _strip_anchor_blocks(v, _memo)
        return stripped

    items: list = []
    _memo[key] = items
    items.extend(_strip_anchor_blocks(v, _memo) for v in node)
    return items


def load_raw_schema(path: str | Path) -> Any:
    """Parse a schema file into plain Python data, without validating it."""
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.load(f, Loader=IncludeLoader)
    except OSError as exc:
        raise SchemaError(f"Cannot read schema file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise SchemaError(f"Invalid YAML in schema file {path}: {exc}") from exc


def load_schema_from_file(path: str | Path) -> CollectionSchema:
    """Load, clean and validate a schema file into a `CollectionSchema`.

    Raises:
        SchemaError: if the file is unreadable, is not valid YAML, or does not
            describe a valid schema (including unknown or misspelled keys).
    """
    data = _strip_anchor_blocks(load_raw_schema(path))
    if not isinstance(data, dict):
        raise SchemaError(
            f"Schema file {path} must contain a mapping at the top level, "
            f"got {type(data).__name__}"
        )
    try:
        return CollectionSchema.model_validate(data)
    except ValidationError as exc:
        raise SchemaError(f"Invalid schema in {path}:\n{_format_errors(exc)}") from exc


def _format_errors(exc: ValidationError) -> str:
    """Render pydantic errors as one indented, location-prefixed line each."""
    lines = []
    seen: set[str] = set()
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        line = f"  {location}: {error['msg']}"
        if line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)
