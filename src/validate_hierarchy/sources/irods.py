"""Build a `Collection` tree from iRODS."""

from collections import defaultdict

from irods.session import iRODSSession

from validate_hierarchy.models import Collection


def load_collection_from_irods(session: iRODSSession, path: str) -> Collection:
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
