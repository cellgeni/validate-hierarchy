import os
import sys
import argparse
import logging
import time
from importlib.metadata import version, PackageNotFoundError
from logging.handlers import RotatingFileHandler
from email.message import EmailMessage
import smtplib
from tqdm import tqdm
from dotenv import load_dotenv
from pydantic import ValidationError
from irods.session import iRODSSession
from irods.exception import NetworkException
from tracking.io import SchemaError, load_schema_from_file
from tracking.irods import load_collection_from_irods, validate_collection, log_validation_report, render_text_report_summarised, render_text_report, render_markdown_report, collect_extra_paths, CollectionSchema, ValidationReport, ValidationIssue
from tracking.local import load_collection_from_dir

load_dotenv()

#: Exit status when at least one path FAILED validation.
EXIT_VALIDATION_FAILED = 1
#: Exit status for a bad invocation: unusable or missing schema. argparse uses
#: the same code for malformed arguments.
EXIT_USAGE = 2


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


def get_version() -> str:
    """Return the installed package version, falling back gracefully."""
    try:
        return version("tracking")
    except PackageNotFoundError:
        return "unknown"


def init_parser() -> argparse.ArgumentParser:
    # Initialize the argument parser
    parser = argparse.ArgumentParser(
        prog="sample-tracking",
        description="A CLI tool for managing and tracking reprocessing datasets",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_version()}",
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
        help="Path to the schema file (YAML or JSON). Defaults to IRODS_SCHEMA_FILE env variable."
    )
    irods_validate_parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Connection timeout for iRODS session (default: 120 seconds)",
    )
    irods_validate_parser.add_argument(
        "--config-file",
        type=str,
        default=None,
        help="Path to the iRODS environment (config) file. Defaults to IRODS_ENVIRONMENT_FILE env variable.",
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
    irods_validate_parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Path to save the validation report",
    )
    irods_validate_parser.add_argument(
        "--min-collection-summary",
        type=int,
        default=5,
        help="Minimum number of collections to trigger summary report (default: 5)",
    )
    irods_validate_parser.add_argument(
        "--progress-bar",
        action="store_true",
        help="Show a progress bar during validation",
    )
    irods_validate_parser.add_argument(
        "--no-exit",
        action="store_true",
        help="Always exit with status 0, even if some collections FAILED validation",
    )
    irods_validate_parser.add_argument(
        "--extra-paths-file",
        type=str,
        default=None,
        help="Path to write the full paths of unexpected files/collections found during validation, one per line",
    )

    # Subparser for local directory validation
    local_validate_parser = subparsers.add_parser(
        "local-validate",
        help="Validate local directories against a schema"
    )
    local_validate_parser.add_argument(
        "directory",
        nargs="+",
        help="Path to the local directory to validate"
    )
    local_validate_parser.add_argument(
        "--schema",
        type=str,
        default=None,
        help="Path to the schema file (YAML or JSON). Defaults to LOCAL_SCHEMA_FILE env variable."
    )
    local_validate_parser.add_argument(
        "--log-file",
        type=str,
        default="local_validation.log",
        help="Path to the log file for validation results (default: local_validation.log)",
    )
    local_validate_parser.add_argument(
        "--report-format",
        choices=["text", "markdown"],
        default="text",
        help="Format of the validation report output (default: text)",
    )
    local_validate_parser.add_argument(
        "--email",
        nargs="+",
        default=None,
        help="Email address to send the validation report to",
    )
    local_validate_parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Path to save the validation report",
    )
    local_validate_parser.add_argument(
        "--min-collection-summary",
        type=int,
        default=5,
        help="Minimum number of directories to trigger summary report (default: 5)",
    )
    local_validate_parser.add_argument(
        "--progress-bar",
        action="store_true",
        help="Show a progress bar during validation",
    )
    local_validate_parser.add_argument(
        "--no-exit",
        action="store_true",
        help="Always exit with status 0, even if some directories FAILED validation",
    )
    local_validate_parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow symlinked directories and files when walking the tree "
             "(e.g. for Nextflow work directories)",
    )
    local_validate_parser.add_argument(
        "--extra-paths-file",
        type=str,
        default=None,
        help="Path to write the full paths of unexpected files/collections found during validation, one per line",
    )

    return parser


def load_and_validate_schema(
    schema_arg: str | None,
    env_var: str = "IRODS_SCHEMA_FILE",
) -> CollectionSchema:
    """
    Resolve the schema path from the CLI arg or the given env variable, load it
    and validate it into a CollectionSchema.

    Args:
        schema_arg: Value of the --schema CLI option (may be None).
        env_var: Name of the environment variable to fall back to for the
            default schema path (e.g. IRODS_SCHEMA_FILE or LOCAL_SCHEMA_FILE).

    Raises:
        SchemaError: If no path can be resolved, or the schema is invalid.
    """
    schema_path = schema_arg or os.environ.get(env_var)
    if schema_path is None:
        raise SchemaError(
            f"No schema given. Pass --schema or set the {env_var} environment variable."
        )

    data = load_schema_from_file(schema_path)
    try:
        return CollectionSchema.model_validate(data)
    except ValidationError as exc:
        raise SchemaError(f"Invalid schema in {schema_path}:\n{format_errors(exc)}") from exc


def format_errors(exc: ValidationError) -> str:
    """
    Render pydantic errors as one indented, location-prefixed line each.
    """
    lines = []
    seen = set()
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        line = f"  {location}: {error['msg']}"
        if line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)


def load_error_report(path: str, message: str) -> ValidationReport:
    """
    Build a FAILED report for a path that could not even be read.
    """
    return ValidationReport(
        path=path,
        ok=False,
        issues=[ValidationIssue(path=path, kind="load_error", message=message)],
    )


