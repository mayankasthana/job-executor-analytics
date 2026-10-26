# AGENTS.md — working conventions for coding agents

Guidance for AI coding agents (and humans) working in this repository.

## Project overview

`job-analytics` reads job execution records from a JSON file (a top-level
array), validates each record, and produces a summary: total jobs, successful
jobs, failed jobs, average successful-job duration, and jobs that required
retries. Malformed records are rejected individually with reasons — one bad
record never aborts the run.

Python 3.12+, **stdlib-only runtime**. Development tooling: `uv` (environment),
`pytest` (tests), `ruff` (lint + format).

## Commands

| Task | Command |
| --- | --- |
| Set up environment | `make setup` |
| Run tests | `make test` |
| Lint + format check | `make lint` |
| Auto-format | `make fmt` |
| Lint + test (default) | `make check` |
| Run the CLI | `make run` (or `make run SAMPLE=path/to/file.json`) |
| Full verification | `make verify` |
| Direct CLI | `uv run python -m job_analytics <file.json> [--format json\|text]` |

`make verify` runs `scripts/verify.py`, which checks tests, lint, the CLI
against an independently recomputed oracle over `data/*.json`, git hygiene,
README completeness, and agentic-readiness artifacts.

## Layout

```
src/job_analytics/
  models.py      domain types: JobStatus, JobRecord, RejectedRecord, SummaryReport
  errors.py      JobAnalyticsError hierarchy (RecordValidationError, InputFileError)
  parsing.py     raw JSON value -> validated JobRecord (or named rejection reason)
  loading.py     RecordSource protocol + streaming JSON-array file source
  analytics.py   SummaryCalculator: pure aggregation over valid records
  app.py         JobAnalyticsApp orchestration with dependency injection
  reporting.py   Reporter protocol, JsonReporter/TextReporter
  cli.py         argparse adapter, exit codes
tests/           pytest suites mirroring the modules; conftest.py has shared builders
data/            committed sample inputs (clean + malformed)
scripts/         verify.py — verification gates
```

## Conventions

- **TDD**: write the failing test first, implement the minimum to pass, then
  refactor. Commit only green states. Conventional commits
  (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `ci:`, `chore:`).
- **Test at seams**: parser, loader, calculator, app, reporters, CLI — always
  through public interfaces. Use fakes (e.g. `StaticSource` in `test_app.py`)
  instead of mocks of internals. No tests against private helpers.
- **Runtime stays stdlib-only**; dev dependencies live in
  `[dependency-groups].dev` in `pyproject.toml`.
- **Sources are single-pass**: `RecordSource.read_records()` may return a
  one-shot iterator; consumers must drain it exactly once and must not
  materialize records unless they truly need them.
- Public API is re-exported from `src/job_analytics/__init__.py`.
- Keep `ruff` clean: line length 100, rules `E,F,W,I,UP,B,SIM,RUF`.
- Behavioral decisions and open questions live in the README's
  "Assumptions and design decisions" section — update it when behavior changes.

## Definition of done

`make check` passes; `make verify` passes on a clean tree; README and this
file still describe reality; history stays incremental (one concern per commit).
