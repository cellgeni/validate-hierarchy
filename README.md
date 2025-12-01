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
- **Configurable Logging**: Detailed logging with customizable levels

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

The tool provides two main commands: `update` for database operations and `irods-validate` for schema validation.

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

# With custom timeout
sample-tracking irods-validate /zone/collection/path --schema schema.yml --timeout 300
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

### `irods-validate` Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `collection` | iRODS collection path | Required |
| `--schema` | Schema file path (YAML/JSON) | `IRODS_SCHEMA_FILE` env var |
| `--timeout` | iRODS connection timeout (seconds) | `120` |

## Development

### Project Structure

```
src/tracking/
├── __init__.py
├── __main__.py          # Entry point for python -m tracking
├── cli.py              # Command-line interface
├── config.py           # Configuration management
├── irods.py            # iRODS validation logic
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

# Validate schema syntax (with explicit schema file)
sample-tracking irods-validate /test/collection --schema test_schema.yml --timeout 30

# Validate using default schema from environment
sample-tracking irods-validate /test/collection --timeout 30
```

## Logging

The tool uses Python's logging module with INFO level by default. Logs include:
- Sample update operations and results
- Validation reports with issue counts
- Database connection status
- Error details for troubleshooting

## License

See the [LICENSE](LICENSE) file for licensing information.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request