import os
import argparse
import logging
from logging.handlers import RotatingFileHandler
from email.message import EmailMessage
import smtplib
import markdown
from dotenv import load_dotenv
from irods.session import iRODSSession
from tracking.io import load_schema_from_file
from tracking.update import update_samples
from tracking.irods import load_collection_from_irods, validate_collection, log_validation_report, render_text_report, render_markdown_report, CollectionSchema

load_dotenv()

def setup_logging(
    log_file: str = "tracking.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,  # Keep 5 backup files
    level: int = logging.INFO
):
    """Setup logging with file rotation"""
    # Remove any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create rotating file handler
    handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    
    # Set format
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger.setLevel(level)
    root_logger.addHandler(handler)


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
        "irods-validate",
        help="Validate iRODS collections against a schema"
    )
    irods_validate_parser.add_argument(
        "collection",
        nargs="+",
        help="Path to the iRODS collection to validate"
    )
    irods_validate_parser.add_argument(
        "--schema",
        type=str,
        default=None,
        help="Path to the schema file (YAML or JSON)"
    )
    irods_validate_parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Connection timeout for iRODS session (default: 120 seconds)",
    )
    irods_validate_parser.add_argument(
        "--log-file",
        type=str,
        default="irods_validation.log",
        help="Path to the log file for validation results (default: irods_validation.log)",
    )
    irods_validate_parser.add_argument(
        "--report-format",
        choices=["text", "markdown"],
        default="text",
        help="Format of the validation report output (default: text)",
    )
    irods_validate_parser.add_argument(
        "--email",
        nargs="+",
        default=None,
        help="Email address to send the validation report to",
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
    update_parser.add_argument(
        "--log-file",
        type=str,
        default="update.log",
        help="Path to the log file for update process (default: update.log)",
    )
    return parser


def main() -> None:
    # init the parser
    parser = init_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(log_file=args.log_file)
    logger = logging.getLogger(__name__)

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
            if args.schema is None and not os.environ.get("IRODS_SCHEMA_FILE"):
                logger.error("Schema file must be provided via --schema or IRODS_SCHEMA_FILE env variable.")
                return

            schema_path = args.schema or os.environ.get("IRODS_SCHEMA_FILE")
            schema = load_schema_from_file(schema_path)

            # Validate schema
            schema = CollectionSchema.model_validate(schema)

            # Validate collection
            env_file = os.environ.get("IRODS_ENVIRONMENT_FILE")
            reports = []
            for collection in args.collection:
                with iRODSSession(irods_env_file=env_file) as session:
                    session.connection_timeout = args.timeout
                    collection = load_collection_from_irods(session, collection)
                    report = validate_collection(collection, schema)
                    reports.append(report)
                # Log validation report
                log_validation_report(report)
            # Also print a text summary to console
            if args.report_format == "markdown":
                text_report = render_markdown_report(reports)
            else:
                text_report = render_text_report(reports)
            print(text_report)

            # if args.email:
            #     markdown_report = render_markdown_report(reports) if args.report_format != "markdown" else text_report
            #     html = markdown.markdown(markdown_report)
            if args.email:
                msg = EmailMessage()
                msg.set_content(text_report)
                msg["Subject"] = "iRODS Validation Report"
                msg["From"] = "noreply-reprocessing@cellgeni-su"
                msg["To"] = ", ".join(args.email)
                msg.set_content(text_report)
                #msg.add_alternative(html, subtype="html")

                with smtplib.SMTP("localhost") as server:
                    server.send_message(msg)