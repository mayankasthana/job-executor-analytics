"""Behavior specs for summary rendering."""

import json

import pytest

from job_analytics.app import RunResult
from job_analytics.models import JobSummaryReport, RejectedRecord, SummaryReport
from job_analytics.reporting import JsonReporter, TextReporter, get_reporter


def run_result(**overrides):
    report_values = dict(
        total_jobs=8,
        successful_jobs=5,
        failed_jobs=2,
        retried_job_count=3,
        average_successful_duration_seconds=375.1,
    )
    report_values.update(overrides.pop("report", {}))
    rejected = overrides.pop("rejected_records", ())
    return RunResult(report=SummaryReport(**report_values), rejected_records=rejected)


class TestJsonReporter:
    def test_the_json_payload_holds_the_full_summary_with_literal_values(self):
        payload = json.loads(JsonReporter().format(run_result()))
        assert payload == {
            "total_jobs": 8,
            "successful_jobs": 5,
            "failed_jobs": 2,
            "average_successful_duration_seconds": 375.1,
            "jobs_requiring_retries": 3,
            "rejected_records": 0,
        }

    def test_a_missing_average_is_rendered_as_null(self):
        result = run_result(report={"average_successful_duration_seconds": None})
        payload = json.loads(JsonReporter().format(result))
        assert payload["average_successful_duration_seconds"] is None

    def test_rejections_are_counted_in_the_json_payload(self):
        rejections = (
            RejectedRecord(index=1, reason="boom"),
            RejectedRecord(index=4, reason="bam"),
        )
        payload = json.loads(JsonReporter().format(run_result(rejected_records=rejections)))
        assert payload["rejected_records"] == 2

    def test_the_output_is_standalone_json_text(self):
        text = JsonReporter().format(run_result())
        assert text.startswith("{")
        json.loads(text)


class TestTextReporter:
    def test_the_text_report_states_every_summary_number(self):
        text = TextReporter().format(run_result())
        assert "Total jobs: 8" in text
        assert "Successful jobs: 5" in text
        assert "Failed jobs: 2" in text
        assert "Jobs requiring retries: 3" in text
        assert "375.1" in text

    def test_a_missing_average_is_rendered_as_not_available(self):
        result = run_result(report={"average_successful_duration_seconds": None})
        assert "n/a" in TextReporter().format(result)

    def test_rejections_are_listed_with_positions_and_reasons(self):
        rejections = (RejectedRecord(index=3, reason="missing field: attempt"),)
        text = TextReporter().format(run_result(rejected_records=rejections))
        assert "index 3" in text
        assert "missing field: attempt" in text

    def test_no_rejection_details_when_everything_parsed(self):
        assert "index" not in TextReporter().format(run_result()).lower()


class TestReporterRegistry:
    def test_json_and_text_are_registered(self):
        assert isinstance(get_reporter("json"), JsonReporter)
        assert isinstance(get_reporter("text"), TextReporter)

    def test_unknown_formats_are_rejected(self):
        with pytest.raises(ValueError, match="csv"):
            get_reporter("csv")


def job_result(**overrides):
    report_values = dict(
        total_jobs=7,
        successful_jobs=5,
        failed_jobs=1,
        running_jobs=1,
        retried_job_count=3,
        successful_after_retry_count=2,
        average_final_attempt_duration_seconds=375.1,
    )
    report_values.update(overrides.pop("report", {}))
    rejected = overrides.pop("rejected_records", ())
    return RunResult(report=JobSummaryReport(**report_values), rejected_records=rejected)


class TestJsonReporterWithJobSummaries:
    def test_the_job_payload_holds_the_per_job_metrics(self):
        payload = json.loads(JsonReporter().format(job_result()))
        assert payload == {
            "total_jobs": 7,
            "successful_jobs": 5,
            "failed_jobs": 1,
            "running_jobs": 1,
            "jobs_requiring_retries": 3,
            "successful_after_retries": 2,
            "average_final_attempt_duration_seconds": 375.1,
            "rejected_records": 0,
        }

    def test_a_missing_average_is_rendered_as_null(self):
        result = job_result(report={"average_final_attempt_duration_seconds": None})
        payload = json.loads(JsonReporter().format(result))
        assert payload["average_final_attempt_duration_seconds"] is None


class TestTextReporterWithJobSummaries:
    def test_the_job_report_states_the_per_job_numbers(self):
        text = TextReporter().format(job_result())
        assert "(per job)" in text
        assert "Total jobs: 7" in text
        assert "Running jobs: 1" in text
        assert "Jobs requiring retries: 3" in text
        assert "Successful after retries: 2" in text
        assert "Average final-attempt duration: 375.1s" in text

    def test_a_missing_average_is_rendered_as_not_available(self):
        result = job_result(report={"average_final_attempt_duration_seconds": None})
        assert "n/a" in TextReporter().format(result)
