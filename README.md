# job-analytics

A small, production-shaped Python CLI that reads **job execution records** from a
JSON file, validates them, and produces a **summary report**:

- total jobs
- successful jobs
- failed jobs
- average successful-job duration
- jobs that required retries

The default view is **per-record**. `--view job` switches to a **per-job**
aggregation where each job's latest attempt decides its outcome — including how
many jobs succeeded after retrying:

```text
Job execution summary (per job)
  Total jobs: 7
  Successful jobs: 5
  Failed jobs: 1
  Running jobs: 1
  Jobs requiring retries: 3
  Successful after retries: 2
  Average final-attempt duration: 375.1s
  Rejected records: 0
```

Malformed records are **rejected individually with a reason** — one bad record
never aborts the run. Records **stream** (peak memory is O(largest record), not
O(file size)). Validation runs on a declarative **pydantic** schema; everything
else is standard library (Python 3.12+). Development tooling: `uv`, `pytest`,
`ruff`, and `mypy --strict`.

## What it does

Given an input file like [`data/jobs.json`](data/jobs.json):

```json
[
  {"job_id": "job-001", "status": "success",
   "started_at": "2026-10-26T09:00:00Z", "finished_at": "2026-10-26T09:10:00Z",
   "attempt": 1},
  {"job_id": "job-002", "status": "failed",
   "started_at": "2026-10-26T09:00:00Z", "finished_at": "2026-10-26T09:02:00Z",
   "attempt": 1},
  {"job_id": "job-002", "status": "success",
   "started_at": "2026-10-26T09:05:00Z", "finished_at": "2026-10-26T09:20:00Z",
   "attempt": 2}
]
```

the CLI prints (default `text` format):

```text
Job execution summary
  Total jobs: 3
  Successful jobs: 2
  Failed jobs: 1
  Average successful duration: 750s
  Jobs requiring retries: 1
  Rejected records: 0
```

or, with `--format json`:

```json
{
  "total_jobs": 3,
  "successful_jobs": 2,
  "failed_jobs": 1,
  "average_successful_duration_seconds": 750.0,
  "jobs_requiring_retries": 1,
  "rejected_records": 0
}
```

When records are malformed, the text report discloses each rejection with its
position in the file and a reason:

```text
  Rejected records: 2
  Rejected record at index 1: record is not a JSON object
  Rejected record at index 2: missing field: attempt
```

## Quickstart

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/) (any recent version).

```bash
git clone <this-repo>
cd <repo-name>
make setup        # uv sync: creates .venv, installs pytest + ruff
make check        # lint + full test suite
make run          # run the CLI on the committed clean sample
make run SAMPLE=data/jobs_malformed.json   # ...and on the malformed sample
uv run python -m job_analytics data/jobs.json --format json   # or invoke it directly
```

Without `uv`, any Python 3.12+ venv works:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e . pytest ruff
python -m pytest -q
python -m job_analytics data/jobs.json
```

## Usage

```text
usage: job_analytics [-h] [--format {text,json}] [--view {record,job}] input

positional arguments:
  input                 path to a JSON file containing a top-level array of records

options:
  -h, --help            show this help message and exit
  --format {text,json}  output format (default: text)
  --view {record,job}   aggregation view (default: record)
```

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | The run completed — **including** runs that rejected some records (rejections are reported, not fatal) |
| `2` | Fatal input error (file missing, invalid JSON, non-array document) or bad usage |

Programmatic use of the public API (re-exported from the package root):

```python
from job_analytics import JobAnalyticsApp, JobSummaryCalculator, JsonFileRecordSource

result = JobAnalyticsApp(JsonFileRecordSource("data/jobs.json")).run()
print(result.report)  # SummaryReport(...)
print(result.rejected_records)  # tuple[RejectedRecord, ...]

per_job = JobAnalyticsApp(JsonFileRecordSource("data/jobs.json"), JobSummaryCalculator()).run()
print(per_job.report)  # JobSummaryReport(...)
```

## How it works

The pipeline is five single-responsibility layers wired by dependency injection:

```
JsonFileRecordSource ──▶ JobAnalyticsApp ──▶ SummaryCalculator ──▶ Reporter
   (loading.py)            (app.py)            (analytics.py)    (reporting.py)
   raw JSON values   │  parse each record  │  pure aggregation │  text / json
                     │  (parsing.py),      │
                     │  collect rejections │
