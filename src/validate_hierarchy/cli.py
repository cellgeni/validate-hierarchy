"""Command-line interface for validate-hierarchy."""

import argparse
import logging
import os
import smtplib
import sys
import time
from collections.abc import Iterable
from email.message import EmailMessage
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from tqdm import tqdm

from validate_hierarchy import __version__
from validate_hierarchy.models import (
    CollectionSchema,
    ValidationIssue,
    ValidationReport,
)
from validate_hierarchy.report import (
    any_failed,
    collect_extra_paths,
    log_validation_report,
    render_markdown_report,
    render_text_report,
    render_text_report_summarised,
)
from validate_hierarchy.schema import SchemaError, load_schema_from_file
from validate_hierarchy.sources.local import load_collection_from_dir
from validate_hierarchy.validate import validate_collection

load_dotenv()

PROG = "validate-hierarchy"

#: Exit status when at least one path FAILED validation.
EXIT_VALIDATION_FAILED = 1
#: Exit status for a bad invocation: unusable schema, missing iRODS extra, etc.
#: (argparse uses the same code for malformed arguments.)
EXIT_USAGE = 2

DEFAULT_EMAIL_FROM = "noreply@localhost"
DEFAULT_SMTP_HOST = "localhost"


def _bounded_int(minimum: int):
    """Build an argparse type that rejects integers below `minimum`.

    Out-of-range values become a usage error (exit 2) rather than silently
    degenerating: `--retries 0`, for instance, would otherwise skip every
    collection and report success.
    """
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
        if number < minimum:
            raise argparse.ArgumentTypeError(f"must be {minimum} or greater, got {number}")
        return number

    return parse


def setup_logging(
    log_file: str,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,  # Keep 5 backup files
    level: int = logging.INFO,
) -> None:
    """Send root-logger output to a rotating file, replacing any handlers."""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        # Close as well as detach: a second call would otherwise leak the file
        # descriptor of the previous log file.
        handler.close()

    handler = RotatingFileHandler(
        filename=log_file, maxBytes=max_bytes, backupCount=backup_count
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )

    root_logger.setLevel(level)
    root_logger.addHandler(handler)


def _add_common_arguments(parser: argparse.ArgumentParser, noun: str) -> None:
    """Add the options shared by every validation subcommand.

    Args:
        parser: The subcommand parser to extend.
        noun: What the subcommand validates ("collections"/"directories"),
            used in help text.
    """
    parser.add_argument(
        "--schema",
        type=str,
        required=True,
        help="Path to the schema file (YAML with !include and/or anchors, or JSON)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to the log file for validation results "
             f"(default: {parser.get_default('log_file_default')})",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Verbosity of the log file (default: info)",
    )
    parser.add_argument(
        "--report-format",
        choices=["text", "markdown"],
        default="text",
        help="Format of the saved validation report (default: text)",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Path to save the full validation report",
    )
    parser.add_argument(
        "--min-collection-summary",
        type=_bounded_int(0),
        default=5,
        help=f"Number of {noun} at or above which the printed/emailed report is "
             "summarised instead of listed in full (default: 5)",
    )
    parser.add_argument(
        "--extra-paths-file",
        type=str,
        default=None,
        help="Path to write the full paths of unexpected files/collections found "
             "during validation, one per line",
    )
    parser.add_argument(
        "--email",
        nargs="+",
        default=None,
        help="Email address(es) to send the validation report to",
    )
    parser.add_argument(
        "--email-from",
        type=str,
        default=os.environ.get("VALIDATE_HIERARCHY_EMAIL_FROM", DEFAULT_EMAIL_FROM),
        help="Sender address for emailed reports (default: "
             f"VALIDATE_HIERARCHY_EMAIL_FROM env variable or {DEFAULT_EMAIL_FROM})",
    )
    parser.add_argument(
        "--email-subject",
        type=str,
        default=None,
        help="Subject line for emailed reports",
    )
    parser.add_argument(
        "--smtp-host",
        type=str,
        default=os.environ.get("VALIDATE_HIERARCHY_SMTP_HOST", DEFAULT_SMTP_HOST),
        help="SMTP host used to send emailed reports (default: "
             f"VALIDATE_HIERARCHY_SMTP_HOST env variable or {DEFAULT_SMTP_HOST})",
    )
    parser.add_argument(
        "--progress-bar",
        action="store_true",
        help="Show a progress bar during validation",
    )
    parser.add_argument(
        "--no-exit",
        action="store_true",
        help=f"Always exit with status 0, even if some {noun} FAILED validation",
    )


