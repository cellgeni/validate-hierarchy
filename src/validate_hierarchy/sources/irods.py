"""Build a `Collection` tree from iRODS.

`python-irodsclient` is an optional dependency, so it is imported lazily: the
rest of the package (and the `local` subcommand) works without it.
"""

from collections import defaultdict

from validate_hierarchy.models import Collection

IRODS_INSTALL_HINT = (
    "iRODS support requires the optional 'irods' extra:\n"
    "    pip install 'validate-hierarchy[irods]'"
)


class IrodsSupportError(RuntimeError):
    """Raised when iRODS is requested but `python-irodsclient` is not installed."""


def require_irods() -> tuple[type, type]:
    """Import and return `(iRODSSession, NetworkException)`.

    Raises:
        IrodsSupportError: if `python-irodsclient` is not installed.
    """
    try:
        from irods.exception import NetworkException
        from irods.session import iRODSSession
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise IrodsSupportError(IRODS_INSTALL_HINT) from exc
    return iRODSSession, NetworkException


def load_collection_from_irods(session, path: str) -> Collection:
    """Load a `Collection` tree from iRODS starting at `path`."""
    return _collection_from_irods(session.collections.get(path))


def _collection_from_irods(irods_collection) -> Collection:
    """Recursively build a `Collection` from an iRODS collection object."""
    metadata: dict[str, list[str]] = defaultdict(list)
    for avu in irods_collection.metadata.items():
        metadata[avu.name].append(avu.value)

    return Collection(
        name=irods_collection.name,
        path=irods_collection.path,
        create_time=irods_collection.create_time,
        modify_time=irods_collection.modify_time,
        metadata=dict(metadata),
        collections=[
            _collection_from_irods(child)
            for child in irods_collection.subcollections
        ],
        data_objects=[obj.name for obj in irods_collection.data_objects],
    )
