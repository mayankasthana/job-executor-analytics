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


class TestArrayDocuments:
    def test_reads_a_json_array_of_records(self, tmp_path):
        path = write_json(tmp_path, [{"job_id": "a"}, {"job_id": "b"}])
        assert list(JsonFileRecordSource(path).read_records()) == [
            {"job_id": "a"},
            {"job_id": "b"},
        ]

    def test_elements_are_returned_untouched(self, tmp_path):
        # Validation belongs to the parsing layer; the loader is a dumb feed.
        path = write_json(tmp_path, [{"a": 1}, "not-a-record", 42])
        assert list(JsonFileRecordSource(path).read_records()) == [{"a": 1}, "not-a-record", 42]

    def test_an_empty_array_is_zero_records(self, tmp_path):
        path = write_json(tmp_path, [])
        assert list(JsonFileRecordSource(path).read_records()) == []


class TestFatalInputErrors:
    def test_a_missing_file_raises_an_input_file_error(self, tmp_path):
        source = JsonFileRecordSource(tmp_path / "records.json")
        with pytest.raises(InputFileError, match=r"records\.json"):
            list(source.read_records())

    @pytest.mark.parametrize(
        "payload",
        [
            "{not json",
            "",
            "   \n",
            '{"jobs": []}',
            '"just a string"',
            "42",
            "[1,2",  # unterminated array
            "[1,2]x",  # trailing data
            "[1,]",  # missing element
            "[1,,2]",  # doubled comma
        ],
    )
    def test_documents_that_are_not_a_json_array_are_fatal(self, tmp_path, payload):
        path = write_json(tmp_path, payload)
        with pytest.raises(InputFileError):
            list(JsonFileRecordSource(path).read_records())


class TestStreamingBehavior:
    def test_read_records_is_lazy_and_single_pass(self, tmp_path):
        path = write_json(tmp_path, [{"a": 1}, {"b": 2}])
        records = JsonFileRecordSource(path).read_records()
        assert iter(records) is records  # an iterator, not a materialized list
        assert next(records) == {"a": 1}

    def test_defects_surface_when_reached_not_up_front(self, tmp_path):
        path = tmp_path / "records.json"
        path.write_text('[{"a": 1}, "junk" {"b": 2}]', encoding="utf-8")
        records = JsonFileRecordSource(path).read_records()
        assert next(records) == {"a": 1}
        assert next(records) == "junk"  # a stream delivers every decodable prefix...
        with pytest.raises(InputFileError):
            next(records)  # ...and the missing comma surfaces when reached

    def test_error_messages_carry_line_numbers(self, tmp_path):
        path = tmp_path / "records.json"
        path.write_text('[\n  {"a": 1},\n  {oops}\n]', encoding="utf-8")
        with pytest.raises(InputFileError, match="line 3"):
            list(JsonFileRecordSource(path).read_records())

    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 7, 64, 1024])
    def test_matches_json_loads_at_every_chunk_boundary(self, tmp_path, chunk_size):
        # Numbers, strings with escapes/commas, and nested structures are all
        # cut mid-token by small chunks; json.loads is the independent oracle.
        text = json.dumps(
            [
                {
                    "job_id": f"job-{index:04d}",
                    "count": 12345678901234 + index,
                    "text": f'value,{index}"\\escape',
                    "nested": [1, [2, {"deep": True}]],
                    "ratio": 1.5e-3,
                }
                for index in range(40)
            ]
        )
        path = tmp_path / "records.json"
        path.write_text(text, encoding="utf-8")
        source = JsonFileRecordSource(path, chunk_size=chunk_size)
        assert list(source.read_records()) == json.loads(text)

    @pytest.mark.parametrize(
        "text",
        [
            "[]",
            "[  ]",
            '[{"a":1},{"b":2}]',
            '[ { "a" : 1 } , { "b" : 2 } ]',
            '[\n{"a": 1},\r\n{"b": 2}\n]\n',
        ],
    )
    def test_whitespace_and_layout_match_json_loads(self, tmp_path, text):
        path = tmp_path / "records.json"
        path.write_text(text, encoding="utf-8")
        assert list(JsonFileRecordSource(path).read_records()) == json.loads(text)
