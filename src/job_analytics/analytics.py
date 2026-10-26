"""Summary computation: pure aggregation over validated records.

No I/O and no parsing, so the calculator is trivially testable and reusable
on records from any source. The aggregate runs in a single pass, which lets
streaming sources flow straight through without materializing the records.
"""

from collections.abc import Iterable
from typing import Protocol

from job_analytics.models import JobRecord, JobStatus, JobSummaryReport, SummaryReport


class SummaryStrategy(Protocol):
    """Anything that can aggregate records into a summary report."""

    def compute(self, records: Iterable[JobRecord]) -> SummaryReport | JobSummaryReport: ...


class SummaryCalculator:
    """Aggregates validated job records into a :class:`SummaryReport`."""

    def compute(self, records: Iterable[JobRecord]) -> SummaryReport:
        """Aggregate records in one pass.

        ``records`` may be any iterable, including one-shot iterators from
        streaming sources; it is consumed exactly once.
        """
        total = 0
        successful = 0
        failed = 0
        duration_total = 0.0
        duration_count = 0
        retried_job_ids: set[str] = set()

        for record in records:
            total += 1
            if record.is_successful:
                successful += 1
                duration = record.duration_seconds
                if duration is not None:
                    duration_total += duration
                    duration_count += 1
            elif record.status is JobStatus.FAILED:
                failed += 1
            if record.attempt > 1:
                retried_job_ids.add(record.job_id)

        return SummaryReport(
            total_jobs=total,
            successful_jobs=successful,
            failed_jobs=failed,
            retried_job_count=len(retried_job_ids),
            average_successful_duration_seconds=(
                duration_total / duration_count if duration_count else None
            ),
        )


class JobSummaryCalculator:
    """Aggregates records into a per-job view: the latest attempt wins.

    Unlike the record-level summary, this needs per-job state
    (O(distinct jobs) memory) for exact latest-attempt and retry semantics.
    A job's final record is the one with the highest attempt number, ties
    broken by the later started_at.
    """

    def compute(self, records: Iterable[JobRecord]) -> JobSummaryReport:
        final_by_job: dict[str, JobRecord] = {}
        retried: set[str] = set()
        for record in records:
            current = final_by_job.get(record.job_id)
            if current is None or (record.attempt, record.started_at) >= (
                current.attempt,
                current.started_at,
            ):
                final_by_job[record.job_id] = record
            if record.attempt > 1:
                retried.add(record.job_id)

        finals = list(final_by_job.values())
        successful = [record for record in finals if record.is_successful]
        durations = [
            record.duration_seconds for record in successful if record.duration_seconds is not None
        ]
        return JobSummaryReport(
            total_jobs=len(finals),
            successful_jobs=len(successful),
            failed_jobs=sum(1 for record in finals if record.status is JobStatus.FAILED),
            running_jobs=sum(1 for record in finals if record.status is JobStatus.RUNNING),
            retried_job_count=len(retried),
            successful_after_retry_count=sum(
                1 for record in successful if record.job_id in retried
            ),
            average_final_attempt_duration_seconds=(
                sum(durations) / len(durations) if durations else None
            ),
        )


_STRATEGIES: dict[str, type[SummaryCalculator | JobSummaryCalculator]] = {
    "record": SummaryCalculator,
    "job": JobSummaryCalculator,
}


def get_strategy(name: str) -> SummaryStrategy:
    """Look up an aggregation strategy by CLI-facing name."""
    try:
        return _STRATEGIES[name]()
    except KeyError:
        available = ", ".join(sorted(_STRATEGIES))
        raise ValueError(f"unknown view {name!r} (available: {available})") from None
