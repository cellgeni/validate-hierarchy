from typing import Dict, Any
from pathlib import Path
import yaml


class SchemaError(Exception):
    """
    Raised when a schema file cannot be read or does not describe a schema.
    """


class IncludeLoader(yaml.SafeLoader):
    """
    YAML Loader with !include support
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


def load_schema_from_file(path: str) -> Dict[str, Any]:
    """
    Load a YAML schema from a file, supporting !include directives
    Args:
        path (str): Path to the schema file (YAML)

    Raises:
        SchemaError: If the file cannot be read or is not valid YAML

    Returns:
        Dict[str, Any]: The loaded schema as a dictionary
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.load(f, Loader=IncludeLoader)
    except OSError as exc:
        raise SchemaError(f"Cannot read schema file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise SchemaError(f"Invalid YAML in schema file {path}: {exc}") from exc
