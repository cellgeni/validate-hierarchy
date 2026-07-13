# Track Reprocessing

A CLI tool for managing and tracking reprocessed datasets with support for database operations and iRODS collection validation.

## Overview

This project provides a command-line interface for:
- **Database Management**: Update sample tracking records in a PostgreSQL database from CSV/JSON files
- **iRODS Validation**: Validate iRODS collections against predefined schemas to ensure data integrity

The tool is designed for bioinformatics workflows where sample data needs to be tracked and validated across different storage systems.

## Features

- **Sample Tracking**: Batch update sample records with configurable status tracking
- **Schema Validation**: Validate iRODS collections against YAML/JSON schemas
- **Database Integration**: PostgreSQL support with SQLAlchemy ORM
- **Flexible Input**: Support for both CSV and JSON input formats
- **Dry Run Mode**: Test operations without making actual changes
- **Configurable Logging**: Detailed logging with file rotation and customizable levels
- **Progress Tracking**: Visual progress bars for long-running validation operations
- **Email Reporting**: Send validation reports via email with file attachments
- **Multiple Output Formats**: Generate reports in text or markdown format
- **Batch Processing**: Validate multiple collections in a single command

## Installation

### Requirements

- Python 3.12 or higher
- PostgreSQL database (for sample tracking)
- iRODS environment (for collection validation)

### Install Dependencies

```bash
# Clone the repository
git clone <repository-url>
cd track_reprocessing

# Install using uv (recommended)
uv pip install -e .

# Or install using pip
pip install -e .
```

### Environment Setup

Create a `.env` file in the project root with the following variables:

```env
# Database configuration
DB_HOST=localhost
DB_PORT=5432
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=reprocessing

# iRODS configuration
IRODS_ENVIRONMENT_FILE=/path/to/your/.irods/irods_environment.json
IRODS_SCHEMA_FILE=/path/to/your/schema.yml
```

## Usage

The tool provides three main commands: `update` for database operations, `irods-validate` for validating iRODS collections against a schema, and `local-validate` for validating local filesystem directories against the same kind of schema.

### Sample Tracking (`update` command)

Update sample records in the database from input files:

```bash
# Basic usage with CSV file
sample-tracking update samples.csv --format csv

# JSON input with custom batch size
sample-tracking update samples.json --format json --batch-size 50

# Dry run to validate input without database changes
sample-tracking update samples.csv --dry-run

# Custom database connection
sample-tracking update samples.csv \
    --db-host localhost \
    --db-port 5432 \
    --db-user myuser \
    --db-password mypass \
    --db-name tracking

# Set default status for new records
sample-tracking update samples.csv --status-default pending
```

#### Input File Format

**CSV Format:**
```csv
sample_name,dataset_name,status,batch_id
sample001,GSE123456,success,batch_01
sample002,GSE123456,pending,batch_01
```

**JSON Format:**
```json
[
  {
    "sample_name": "sample001",
    "dataset_name": "GSE123456", 
    "status": "success",
    "batch_id": "batch_01"
  }
]
```

### iRODS Collection Validation (`irods-validate` command)

Validate iRODS collections against predefined schemas:

```bash
# Basic validation (using schema from IRODS_SCHEMA_FILE env variable)
sample-tracking irods-validate /zone/collection/path

# Validation with explicit schema file
sample-tracking irods-validate /zone/collection/path --schema schema.yml

# Multiple collections at once
sample-tracking irods-validate /path/collection1 /path/collection2 /path/collection3 --schema schema.yml

# With progress bar
sample-tracking irods-validate /zone/collection/path --schema schema.yml --progress-bar

# Save report to file
sample-tracking irods-validate /zone/collection/path --schema schema.yml --report validation_report.md --report-format markdown

# Send email report
sample-tracking irods-validate /zone/collection/path --schema schema.yml --email user@example.com admin@example.com

# Complete example with all features
sample-tracking irods-validate /path/collection1 /path/collection2 \
    --schema validation_schema.yml \
    --progress-bar \
    --report-format markdown \
    --report validation_results.md \
    --email alice@example.com bob@example.com \
    --timeout 300 \
    --log-file validation.log

# Validate collections from a file list
sample-tracking irods-validate $(cat collections.txt) --schema schema.yml --progress-bar
```

