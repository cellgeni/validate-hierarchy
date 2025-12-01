import os
import argparse
import logging
from dotenv import load_dotenv
from irods.session import iRODSSession
from tracking.update import update_samples
from tracking.irods import load_collection_from_irods, validate_collection, load_schema_from_file, log_validation_report

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()


def init_parser() -> argparse.ArgumentParser:
    # Initialize the argument parser
    parser = argparse.ArgumentParser(
        prog="sample-tracking",
        description="A CLI tool for managing and tracking reprocessing datasets",
    )

    # Add subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subparser for schema validation
    irods_validate_parser = subparsers.add_parser(
        "irods-validate", help="Validate iRODS collections against a schema"
    )
    irods_validate_parser.add_argument(
        "collection", type=str, help="Path to the iRODS collection to validate"
    )
    irods_validate_parser.add_argument(
        "schema", type=str, help="Path to the schema file (YAML or JSON)"
    )
    irods_validate_parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Connection timeout for iRODS session (default: 120 seconds)",
    )

    # Subparser for update command
    update_parser = subparsers.add_parser("update", help="Update the tracking database")
    update_parser.add_argument(
        "path", type=str, help="Path to the input file (CSV, JSON)"
    )
    update_parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="Format of the input file (default: csv)",
    )
    update_parser.add_argument(
        "--db-url",
        type=str,
        default=os.environ.get("DB_HOST"),
        help="Database connection URL (default: from DATABASE_URL env variable)",
    )
    update_parser.add_argument(
        "--db-port",
        type=int,
        default=os.environ.get("DB_PORT", 5432),
        help="Database port (default: 5432 or from DB_PORT env variable)",
    )
    update_parser.add_argument(
        "--db-user",
        type=str,
        default=os.environ.get("DB_USER"),
        help="Database user (default: from DB_USER env variable)",
    )
    update_parser.add_argument(
        "--db-password",
        type=str,
        default=os.environ.get("DB_PASSWORD"),
        help="Database password (default: from DB_PASSWORD env variable)",
    )
    update_parser.add_argument(
        "--db-name",
        type=str,
        default=os.environ.get("DB_NAME", "reprocessing"),
        help="Database name (default: reprocessing or from DB_NAME env variable)",
    )
    update_parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of records to process in each batch (default: 100)",
    )
    update_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse/validate the input file without updating the database",
    )
    update_parser.add_argument(
        "--status-default",
        choices=["success", "fail", "skip", "pending"],
        default="pending",
        help="Default status for new records (default: pending)",
    )
    return parser


def main() -> None:
    # init the parser
    parser = init_parser()
    args = parser.parse_args()

    # Run update command if specified
    match args.command:
        case "update":
            update_samples(
                path=args.path,
                fmt=args.format,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
            )
        case "irods-validate":
            # Load schema
            schema = load_schema_from_file(args.schema)

            # Validate collection
            env_file = os.environ.get("IRODS_ENVIRONMENT_FILE")
            with iRODSSession(irods_env_file=env_file) as session:
                session.connection_timeout = args.timeout
                collection = load_collection_from_irods(session, args.collection)
                report = validate_collection(collection, schema)
            # Log validation report
            log_validation_report(report)