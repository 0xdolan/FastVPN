"""Shared records for servers and resolved paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Server:
    path: Path
    filename: str
    protocol: str
    country_code: str | None
    country: str | None
    city: str | None
    virtual: bool
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "country_code": self.country_code,
            "country": self.country,
            "city": self.city,
            "virtual": self.virtual,
            "filename": self.filename,
            "path": str(self.path),
            "source": self.source,
        }


@dataclass(frozen=True)
class AppPaths:
    primary_root: Path
    scan_roots: tuple[tuple[Path, str], ...]
    config_dir: Path
    credentials_dir: Path
    cache_dir: Path
    project_credentials: Path

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "config.toml"
