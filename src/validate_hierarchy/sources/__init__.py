"""Loaders that build the shared `Collection` model from a storage backend.

`local` has no extra dependencies. `irods` requires the optional `irods`
extra and is therefore *not* imported here — import it directly, and catch
`validate_hierarchy.sources.irods.IrodsSupportError`.
"""

from validate_hierarchy.sources.local import load_collection_from_dir

__all__ = ["load_collection_from_dir"]
