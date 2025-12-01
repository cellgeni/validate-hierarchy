from tracking.models import Sample
from tracking.queries import find_sample_by_name_and_dataset, update_sample_entry
from tracking.queries import session_scope
from tracking.io import load_records
from sqlalchemy.orm import Session
from typing import Any, Dict, Iterable, List
import logging

logger = logging.getLogger(__name__)


def update_sample(
    updates: Dict[str, Any],
    session: Session,
):
    """
    Update a single sample in the database.
    Args:
        updates (Dict[str, Any]): The updates to apply to the sample.
        session (Session): The database session.
    """
    sample_name = updates.get("sample_name")
    dataset_name = updates.get("dataset_name")

    if not sample_name or not dataset_name:
        logger.warning(
            "Skipping record with missing sample_name or dataset_name: %s", updates
        )
        return

    sample = find_sample_by_name_and_dataset(session, sample_name, dataset_name)
    if not sample:
        logger.warning(
            "Sample not found, creating a new one: sample_name=%s, dataset_name=%s",
            sample_name,
            dataset_name,
        )
        sample = Sample(sample_name=sample_name, dataset_name=dataset_name)
        session.add(sample)

    update_sample_entry(sample, updates)
    logger.info("Updated sample: %s with %d fields", sample, len(updates))


def update_samples(path: str, fmt: str, batch_size: int, dry_run: bool):
    """
    Update multiple samples in the database.

    Args:
        path (str): Path to the input file (CSV or JSON).
        fmt (str): Format of the input file (csv or json).
        batch_size (int): Number of records to process in each batch.
        dry_run (bool): If True, parse/validate the input file without updating the database

    """
    logger.info("Loading records from %s (format: %s)", path, fmt)
    records: List[Dict[str, Any]] = load_records(path, fmt)
    logger.info("Loaded %d records", len(records))

    with session_scope() as session:
        processed = 0
        while processed < len(records):
            chunk = records[processed : processed + batch_size]
            try:
                for record in chunk:
                    update_sample(record, session)
                    processed += 1
                if not dry_run:
                    session.commit()
                logger.info("Processed %d/%d records", processed, len(records))
            except Exception as e:
                logger.error("Failed to process batch: %s", e)
                if not dry_run:
                    session.rollback()
