"""Behavior specs for the application pipeline."""

import pytest

from job_analytics.app import JobAnalyticsApp, RunResult
from job_analytics.errors import InputFileError
from job_analytics.models import SummaryReport


class StaticSource:
    """Fake RecordSource: returns canned raw records, no I/O."""

    def __init__(self, records):
        self._records = records
        self.read_calls = 0

    def read_records(self):
        self.read_calls += 1
        return list(self._records)


def valid_raw(**overrides):
    raw = {
        "job_id": "job-1",
        "status": "success",
        "started_at": "2026-10-26T09:00:00Z",
        "finished_at": "2026-10-26T09:01:00Z",
        "attempt": 1,
    }
    raw.update(overrides)
    return raw


class TestHappyPath:
    def test_valid_records_flow_through_to_the_summary(self):
        source = StaticSource([valid_raw(), valid_raw(job_id="job-2", attempt=2)])
        result = JobAnalyticsApp(source).run()
        assert isinstance(result, RunResult)
        assert result.report.total_jobs == 2
        assert result.report.retried_job_count == 1
        assert result.rejected_records == ()

    def test_the_source_is_read_exactly_once(self):
        source = StaticSource([valid_raw()])
        JobAnalyticsApp(source).run()
        assert source.read_calls == 1


class TestGracefulRejections:
    def test_malformed_records_are_rejected_with_position_and_reason(self):
        source = StaticSource([valid_raw(job_id="ok"), "not-an-object", valid_raw(status="bogus")])
        result = JobAnalyticsApp(source).run()
        assert result.report.total_jobs == 1
        assert [r.index for r in result.rejected_records] == [1, 2]
        assert all(r.reason for r in result.rejected_records)
        assert "JSON object" in result.rejected_records[0].reason
        assert "status" in result.rejected_records[1].reason

    def test_rejection_positions_refer_to_the_original_file_order(self):
        source = StaticSource(
            ["bad", valid_raw(), {"status": "failed", "started_at": "x", "attempt": 1}]
        )
        result = JobAnalyticsApp(source).run()
        assert [r.index for r in result.rejected_records] == [0, 2]

    def test_all_rejected_input_yields_an_empty_summary(self):
        result = JobAnalyticsApp(StaticSource(["bad", 42])).run()
        assert result.report == SummaryReport(
            total_jobs=0, successful_jobs=0, failed_jobs=0, retried_job_count=0
        )
        assert len(result.rejected_records) == 2


class TestFailurePropagation:
    def test_source_errors_are_not_swallowed(self):
        class BrokenSource:
            def read_records(self):
                raise InputFileError("boom")

        with pytest.raises(InputFileError):
            JobAnalyticsApp(BrokenSource()).run()
