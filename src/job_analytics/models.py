"""Domain model: job execution records and the summary report shape.

These types are plain immutable data — no parsing and no I/O — so every other
layer can depend on them without transitive coupling.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class JobStatus(StrEnum):
    """The states a job execution record can carry on the wire."""

    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"


@dataclass(frozen=True, slots=True)
class JobRecord:
    """A single validated job execution record."""

    job_id: str
    status: JobStatus
    started_at: datetime
    finished_at: datetime | None
    attempt: int

    @property
    def is_successful(self) -> bool:
        return self.status is JobStatus.SUCCESS

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock execution time; None while the job has not finished."""
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


@dataclass(frozen=True, slots=True)
class RejectedRecord:
    """A raw input element that failed validation, kept for reporting."""

    index: int
    reason: str


@dataclass(frozen=True, slots=True)
class SummaryReport:
    """Aggregated view over the valid job records (one row per record)."""

    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    retried_job_count: int
    average_successful_duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class JobSummaryReport:
    """Aggregated view where each job's latest attempt decides the outcome."""

    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    running_jobs: int
    retried_job_count: int
    successful_after_retry_count: int
    average_final_attempt_duration_seconds: float | None = None