def init_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Validate directory and iRODS collection hierarchies "
                    "against a declarative YAML schema.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ---- local filesystem ---------------------------------------------------
    local = subparsers.add_parser(
        "local",
        help="Validate local directories against a schema",
        description="Validate local filesystem directories against a schema. "
                    "Files map to data objects and sub-directories to "
                    "sub-collections.",
    )
    local.set_defaults(
        log_file_default="local_validation.log",
        email_subject_default="Local Directory Validation Report",
        summary_title="Local Directory Validation Report",
    )
    local.add_argument(
        "directory", nargs="+", help="Path to the local directory to validate"
    )
    _add_common_arguments(local, noun="directories")
    local.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow symlinked directories and files when walking the tree "
             "(e.g. for Nextflow work directories)",
    )

    # ---- iRODS --------------------------------------------------------------
    irods = subparsers.add_parser(
        "irods",
        help="Validate iRODS collections against a schema (requires the "
             "'irods' extra)",
        description="Validate iRODS collections against a schema. Requires "
                    "python-irodsclient: pip install 'validate-hierarchy[irods]'",
    )
    irods.set_defaults(
        log_file_default="irods_validation.log",
        email_subject_default="iRODS Validation Report",
        summary_title="iRODS Validation Report",
    )
    irods.add_argument(
        "collection", nargs="+", help="Path to the iRODS collection to validate"
    )
    _add_common_arguments(irods, noun="collections")
    irods.add_argument(
        "--config-file",
        type=str,
        default=None,
        help="Path to the iRODS environment (config) file. Defaults to the "
             "IRODS_ENVIRONMENT_FILE env variable.",
    )
    irods.add_argument(
        "--timeout",
        type=_bounded_int(1),
        default=120,
        help="Connection timeout for the iRODS session (default: 120 seconds)",
    )
    irods.add_argument(
        "--retries",
        type=_bounded_int(1),
        default=3,
        help="Attempts per collection before giving up on network errors "
             "(default: 3)",
    )
    irods.add_argument(
        "--retry-delay",
        type=_bounded_int(0),
        default=15,
        help="Seconds to wait between network-error retries (default: 15)",
    )

    # ---- schema conversion --------------------------------------------------
    flatten = subparsers.add_parser(
        "flatten",
        help="Rewrite an !include-based schema as one anchored file",
        description="Resolve every !include in a schema and re-emit it as a "
                    "single self-contained file, using YAML anchors so "
                    "fragments used more than once are still written once. "
                    "The result is checked to parse back to identical data "
                    "before it is written.",
    )
    flatten.add_argument("schema", help="Path to the schema file to flatten")
    flatten.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Write to this file instead of standard output",
    )

    return parser


def _progress(paths: list[str], enabled: bool, unit: str):
    """Wrap `paths` in a tqdm bar when `enabled`, else return them unchanged."""
    if not enabled:
        return paths
    return tqdm(paths, desc=f"Validating {unit}s", unit=unit)


def _set_status(iterable, enabled: bool, status: str) -> None:
    if enabled:
        iterable.set_postfix_str(status)


def _load_error_report(path: str, message: str) -> ValidationReport:
    """Build a FAILED report for a path that could not even be read."""
    return ValidationReport(
        path=path,
        ok=False,
        issues=[ValidationIssue(path=path, kind="load_error", message=message)],
    )


def validate_local_paths(
    directories: list[str], schema: CollectionSchema, *, follow_symlinks: bool,
    progress_bar: bool,
) -> list[ValidationReport]:
    """Validate each local directory, collecting one report per directory."""
    logger = logging.getLogger(__name__)
    reports: list[ValidationReport] = []
    iterable = _progress(directories, progress_bar, unit="directory")

    for path in iterable:
        _set_status(iterable, progress_bar, f"Processing: {path}")
        logger.info("Validating local directory: %s", path)
        try:
            collection = load_collection_from_dir(
                path, follow_symlinks=follow_symlinks
            )
        except OSError as exc:
            logger.error("Cannot validate %s: %s", path, exc)
            reports.append(_load_error_report(path, str(exc)))
            _set_status(iterable, progress_bar, f"Failed: {path}")
            continue

        report = validate_collection(collection, schema)
        reports.append(report)
        log_validation_report(report)

    return reports


