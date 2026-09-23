"""FastVPN terminal client."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__version__ = "1.0.0"


def distribution_version() -> str:
    """Return the installed version, falling back to the package constant."""
    try:
        return version("fastvpn")
    except PackageNotFoundError:
        return __version__
