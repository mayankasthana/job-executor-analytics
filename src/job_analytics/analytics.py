"""Summary computation: pure aggregation over validated records.

No I/O and no parsing, so the calculator is trivially testable and reusable
on records from any source. The aggregate runs in a single pass, which lets
streaming sources flow straight through without materializing the records.
"""

from collections.abc import Iterable

from job_analytics.models import JobRecord, JobStatus, SummaryReport


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
