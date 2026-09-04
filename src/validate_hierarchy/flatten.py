"""Rewrite an ``!include``-based schema as one self-contained anchored file.

The two block-reuse mechanisms described in `validate_hierarchy.schema` are
equivalent in what they express, but only one of them can be read end to end
without opening other files. This converts the multi-file form into the
single-file form:

* every ``!include`` is resolved inline;
* a fragment included more than once becomes a YAML anchor at its first use
  and an alias at the rest, named after the fragment file, so the output is
  no larger than the sum of its parts;
* anchor-only keys (``_``/``x-`` prefixed) are dropped, since the output has
  no need for them.

The result is verified to parse back to *exactly* the data the original
produced before it is returned, so a conversion either round-trips or fails.
"""

import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from validate_hierarchy.models import CollectionSchema
from validate_hierarchy.schema import (
    SchemaError,
    _format_errors,
    _strip_anchor_blocks,
    load_raw_schema,
)

#: Characters allowed in a YAML anchor name. Anything else is replaced.
_ANCHOR_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")

#: Strings holding any of these read as regexes rather than prose, and are
#: quoted so the pattern's boundaries are obvious to anyone editing the file.
_REGEX_METACHARACTERS = set(r"\^$.*+?[]{}()|")


def _sanitise_anchor(name: str) -> str:
    """Reduce `name` to something usable as a YAML anchor."""
    cleaned = _ANCHOR_UNSAFE.sub("_", name).strip("_")
    return cleaned or "block"


def _anchor_name(path: Path) -> str:
    """Derive a YAML anchor name from an included fragment's filename.

    ``_gene_files.yml`` becomes ``gene_files``: the leading underscore marks
    the file as a fragment and carries no meaning in the output.
    """
    return _sanitise_anchor(path.stem)


def _provenance_loader(names: dict[int, str], keep_alive: list[Any]):
    """Build a loader that records a candidate anchor name for reusable nodes.

    Two sources of names, so that flattening is idempotent and can handle a
    schema that already mixes both reuse mechanisms:

    * an ``!include``d fragment is named after its file;
    * a node carrying an explicit ``&anchor`` keeps that anchor's name.

    Nodes are tracked by `id`, so every recorded object is also appended to
    `keep_alive`: an id is only meaningful while its object exists.
    """

    class ProvenanceLoader(yaml.SafeLoader):
        def __init__(self, stream):
            self._root = Path(getattr(stream, "name", ".")).resolve().parent
            self._node_anchors: dict[int, str] = {}
            super().__init__(stream)

        def compose_node(self, parent, index):
            # peek_event() exposes the anchor declared on the node we are about
            # to compose; the composer itself discards this once the document
            # is built.
            anchor = None
            if not self.check_event(yaml.AliasEvent):
                anchor = self.peek_event().anchor
            node = super().compose_node(parent, index)
            if anchor:
                self._node_anchors[id(node)] = anchor
            return node

        def construct_object(self, node, deep=False):
            obj = super().construct_object(node, deep=deep)
            anchor = self._node_anchors.get(id(node))
            if anchor and isinstance(obj, (dict, list)):
                keep_alive.append(obj)
                names.setdefault(id(obj), _sanitise_anchor(anchor))
            return obj

    def construct_include(loader: ProvenanceLoader, node: yaml.nodes.ScalarNode):
        filename = loader.construct_scalar(node)
        filepath = (loader._root / filename).resolve()
        try:
            with open(filepath, encoding="utf-8") as f:
                data = yaml.load(f, ProvenanceLoader)
        except (OSError, UnicodeDecodeError) as exc:
            raise SchemaError(
                f"Cannot read included schema file {filepath}: {exc}"
            ) from exc
        except yaml.YAMLError as exc:
            raise SchemaError(
                f"Invalid YAML in included schema file {filepath}: {exc}"
            ) from exc

        if isinstance(data, (dict, list)):
            keep_alive.append(data)
            names.setdefault(id(data), _anchor_name(filepath))
        return data

    ProvenanceLoader.add_constructor("!include", construct_include)
    return ProvenanceLoader


def _canonical(node: Any) -> str:
    """A stable string identifying a subtree's content, for equality testing."""
    return json.dumps(node, sort_keys=True, default=str)


