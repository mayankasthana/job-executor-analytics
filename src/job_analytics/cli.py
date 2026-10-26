"""Command-line entry point: a thin adapter over the application layer.

Argument parsing, error rendering, and exit codes live here — no business
logic. Exit codes: 0 on a successful run (even with rejected records),
2 on fatal input errors or bad usage.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from job_analytics.analytics import get_strategy
from job_analytics.app import JobAnalyticsApp
from job_analytics.errors import JobAnalyticsError
from job_analytics.loading import JsonFileRecordSource
from job_analytics.reporting import get_reporter


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="job_analytics",
        description="Summarize job execution records from a JSON file.",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="path to a JSON file containing a top-level array of records",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: %(default)s)",
    )
    parser.add_argument(
        "--view",
        choices=("record", "job"),
        default="record",
        help="aggregation view: per-record (default) or per-job, where the "
        "latest attempt decides each job's outcome",
    )
    args = parser.parse_args(argv)

    try:
        source = JsonFileRecordSource(args.input)
        result = JobAnalyticsApp(source, get_strategy(args.view)).run()
    except JobAnalyticsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(get_reporter(args.format).format(result))
    return 0
