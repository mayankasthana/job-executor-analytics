"""Behavior specs for summary computation.

Expected values are worked examples computed by hand from the inputs —
never derived from the implementation.
"""

from datetime import UTC, datetime

import pytest

from job_analytics.analytics import JobSummaryCalculator, SummaryCalculator
from job_analytics.models import JobStatus, JobSummaryReport, SummaryReport


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


class TestStreamingInput:
    def test_a_one_shot_iterable_is_consumed_exactly_once(self, make_record, calc):
        # Streaming sources yield records once; a multi-pass implementation
        # would see an exhausted iterator and silently miscount.
        records = iter(
            [
                make_record(job_id="a"),
                make_record(job_id="b", status=JobStatus.FAILED, attempt=2),
                make_record(job_id="c", status=JobStatus.RUNNING, finished_at=None),
            ]
        )
        report = calc.compute(records)
        assert report.total_jobs == 3
        assert report.successful_jobs == 1
        assert report.failed_jobs == 1
        assert report.retried_job_count == 1
        assert report.average_successful_duration_seconds == 600.0

    def test_a_one_shot_iterable_with_no_successful_jobs_has_no_average(self, make_record, calc):
        records = iter([make_record(job_id="a", status=JobStatus.FAILED)])
        assert calc.compute(records).average_successful_duration_seconds is None


@pytest.fixture
def job_calc():
    return JobSummaryCalculator()


class TestJobLevelAggregation:
    """Latest attempt wins: one row per distinct job_id."""

    def test_the_sample_scenario_aggregates_per_job(self, make_record, job_calc):
        # Same 8 records as the record-level scenario, but 7 distinct jobs:
        # job-002 recovers on attempt 2, job-005 stays failed after 3 tries,
        # job-007 succeeds on attempt 2, job-004 is still running.
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

        report = job_calc.compute(records)

        assert report == JobSummaryReport(
            total_jobs=7,
            successful_jobs=5,
            failed_jobs=1,
            running_jobs=1,
            retried_job_count=3,
            successful_after_retry_count=2,
            average_final_attempt_duration_seconds=pytest.approx(375.1),
        )

    def test_the_latest_attempt_decides_the_outcome(self, make_record, job_calc):
        recovered = [
            make_record(job_id="a", status=JobStatus.FAILED, attempt=1),
            make_record(job_id="a", attempt=2),
        ]
        assert job_calc.compute(recovered).successful_jobs == 1

        regressed = [
            make_record(job_id="a", attempt=1),
            make_record(job_id="a", status=JobStatus.FAILED, attempt=2),
        ]
        report = job_calc.compute(regressed)
        assert report.successful_jobs == 0
        assert report.failed_jobs == 1

    def test_equal_attempts_are_broken_by_started_time(self, make_record, job_calc):
        records = [
            make_record(
                job_id="a",
                status=JobStatus.FAILED,
                attempt=2,
                started_at=datetime(2026, 10, 26, 9, 0, tzinfo=UTC),
            ),
            make_record(
                job_id="a",
                attempt=2,
                started_at=datetime(2026, 10, 26, 10, 0, tzinfo=UTC),
            ),
        ]
        report = job_calc.compute(records)
        assert report.total_jobs == 1
        assert report.successful_jobs == 1  # the later attempt won

    def test_a_still_running_job_counts_as_running(self, make_record, job_calc):
        report = job_calc.compute(
            [make_record(job_id="a", status=JobStatus.RUNNING, finished_at=None)]
        )
        assert report.running_jobs == 1
        assert report.successful_jobs == 0
        assert report.failed_jobs == 0

    def test_success_after_retries_is_counted(self, make_record, job_calc):
        records = [
            make_record(job_id="a", status=JobStatus.FAILED, attempt=1),
            make_record(job_id="a", attempt=2),  # recovered
            make_record(job_id="b", attempt=1),  # success on the first try
            make_record(job_id="c", status=JobStatus.FAILED, attempt=3),  # retried, still failed
        ]
        report = job_calc.compute(records)
        assert report.retried_job_count == 2
        assert report.successful_after_retry_count == 1

    def test_the_average_uses_only_final_successful_attempts(self, make_record, job_calc):
        records = [
            make_record(job_id="a", status=JobStatus.FAILED, attempt=1),  # 600s, but failed
            make_record(
                job_id="a",
                attempt=2,
                finished_at=datetime(2026, 10, 26, 9, 5, tzinfo=UTC),  # 300s, won
            ),
        ]
        report = job_calc.compute(records)
        assert report.average_final_attempt_duration_seconds == 300.0

    def test_an_unfinished_final_success_feeds_no_duration(self, make_record, job_calc):
        report = job_calc.compute([make_record(job_id="a", finished_at=None)])
        assert report.successful_jobs == 1
        assert report.average_final_attempt_duration_seconds is None

    def test_empty_input_yields_a_zero_job_summary(self, job_calc):
        assert job_calc.compute([]) == JobSummaryReport(
            total_jobs=0,
            successful_jobs=0,
            failed_jobs=0,
            running_jobs=0,
            retried_job_count=0,
            successful_after_retry_count=0,
        )

    def test_a_one_shot_iterable_is_consumed_exactly_once(self, make_record, job_calc):
        records = iter(
            [
                make_record(job_id="a", status=JobStatus.FAILED, attempt=1),
                make_record(job_id="a", attempt=2),
            ]
        )
        report = job_calc.compute(records)
        assert report.total_jobs == 1
        assert report.successful_after_retry_count == 1
