"""Summary computation: pure aggregation over validated records.

No I/O and no parsing, so the calculator is trivially testable and reusable
on records from any source.
"""

from collections.abc import Sequence

from job_analytics.models import JobRecord, JobStatus, SummaryReport


class SummaryCalculator:
    """Aggregates validated job records into a :class:`SummaryReport`."""

    def compute(self, records: Sequence[JobRecord]) -> SummaryReport:
        successful = [record for record in records if record.is_successful]
        durations = [
            record.duration_seconds for record in successful if record.duration_seconds is not None
        ]
        return SummaryReport(
            total_jobs=len(records),
            successful_jobs=len(successful),
            failed_jobs=sum(1 for record in records if record.status is JobStatus.FAILED),
            retried_job_count=len({record.job_id for record in records if record.attempt > 1}),
            average_successful_duration_seconds=(
                sum(durations) / len(durations) if durations else None
            ),
        )
