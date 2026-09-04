"""Logging and rendering of validation reports."""

import json
import logging
from collections import Counter
from collections.abc import Iterable

from validate_hierarchy.models import ValidationReport

ISSUE_LEVELS: dict[str, int] = {
    "load_error":             logging.ERROR,
    "name_mismatch":          logging.ERROR,
    "missing_files":          logging.ERROR,
    "too_many_files":         logging.ERROR,
    "unexpected_files":       logging.WARNING,
    "missing_collections":    logging.ERROR,
    "too_many_collections":   logging.ERROR,
    "unexpected_collections": logging.WARNING,
    "missing_metadata_keys":  logging.ERROR,
}

EMPTY_REPORT = "No paths were validated."


def log_validation_report(
    report: ValidationReport,
    *,
    logger: logging.Logger | None = None,
    as_json: bool = False,
) -> None:
    """Log every issue in `report`, then a one-line summary."""
    if logger is None:
        logger = logging.getLogger("validate_hierarchy.validation")

    for issue in report.issues:
        level = ISSUE_LEVELS.get(issue.kind, logging.INFO)

        if as_json:
            logger.log(level, json.dumps({
                "path": issue.path,
                "kind": issue.kind,
                "message": issue.message,
                "details": issue.details,
            }, ensure_ascii=False))
        else:
            msg = f"{issue.path} | {issue.kind}: {issue.message}"
            if issue.details:
                msg += f" | details={issue.details}"
            logger.log(level, msg)

    counts = Counter(issue.kind for issue in report.issues)
    summary = ", ".join(f"{k}={counts[k]}" for k in sorted(counts)) or "no issues"
    status = "PASSED" if report.ok else "FAILED"
    logger.info("Validation %s for %s (%s)", status, report.path, summary)


def any_failed(reports: Iterable[ValidationReport]) -> bool:
    """Return True if any report represents a FAILED validation."""
    return any(not report.ok for report in reports)


def _relative_issue_path(issue_path: str, report_root: str) -> str:
    """Present the location of an issue relative to the report's root.

    Issues carry the absolute path of the sub-collection they occurred in. When
    that path is nested under the report root, show it relative to the root so
    it is clear *which* subdirectory the issue belongs to. The root itself is
    shown as ".".
    """
    if issue_path == report_root:
        return "."
    prefix = report_root.rstrip("/") + "/"
    if issue_path.startswith(prefix):
        return issue_path[len(prefix):]
    return issue_path


def collect_extra_paths(reports: Iterable[ValidationReport]) -> list[str]:
    """Collect full paths of every unexpected file/collection across `reports`."""
    paths: list[str] = []
    for report in reports:
        for issue in report.issues:
            names = issue.details.get(issue.kind, [])
            if issue.kind in ("unexpected_files", "unexpected_collections") and names:
                paths.extend(f"{issue.path.rstrip('/')}/{name}" for name in names)
    return paths


def render_text_report(reports: list[ValidationReport]) -> str:
    """Render every report in full as plain text."""
    if not reports:
        return EMPTY_REPORT

    lines: list[str] = []
    for report in reports:
        lines.append("=" * len(report.path))
        lines.append(report.path)
        lines.append("=" * len(report.path))

        if report.ok:
            lines.append("Status: OK ✅ (no issues)")
        else:
            lines.append(f"Status: FAILED ❌ ({len(report.issues)} issues)")
            for i, issue in enumerate(report.issues, start=1):
                lines.append(f"  [{i}] {_relative_issue_path(issue.path, report.path)}")
                lines.append(f"      {issue.kind}: {issue.message}")
                if issue.details:
                    lines.append(f"      details: {issue.details}")
        lines.append("")  # blank line between collections

    return "\n".join(lines)


def render_text_report_summarised(
    reports: list[ValidationReport], title: str = "Validation Report"
) -> str:
    """Render pass/fail counts and issue totals instead of per-report detail."""
    if not reports:
        return EMPTY_REPORT

    total = len(reports)
    failing = sum(1 for report in reports if not report.ok)

    issue_counter: Counter = Counter()
    for report in reports:
        issue_counter.update(issue.kind for issue in report.issues)

    lines = [
        title,
        "=" * len(title),
        f"Total paths checked:   {total}",
        f"✅ Passing:            {total - failing}",
        f"❌ Failing:            {failing}",
        "",
    ]

    if issue_counter:
        lines.append("Issue counts by type:")
        lines.extend(
            f"  - {kind}: {count}" for kind, count in sorted(issue_counter.items())
        )
    return "\n".join(lines)


def render_markdown_report(reports: list[ValidationReport]) -> str:
    """Render every report in full as Markdown."""
    if not reports:
        return f"_{EMPTY_REPORT}_"

    lines: list[str] = []
    for report in reports:
        lines.append(f"## `{report.path}`  ")

        if report.ok:
            lines.append("\n**Status:** ✅ OK (no issues)\n")
        else:
            lines.append(f"\n**Status:** ❌ FAILED ({len(report.issues)} issues)\n")
            for issue in report.issues:
                location = _relative_issue_path(issue.path, report.path)
                lines.append(f"- `{location}` — **{issue.kind}** – {issue.message}")
                if issue.details:
                    lines.append(f"  - details: `{issue.details}`")
        lines.append("")  # blank line

    return "\n".join(lines)
