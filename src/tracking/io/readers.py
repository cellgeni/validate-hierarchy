import csv
import json
from typing import List, Dict, Any
from pathlib import Path
import yaml


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
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.load(f, IncludeLoader)


IncludeLoader.add_constructor("!include", _construct_include)


def load_schema_from_file(path: str) -> Dict[str, Any]:
    """
    Load a YAML schema from a file, supporting !include directives
    Args:
        path (str): Path to the schema file (YAML)
    Returns:
        Dict[str, Any]: The loaded schema as a dictionary
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.load(f, Loader=IncludeLoader)
    return data



def load_records(path: str, fmt: str) -> List[Dict[str, Any]]:
    """
    Load records from a file in the specified format (CSV or JSON)
    Args:
        path (str): Path to the input file
        fmt (str): Format of the input file (csv or json)

    Raises:
        ValueError: If the format is unsupported

    Returns:
        List[Dict[str, Any]]: A list of records loaded from the file
    """
    fmt = fmt.lower()
    if fmt == "csv":
        return _read_csv(path)
    if fmt == "json":
        return _read_json(path)
    if fmt in ("jsonl", "ndjson"):
        return _read_jsonl(path)
    raise ValueError("Unsupported format: " + fmt)


def _read_csv(path: str) -> List[Dict[str, Any]]:
    """
    Read records from a CSV file
    Args:
        path (str): Path to the CSV file

    Returns:
        List[Dict[str, Any]]: A list of records loaded from the CSV file
    """
    with Path(path).open("r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        return [row for row in reader]


def _read_json(path: str) -> List[Dict[str, Any]]:
    """
    Read records from a JSON file
    Args:
        path (str): Path to the JSON file

    Raises:
        ValueError: If the JSON file is not valid

    Returns:
        List[Dict[str, Any]]: A list of records loaded from the JSON file
    """
    with Path(path).open("r", encoding="utf-8") as jsonfile:
        data = json.load(jsonfile)

    if not data:
        return []

    if not isinstance(data, list):
        raise ValueError("JSON file must contain a list of records")
    return data


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    """
    Read records from a JSONL (JSON Lines) file
    Args:
        path (str): Path to the JSONL file

    Raises:
        ValueError: If any line in the JSONL file is not valid JSON

    Returns:
        List[Dict[str, Any]]: A list of records loaded from the JSONL file
    """
    records = []
    with Path(path).open("r", encoding="utf-8") as jsonlfile:
        for line in jsonlfile:
            line = line.strip()
            if line:  # Skip empty lines
                try:
                    record = json.loads(line)
                    records.append(record)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in line: {line}") from e
    return records
