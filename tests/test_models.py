"""Behavior specs for the domain model types."""

from datetime import UTC, datetime

import pytest

from job_analytics.models import JobRecord, JobStatus, RejectedRecord, SummaryReport


def make_record(**overrides):
    defaults = dict(
        job_id="job-001",
        status=JobStatus.SUCCESS,
        started_at=datetime(2026, 10, 26, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 26, 9, 10, tzinfo=UTC),
        attempt=1,
    )
    defaults.update(overrides)
    return JobRecord(**defaults)


class TestJobStatus:
    def test_status_values_match_the_json_wire_format(self):
        assert JobStatus.SUCCESS.value == "success"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.RUNNING.value == "running"


class TestJobRecord:
    def test_duration_for_a_completed_job(self):
        assert make_record().duration_seconds == 600.0

    def test_duration_is_none_while_the_job_has_not_finished(self):
        assert make_record(finished_at=None).duration_seconds is None

    def test_duration_keeps_sub_second_precision(self):
        record = make_record(finished_at=datetime(2026, 10, 26, 9, 0, 45, 500_000, tzinfo=UTC))
        assert record.duration_seconds == 45.5

    def test_records_are_immutable(self):
        with pytest.raises((AttributeError, TypeError)):
            make_record().job_id = "changed"

    def test_successful_jobs_are_identified_by_status(self):
        assert make_record(status=JobStatus.SUCCESS).is_successful
        assert not make_record(status=JobStatus.FAILED).is_successful
        assert not make_record(status=JobStatus.RUNNING).is_successful


class TestSummaryReport:
    def test_a_summary_without_successful_jobs_has_no_average(self):
        report = SummaryReport(total_jobs=2, successful_jobs=0, failed_jobs=2, retried_job_count=0)
        assert report.average_successful_duration_seconds is None


class TestRejectedRecord:
    def test_a_rejection_records_where_and_why(self):
        rejection = RejectedRecord(index=3, reason="missing field: attempt")
        assert rejection.index == 3
        assert "attempt" in rejection.reason