```

| Module | Responsibility | SOLID principle it serves |
| --- | --- | --- |
| `models.py` | Immutable domain data (`JobStatus`, `JobRecord`, `RejectedRecord`, `SummaryReport`, `JobSummaryReport`) | Single Responsibility — pure data, no I/O |
| `errors.py` | Deliberate exception hierarchy rooted at `JobAnalyticsError` | LSP-friendly handling: callers catch the base |
| `schema.py` | Declarative pydantic schema: the single definition of a valid record | Single Responsibility — shape and coercion rules declared, not coded |
| `parsing.py` | Seam: raw JSON value → validated `JobRecord`, or a named rejection reason | Dependency Inversion — the schema engine sits behind a stable seam |
| `loading.py` | `RecordSource` protocol + streaming JSON-array file source | Dependency Inversion — the app depends on the protocol, not files |
| `analytics.py` | `SummaryCalculator` (per-record) and `JobSummaryCalculator` (per-job) behind a `SummaryStrategy` protocol | Open/Closed — new aggregation views plug in without touching the app |
| `app.py` | `JobAnalyticsApp`: load → parse → compute, injecting source + strategy | Dependency Inversion — every dependency is injectable |
| `reporting.py` | `Reporter` protocol; both reporters render either report type via dispatch tables | Open/Closed — new formats and report types register, not branch |
| `cli.py` | argparse adapter (`--format`, `--view`), exit codes, error rendering | Single Responsibility — no business logic |

Data flows one way: `loading` produces raw values, `parsing` produces trusted
`JobRecord`s, `analytics` consumes records and returns a `SummaryReport`, and
`reporting` renders a `RunResult` (summary + rejections). Nothing downstream
knows where records came from, so a database or HTTP source only needs to
implement `RecordSource.read_records()`.

**Everything streams.** `JsonFileRecordSource` decodes the array one element at
a time (`json.JSONDecoder.raw_decode` over chunked reads) and the app feeds
parsed records straight into the calculator, which aggregates in a single pass.
Peak memory is O(largest single record) plus the rejection details and the set
of distinct retried job ids — never O(file size). A completeness guard
re-decodes a token until a delimiter or EOF follows it, so a number split by a
chunk boundary is never yielded truncated. Fatal document errors (invalid JSON,
non-array root) surface at the start of iteration; per-record defects surface
when reached.

## Assumptions and design decisions

The exercise leaves several details open; these are the decisions made and why.

1. **Document shape.** The input file is a single top-level JSON **array** of
   records, consumed as a stream (one element at a time — see "How it works").
   Anything else (object, string, empty file) is a *fatal* input error
   with exit code 2 — distinguishable from per-record rejections.
2. **Records are per-attempt.** A job that retried appears as multiple records
   sharing a `job_id` with increasing `attempt` numbers. Consequences:
   - `total_jobs` counts **valid records** (each execution attempt is a job run).
   - `successful_jobs` / `failed_jobs` count records by status; `running` records
     count only toward the total.
   - "jobs that required retries" counts **distinct `job_id`s** having any record
     with `attempt > 1`.
   The default summary is record-level. `--view job` aggregates per job instead:
   a job's **latest attempt wins** (highest `attempt`, ties broken by the later
   `started_at`), which decides `successful_jobs` / `failed_jobs` /
   `running_jobs`; `successful_after_retries` counts jobs whose final attempt
   succeeded after any `attempt > 1`; the average uses only final successful
   attempts.
3. **Statuses.** Recognized values (case/whitespace-insensitive) are
   `success`, `failed`, `running`. Any other value — including plausible
   variants like `succeeded` — is a malformed record, not a guess.
4. **Durations.** Only records with both timestamps contribute. Duration is
   wall-clock (`finished_at − started_at`, sub-second precision kept). The
   **average is over successful finished records only**, per the spec's
   "average successful-job duration". A successful record without a
   `finished_at` counts as successful but feeds no duration.
5. **Timestamps.** ISO 8601 (`datetime.fromisoformat`, so `Z` and `±HH:MM`
   offsets work). Naive timestamps are interpreted as **UTC** so that aware and
   naive inputs can be compared safely.
6. **`finished_at` before `started_at`** is treated as malformed (a negative
   duration is meaningless data, not a job to average in). Equal timestamps are
   valid (zero duration).
7. **`attempt`** must be an integer ≥ 1. Booleans are explicitly rejected — in
   Python `True` is an `int`, and `attempt: true` is a realistic data bug.
8. **Graceful vs fatal.** Bad *records* are skipped and reported (the spec's
   "handle malformed records gracefully"); an unreadable or non-conforming
   *document* is fatal. Unknown extra fields on a record are ignored
   (forward-compatible).
9. **Empty input** (an empty array, or all records rejected) yields a zeroed
   summary with `average_successful_duration_seconds: null` rather than an
   error or `NaN`.
10. **Pydantic for validation.** The first build was stdlib-only with hand-rolled
    rules; adopting the improvement list, validation now runs on a declarative
    pydantic schema (`schema.py`) — coercion and error structure centralized,
    user-facing messages preserved. The swap happened behind the unchanged
    `parse_record` seam: every behavior spec passed unmodified, which is exactly
    what seam tests are for. pydantic is the package's one runtime dependency;
    everything else stays standard library.
11. **Rejections are reported, not silent.** Both output formats disclose how
    many records were rejected; the text format lists each reason. Silent
    data loss is the one unacceptable failure mode for an analytics tool.

## Testing

Run everything with:

```bash
make test        # pytest
make lint        # ruff check + format check
make type        # mypy --strict
make verify      # all gates: tests, lint, types, oracles (record/job/streaming), repo hygiene
```

The suite (126 tests) is written test-first and targets **public seams only** —
no tests against private helpers, no mocks of internals:

| Seam | What's specified |
| --- | --- |
| `parsing.parse_record` | Every validation rule, including the `bool`-as-`int` attempt trap, naive timestamps, out-of-order timestamps, and per-field error messages. These specs pinned the seam while the engine was swapped to the pydantic schema — they passed unmodified through the swap |
| `loading.JsonFileRecordSource` | Array documents, empty arrays, missing files, invalid JSON, non-array roots; streaming laziness, error timing with line numbers, and chunk-boundary stress (sizes 1–64) with `json.loads` as the oracle |
| `analytics.SummaryCalculator` / `JobSummaryCalculator` | A hand-computed end-to-end scenario, edge cases (empty input, failures-only, unfinished successes, retry counting per distinct job), one-shot iterable consumption, and the per-job view (latest attempt wins, tie-breaking, recovery counting, final-attempt average) |
| `app.JobAnalyticsApp` | Orchestration with fake in-memory and generator sources — rejections keep their original positions; source errors propagate, including lazily raised ones; strategies are injectable |
| `reporting` | Exact JSON payloads for both report types (literal expected values), text content, rejection disclosure, reporter registry |
| `cli.main` | End-to-end via `capsys` and a real `python -m job_analytics` subprocess: exit codes 0/2, stderr errors, malformed input still exiting 0, `--view job` payloads |

Expected values are worked examples computed by hand (an independent source of
truth), and `scripts/verify.py` goes further: it **recomputes the expected
summaries — record-level, per-job, and streaming — from the raw sample JSON with
its own logic** and diffs them against the CLI's output, so the sample data and
the package cannot quietly drift apart. It also proves pydantic is the declared
validation engine and that `mypy --strict` stays clean.

Expected values are worked examples computed by hand (an independent source of
truth), and `scripts/verify.py` goes further: it **recomputes the expected
summary from the raw sample JSON with its own logic** and diffs it against the
CLI's output, so the sample data and the package cannot quietly drift apart.

During development the red/green cycle caught two fixture bugs exactly this
way (a record inheriting a default finish time, and a missing `attempt=2`),
which is why the end-to-end expectations reference a comment listing the
intended durations.

## Items that can be improved

Honest list, roughly in order of value:

1. **Retry-window definition.** "Required retries" currently ignores *when*
   attempts happened and which attempt ultimately succeeded. Time-aware retry
   analytics (e.g., success rate after N attempts) would be more actionable.
2. **Output options.** `--output <file>`, CSV/markdown reporters (the registry
   makes this a two-class change), and a `--strict` flag that escalates any
   rejection to exit code 1 for pipelines that want fail-fast behavior.
3. **Structured logging.** Rejections currently live only in the report; a
   `logging` hook (or JSON-lines diagnostics stream) would help operators
   audit data quality over time.
4. **Property-based tests.** `hypothesis` round-trip properties (e.g., summary
   counts always sum consistently; parsing never raises anything other than
   `RecordValidationError`) would harden the parser beyond example cases.
5. **Performance headroom.** The file is streamed and aggregation is a single
   O(n) pass, so the remaining cost is per-element `raw_decode` versus one bulk
   `json.loads` — a constant factor that only matters at extreme scale, where a
   line-delimited JSON input format would be the better lever.
6. **Packaging/publishing.** Console-script entry point (`[project.scripts]`),
   pinned lock for CI, a `LICENSE`, and publishing to a private index.

## Project structure

```
.
├── AGENTS.md              conventions for coding agents (commands, layout, TDD rules)
├── Makefile               setup / test / lint / fmt / check / run / verify
├── README.md              this file
├── pyproject.toml         package metadata, pytest + ruff configuration
├── uv.lock                reproducible dev environment
├── .github/workflows/ci.yml   lint + tests on Python 3.12 and 3.14
├── data/
│   ├── jobs.json          clean sample (8 records, known expected summary)
│   └── jobs_malformed.json  9 invalid + 1 valid record, every rejection reason
├── scripts/
│   └── verify.py          verification gates incl. an independent CLI oracle
├── src/job_analytics/     the application (see "How it works")
└── tests/                 pytest suites mirroring the modules
```

AI coding assistants were used while building this (as the brief allows); the
development workflow and guardrails they followed live in [AGENTS.md](AGENTS.md).
