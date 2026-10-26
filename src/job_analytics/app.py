"""Application orchestration: load -> parse -> compute.

:class:`JobAnalyticsApp` wires a :class:`RecordSource`, the parser, and a
calculator together. Dependencies are injected, so any of them can be faked
in tests or replaced in production (open/closed + dependency inversion).
"""

from collections.abc import Iterator
from dataclasses import dataclass

from job_analytics.analytics import SummaryCalculator, SummaryStrategy
from job_analytics.errors import RecordValidationError
from job_analytics.loading import RecordSource
from job_analytics.models import JobRecord, JobSummaryReport, RejectedRecord, SummaryReport
from job_analytics.parsing import parse_record


@dataclass(frozen=True, slots=True)
class RunResult:
    """Everything a run produced: the summary plus why records were rejected.

    The report type depends on the injected strategy: a record-level
    :class:`SummaryReport` or a per-job :class:`JobSummaryReport`.
    """

    report: SummaryReport | JobSummaryReport
    rejected_records: tuple[RejectedRecord, ...]


class JobAnalyticsApp:
    """Turns a source of raw records into a summary plus rejection details.

    Records stream end to end: raw values are parsed one at a time and fed
    straight into the calculator, so valid records are never materialized.
    Only the rejection details and the calculator's running state are held
    in memory. The source may raise fatal input errors lazily; they
    propagate out of :meth:`run`.
    """

    def __init__(self, source: RecordSource, calculator: SummaryStrategy | None = None) -> None:
        self._source = source
        self._calculator = calculator or SummaryCalculator()

    def run(self) -> RunResult:
        rejected: list[RejectedRecord] = []

        def valid_records() -> Iterator[JobRecord]:
            # Single pass: rejections are collected as a side effect while
            # the calculator drains the generator exactly once.
            for index, raw in enumerate(self._source.read_records()):
                try:
                    yield parse_record(raw)
                except RecordValidationError as exc:
                    rejected.append(RejectedRecord(index=index, reason=str(exc)))

        return RunResult(
            report=self._calculator.compute(valid_records()),
            rejected_records=tuple(rejected),
        )
