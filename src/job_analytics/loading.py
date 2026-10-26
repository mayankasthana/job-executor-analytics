"""Input adapters: where raw records come from.

The pipeline depends on the :class:`RecordSource` protocol, not on files, so
other sources (HTTP, database, stdin) can be added without touching it.
"""

import json
from pathlib import Path
from typing import Any, Protocol

from job_analytics.errors import InputFileError


class RecordSource(Protocol):
    """Anything that can supply raw records on demand."""

    def read_records(self) -> list[Any]: ...


class JsonFileRecordSource:
    """Reads a top-level JSON array of records from a file.

    The array may contain anything; deciding which elements are valid records
    is the parsing layer's responsibility, not this class's.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def read_records(self) -> list[Any]:
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise InputFileError(f"cannot read input file {self._path}: {exc.strerror}") from exc
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InputFileError(
                f"input file {self._path} is not valid JSON: {exc.msg} (line {exc.lineno})"
            ) from exc
        if not isinstance(document, list):
            raise InputFileError(
                f"input file {self._path} must contain a top-level JSON array of records, "
                f"got {type(document).__name__}"
            )
        return document
