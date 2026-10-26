"""Input adapters: where raw records come from.

The pipeline depends on the :class:`RecordSource` protocol, not on files, so
other sources (HTTP, database, stdin) can be added without touching it.
"""

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Protocol, TextIO

from job_analytics.errors import InputFileError


class RecordSource(Protocol):
    """Anything that can supply raw records on demand.

    The returned iterable may be single-pass: iterate it exactly once.
    Implementations may defer reading until iteration starts, so fatal input
    errors can surface lazily while iterating.
    """

    def read_records(self) -> Iterable[Any]: ...


class JsonFileRecordSource:
    """Streams records from a top-level JSON array in a file.

    The document is never held in memory: array elements are decoded one at a
    time with :meth:`json.JSONDecoder.raw_decode` over chunked reads, so peak
    memory is proportional to the largest single record, not the file size.
    The array may contain anything; deciding which elements are valid records
    is the parsing layer's responsibility, not this class's.

    Fatal input errors (missing file, invalid JSON, non-array root, trailing
    data) surface during iteration as :class:`InputFileError`.
    """

    _WHITESPACE = " \t\r\n"  # exactly JSON's four whitespace characters

    def __init__(self, path: Path | str, *, chunk_size: int = 1 << 20) -> None:
        self._path = Path(path)
        self._chunk_size = chunk_size

    def read_records(self) -> Iterator[Any]:
        try:
            stream = self._path.open("r", encoding="utf-8")
        except OSError as exc:
            raise InputFileError(f"cannot read input file {self._path}: {exc.strerror}") from exc
        with stream:
            yield from self._stream_array(stream)

    def _stream_array(self, stream: TextIO) -> Iterator[Any]:
        decoder = json.JSONDecoder()
        buffer = ""
        eof = False
        newlines = 0  # newlines consumed so far, for error line numbers

        def fail(message: str) -> InputFileError:
            return InputFileError(f"input file {self._path} is not valid JSON: {message}")

        def fill() -> None:
            nonlocal buffer, eof
            chunk = stream.read(self._chunk_size)
            if not chunk:
                eof = True
            buffer += chunk

        def skip_whitespace() -> None:
            nonlocal buffer, newlines
            trimmed = buffer.lstrip(self._WHITESPACE)
            newlines += buffer.count("\n", 0, len(buffer) - len(trimmed))
            buffer = trimmed

        while True:  # expect the opening bracket
            skip_whitespace()
            if buffer:
                break
            if eof:
                raise fail("document is empty")
            fill()

        if buffer[0] != "[":
            raise fail(f"expected a top-level JSON array, got {buffer[0]!r}")
        buffer = buffer[1:]

        expecting_value = True  # True right after '[' or ','
        elements_seen = False
        while True:
            skip_whitespace()
            if not buffer:
                if eof:
                    raise fail("unterminated array (missing ']')")
                fill()
                continue

            if expecting_value:
                if buffer[0] == "]":
                    if elements_seen:
                        raise fail(f"expected a value before ']' (line {newlines + 1})")
                    buffer = buffer[1:]  # empty array
                    break
                while True:  # decode one element
                    try:
                        value, end = decoder.raw_decode(buffer)
                    except json.JSONDecodeError as exc:
                        if eof:
                            line = newlines + buffer.count("\n", 0, exc.pos) + 1
                            raise fail(f"{exc.msg} (line {line})") from None
                        fill()
                        continue
                    if eof or buffer[end:].strip():
                        # A delimiter (or EOF) follows: the token is complete.
                        # Without this check a number split by a chunk boundary
                        # would be yielded truncated.
                        break
                    fill()  # the value may continue in the next chunk
                newlines += buffer.count("\n", 0, end)
                yield value
                buffer = buffer[end:]
                elements_seen = True
                expecting_value = False
            elif buffer[0] == ",":
                buffer = buffer[1:]
                expecting_value = True
            elif buffer[0] == "]":
                buffer = buffer[1:]
                break
            else:
                raise fail(f"expected ',' or ']' (line {newlines + 1})")

        while not eof:  # after ']': only whitespace may remain
            skip_whitespace()
            if buffer:
                raise fail("trailing data after the array")
            fill()
