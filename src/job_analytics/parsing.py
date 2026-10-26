"""Validation seam: raw JSON values in, trusted :class:`JobRecord`s out.

The rules live on the declarative schema in ``schema.py`` (the single
definition of "what makes a record valid"); this module is the seam that
turns one raw value into a :class:`JobRecord` or a
:class:`RecordValidationError` with a human-readable reason. Rejections are
expected on real data; callers collect them instead of aborting the run.
"""

from typing import Any

from pydantic import ValidationError

from job_analytics.errors import RecordValidationError
from job_analytics.models import JobRecord
from job_analytics.schema import JobRecordSchema

_NOT_AN_OBJECT = "record is not a JSON object"
_VALUE_ERROR_PREFIX = "Value error, "


def parse_record(raw: Any) -> JobRecord:
    """Convert one raw JSON value into a validated :class:`JobRecord`.

    Raises :class:`RecordValidationError` with the first failing rule's
    human-readable reason otherwise (pydantic collects every violation; the
    first, in field-declaration order, is reported).
    """
    if not isinstance(raw, dict):
        raise RecordValidationError(_NOT_AN_OBJECT)
    try:
        model = JobRecordSchema.model_validate(raw)
    except ValidationError as exc:
        raise RecordValidationError(_format_first_error(exc)) from None
    return model.to_record()


def _format_first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    error_type: str = error["type"]
    if error_type == "missing":
        return f"missing field: {error['loc'][0]}"
    if error_type.startswith("datetime_"):
        return (
            f"field '{error['loc'][0]}' is not an ISO-8601 timestamp string: {error.get('input')!r}"
        )
    return str(error["msg"]).removeprefix(_VALUE_ERROR_PREFIX)
