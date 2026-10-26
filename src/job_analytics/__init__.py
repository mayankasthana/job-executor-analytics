"""Job execution record analytics.

Reads job execution records from a JSON file, validates them, and produces
a summary. See the README for usage and design notes.
"""

from job_analytics.analytics import SummaryCalculator
from job_analytics.app import JobAnalyticsApp, RunResult
from job_analytics.loading import JsonFileRecordSource, RecordSource
from job_analytics.models import JobRecord, JobStatus, RejectedRecord, SummaryReport

__version__ = "0.1.0"

__all__ = [
    "JobAnalyticsApp",
    "JobRecord",
    "JobStatus",
    "JsonFileRecordSource",
    "RecordSource",
    "RejectedRecord",
    "RunResult",
    "SummaryCalculator",
    "SummaryReport",
    "__version__",
]