#### Schema Format

Schemas are defined in YAML or JSON format. Example schema (`schema.yml`):

```yaml
name:
  pattern: '^(?:GSE|E-MTAB-|EGAD|PRJEB|PRJNA|HRA)\d+$'

metadata_keys: []

data_objects:
  - pattern: '^.*(?:ena|sra)\.tsv$'
    min: 1
    max: 2
    description: "ENA/SRA metadata files"
  - pattern: '^.*family\.soft$'
    min: 0
    max: 1
    description: "SOFT family files"
  - pattern: '^.*parsed\.tsv$'
    min: 1
    max: 1
    description: "Parsed metadata"

collections:
  - pattern: '^sample_\d+$'
    min: 1
    max: null
    description: "Sample directories"
```

### Local Directory Validation (`local-validate` command)

Validate local filesystem directories against the same schemas used for iRODS
collections. This is useful for checking datasets on disk before they are
uploaded to iRODS. Directories are validated recursively; files map to data
objects and sub-directories map to sub-collections. Local directories carry no
metadata, so schema `metadata_keys` should be left empty.

```bash
# Basic validation (using schema from IRODS_SCHEMA_FILE env variable)
sample-tracking local-validate /path/to/dataset

# Validation with explicit schema file
sample-tracking local-validate /path/to/dataset --schema schema.yml

# Multiple directories at once
sample-tracking local-validate /data/ds1 /data/ds2 /data/ds3 --schema schema.yml

# With progress bar
sample-tracking local-validate /path/to/dataset --schema schema.yml --progress-bar

# Save report to file
sample-tracking local-validate /path/to/dataset --schema schema.yml --report validation_report.md --report-format markdown

# Send email report
sample-tracking local-validate /path/to/dataset --schema schema.yml --email user@example.com

# Validate directories from a file list
sample-tracking local-validate $(cat directories.txt) --schema schema.yml --progress-bar
```

The `local-validate` command shares its schema format, report formats
(`text`/`markdown`), summary threshold (`--min-collection-summary`) and email
options with `irods-validate`. It does not accept the iRODS-only `--timeout`
option.

## Command Reference

### `update` Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `path` | Path to input file (CSV/JSON) | Required |
| `--format` | Input file format (`csv`, `json`) | `csv` |
| `--db-url` | Database host URL | `DB_HOST` env var |
| `--db-port` | Database port | `5432` or `DB_PORT` env var |
| `--db-user` | Database username | `DB_USER` env var |
| `--db-password` | Database password | `DB_PASSWORD` env var |
| `--db-name` | Database name | `reprocessing` or `DB_NAME` env var |
| `--batch-size` | Records per batch | `100` |
| `--dry-run` | Validate without updating | `False` |
| `--status-default` | Default status for new records | `pending` |
| `--log-file` | Path to log file for update process | `update.log` |

### `irods-validate` Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `collection` | iRODS collection path(s) - accepts multiple paths | Required |
| `--schema` | Schema file path (YAML/JSON) | `IRODS_SCHEMA_FILE` env var |
| `--timeout` | iRODS connection timeout (seconds) | `120` |
| `--log-file` | Path to log file for validation results | `irods_validation.log` |
| `--report-format` | Output format (`text`, `markdown`) | `text` |
| `--email` | Email address(es) to send report to (space-separated) | None |
| `--report` | Path to save validation report file | None |
| `--min-collection-summary` | Min collections to trigger summary report | `5` |
| `--progress-bar` | Show progress bar during validation | `False` |

