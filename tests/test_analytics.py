"""Behavior specs for summary computation.

Expected values are worked examples computed by hand from the inputs —
never derived from the implementation.
"""

from datetime import UTC, datetime

import pytest

from job_analytics.analytics import SummaryCalculator
from job_analytics.models import JobStatus, SummaryReport


@pytest.fixture
def calc():
    return SummaryCalculator()


class TestEndToEndAggregation:
    def test_the_sample_scenario_summarizes_end_to_end(self, make_record, calc):
        # 5 successful (600s, 900s, 30s, 45.5s, 300s), 2 failed, 1 running,
        # retries on job-002 (attempt 2), job-005 (attempt 3), job-007 (attempt 2).
        records = [
            make_record(job_id="job-001"),
            make_record(job_id="job-002", status=JobStatus.FAILED),
            make_record(
                job_id="job-002",
                attempt=2,
                started_at=datetime(2026, 10, 26, 9, 5, tzinfo=UTC),
                finished_at=datetime(2026, 10, 26, 9, 20, tzinfo=UTC),
            ),
            make_record(
                job_id="job-003",
                finished_at=datetime(2026, 10, 26, 9, 0, 30, tzinfo=UTC),
            ),
            make_record(job_id="job-004", status=JobStatus.RUNNING, finished_at=None),
            make_record(
                job_id="job-005",
                status=JobStatus.FAILED,
                attempt=3,
                finished_at=datetime(2026, 10, 26, 9, 1, tzinfo=UTC),
            ),
            make_record(
                job_id="job-006",
                finished_at=datetime(2026, 10, 26, 9, 0, 45, 500_000, tzinfo=UTC),
            ),
            make_record(
                job_id="job-007",
                started_at=datetime(2026, 10, 26, 14, 0, tzinfo=UTC),
                finished_at=datetime(2026, 10, 26, 14, 5, tzinfo=UTC),
                attempt=2,
            ),
        ]

        report = calc.compute(records)

        assert report.total_jobs == 8
        assert report.successful_jobs == 5
        assert report.failed_jobs == 2
        assert report.average_successful_duration_seconds == pytest.approx(375.1)
        assert report.retried_job_count == 3


class TestEdgeCases:
    def test_empty_input_yields_a_zero_summary(self, calc):
        assert calc.compute([]) == SummaryReport(
            total_jobs=0, successful_jobs=0, failed_jobs=0, retried_job_count=0
        )

    def test_input_with_only_failures_has_no_average(self, make_record, calc):
        records = [
            make_record(job_id="a", status=JobStatus.FAILED),
            make_record(job_id="b", status=JobStatus.FAILED),
        ]
        report = calc.compute(records)
        assert report.failed_jobs == 2
        assert report.average_successful_duration_seconds is None

    def test_unfinished_successful_jobs_count_but_do_not_feed_the_average(self, make_record, calc):
        records = [make_record(job_id="a"), make_record(job_id="b", finished_at=None)]
        report = calc.compute(records)
        assert report.successful_jobs == 2
        assert report.average_successful_duration_seconds == 600.0

    def test_running_jobs_count_toward_the_total_only(self, make_record, calc):
        report = calc.compute([make_record(status=JobStatus.RUNNING, finished_at=None)])
        assert report.total_jobs == 1
        assert report.successful_jobs == 0
        assert report.failed_jobs == 0


class TestRetryDetection:
    def test_a_job_retried_many_times_is_counted_once(self, make_record, calc):
        records = [make_record(job_id="job-a", attempt=attempt) for attempt in (1, 2, 3)]
        assert calc.compute(records).retried_job_count == 1

    def test_first_attempts_are_not_retries(self, make_record, calc):
        assert calc.compute([make_record(attempt=1)]).retried_job_count == 0

    def test_retries_are_counted_per_distinct_job(self, make_record, calc):
        records = [
            make_record(job_id="job-a", attempt=2),
            make_record(job_id="job-b", attempt=2),
        ]
        assert calc.compute(records).retried_job_count == 2
