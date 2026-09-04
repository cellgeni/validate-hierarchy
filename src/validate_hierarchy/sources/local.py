"""Build a `Collection` tree from the local filesystem."""

import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from validate_hierarchy.models import Collection


def load_collection_from_dir(path: str, follow_symlinks: bool = False) -> Collection:
    """Load a collection tree from a local directory starting at `path`.

    Mirrors `load_collection_from_irods` but builds the model from the local
    filesystem. Local directories carry no AVU metadata, so `metadata` is
    always empty.

    Args:
        path: Path to the local directory to load.
        follow_symlinks: If True, follow symlinked directories and files when
            walking the tree. Useful for Nextflow work directories, where
            entries are symlinks. Defaults to False.

    Raises:
        FileNotFoundError: If the path does not exist.
        NotADirectoryError: If the path is not a directory.
    """
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"Directory does not exist: {path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")
    # Make the root absolute without resolving symlinks so that reported paths
    # reflect the logical traversal path (as given by the user) rather than the
    # physical targets of any symlinks followed with --follow-symlinks.
    root = Path(os.path.abspath(root))
    return _collection_from_dir(root, follow_symlinks=follow_symlinks)


def _collection_from_dir(directory: Path, follow_symlinks: bool = False) -> Collection:
    """Recursively build a `Collection` from a local directory."""
    subcollections = []
    data_objects = []
    for entry in os.scandir(directory):
        if entry.is_dir(follow_symlinks=follow_symlinks):
            subcollections.append(
                _collection_from_dir(Path(entry.path), follow_symlinks=follow_symlinks)
            )
        elif entry.is_file(follow_symlinks=follow_symlinks):
            data_objects.append(entry.name)

    stat = directory.stat()
    return Collection(
        name=directory.name,
        path=PurePosixPath(directory.as_posix()),
        create_time=datetime.fromtimestamp(
            getattr(stat, "st_ctime", stat.st_mtime), tz=UTC
        ),
        modify_time=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        metadata={},
        collections=subcollections,
        data_objects=data_objects,
    )
