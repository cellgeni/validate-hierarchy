"""Loaders that build the shared `Collection` model from a storage backend."""

from validate_hierarchy.sources.irods import load_collection_from_irods
from validate_hierarchy.sources.local import load_collection_from_dir

__all__ = ["load_collection_from_dir", "load_collection_from_irods"]