def any_failed(reports) -> bool:
    """
    Return True if any report represents a FAILED validation.
    """
    return any(not report.ok for report in reports)


def emit_reports(reports, args, subject: str) -> None:
    """
    Render, print, optionally save and optionally email a list of validation
    reports. Shared between iRODS and local validation commands.
    """
    if args.report_format == "markdown":
        text_report = render_markdown_report(reports)
    else:
        text_report = render_text_report(reports)

    report_to_show = text_report if len(reports) < args.min_collection_summary else render_text_report_summarised(reports)
    print(report_to_show)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(text_report)

    if args.extra_paths_file:
        extra_paths = collect_extra_paths(reports)
        with open(args.extra_paths_file, "w", encoding="utf-8") as f:
            f.write("\n".join(extra_paths))
            if extra_paths:
                f.write("\n")

    if args.email:
        msg = EmailMessage()
        msg.set_content(report_to_show)
        msg["Subject"] = subject
        msg["From"] = "noreply-reprocessing@cellgeni-su"
        msg["To"] = ", ".join(args.email)
        if args.report:
            with open(args.report, "rb") as f:
                file_data = f.read()
                file_name = os.path.basename(args.report)
            msg.add_attachment(
                file_data,
                maintype="text",
                subtype="plain",
                filename=file_name
            )

        with smtplib.SMTP("localhost") as server:
            server.send_message(msg)


def main() -> None:
    # init the parser
    parser = init_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(log_file=args.log_file)
    logger = logging.getLogger(__name__)

    match args.command:
        case "irods-validate":
            # Load schema
            try:
                schema = load_and_validate_schema(args.schema)
            except SchemaError as exc:
                logger.error("%s", exc)
                print(f"sample-tracking: error: {exc}", file=sys.stderr)
                sys.exit(EXIT_USAGE)

            # Validate collection
            env_file = args.config_file or os.environ.get("IRODS_ENVIRONMENT_FILE")
            reports = []
            collection_iterable = tqdm(args.collection, desc="Validating collections", unit="collection") if args.progress_bar else args.collection
            
            for collection_path in collection_iterable:
                if args.progress_bar:
                    collection_iterable.set_postfix_str(f"Processing: {collection_path}")
                
                logger.info("Validating iRODS collection: %s", collection_path)
                
                # Retry logic for network exceptions
                max_retries = 3
                retry_count = 0
                
                while retry_count < max_retries:
                    try:
                        with iRODSSession(irods_env_file=env_file) as session:
                            session.connection_timeout = args.timeout
                            collection_obj = load_collection_from_irods(session, collection_path)
                            report = validate_collection(collection_obj, schema)
                            reports.append(report)
                            
                        # Log validation report
                        log_validation_report(report)
                        break  # Success, exit retry loop
                        
                    except NetworkException as e:
                        retry_count += 1
                        if retry_count < max_retries:
                            logger.warning(
                                f"Network error for collection {collection_path} (attempt {retry_count}/{max_retries}): {e}. "
                                f"Retrying in 15 seconds..."
                            )
                            if args.progress_bar:
                                collection_iterable.set_postfix_str(f"Retrying {collection_path} in 15s...")
                            time.sleep(15)
                        else:
                            logger.error(
                                f"Failed to validate {collection_path} after {max_retries} attempts: {e}"
                            )
                            reports.append(load_error_report(
                                collection_path,
                                f"Network error after {max_retries} attempts: {e}",
                            ))
                            if args.progress_bar:
                                collection_iterable.set_postfix_str(f"Failed: {collection_path}")

                    except Exception as e:
                        logger.error(f"Unexpected error validating {collection_path}: {e}")
                        reports.append(load_error_report(
                            collection_path, f"{type(e).__name__}: {e}"
                        ))
                        if args.progress_bar:
                            collection_iterable.set_postfix_str(f"Error: {collection_path}")
                        break  # Don't retry for non-network errors

            emit_reports(reports, args, subject="iRODS Validation Report")

            if any_failed(reports) and not args.no_exit:
                sys.exit(EXIT_VALIDATION_FAILED)

        case "local-validate":
            # Load schema
            try:
                schema = load_and_validate_schema(args.schema, env_var="LOCAL_SCHEMA_FILE")
            except SchemaError as exc:
                logger.error("%s", exc)
                print(f"sample-tracking: error: {exc}", file=sys.stderr)
                sys.exit(EXIT_USAGE)

            reports = []
            dir_iterable = tqdm(args.directory, desc="Validating directories", unit="directory") if args.progress_bar else args.directory

            for dir_path in dir_iterable:
                if args.progress_bar:
                    dir_iterable.set_postfix_str(f"Processing: {dir_path}")

                logger.info("Validating local directory: %s", dir_path)

                try:
                    collection_obj = load_collection_from_dir(dir_path, follow_symlinks=args.follow_symlinks)
                    report = validate_collection(collection_obj, schema)
                    reports.append(report)
                    log_validation_report(report)
                except OSError as e:
                    logger.error(f"Cannot validate {dir_path}: {e}")
                    reports.append(load_error_report(dir_path, str(e)))
                    if args.progress_bar:
                        dir_iterable.set_postfix_str(f"Failed: {dir_path}")
                except Exception as e:
                    logger.error(f"Unexpected error validating {dir_path}: {e}")
                    reports.append(load_error_report(dir_path, f"{type(e).__name__}: {e}"))
                    if args.progress_bar:
                        dir_iterable.set_postfix_str(f"Error: {dir_path}")

            emit_reports(reports, args, subject="Local Directory Validation Report")

            if any_failed(reports) and not args.no_exit:
                sys.exit(EXIT_VALIDATION_FAILED)