"""Shared test fixtures."""

from datetime import UTC, datetime

import pytest

from job_analytics.models import JobRecord, JobStatus


@pytest.fixture
def make_record():
    """Build a JobRecord with sensible defaults, overridden per test."""

    def _make(**overrides) -> JobRecord:
        defaults = dict(
            job_id="job-001",
            status=JobStatus.SUCCESS,
            started_at=datetime(2026, 10, 26, 9, 0, tzinfo=UTC),
            finished_at=datetime(2026, 10, 26, 9, 10, tzinfo=UTC),
            attempt=1,
        )
        defaults.update(overrides)
        return JobRecord(**defaults)

    return _make
