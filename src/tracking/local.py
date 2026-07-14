import os
import logging
from datetime import datetime
from pathlib import Path, PurePosixPath

from tracking.irods import IrodsCollection

logger = logging.getLogger(__name__)


def load_collection_from_dir(path: str, follow_symlinks: bool = False) -> IrodsCollection:
    """
    Load a collection tree from a local directory starting at `path`.

    Mirrors `load_collection_from_irods` but builds the same `IrodsCollection`
    data model from the local filesystem. Local directories carry no AVU
    metadata, so `metadata` is always empty.

    Args:
        path (str): Path to the local directory to load
        follow_symlinks (bool): If True, follow symlinked directories and files
            when walking the tree. Useful for Nextflow work directories where
            entries are symlinks. Defaults to False.

    Raises:
        FileNotFoundError: If the path does not exist
        NotADirectoryError: If the path is not a directory

    Returns:
        IrodsCollection: The collection tree rooted at `path`
    """
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"Directory does not exist: {path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")
    return _collection_from_dir(root, follow_symlinks=follow_symlinks)


def _collection_from_dir(directory: Path, follow_symlinks: bool = False) -> IrodsCollection:
    """
    Recursively build an `IrodsCollection` from a local directory.
    """
    subcollections = []
    data_objects = []
    for entry in os.scandir(directory):
        if entry.is_dir(follow_symlinks=follow_symlinks):
            subcollections.append(_collection_from_dir(Path(entry.path), follow_symlinks=follow_symlinks))
        elif entry.is_file(follow_symlinks=follow_symlinks):
            data_objects.append(entry.name)

    stat = directory.stat()
    return IrodsCollection(
        name=directory.name,
        path=PurePosixPath(directory.resolve().as_posix()),
        create_time=datetime.fromtimestamp(getattr(stat, "st_ctime", stat.st_mtime)),
        modify_time=datetime.fromtimestamp(stat.st_mtime),
        metadata={},
        collections=subcollections,
        data_objects=data_objects,
    )
