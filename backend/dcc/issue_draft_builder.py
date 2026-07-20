"""Build JIRA draft content from an integrity-checked private analysis report."""

import json
import math

from django.core.files import File
from rest_framework.exceptions import ValidationError

from jobs.handoffs import verify_artifact_integrity
from jobs.models import JobStatus
from word.analysis_contracts import ANALYSIS_CHECKS

MAX_REPORT_BYTES = 1024 * 1024


def build_draft_content(job):
    """Return bounded summary and description from one verified analysis job."""

    report = load_analysis_report(job)
    checks = validate_report_checks(report.get("checks"))
    summary = f"Review document analysis: {job.input_name}"[:255]
    description = render_description(job, checks)
    return summary, description[:30000]


def load_analysis_report(job):
    """Load an owned analysis artifact only after state and integrity checks."""

    validate_source_job(job)
    try:
        size = job.output_file.size
    except (OSError, ValueError) as error:
        raise ValidationError({"source_job_id": "The analysis report is unavailable."}) from error
    if size > MAX_REPORT_BYTES:
        raise ValidationError({"source_job_id": "The analysis report exceeds the bridge limit."})
    payload = read_verified_report(job)
    return decode_report(payload)


def read_verified_report(job):
    """Read a bounded private artifact while preserving integrity failures."""

    try:
        with job.output_file.open("rb") as output:
            artifact = File(output, name=job.output_name)
            verify_artifact_integrity(artifact, job.output_sha256)
            return artifact.read(MAX_REPORT_BYTES + 1)
    except (OSError, ValueError) as error:
        raise ValidationError({"source_job_id": "The analysis report is unavailable."}) from error


def validate_source_job(job):
    """Require a successful private document-analysis output."""

    valid = (
        job.kind == "word.analyze"
        and job.status == JobStatus.SUCCEEDED
        and bool(job.output_file)
        and bool(job.output_sha256)
    )
    if not valid:
        raise ValidationError({"source_job_id": "Select a completed document-analysis job."})


def decode_report(payload):
    """Decode a bounded generated JSON report behind a safe validation boundary."""

    try:
        report = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError({"source_job_id": "The analysis report is invalid."}) from error
    if not isinstance(report, dict):
        raise ValidationError({"source_job_id": "The analysis report is invalid."})
    return report


def validate_report_checks(value):
    """Accept only the bounded check schema emitted by the analysis worker."""

    if not isinstance(value, list) or not value or len(value) > len(ANALYSIS_CHECKS):
        raise ValidationError({"source_job_id": "The analysis report has invalid checks."})
    if any(not valid_check(item) for item in value):
        raise ValidationError({"source_job_id": "The analysis report has invalid checks."})
    return value


def valid_check(item):
    """Return whether one generated check uses the allowlisted schema."""

    return (
        isinstance(item, dict)
        and item.get("id") in ANALYSIS_CHECKS
        and item.get("status") in {"success", "warning", "error"}
        and isinstance(item.get("evidence", []), list)
        and len(item.get("evidence", [])) <= 5
    )


def render_description(job, checks):
    """Render concise JIRA-safe plain text with explainable evidence."""

    lines = [
        "AW Center document analysis review",
        f"Source document: {job.input_name}",
        f"Analysis job: {job.id}",
        "",
    ]
    for check in checks:
        lines.extend(render_check(check))
    return "\n".join(lines)


def render_check(check):
    """Render one bounded analysis check and its evidence snippets."""

    score = normalized_score(check.get("score"))
    title = bounded_text(check.get("title"), 500)
    lines = [f"[{check['status'].upper()}] {title} ({score:.0%})"]
    explanation = bounded_text(check.get("explanation"), 1000)
    if explanation:
        lines.append(f"Explanation: {explanation}")
    lines.extend(render_evidence(check.get("evidence", [])))
    return [*lines, ""]


def render_evidence(items):
    """Render up to five bounded evidence snippets without internal paths."""

    rendered = []
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        heading = bounded_text(item.get("heading"), 200)
        text = bounded_text(item.get("text"), 800)
        prefix = f"{heading}: " if heading else ""
        if text:
            rendered.append(f"- Evidence: {prefix}{text}")
    return rendered


def bounded_text(value, limit):
    """Flatten untrusted generated text into bounded single-line content."""

    printable = "".join(character if ord(character) >= 32 else " " for character in str(value or ""))
    return " ".join(printable.split())[:limit]


def normalized_score(value):
    """Return a finite bounded score for display in the issue draft."""

    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score)) if math.isfinite(score) else 0.0
