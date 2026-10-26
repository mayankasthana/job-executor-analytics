"""Presentation: rendering a :class:`RunResult` for humans or machines.

Reporters implement a tiny protocol; adding a format (CSV, markdown) means
adding a class and registering it in ``_REPORTERS`` — no changes elsewhere
(open/closed principle).
"""

import json
from typing import Protocol

from job_analytics.app import RunResult
from job_analytics.models import SummaryReport


class Reporter(Protocol):
    """Anything that can render a run result as text."""

    def format(self, result: RunResult) -> str: ...


class JsonReporter:
    """Machine-readable rendering: one JSON document."""

    def format(self, result: RunResult) -> str:
        report = result.report
        payload = {
            "total_jobs": report.total_jobs,
            "successful_jobs": report.successful_jobs,
            "failed_jobs": report.failed_jobs,
            "average_successful_duration_seconds": report.average_successful_duration_seconds,
            "jobs_requiring_retries": report.retried_job_count,
            "rejected_records": len(result.rejected_records),
        }
        return json.dumps(payload, indent=2)


class TextReporter:
    """Human-readable rendering."""

    def format(self, result: RunResult) -> str:
        report = result.report
        lines = [
            "Job execution summary",
            f"  Total jobs: {report.total_jobs}",
            f"  Successful jobs: {report.successful_jobs}",
            f"  Failed jobs: {report.failed_jobs}",
            f"  Average successful duration: {_format_average(report)}",
            f"  Jobs requiring retries: {report.retried_job_count}",
            f"  Rejected records: {len(result.rejected_records)}",
        ]
        lines += [
            f"  Rejected record at index {rejection.index}: {rejection.reason}"
            for rejection in result.rejected_records
        ]
        return "\n".join(lines)


def _format_average(report: SummaryReport) -> str:
    average = report.average_successful_duration_seconds
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
