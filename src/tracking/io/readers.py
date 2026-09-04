"""
Loading schema files.

Repeated blocks can be factored out in two interchangeable ways, both
supported, and usable together in the same schema:

1. !include directives, which split a schema over several files. Paths are
   resolved relative to the including file, and includes may nest.
2. YAML anchors and aliases, which keep everything in one self-contained file.
   Mapping keys beginning with '_' or 'x-' are ignored, so a schema may carry
   a section that exists purely to host anchors.

Anchors are resolved per file by the YAML parser, so an alias cannot refer to
an anchor declared in a different file; use !include to share across files and
anchors to share within one.
"""

from typing import Dict, Any, Optional
from pathlib import Path
import yaml

#: Mapping keys with these prefixes are dropped before schema validation, so a
#: schema can hold anchor-only sections that are not schema fields themselves.
ANCHOR_BLOCK_PREFIXES = ("_", "x-")


class SchemaError(Exception):
    """
    Raised when a schema file cannot be read or does not describe a schema.
    """


class IncludeLoader(yaml.SafeLoader):
    """
    YAML Loader with !include support.

    Subclasses SafeLoader, so anchors, aliases and merge keys keep working as
    standard YAML alongside the custom !include tag.
    """
    def __init__(self, stream):
        self._root = Path(getattr(stream, "name", ".")).resolve().parent
        super().__init__(stream)


def _construct_include(loader: IncludeLoader, node: yaml.nodes.ScalarNode):
    """
    Constructs an !include node by loading the specified file
    Args:
        loader (IncludeLoader): The YAML loader
        node (yaml.nodes.ScalarNode): The node containing the filename to include
    Returns:
        The contents of the included file
    """
    filename = loader.construct_scalar(node)
    filepath = (loader._root / filename).resolve()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.load(f, IncludeLoader)
    except OSError as exc:
        raise SchemaError(f"Cannot read included schema file {filepath}: {exc}") from exc


IncludeLoader.add_constructor("!include", _construct_include)


def _is_anchor_block(key: Any) -> bool:
    return isinstance(key, str) and key.startswith(ANCHOR_BLOCK_PREFIXES)


def _strip_anchor_blocks(node: Any, _memo: Optional[Dict[int, Any]] = None) -> Any:
    """
    Return `node` with all anchor-only mapping keys removed.

    Aliased nodes are the *same* Python object in several places once PyYAML
    has parsed the document, so results are memoised by object identity. That
    keeps the sharing intact, avoids re-walking heavily aliased schemas, and
    makes self-referential anchors terminate instead of recursing forever.
    """
    if _memo is None:
        _memo = {}
    if not isinstance(node, (dict, list)):
        return node

    key = id(node)
    if key in _memo:
        return _memo[key]

    if isinstance(node, dict):
        stripped: Dict[Any, Any] = {}
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


def load_raw_schema(path: str) -> Any:
    """
    Parse a schema file into plain Python data, without cleaning or validating.

    Args:
        path (str): Path to the schema file (YAML)

    Raises:
        SchemaError: If the file cannot be read or is not valid YAML
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.load(f, Loader=IncludeLoader)
    except OSError as exc:
        raise SchemaError(f"Cannot read schema file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise SchemaError(f"Invalid YAML in schema file {path}: {exc}") from exc


def load_schema_from_file(path: str) -> Dict[str, Any]:
    """
    Load a YAML schema from a file, supporting !include directives and anchors
    Args:
        path (str): Path to the schema file (YAML)

    Raises:
        SchemaError: If the file cannot be read, is not valid YAML, or does not
            hold a mapping at the top level

    Returns:
        Dict[str, Any]: The loaded schema as a dictionary
    """
    data = _strip_anchor_blocks(load_raw_schema(path))
    if not isinstance(data, dict):
        raise SchemaError(
            f"Schema file {path} must contain a mapping at the top level, "
            f"got {type(data).__name__}"
        )
    return data
