#!/usr/bin/env python3
"""Verification gates for this repository.

Each subcommand prints a decisive success token only after all of its
assertions pass, so callers (GATES.md / `make verify`) can rely on output
plus exit code.

The `cli` gate recomputes the expected summary directly from the raw sample
JSON with independent logic — it never imports job_analytics — then runs the
CLI as a subprocess and compares. That makes it an oracle rather than a
re-run of the same code.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

TOKENS = {
    "tests": "GATE-TESTS-OK",
    "lint": "GATE-LINT-OK",
    "cli": "GATE-CLI-OK",
    "git": "GATE-GIT-OK",
    "readme": "GATE-README-OK",
    "agentic": "GATE-AGENTIC-OK",
    "streaming": "GATE-STREAMING-OK",
    "schema": "GATE-SCHEMA-OK",
    "jobview": "GATE-JOBVIEW-OK",
    "types": "GATE-TYPES-OK",
}

README_SECTIONS = (
    "## What it does",
    "## Quickstart",
    "## Usage",
    "## How it works",
    "## Assumptions and design decisions",
    "## Testing",
    "## Items that can be improved",
)

AGENTS_MARKERS = ("## Commands", "## Layout", "## Conventions", "## Definition of done")


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run through uv when available so the project's environment is used."""
    argv = ("uv", "run", *args) if shutil.which("uv") else args
    return subprocess.run(argv, cwd=REPO, capture_output=True, text=True, check=check)


def gate_tests() -> None:
    if run("python", "-m", "pytest", "-q", check=False).returncode != 0:
        fail("pytest did not pass")


def gate_lint() -> None:
    for command in (("ruff", "check", "."), ("ruff", "format", "--check", ".")):
        if run(*command, check=False).returncode != 0:
            fail(f"{' '.join(command)} is not clean")


def _independent_valid(
    raw_records: list,
) -> tuple[list[tuple[str, str, datetime, datetime | None, int]], int]:
    """Validate raw records with independent logic; returns (valid, rejected_count)."""
    valid: list[tuple[str, str, datetime, datetime | None, int]] = []
    rejected = 0
    for record in raw_records:
        try:
            if not isinstance(record, dict):
                raise ValueError("not an object")
            job_id = record["job_id"]
            status = str(record["status"]).strip().lower()
            started = datetime.fromisoformat(str(record["started_at"]).replace("Z", "+00:00"))
            attempt = record["attempt"]
            finished = None
            if record.get("finished_at") is not None:
                finished = datetime.fromisoformat(str(record["finished_at"]).replace("Z", "+00:00"))
            if not isinstance(job_id, str) or not job_id.strip():
                raise ValueError("bad job_id")
            if status not in ("success", "failed", "running"):
                raise ValueError("bad status")
            if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
                raise ValueError("bad attempt")
            if finished is not None and finished < started:
                raise ValueError("bad timestamps")
        except (KeyError, TypeError, ValueError):
            rejected += 1
            continue
        valid.append((job_id, status, started, finished, attempt))
    return valid, rejected


def independent_summary(raw_records: list) -> dict:
    """Recompute the expected record-level summary from raw JSON, independently of the package."""
    valid, rejected = _independent_valid(raw_records)

    durations = [
        (finished - started).total_seconds()
        for _, status, started, finished, _ in valid
        if status == "success" and finished is not None
    ]
    return {
        "total_jobs": len(valid),
        "successful_jobs": sum(1 for entry in valid if entry[1] == "success"),
        "failed_jobs": sum(1 for entry in valid if entry[1] == "failed"),
        "average_successful_duration_seconds": (
            sum(durations) / len(durations) if durations else None
        ),
        "jobs_requiring_retries": len({entry[0] for entry in valid if entry[4] > 1}),
        "rejected_records": rejected,
    }


def independent_job_summary(raw_records: list) -> dict:
    """Recompute the expected per-job summary (latest attempt wins), independently."""
    valid, rejected = _independent_valid(raw_records)
    final: dict[str, tuple[str, datetime, datetime | None, int]] = {}
    retried: set[str] = set()
    for job_id, status, started, finished, attempt in valid:
        current = final.get(job_id)
        if current is None or (attempt, started) >= (current[3], current[1]):
            final[job_id] = (status, started, finished, attempt)
        if attempt > 1:
            retried.add(job_id)

    successful = [(job_id, entry) for job_id, entry in final.items() if entry[0] == "success"]
    durations = [
        (finished - started).total_seconds()
        for _, (_, started, finished, _) in successful
        if finished is not None
    ]
    return {
        "total_jobs": len(final),
        "successful_jobs": len(successful),
        "failed_jobs": sum(1 for entry in final.values() if entry[0] == "failed"),
        "running_jobs": sum(1 for entry in final.values() if entry[0] == "running"),
        "jobs_requiring_retries": len(retried),
        "successful_after_retries": sum(1 for job_id, _ in successful if job_id in retried),
        "average_final_attempt_duration_seconds": (
            sum(durations) / len(durations) if durations else None
        ),
        "rejected_records": rejected,
    }


def run_cli(path: Path, *flags: str) -> dict:
    process = run("python", "-m", "job_analytics", str(path), *flags, check=False)
    if process.returncode != 0:
        fail(f"CLI exited {process.returncode}: {process.stderr.strip()}")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        fail(f"CLI printed unparseable JSON: {process.stdout!r}")


