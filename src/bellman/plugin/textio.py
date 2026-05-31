"""Injectable stdin/stdout/stderr for plugin commands."""

from __future__ import annotations

import sys
from typing import Any
from typing import TextIO as TypingTextIO

__all__ = ["TextIO"]


class TextIO:
    """Represent input, output, and error I/O streams for plugins.

    Defaults to process ``sys.stdin``, ``sys.stdout``, and ``sys.stderr`` (text
    mode). Inject alternate streams in tests.
    """

    def __init__(
        self,
        input_stream: TypingTextIO | Any = sys.stdin,
        output_stream: TypingTextIO | Any = sys.stdout,
        error_stream: TypingTextIO | Any = sys.stderr,
    ) -> None:
        """Initialize with the given I/O streams.

        Args:
            input_stream: Readable text stream.
            output_stream: Writable text stream for normal output.
            error_stream: Writable text stream for diagnostics.
        """
        self._input = input_stream
        self._output = output_stream
        self._error = error_stream

    def read(self, num_chars: int = -1) -> str:
        """Read from the input stream.

        Args:
            num_chars: Maximum characters to read, or ``-1`` for all.

        Returns:
            Text read from the input stream.
        """
        return self._input.read(num_chars)

    def readline(self) -> str:
        """Read a line from the input stream.

        Returns:
            A single line including its trailing newline when present.
        """
        return self._input.readline()

    def write(self, data: str) -> int:
        """Write data to the output stream.

        Args:
            data: Text to write.

        Returns:
            Number of characters written.
        """
        return self._output.write(data)

    def writeline(self, data: str) -> None:
        """Write a line to the output stream (no extra newline added).

        Args:
            data: Line text to write.
        """
        self._output.write(data)
        if not data.endswith("\n"):
            self._output.write("\n")

    def write_error(self, data: str) -> int:
        """Write data to the error stream.

        Args:
            data: Text to write.

        Returns:
            Number of characters written.
        """
        return self._error.write(data)

    def writeline_error(self, data: str) -> None:
        """Write a line to the error stream (no extra newline added).

        Args:
            data: Line text to write.
        """
        self._error.write(data)
        if not data.endswith("\n"):
            self._error.write("\n")
