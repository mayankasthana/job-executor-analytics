"""Validation: raw JSON values in, trusted :class:`JobRecord`s out.

Every rule lives here so that "what makes a record valid" has exactly one
definition. The parser never touches the filesystem and never aggregates —
those are the loading and analytics layers' jobs.
"""

from datetime import UTC, datetime
from typing import Any

from job_analytics.errors import RecordValidationError
from job_analytics.models import JobRecord, JobStatus

_ISO_8601_HINT = "an ISO-8601 timestamp string"


def parse_record(raw: Any) -> JobRecord:
    """Convert one raw JSON value into a validated :class:`JobRecord`.

    Raises :class:`RecordValidationError` with a human-readable reason
    otherwise. Rejections are expected on real data; callers collect them
    instead of aborting the whole run.
    """
    if not isinstance(raw, dict):
        raise RecordValidationError("record is not a JSON object")

    job_id = _required_text(raw, "job_id")
    status = _parse_status(raw)
    started_at = _parse_timestamp(raw, "started_at", required=True)
    finished_at = _parse_timestamp(raw, "finished_at", required=False)
    attempt = _parse_attempt(raw)

    if finished_at is not None and finished_at < started_at:
        raise RecordValidationError(
            "field 'finished_at' is before 'started_at' "
            f"({finished_at.isoformat()} < {started_at.isoformat()})"
        )

    return JobRecord(
        job_id=job_id,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        attempt=attempt,
    )


def _require(raw: dict[str, Any], field: str) -> Any:
    if field not in raw or raw[field] is None:
        raise RecordValidationError(f"missing field: {field}")
    return raw[field]


def _required_text(raw: dict[str, Any], field: str) -> str:
    value = _require(raw, field)
    if not isinstance(value, str):
        raise RecordValidationError(f"field '{field}' must be a string")
    value = value.strip()
    if not value:
        raise RecordValidationError(f"field '{field}' must not be blank")
    return value


def _parse_status(raw: dict[str, Any]) -> JobStatus:
    value = _require(raw, "status")
    if not isinstance(value, str):
        raise RecordValidationError("field 'status' must be a string")
    normalized = value.strip().lower()
    try:
        return JobStatus(normalized)
    except ValueError:
        expected = ", ".join(status.value for status in JobStatus)
        raise RecordValidationError(
            f"unknown status {value!r} (expected one of: {expected})"
        ) from None


def _parse_timestamp(raw: dict[str, Any], field: str, *, required: bool) -> datetime | None:
    if field not in raw or raw[field] is None:
        if required:
            raise RecordValidationError(f"missing field: {field}")
        return None
    value = raw[field]
    if not isinstance(value, str):
        raise RecordValidationError(f"field '{field}' must be {_ISO_8601_HINT}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise RecordValidationError(f"field '{field}' is not {_ISO_8601_HINT}: {value!r}") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_attempt(raw: dict[str, Any]) -> int:
    value = _require(raw, "attempt")
    # bool is a subclass of int; True/False are not valid attempts.
    if isinstance(value, bool) or not isinstance(value, int):
        raise RecordValidationError("field 'attempt' must be an integer")
    if value < 1:
        raise RecordValidationError(f"field 'attempt' must be >= 1, got {value}")
    return value