def _share_fragments(
    node: Any, names: dict[int, str], canonical: dict[tuple, Any],
    seen: dict[int, Any] | None = None,
) -> Any:
    """Collapse identical included fragments onto one shared object.

    PyYAML emits an anchor and aliases whenever the *same* object appears more
    than once, so making the duplicates identical is all that is needed to get
    anchors in the output. Only nodes that came from an ``!include`` are
    collapsed: sharing every structurally equal `{min: 1, max: 1}` would
    produce a thicket of anchors nobody wants to read.
    """
    if seen is None:
        seen = {}
    if not isinstance(node, (dict, list)):
        return node
    if id(node) in seen:
        return seen[id(node)]
    seen[id(node)] = node

    # Post-order: children are collapsed before the parent is keyed on content.
    if isinstance(node, dict):
        for key, value in node.items():
            node[key] = _share_fragments(value, names, canonical, seen)
    else:
        node[:] = [_share_fragments(v, names, canonical, seen) for v in node]

    name = names.get(id(node))
    if name is None:
        return node

    key = (name, _canonical(node))
    shared = canonical.setdefault(key, node)
    if shared is not node:
        names.setdefault(id(shared), name)
        seen[id(node)] = shared
    return shared


def _make_dumper(names: dict[int, str]):
    """Build a dumper that names anchors after their fragment file."""

    class AnchorNamingDumper(yaml.SafeDumper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._node_names: dict[int, str] = {}
            self._used: set[str] = set()

        def represent_data(self, data):
            node = super().represent_data(data)
            name = names.get(id(data))
            if name is not None:
                self._node_names[id(node)] = name
            return node

        def generate_anchor(self, node):
            name = self._node_names.get(id(node))
            if name is None:
                return super().generate_anchor(node)
            # Two fragments can share a filename without sharing content
            # (a/_shared.yml and b/_shared.yml). Suffix rather than fall back
            # to PyYAML's id001, which tells the reader nothing.
            candidate, suffix = name, 1
            while candidate in self._used:
                suffix += 1
                candidate = f"{name}_{suffix}"
            self._used.add(candidate)
            return candidate

        def increase_indent(self, flow=False, indentless=False):
            # Indent list items under their key, matching the hand-written
            # schemas rather than PyYAML's flush-left default.
            return super().increase_indent(flow, False)

    def represent_str(dumper: yaml.SafeDumper, data: str):
        """Single-quote regex-looking strings; leave prose and keys plain.

        PyYAML already quotes whatever *needs* quoting to round-trip. This is
        purely for the reader: an unquoted `^.*(?:ena|sra)\\.tsv$` is hard to
        see the edges of, and quoting it matches how the schemas are written
        by hand.
        """
        style = "'" if _REGEX_METACHARACTERS.intersection(data) else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)

    AnchorNamingDumper.add_representer(str, represent_str)
    return AnchorNamingDumper


def flatten_schema(path: str | Path) -> str:
    """Return `path` rewritten as a single self-contained anchored schema.

    Raises:
        SchemaError: if the schema cannot be read or validated, or if the
            generated output does not parse back to the same data.
    """
    # Load once with provenance, to learn which nodes came from which fragment.
    names: dict[int, str] = {}
    keep_alive: list[Any] = []
    loader = _provenance_loader(names, keep_alive)
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.load(f, Loader=loader)
    except (OSError, UnicodeDecodeError) as exc:
        raise SchemaError(f"Cannot read schema file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise SchemaError(f"Invalid YAML in schema file {path}: {exc}") from exc

    # Strip anchor-only keys, carrying the provenance names onto the copies
    # that `_strip_anchor_blocks` builds. Its memo maps old id -> new object.
    memo: dict[int, Any] = {}
    data = _strip_anchor_blocks(raw, memo)
    stripped_names = {
        id(memo[node_id]): name
        for node_id, name in names.items()
        if node_id in memo
    }

    if not isinstance(data, dict):
        raise SchemaError(
            f"Schema file {path} must contain a mapping at the top level, "
            f"got {type(data).__name__}"
        )

    _share_fragments(data, stripped_names, {})

    text = yaml.dump(
        data,
        Dumper=_make_dumper(stripped_names),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )

    _verify_round_trip(text, path)
    return text


def _verify_round_trip(text: str, source: str | Path) -> None:
    """Fail unless `text` parses to the same schema as `source`.

    Compares the cleaned raw data rather than the validated models, so a
    difference in any key — including ones the schema model ignores — is
    caught.
    """
    expected = _strip_anchor_blocks(load_raw_schema(source))
    try:
        produced = _strip_anchor_blocks(yaml.safe_load(text))
    except yaml.YAMLError as exc:  # pragma: no cover - would be a bug here
        raise SchemaError(
            f"Flattening {source} produced invalid YAML: {exc}"
        ) from exc

    if produced != expected:
        raise SchemaError(
            f"Flattening {source} changed the schema; refusing to emit it. "
            "This is a bug in validate-hierarchy — please report it."
        )

    # Also confirm the output is a usable schema in its own right.
    try:
        CollectionSchema.model_validate(produced)
    except ValidationError as exc:
        raise SchemaError(
            f"Flattening {source} produced something that is not a valid "
            f"schema:\n{_format_errors(exc)}"
        ) from exc
