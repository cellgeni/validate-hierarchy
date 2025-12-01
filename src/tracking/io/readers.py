import csv
import json
from typing import List, Dict, Any, Iterable
from pathlib import Path


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
