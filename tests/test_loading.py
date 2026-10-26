"""Behavior specs for reading raw records from JSON files."""

import json
from pathlib import Path

import pytest

from job_analytics.errors import InputFileError
from job_analytics.loading import JsonFileRecordSource


def write_json(tmp_path: Path, payload, name="records.json") -> Path:
    path = tmp_path / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestHappyPath:
    def test_reads_a_json_array_of_records(self, tmp_path):
        path = write_json(tmp_path, [{"job_id": "a"}, {"job_id": "b"}])
        assert JsonFileRecordSource(path).read_records() == [{"job_id": "a"}, {"job_id": "b"}]

    def test_elements_are_returned_untouched(self, tmp_path):
        # Validation belongs to the parsing layer; the loader is a dumb feed.
        path = write_json(tmp_path, [{"a": 1}, "not-a-record", 42])
        assert JsonFileRecordSource(path).read_records() == [{"a": 1}, "not-a-record", 42]

    def test_an_empty_array_is_zero_records(self, tmp_path):
        path = write_json(tmp_path, [])
        assert JsonFileRecordSource(path).read_records() == []


class TestFatalInputErrors:
    def test_a_missing_file_raises_an_input_file_error(self, tmp_path):
        source = JsonFileRecordSource(tmp_path / "records.json")
        with pytest.raises(InputFileError, match=r"records\.json"):
            source.read_records()

    @pytest.mark.parametrize(
        "payload",
        ["{not json", "", "   \n", '{"jobs": []}', '"just a string"', "42"],
    )
    def test_documents_that_are_not_a_json_array_are_fatal(self, tmp_path, payload):
        path = write_json(tmp_path, payload)
        with pytest.raises(InputFileError):
            JsonFileRecordSource(path).read_records()
