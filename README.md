# validate-hierarchy

Validate directory and iRODS collection hierarchies against a declarative YAML
schema.

You describe the shape you expect — regex name patterns plus `min`/`max`
cardinalities for files and sub-collections at every level — and
`validate-hierarchy` walks the real tree and reports everything that does not
match: missing files, files that appear too many times, unexpected extra
entries, misnamed collections, and (for iRODS) missing metadata keys.

Both backends share the same schema format and the same data model, so a
dataset can be checked on disk before upload and again in iRODS afterwards.

> **Note**
> This tool was split out of the combined `sample-tracking` CLI. The database
> tracking side (PostgreSQL models, `update` command) is not part of this
> package; the last combined version is preserved on the `legacy` git tag.

## Installation

```bash
# Local filesystem validation only
pip install validate-hierarchy

# With iRODS support
pip install 'validate-hierarchy[irods]'
```

Requires Python 3.12+. `python-irodsclient` is an optional extra so that the
common local-validation case stays dependency-light; the `irods` subcommand
prints an install hint if the extra is missing.

### From source

```bash
git clone https://github.com/cellgeni/validate-hierarchy.git
cd validate-hierarchy
uv sync --all-extras
uv run validate-hierarchy --help
```

## Quick start

```bash
# Validate one directory
validate-hierarchy local /data/GSE123456 --schema schema/local_dataset_root.yml

# Validate many, with a progress bar and a saved report
validate-hierarchy local /data/GSE* \
    --schema schema/local_dataset_root.yml \
    --progress-bar \
    --report report.txt

# Validate iRODS collections
validate-hierarchy irods /archive/cellgeni/datasets/GSE123456 \
    --schema schema/dataset_root.yml
```

The exit status is `0` when everything passed and `1` when any path failed, so
the command drops straight into CI pipelines and cron jobs. Pass `--no-exit` to
always exit `0` (e.g. when you only want the report emailed).

## Schema format

A schema is a nested description of one collection. Every level accepts:

