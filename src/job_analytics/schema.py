"""Declarative record schema: the single definition of a valid record.

Validation runs on a pydantic model (a deliberate dependency, see the README's
"Assumptions and design decisions"): the model declares the record shape and
coercion rules, and ``mode="before"`` validators carry the user-facing
rejection messages. Naive timestamps are normalized to UTC, and cross-field
ordering is checked after coercion. The public seam is
:func:`job_analytics.parsing.parse_record`, which translates pydantic's
structured errors into :class:`RecordValidationError`.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from job_analytics.models import JobRecord, JobStatus

_ISO_8601_HINT = "an ISO-8601 timestamp string"


def _expected_statuses() -> str:
    return ", ".join(status.value for status in JobStatus)


class JobRecordSchema(BaseModel):
    """The declared shape of a raw job execution record."""

    model_config = ConfigDict(extra="ignore")

    job_id: str
    status: JobStatus
    started_at: datetime
    finished_at: datetime | None = None
    attempt: int

    @field_validator("job_id", mode="before")
    @classmethod
    def _validate_job_id(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("missing field: job_id")
        if not isinstance(value, str):
            raise ValueError("field 'job_id' must be a string")
        value = value.strip()
        if not value:
            raise ValueError("field 'job_id' must not be blank")
        return value

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("missing field: status")
        if not isinstance(value, str):
            raise ValueError("field 'status' must be a string")
        normalized = value.strip().lower()
        if normalized not in JobStatus.__members__.values():
            raise ValueError(f"unknown status {value!r} (expected one of: {_expected_statuses()})")
        return normalized

    @field_validator("started_at", mode="before")
    @classmethod
    def _validate_started_at(cls, value: Any) -> Any:
        return _validate_timestamp(value, "started_at", required=True)

    @field_validator("finished_at", mode="before")
    @classmethod
    def _validate_finished_at(cls, value: Any) -> Any:
        return _validate_timestamp(value, "finished_at", required=False)

    @field_validator("attempt", mode="before")
    @classmethod
    def _validate_attempt(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("missing field: attempt")
        # bool is a subclass of int; True/False are not valid attempts.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("field 'attempt' must be an integer")
        if value < 1:
            raise ValueError(f"field 'attempt' must be >= 1, got {value}")
        return value

    @field_validator("started_at", "finished_at")
    @classmethod
    def _ensure_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    @model_validator(mode="after")
    def _check_ordering(self) -> "JobRecordSchema":
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError(
                "field 'finished_at' is before 'started_at' "
                f"({self.finished_at.isoformat()} < {self.started_at.isoformat()})"
            )
        return self

    def to_record(self) -> JobRecord:
        return JobRecord(
            job_id=self.job_id,
            status=self.status,
            started_at=self.started_at,
            finished_at=self.finished_at,
            attempt=self.attempt,
        )


def _validate_timestamp(value: Any, field: str, *, required: bool) -> Any:
    if value is None:
        if required:
            raise ValueError(f"missing field: {field}")
        return None
    if not isinstance(value, str):
        raise ValueError(f"field '{field}' must be {_ISO_8601_HINT}")
    return value  # parsed by the declared datetime field