### `local-validate` Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `directory` | Local directory path(s) - accepts multiple paths | Required |
| `--schema` | Schema file path (YAML/JSON) | `IRODS_SCHEMA_FILE` env var |
| `--log-file` | Path to log file for validation results | `local_validation.log` |
| `--report-format` | Output format (`text`, `markdown`) | `text` |
| `--email` | Email address(es) to send report to (space-separated) | None |
| `--report` | Path to save validation report file | None |
| `--min-collection-summary` | Min directories to trigger summary report | `5` |
| `--progress-bar` | Show progress bar during validation | `False` |

## Development

### Project Structure

```
src/tracking/
├── __init__.py
├── __main__.py          # Entry point for python -m tracking
├── cli.py              # Command-line interface
├── config.py           # Configuration management
├── irods.py            # iRODS validation logic (shared data model, schema, validation, renderers)
├── local.py            # Local directory loader (builds the shared model from disk)
├── io/
│   ├── __init__.py
│   └── readers.py      # File reading utilities
├── models/
│   ├── __init__.py
│   └── samples.py      # Database models
├── queries/
│   ├── __init__.py
│   ├── crud.py         # Database operations
│   └── session.py      # Database session management
└── update/
    ├── __init__.py
    └── samples.py      # Sample update logic
```

### Running from Source

```bash
# Run as module
python -m tracking update samples.csv

# Run directly
python src/tracking/cli.py update samples.csv
```

### Testing

```bash
# Dry run to test input validation
sample-tracking update test_samples.csv --dry-run

# Validate with progress bar and save report
sample-tracking irods-validate /test/collection --schema test_schema.yml --progress-bar --report test_results.md

# Validate multiple collections with email notification
sample-tracking irods-validate /collection1 /collection2 /collection3 \
    --schema schema.yml \
    --progress-bar \
    --email admin@example.com \
    --report-format markdown

# Validate collections from file list
mapfile -t collections < collections.txt
sample-tracking irods-validate "${collections[@]}" --schema schema.yml --progress-bar
```

## Advanced Usage

### Multiple Collection Validation

You can validate multiple collections in several ways:

```bash
# Direct multiple arguments
sample-tracking irods-validate /path/coll1 /path/coll2 /path/coll3 --schema schema.yml

# From a file containing collection paths (one per line)
sample-tracking irods-validate $(cat collections.txt) --schema schema.yml

# Using bash arrays for complex processing
mapfile -t collections < <(find /archive -name "GSE*" -type d | head -10)
sample-tracking irods-validate "${collections[@]}" --schema schema.yml --progress-bar
```

### Email Reports

Send validation results via email:

```bash
# Single recipient
sample-tracking irods-validate /collection --email user@example.com

# Multiple recipients
sample-tracking irods-validate /collection --email admin@example.com user@example.com

# With file attachment
sample-tracking irods-validate /collection \
    --email admin@example.com \
    --report validation_results.md \
    --report-format markdown
```

### Progress Tracking

For long-running validations, use the progress bar:

```bash
# Basic progress bar
sample-tracking irods-validate /large/collection --progress-bar

# Progress bar shows current collection being processed
sample-tracking irods-validate /coll1 /coll2 /coll3 --progress-bar
```

Example output:
```
Validating collections: 67%|██████▋   | 2/3 [00:30<00:15] Processing: GSE123456
```

## Logging

The tool uses Python's logging module with INFO level by default. Logs include:
- Sample update operations and results
- Validation reports with issue counts
- Database connection status
- Error details for troubleshooting

### Log File Configuration

Each command generates its own log file:
- `irods-validate`: Uses `irods_validation.log` by default
- `update`: Uses `update.log` by default

Configure log files with the `--log-file` option:

```bash
# Custom log file for validation
sample-tracking irods-validate /collection --log-file my_validation.log

# Custom log file for updates  
sample-tracking update data.csv --log-file my_update.log
```

Log files automatically rotate when they reach 10MB, keeping 5 backup files.

## License

See the [LICENSE](LICENSE) file for licensing information.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request