| Key | Meaning | Default |
|-----|---------|---------|
| `name` | A [name rule](#name-rules) the collection's own name must match | matches anything |
| `data_objects` | List of name rules for the files directly inside | `[]` |
| `collections` | List of nested schemas for the sub-collections | `[]` |
| `metadata_keys` | Metadata (AVU) keys that must be present — iRODS only | `[]` |
| `allow_extra_files` | Permit files matched by no rule | `false` |
| `allow_extra_collections` | Permit sub-collections matched by no rule | `false` |

### Name rules

| Key | Meaning | Default |
|-----|---------|---------|
| `pattern` | Python regex, applied with `fullmatch` | required |
| `min` | Fewest entries that must match | `1` |
| `max` | Most entries that may match; `null` means unbounded | `null` |
| `description` | Free-text note, ignored by validation | — |

Unknown keys are rejected, so a typo like `data_object:` fails loudly instead
of silently matching nothing.

```yaml
name:
  pattern: '^(?:GSE|E-MTAB-|EGAD|PRJEB|PRJNA|HRA)\d+$'

data_objects:
  - pattern: '^.*(?:ena|sra)\.tsv$'
    min: 1
    max: 2
  - pattern: '^.*parsed\.tsv$'
    min: 1
    max: 1

collections:
  - name:
      pattern: '^(SRS|GSM|ERS)\d+$'
      min: 1
      max: null          # any number of samples
    data_objects:
      - pattern: '^Log\.final\.out$'
        min: 1
        max: 1
    allow_extra_files: false
    allow_extra_collections: false

allow_extra_files: false
allow_extra_collections: false
```

### Reusing blocks

Real hierarchies repeat themselves. Both of these mechanisms are supported, and
they can be mixed freely in the same schema.

**1. YAML anchors and aliases** — plain YAML, one self-contained file. Declare a
block once with `&name` and reuse it with `*name`:

```yaml
collections:
  - name: {pattern: '^Gene$', min: 1, max: 1}
    data_objects: &gene_files          # declare
      - pattern: '^Features\.stats$'
        min: 1
        max: 1
      - pattern: '^Summary\.csv$'
        min: 1
        max: 1

  - name: {pattern: 'GeneFull$', min: 1, max: 1}
    data_objects: *gene_files          # reuse
```

Mapping keys starting with `_` or `x-` are ignored by the loader, so a schema
can also keep a section that exists purely to host anchors:

```yaml
_definitions:
  matrix_files: &matrix_files
    - pattern: '^barcodes\.tsv\.gz$'
      min: 1
      max: 1
    - pattern: '^matrix\.mtx\.gz$'
      min: 1
      max: 1

collections:
  - name: {pattern: '^raw$'}
    data_objects: *matrix_files
```

See [schema/dataset_root.anchored.yml](schema/dataset_root.anchored.yml) for a
full anchored schema.

**2. `!include` directives** — split a schema over several files. Paths resolve
relative to the *including* file and may nest:

```yaml
# dataset_root.yml
name:
  pattern: '^(?:GSE|E-MTAB-|EGAD|PRJEB|PRJNA|HRA)\d+$'
data_objects: !include _dataset_files.yml
collections:  !include _sample_collections.yml
```

See [schema/dataset_root.yml](schema/dataset_root.yml) and its `_*.yml`
fragments.

Anchors are resolved by the YAML parser per file, so an alias cannot refer to an
anchor declared in a different file. Use `!include` to share across files and
anchors to share within one.

JSON schema files also work, since JSON is a subset of YAML.

> **Note**
> Schema files are trusted input. `!include` paths are deliberately not confined
> to the including file's directory, so `!include ../common/_files.yml` and
> absolute paths both work — which also means a schema can read any file the
> user running the command can read. Don't run the tool against a schema from an
> untrusted source.

### Converting between the two forms

`validate-hierarchy flatten` resolves every `!include` and re-emits the schema
as one self-contained file, turning fragments used more than once into anchors:

```bash
# Print the flattened schema
validate-hierarchy flatten schema/dataset_root.yml

# Write it to a file
validate-hierarchy flatten schema/dataset_root.yml -o schema/dataset_root.anchored.yml
```

A fragment is anchored under its filename, so `_gene_files.yml` included twice
becomes `&gene_files` at its first use and `*gene_files` after. Existing anchor
names in the input are kept, which makes the command idempotent — flattening an
already-flat schema returns it unchanged.

The output is checked to parse back to exactly the data the original produced
before anything is written, so a conversion either round-trips or fails with
exit 2. Note that YAML comments are not preserved: the parser discards them, so
they cannot be carried into the output.

There is no reverse command. Splitting a schema into fragments requires
deciding where the seams go, which is a judgement call rather than a
transformation.

## Commands

### `validate-hierarchy local`

Validates local filesystem directories. Files map to data objects and
sub-directories to sub-collections. Local directories carry no metadata, so
leave `metadata_keys` empty.

```bash
validate-hierarchy local /data/ds1 /data/ds2 --schema schema.yml

# Nextflow work directories are built from symlinks
validate-hierarchy local work/ab/cdef... --schema schema.yml --follow-symlinks

# Validate a list of directories from a file
mapfile -t dirs < directories.txt
validate-hierarchy local "${dirs[@]}" --schema schema.yml --progress-bar
```

| Option | Description | Default |
|--------|-------------|---------|
| `directory` | Directory path(s); accepts many | required |
| `--follow-symlinks` | Follow symlinked directories and files when walking | `false` |

Reported paths reflect the logical traversal path you passed in, not the
physical symlink targets.

### `validate-hierarchy irods`

Validates iRODS collections. Requires the `irods` extra. Transient network
failures are retried; a collection that still cannot be read is reported as a
`load_error` rather than silently skipped.

```bash
validate-hierarchy irods /zone/collection/path --schema schema.yml

# Explicit iRODS environment file and a longer timeout
validate-hierarchy irods /zone/coll \
    --schema schema.yml \
    --config-file ~/.irods/irods_environment.json \
    --timeout 300

# Validate every dataset collection in a zone
iquest --no-page "SELECT COLL_NAME WHERE COLL_PARENT_NAME = '/archive/cellgeni/datasets'" \
  | grep -v '^--' | awk -F' = ' '{print $2}' | sort > collections.txt
mapfile -t collections < collections.txt
validate-hierarchy irods "${collections[@]}" --progress-bar
```

| Option | Description | Default |
|--------|-------------|---------|
| `collection` | iRODS collection path(s); accepts many | required |
| `--config-file` | iRODS environment file | `IRODS_ENVIRONMENT_FILE` env var |
| `--timeout` | Connection timeout, seconds | `120` |
| `--retries` | Attempts per collection on network errors | `3` |
| `--retry-delay` | Seconds between retries | `15` |

### `validate-hierarchy flatten`

Rewrites an `!include`-based schema as a single anchored file. See
[Converting between the two forms](#converting-between-the-two-forms).

| Option | Description | Default |
|--------|-------------|---------|
| `schema` | Path to the schema file to flatten | required |
| `-o`, `--output` | Write to this file instead of standard output | stdout |

This subcommand takes none of the shared options below: it rewrites a file
rather than validating a tree, so it produces no report and writes no log.

### Shared options

| Option | Description | Default |
|--------|-------------|---------|
| `--schema` | Schema file path | `LOCAL_SCHEMA_FILE` / `IRODS_SCHEMA_FILE` env var |
| `--report` | Path to save the full report | none |
| `--report-format` | Saved report format (`text`, `markdown`) | `text` |
| `--min-collection-summary` | Path count at or above which stdout/email is summarised | `5` |
| `--extra-paths-file` | Write the full path of every unexpected entry, one per line | none |
| `--email` | Recipient address(es) for the report | none |
| `--email-from` | Sender address | `VALIDATE_HIERARCHY_EMAIL_FROM` or `noreply@localhost` |
| `--email-subject` | Subject line | per-command default |
| `--smtp-host` | SMTP host | `VALIDATE_HIERARCHY_SMTP_HOST` or `localhost` |
| `--log-file` | Log file path | `local_validation.log` / `irods_validation.log` |
| `--log-level` | Log verbosity (`debug`, `info`, `warning`, `error`) | `info` |
| `--progress-bar` | Show a progress bar | `false` |
| `--no-exit` | Always exit `0`, even on failures | `false` |

`--report` always contains the full per-path detail. What is printed to stdout
and emailed switches to a summary once the number of paths reaches
`--min-collection-summary`, so a nightly sweep over thousands of collections
emails counts rather than a wall of text.

`--extra-paths-file` is useful for follow-up work — feed it into a cleanup or
archival step to act on entries the schema did not expect.

## Environment variables

Read from the environment and from a `.env` file in the working directory (see
[.env.example](.env.example)):

| Variable | Purpose |
|----------|---------|
| `LOCAL_SCHEMA_FILE` | Default `--schema` for `local` |
| `IRODS_SCHEMA_FILE` | Default `--schema` for `irods` |
| `IRODS_ENVIRONMENT_FILE` | Default `--config-file` for `irods` |
| `VALIDATE_HIERARCHY_EMAIL_FROM` | Default `--email-from` |
| `VALIDATE_HIERARCHY_SMTP_HOST` | Default `--smtp-host` |

The two schema variables are independent: neither subcommand falls back to the
other's.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Everything passed (or `--no-exit` was given) |
| `1` | At least one path FAILED validation |
| `2` | Bad invocation: unusable/missing schema, missing `irods` extra, bad arguments |

## Issue kinds

Every issue in a report carries a `kind`, which is also its log level:

| Kind | Level | Meaning |
|------|-------|---------|
| `load_error` | error | The path could not be read at all |
| `name_mismatch` | error | Collection name does not match its `pattern` |
| `missing_files` | error | Fewer than `min` files matched a rule |
| `too_many_files` | error | More than `max` files matched a rule |
| `unexpected_files` | warning | Files matched by no rule, with `allow_extra_files: false` |
| `missing_collections` | error | Fewer than `min` sub-collections matched |
| `too_many_collections` | error | More than `max` sub-collections matched |
| `unexpected_collections` | warning | Sub-collections matched by no rule |
| `missing_metadata_keys` | error | Required AVU keys absent (iRODS only) |

Any issue, warning-level included, makes a report FAILED.

## Docker

```bash
docker build -t validate-hierarchy .
docker run --rm -v /data:/data validate-hierarchy \
    validate-hierarchy local /data/GSE123456
```

The image installs the `irods` extra, bundles the example schemas under
`/app/schema`, and presets `LOCAL_SCHEMA_FILE` and `IRODS_SCHEMA_FILE` so
`--schema` can be omitted. There is no `ENTRYPOINT`, so Nextflow can run
arbitrary commands under the Docker executor.

## Python API

```python
from validate_hierarchy import (
    load_schema_from_file,
    load_collection_from_dir,
    validate_collection,
    render_text_report,
)

schema = load_schema_from_file("schema/local_dataset_root.yml")
collection = load_collection_from_dir("/data/GSE123456")
report = validate_collection(collection, schema)

print(report.ok, len(report.issues))
print(render_text_report([report]))
```

## Project structure

```
src/validate_hierarchy/
├── __init__.py          # Public API
├── __main__.py          # python -m validate_hierarchy
├── cli.py               # Argument parsing and command orchestration
├── models.py            # Collection, CollectionSchema, NameRule, reports
├── schema.py            # Schema loading (!include, anchors) and validation
├── flatten.py           # Rewrites an !include schema as one anchored file
├── validate.py          # Recursive collection-vs-schema validation
├── report.py            # Logging and text/markdown rendering
└── sources/
    ├── local.py         # Build a Collection from the filesystem
    └── irods.py         # Build a Collection from iRODS (optional extra)

schema/                  # Example schemas for Cellgeni reprocessing datasets
scripts/cron.bsub        # LSF job that sweeps an iRODS zone nightly
```

## Releasing

Releases are published to PyPI by
[.github/workflows/publish.yml](.github/workflows/publish.yml) on a `v*` tag,
using PyPI Trusted Publishing (OIDC) — no API token in repository secrets.

Before the first release, register a trusted publisher on PyPI with owner
`cellgeni`, repository `validate-hierarchy`, workflow `publish.yml` and
environment `pypi`. Then:

```bash
uv version --bump minor    # updates pyproject.toml
git commit -am "Release v0.2.0"
git tag v0.2.0
git push origin main --tags
```

The workflow refuses to publish if the tag does not match the version in
`pyproject.toml`.

## License

MIT — see [LICENSE](LICENSE).
