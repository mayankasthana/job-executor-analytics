"""End-to-end specs for the command-line interface."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from job_analytics.cli import main


def write_records(tmp_path: Path, records, name="records.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def valid_raw(**overrides):
    raw = {
        "job_id": "job-1",
        "status": "success",
        "started_at": "2026-10-26T09:00:00Z",
        "finished_at": "2026-10-26T09:01:00Z",
        "attempt": 1,
    }
    raw.update(overrides)
    return raw


class TestSuccessfulRuns:
    def test_text_output_goes_to_stdout_with_exit_zero(self, tmp_path, capsys):
        path = write_records(tmp_path, [valid_raw(), valid_raw(job_id="job-2", attempt=2)])
        assert main([str(path)]) == 0
        assert "Total jobs: 2" in capsys.readouterr().out

    def test_json_output_is_parseable(self, tmp_path, capsys):
        path = write_records(tmp_path, [valid_raw()])
        assert main([str(path), "--format", "json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["total_jobs"] == 1
        assert payload["successful_jobs"] == 1

    def test_malformed_records_still_exit_zero_but_are_counted(self, tmp_path, capsys):
        path = write_records(tmp_path, [valid_raw(), "junk"])
        assert main([str(path), "--format", "json"]) == 0
        assert json.loads(capsys.readouterr().out)["rejected_records"] == 1


class TestFailureExitCodes:
    def test_a_missing_input_file_exits_two_with_a_stderr_hint(self, tmp_path, capsys):
        missing = tmp_path / "nope.json"
        assert main([str(missing)]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "nope.json" in captured.err

    def test_invalid_json_exits_two(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        assert main([str(path)]) == 2

    @pytest.mark.parametrize("argv", [[], ["a.json", "--format", "xml"]])
    def test_bad_arguments_exit_two(self, argv):
        with pytest.raises(SystemExit) as excinfo:
            main(argv)
        assert excinfo.value.code == 2


class TestModuleInvocation:
    def test_python_dash_m_entry_point_works(self, tmp_path):
        path = write_records(tmp_path, [valid_raw()])
        completed = subprocess.run(
            [sys.executable, "-m", "job_analytics", str(path), "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0
        assert json.loads(completed.stdout)["total_jobs"] == 1


class TestJobView:
    def test_the_job_view_reports_one_row_per_job(self, tmp_path, capsys):
        path = write_records(
            tmp_path,
            [
                valid_raw(job_id="a", status="failed", attempt=1),
                valid_raw(job_id="a", attempt=2),
                valid_raw(job_id="b"),
            ],
        )
        assert main([str(path), "--view", "job", "--format", "json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["total_jobs"] == 2
        assert payload["successful_jobs"] == 2
        assert payload["jobs_requiring_retries"] == 1
        assert payload["successful_after_retries"] == 1

    def test_the_job_view_text_labels_the_per_job_summary(self, tmp_path, capsys):
        path = write_records(tmp_path, [valid_raw()])
        assert main([str(path), "--view", "job"]) == 0
        assert "(per job)" in capsys.readouterr().out

    def test_an_unknown_view_exits_two(self):
        with pytest.raises(SystemExit) as excinfo:
            main(["a.json", "--view", "everything"])
        assert excinfo.value.code == 2
