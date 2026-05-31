"""Snark validation and layout errors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SnarkError:
    """Single validation or layout error."""

    path: str
    message: str
    line: int | None = None

    def format(self) -> str:
        if self.line is not None:
            return f"{self.path}:{self.line}: {self.message}"
        return f"{self.path}: {self.message}"


@dataclass(frozen=True, slots=True)
class SnarkWarning:
    """Non-fatal validation warning."""

    path: str
    message: str
    line: int | None = None

    def format(self) -> str:
        if self.line is not None:
            return f"{self.path}:{self.line}: {self.message}"
        return f"{self.path}: {self.message}"


class SnarkLayoutError(Exception):
    """Filesystem layout operation failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
