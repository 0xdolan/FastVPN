"""Resolve project, data, config, and cache directories."""

from __future__ import annotations

import os
from pathlib import Path

from fastvpn.models import AppPaths


def config_directory() -> Path:
    override = os.environ.get("FASTVPN_CONFIG_HOME")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "fastvpn"


def data_directory() -> Path:
    override = os.environ.get("FASTVPN_DATA_HOME")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".local" / "share"
    return root / "fastvpn"


def cache_directory() -> Path:
    override = os.environ.get("FASTVPN_CACHE_HOME")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".cache"
    return root / "fastvpn"


def _is_project(path: Path) -> bool:
    if (path / "tcp").is_dir() or (path / "udp").is_dir():
        return True
    manifest = path / "pyproject.toml"
    if not manifest.is_file():
        return False
    try:
        text = manifest.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return 'name = "fastvpn"' in text or "name = 'fastvpn'" in text


def find_project(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if _is_project(candidate):
            return candidate
    return None


def resolve_paths(
    root: Path | None,
    extra: list[Path] | None = None,
    cwd: Path | None = None,
) -> AppPaths:
    """Choose which directories are scanned and where new profiles are written.

    ``FASTVPN_ROOT`` and ``--root`` select a single server root. Without them,
    the project that contains ``tcp/`` or ``udp/`` is scanned together with the
    user data directory.
    """
    extra = extra or []
    cwd = (cwd or Path.cwd()).resolve()
    config_dir = config_directory()
    data_dir = data_directory()
    cache_dir = cache_directory()

    env_value = os.environ.get("FASTVPN_ROOT")
    env_root = Path(env_value).expanduser().resolve() if env_value else None
    explicit = root.expanduser().resolve() if root is not None else None

    scan: list[tuple[Path, str]] = []
    seen: set[Path] = set()

    def add(path: Path, label: str) -> None:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        scan.append((resolved, label))

    for item in extra:
        add(item, "extra")

    if explicit is not None:
        primary = explicit
        add(explicit, "root")
    elif env_root is not None:
        primary = env_root
        add(env_root, "root")
    else:
        project = find_project(cwd)
        if project is not None:
            primary = project
            add(project, "project")
        else:
            primary = data_dir
        add(data_dir, "data")

    return AppPaths(
        primary_root=primary,
        scan_roots=tuple(scan),
        config_dir=config_dir,
        credentials_dir=config_dir / "credentials",
        cache_dir=cache_dir,
        project_credentials=primary / "credentials.txt",
    )