def gate_cli() -> None:
    for name in ("jobs.json", "jobs_malformed.json"):
        path = REPO / "data" / name
        expected = independent_summary(json.loads(path.read_text(encoding="utf-8")))
        actual = run_cli(path, "--format", "json")
        if actual != expected:
            fail(f"{name} mismatch:\n  cli:      {actual}\n  expected: {expected}")

    process = run("python", "-m", "job_analytics", str(REPO / "data" / "jobs_malformed.json"))
    if "Rejected records: 9" not in process.stdout:
        fail("text report does not disclose the expected 9 rejections")

    missing = run(
        "python",
        "-m",
        "job_analytics",
        str(REPO / "data" / "does-not-exist.json"),
        check=False,
    )
    if missing.returncode != 2 or "error:" not in missing.stderr:
        fail("a missing input file must exit 2 with an error on stderr")


def gate_streaming() -> None:
    """End-to-end streaming check: the CLI streams its input, so on a dataset
    large enough to span multiple read chunks it must still reproduce the
    independent oracle exactly. Padding of randomized width pushes chunk
    boundaries into tokens (strings, numbers)."""
    rng = random.Random(20261027)
    records = []
    for index in range(20_000):
        status = rng.choice(("success", "failed", "running"))
        record = {
            "job_id": f"job-{index:05d}",
            "status": status,
            "started_at": "2026-10-26T09:00:00Z",
            "attempt": rng.choice((1, 1, 1, 2, 3)),
            "padding": "x" * rng.randint(0, 240),
        }
        if status != "running":
            minute = rng.randint(0, 600)
            second = rng.randint(0, 59)
            record["finished_at"] = (
                f"2026-10-26T{9 + minute // 60:02d}:{minute % 60:02d}:{second:02d}Z"
            )
        records.append(record)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "big.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        if path.stat().st_size < 3 * 1_048_576:
            fail("synthetic dataset is too small to span multiple read chunks")
        expected = independent_summary(records)
        actual = run_cli(path, "--format", "json")
        if actual != expected:
            fail(f"streamed run mismatch:\n  cli:      {actual}\n  expected: {expected}")


def gate_schema() -> None:
    """Validation must run on the pydantic schema behind the unchanged seam."""
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    if not any(dependency.startswith("pydantic") for dependency in dependencies):
        fail("pydantic is not declared as a runtime dependency")
    if run("python", "-c", "from job_analytics.schema import JobRecordSchema").returncode != 0:
        fail("the declarative schema module is not importable")
    result = run("python", "-m", "pytest", "tests/test_parsing.py", "-q", check=False)
    if result.returncode != 0:
        fail("the parsing seam behavior specs did not pass unchanged")


def gate_jobview() -> None:
    """The CLI's per-job view must match an independently recomputed oracle."""
    for name in ("jobs.json", "jobs_malformed.json"):
        path = REPO / "data" / name
        raw_records = json.loads(path.read_text(encoding="utf-8"))
        expected = independent_job_summary(raw_records)
        actual = run_cli(path, "--view", "job", "--format", "json")
        if actual != expected:
            fail(f"job-view mismatch on {name}:\n  cli:      {actual}\n  expected: {expected}")
    process = run(
        "python", "-m", "job_analytics", str(REPO / "data" / "jobs.json"), "--view", "job"
    )
    if "(per job)" not in process.stdout or "Successful after retries: 2" not in process.stdout:
        fail("the text report does not disclose the per-job metrics")


def gate_types() -> None:
    result = run("mypy", check=False)
    if result.returncode != 0:
        fail(f"mypy --strict found issues:\n{result.stdout}{result.stderr}")


def gate_git() -> None:
    count = int(run("git", "rev-list", "--count", "HEAD").stdout.strip())
    if count < 8:
        fail(f"expected at least 8 commits, found {count}")

    subjects = run("git", "log", "--format=%s").stdout.strip().splitlines()
    allowed = {"chore", "ci", "docs", "feat", "fix", "perf", "refactor", "style", "test"}
    bad = [s for s in subjects if s.split(":", 1)[0] not in allowed]
    if bad:
        fail(f"commit subjects outside conventional style: {bad}")

    if run("git", "status", "--porcelain").stdout.strip():
        fail("working tree is not clean")


def gate_readme() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    missing = [s for s in README_SECTIONS if s not in readme]
    if missing:
        fail(f"README is missing sections: {missing}")
    for marker in ("make test", "uv run python -m job_analytics", "make verify"):
        if marker not in readme:
            fail(f"README does not mention the runnable command: {marker}")


def gate_agentic() -> None:
    required = (
        "AGENTS.md",
        "Makefile",
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "uv.lock",
        ".gitignore",
        "scripts/verify.py",
    )
    missing = [name for name in required if not (REPO / name).is_file()]
    if missing:
        fail(f"missing agentic-development files: {missing}")

    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for marker in ("pytest", "ruff"):
        if marker not in ci:
            fail(f"CI workflow does not run {marker}")

    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    for target in ("test:", "lint:", "check:", "run:", "verify:"):
        if target not in makefile:
            fail(f"Makefile is missing the {target.removesuffix(':')} target")

    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    missing_markers = [s for s in AGENTS_MARKERS if s not in agents]
    if missing_markers:
        fail(f"AGENTS.md is missing sections: {missing_markers}")

    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    for marker in ("[tool.ruff]", "[tool.pytest.ini_options]"):
        if marker not in pyproject:
            fail(f"pyproject.toml is missing {marker}")


def main() -> None:
    gates = {
        "tests": gate_tests,
        "lint": gate_lint,
        "types": gate_types,
        "cli": gate_cli,
        "streaming": gate_streaming,
        "schema": gate_schema,
        "jobview": gate_jobview,
        "git": gate_git,
        "readme": gate_readme,
        "agentic": gate_agentic,
    }
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in gates:
        print(f"usage: verify.py {{{','.join(gates)}}}", file=sys.stderr)
        raise SystemExit(2)
    gates[name]()
    print(TOKENS[name])


if __name__ == "__main__":
    main()
