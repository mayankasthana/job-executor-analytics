"""Behavior specs for raw-record validation."""

from datetime import UTC, datetime

import pytest

from job_analytics.errors import RecordValidationError
from job_analytics.models import JobStatus
from job_analytics.parsing import parse_record


def valid_raw(**overrides):
    raw = {
        "job_id": "job-001",
        "status": "success",
        "started_at": "2026-10-26T09:00:00Z",
        "finished_at": "2026-10-26T09:10:00Z",
        "attempt": 1,
    }
    raw.update(overrides)
    return raw


def rejects(raw, *, match):
    with pytest.raises(RecordValidationError, match=match):
        parse_record(raw)


class TestValidRecords:
    def test_a_valid_record_parses_to_a_job_record(self):
        record = parse_record(valid_raw())
        assert record.job_id == "job-001"
        assert record.status is JobStatus.SUCCESS
        assert record.attempt == 1
        assert record.duration_seconds == 600.0

    def test_explicit_utc_offsets_parse_equally_to_z(self):
        record = parse_record(valid_raw(started_at="2026-10-26T09:00:00+00:00"))
        assert record.started_at == datetime(2026, 10, 26, 9, 0, tzinfo=UTC)

    def test_naive_timestamps_are_interpreted_as_utc(self):
        record = parse_record(valid_raw(started_at="2026-10-26T09:00:00"))
        assert record.started_at.tzinfo is not None

    def test_a_null_finished_at_is_allowed(self):
        record = parse_record(valid_raw(finished_at=None))
        assert record.finished_at is None
        assert record.duration_seconds is None

    def test_the_finished_at_key_may_be_absent_entirely(self):
        raw = valid_raw()
        del raw["finished_at"]
        assert parse_record(raw).finished_at is None

    def test_running_jobs_parse_without_a_finish_time(self):
        record = parse_record(valid_raw(status="running", finished_at=None))
        assert record.status is JobStatus.RUNNING
        assert record.duration_seconds is None

    def test_status_matching_is_case_and_whitespace_insensitive(self):
        record = parse_record(valid_raw(status=" Success "))
        assert record.status is JobStatus.SUCCESS

    def test_unknown_extra_fields_are_ignored(self):
        record = parse_record(valid_raw(region="eu-west-1", queue_depth=7))
        assert record.job_id == "job-001"

    def test_zero_duration_is_valid(self):
        record = parse_record(valid_raw(finished_at="2026-10-26T09:00:00Z"))
        assert record.duration_seconds == 0.0


class TestStructuralRejections:
    @pytest.mark.parametrize("raw", ["a string", 42, None, [1, 2], 3.14])
    def test_only_json_objects_can_be_records(self, raw):
        rejects(raw, match="JSON object")

    @pytest.mark.parametrize("field", ["job_id", "status", "started_at", "attempt"])
    def test_missing_required_fields_name_the_field(self, field):
        raw = valid_raw()
        del raw[field]
        rejects(raw, match=field)

    def test_null_required_fields_are_treated_as_missing(self, field="status"):
        rejects(valid_raw(status=None), match=field)


class TestJobIdRejections:
    @pytest.mark.parametrize("bad", [7, "", "   "])
    def test_non_string_or_blank_job_ids_are_rejected(self, bad):
        rejects(valid_raw(job_id=bad), match="job_id")


class TestStatusRejections:
    def test_unknown_statuses_are_rejected(self):
        rejects(valid_raw(status="succeeded"), match="status")

    def test_non_string_statuses_are_rejected(self):
        rejects(valid_raw(status=1), match="status")


class TestTimestampRejections:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("started_at", "not-a-date"),
            ("started_at", "2026/10/26 09:00"),
            ("finished_at", "not-a-date"),
        ],
    )
    def test_unparseable_timestamps_are_rejected(self, field, value):
        rejects(valid_raw(**{field: value}), match=field)

    @pytest.mark.parametrize(
        ("field", "value"),
        [("started_at", 1_760_000_000), ("finished_at", 1.5)],
    )
    def test_non_string_timestamps_are_rejected(self, field, value):
        rejects(valid_raw(**{field: value}), match=field)

    def test_finishing_before_starting_is_rejected(self):
        rejects(
            valid_raw(
                started_at="2026-10-26T09:00:00Z",
                finished_at="2026-10-26T08:00:00Z",
            ),
            match="finished_at",
        )


class TestAttemptRejections:
    @pytest.mark.parametrize("bad", [0, -1, 1.0, "1", True, None])
    def test_invalid_attempts_are_rejected(self, bad):
        rejects(valid_raw(attempt=bad), match="attempt")

    def test_booleans_do_not_pass_as_attempts(self):
        # True is an int in Python; it must still be rejected.
        rejects(valid_raw(attempt=True), match="attempt")
