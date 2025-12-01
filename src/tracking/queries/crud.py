import logging
from typing import Any, Dict, Iterable
from tracking.models import Sample
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


IMMUTABLE_FIELDS = {"id", "created_at", "updated_at"}
ALL_FIELDS = {c.name for c in Sample.__table__.columns}
MUTABLE_FIELDS = ALL_FIELDS - IMMUTABLE_FIELDS


def find_sample_by_name_and_dataset(
    session: Session, sample_name: str, dataset_name: str
) -> "Sample | None":
    """
    Find a sample by its sample name and dataset name.

    Args:
        session (Session): The SQLAlchemy session to use for the query.
        sample_name (str): The name of the sample.
        dataset_name (str): The name of the dataset.

    Returns:
        Sample | None: The found sample or None if not found.
    """
    return (
        session.query(Sample)
        .filter_by(sample_name=sample_name, dataset_name=dataset_name)
        .one_or_none()
    )


def update_sample_entry(
    sample: Sample,
    updates: Dict[str, Any],
):
    """
    Validate and apply updates to a Sample instance.
    Args:
        sample (Sample): The sample instance to update.
        updates (Dict[str, Any]): A dictionary of fields to update and their new values.

    Raises:
        ValueError: If unknown fields are present in the updates.
        ValueError: If an attempt is made to update an immutable field.
    """
    # Check if updates contain any unknown fields
    unknown_fields = set(updates.keys()) - ALL_FIELDS
    if unknown_fields:
        logger.error(
            "Unknown fields in updates for sample %s: %s",
            sample.sample_name,
            unknown_fields,
        )
        raise ValueError(f"Unknown fields: {unknown_fields}")

    # Update sample fields
    for key, value in updates.items():
        if key in IMMUTABLE_FIELDS:
            logger.error(
                "Attempted to update immutable field '%s' for sample %s",
                key,
                sample.sample_name,
            )
            raise ValueError(f"Field '{key}' is immutable and cannot be updated.")
        elif getattr(sample, key) == value:
            logger.warning(
                "Field '%s' for sample %s is already set to the provided value.",
                key,
                sample.sample_name,
            )
        else:
            setattr(sample, key, value)
            logger.info(
                "Updated field '%s' for sample %s to '%s'.",
                key,
                sample.sample_name,
                value,
            )
