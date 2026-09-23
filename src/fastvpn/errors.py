"""User-facing command errors."""

from __future__ import annotations


class FastVPNError(Exception):
    """A problem the command can explain and exit on."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code