def validate_irods_paths(
    collections: list[str], schema: CollectionSchema, *, env_file: str | None,
    timeout: int, retries: int, retry_delay: int, progress_bar: bool,
) -> list[ValidationReport]:
    """Validate each iRODS collection, retrying transient network failures."""
    from validate_hierarchy.sources.irods import (
        load_collection_from_irods,
        require_irods,
    )

    irods_session, network_exception = require_irods()

    logger = logging.getLogger(__name__)
    reports: list[ValidationReport] = []
    iterable = _progress(collections, progress_bar, unit="collection")

    for path in iterable:
        _set_status(iterable, progress_bar, f"Processing: {path}")
        logger.info("Validating iRODS collection: %s", path)

        for attempt in range(1, retries + 1):
            try:
                with irods_session(irods_env_file=env_file) as session:
                    session.connection_timeout = timeout
                    collection = load_collection_from_irods(session, path)
                report = validate_collection(collection, schema)
                reports.append(report)
                log_validation_report(report)
                break

            except network_exception as exc:
                if attempt < retries:
                    logger.warning(
                        "Network error for collection %s (attempt %d/%d): %s. "
                        "Retrying in %d seconds...",
                        path, attempt, retries, exc, retry_delay,
                    )
                    _set_status(
                        iterable, progress_bar,
                        f"Retrying {path} in {retry_delay}s...",
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        "Failed to validate %s after %d attempts: %s",
                        path, retries, exc,
                    )
                    reports.append(_load_error_report(
                        path, f"Network error after {retries} attempts: {exc}"
                    ))
                    _set_status(iterable, progress_bar, f"Failed: {path}")

            # Deliberately broad: one unreadable collection must not abort a
            # sweep over thousands. It is recorded as a load_error instead.
            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected error validating %s: %s", path, exc)
                reports.append(_load_error_report(path, f"{type(exc).__name__}: {exc}"))
                _set_status(iterable, progress_bar, f"Error: {path}")
                break  # Don't retry for non-network errors

    return reports


def send_email_report(
    body: str, recipients: Iterable[str], *, subject: str, sender: str,
    smtp_host: str, attachment: str | None = None,
) -> None:
    """Email `body`, optionally attaching the saved report file."""
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    if attachment:
        with open(attachment, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype="text",
                subtype="plain",
                filename=os.path.basename(attachment),
            )

    with smtplib.SMTP(smtp_host) as server:
        server.send_message(msg)


def emit_reports(reports: list[ValidationReport], args: argparse.Namespace) -> None:
    """Print, optionally save, and optionally email a list of reports."""
    full_report = (
        render_markdown_report(reports)
        if args.report_format == "markdown"
        else render_text_report(reports)
    )

    if len(reports) < args.min_collection_summary:
        shown = render_text_report(reports)
    else:
        shown = render_text_report_summarised(reports, title=args.summary_title)
    print(shown)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(full_report)

    if args.extra_paths_file:
        extra_paths = collect_extra_paths(reports)
        with open(args.extra_paths_file, "w", encoding="utf-8") as f:
            f.writelines(f"{path}\n" for path in extra_paths)

    if args.email:
        send_email_report(
            shown,
            args.email,
            subject=args.email_subject or args.email_subject_default,
            sender=args.email_from,
            smtp_host=args.smtp_host,
            attachment=args.report,
        )


def run_flatten(args: argparse.Namespace) -> int:
    """Flatten a schema to stdout or `--output`. Returns the exit status."""
    from validate_hierarchy.flatten import flatten_schema

    try:
        text = flatten_schema(args.schema)
    except SchemaError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns the process exit status."""
    parser = init_parser()
    args = parser.parse_args(argv)

    # `flatten` rewrites a file rather than validating a tree: it wants no log
    # file, no schema resolution from the environment and no report.
    if args.command == "flatten":
        return run_flatten(args)

    setup_logging(
        log_file=args.log_file or args.log_file_default,
        level=getattr(logging, args.log_level.upper()),
    )
    logger = logging.getLogger(__name__)

    try:
        schema = load_schema_from_file(args.schema)
    except SchemaError as exc:
        logger.error("%s", exc)
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.command == "local":
        reports = validate_local_paths(
            args.directory,
            schema,
            follow_symlinks=args.follow_symlinks,
            progress_bar=args.progress_bar,
        )
    else:
        from validate_hierarchy.sources.irods import IrodsSupportError

        try:
            reports = validate_irods_paths(
                args.collection,
                schema,
                env_file=args.config_file or os.environ.get("IRODS_ENVIRONMENT_FILE"),
                timeout=args.timeout,
                retries=args.retries,
                retry_delay=args.retry_delay,
                progress_bar=args.progress_bar,
            )
        except IrodsSupportError as exc:
            logger.error("%s", exc)
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return EXIT_USAGE

    emit_reports(reports, args)

    if any_failed(reports) and not args.no_exit:
        return EXIT_VALIDATION_FAILED
    return 0
