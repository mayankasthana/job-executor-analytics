"""Presentation: rendering a :class:`RunResult` for humans or machines.

Reporters implement a tiny protocol; adding a format (CSV, markdown) means
adding a class and registering it in ``_REPORTERS`` — no changes elsewhere.
Each reporter renders any registered report type (record-level or per-job)
through the ``_JSON_PAYLOADS`` / ``_TEXT_LINES`` dispatch tables, so a new
report type is one function plus one registration.
"""

import json
from collections.abc import Callable
from typing import Any, Protocol

from job_analytics.app import RunResult
from job_analytics.models import JobSummaryReport, SummaryReport


class Reporter(Protocol):
    """Anything that can render a run result as text."""

    def format(self, result: RunResult) -> str: ...


def _record_json(report: SummaryReport) -> dict[str, Any]:
    return {
        "total_jobs": report.total_jobs,
        "successful_jobs": report.successful_jobs,
        "failed_jobs": report.failed_jobs,
        "average_successful_duration_seconds": report.average_successful_duration_seconds,
        "jobs_requiring_retries": report.retried_job_count,
    }


def _job_json(report: JobSummaryReport) -> dict[str, Any]:
    return {
        "total_jobs": report.total_jobs,
        "successful_jobs": report.successful_jobs,
        "failed_jobs": report.failed_jobs,
        "running_jobs": report.running_jobs,
        "jobs_requiring_retries": report.retried_job_count,
        "successful_after_retries": report.successful_after_retry_count,
        "average_final_attempt_duration_seconds": report.average_final_attempt_duration_seconds,
    }


_JSON_PAYLOADS: dict[type[Any], Callable[[Any], dict[str, Any]]] = {
    SummaryReport: _record_json,
    JobSummaryReport: _job_json,
}


def _record_lines(report: SummaryReport) -> list[str]:
    return [
        "Job execution summary",
        f"  Total jobs: {report.total_jobs}",
        f"  Successful jobs: {report.successful_jobs}",
        f"  Failed jobs: {report.failed_jobs}",
        f"  Average successful duration: "
        f"{_format_average(report.average_successful_duration_seconds)}",
        f"  Jobs requiring retries: {report.retried_job_count}",
    ]


def _job_lines(report: JobSummaryReport) -> list[str]:
    return [
        "Job execution summary (per job)",
        f"  Total jobs: {report.total_jobs}",
        f"  Successful jobs: {report.successful_jobs}",
        f"  Failed jobs: {report.failed_jobs}",
        f"  Running jobs: {report.running_jobs}",
        f"  Jobs requiring retries: {report.retried_job_count}",
        f"  Successful after retries: {report.successful_after_retry_count}",
        "  Average final-attempt duration: "
        f"{_format_average(report.average_final_attempt_duration_seconds)}",
    ]


_TEXT_LINES: dict[type[Any], Callable[[Any], list[str]]] = {
    SummaryReport: _record_lines,
    JobSummaryReport: _job_lines,
}


class JsonReporter:
    """Machine-readable rendering: one JSON document."""

    def format(self, result: RunResult) -> str:
        payload = _JSON_PAYLOADS[type(result.report)](result.report)
        payload["rejected_records"] = len(result.rejected_records)
        return json.dumps(payload, indent=2)


class TextReporter:
    """Human-readable rendering."""

    def format(self, result: RunResult) -> str:
        lines = _TEXT_LINES[type(result.report)](result.report)
        lines.append(f"  Rejected records: {len(result.rejected_records)}")
        lines += [
            f"  Rejected record at index {rejection.index}: {rejection.reason}"
            for rejection in result.rejected_records
        ]
        return "\n".join(lines)


def _format_average(average: float | None) -> str:
    return "n/a" if average is None else f"{average:g}s"


_REPORTERS: dict[str, type[Reporter]] = {
    "json": JsonReporter,
    "text": TextReporter,
}


def get_reporter(name: str) -> Reporter:
    """Look up a reporter by CLI-facing name."""
    try:
        return _REPORTERS[name]()
    except KeyError:
        available = ", ".join(sorted(_REPORTERS))
        raise ValueError(f"unknown report format {name!r} (available: {available})") from None
