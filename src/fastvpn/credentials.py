"""Credential files and named profiles.

OpenVPN auth files are two lines: username, then password. The password is
written to disk and handed to OpenVPN by path. It is never included in
command output.
"""

from __future__ import annotations

import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from fastvpn.errors import FastVPNError
from fastvpn.models import AppPaths

_PROFILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_RESERVED = {"project"}


@dataclass(frozen=True)
class CredentialRef:
    path: Path
    username: str
    source: str
    profile: str | None

    def public(self) -> dict[str, object]:
        mode = None
        if self.path.exists():
            mode = self.path.stat().st_mode & 0o777
        return {
            "source": self.source,
            "profile": self.profile,
            "path": str(self.path),
            "username": self.username,
            "permissions": format(mode, "03o") if mode is not None else None,
            "private": mode is not None and mode & 0o077 == 0,
        }


def inspect_file(path: Path) -> str:
    """Return the username when the file has the two-line OpenVPN layout."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise FastVPNError(f"Credentials file is not UTF-8 text: {path}") from exc
    except OSError as exc:
        raise FastVPNError(f"Could not read credentials file {path}: {exc.strerror}") from exc
    lines = text.splitlines()
    if len(lines) < 2 or not lines[0].strip() or lines[1] == "":
        raise FastVPNError(
            f"{path} needs two lines: username, then password. "
            "OpenVPN reads those lines exactly and does not treat '#' as a comment."
        )
    return lines[0].strip()


def write_file(path: Path, username: str, password: str) -> None:
    if not username.strip() or password == "":
        raise FastVPNError("Username and password are both required.")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    payload = f"{username.strip()}\n{password}\n".encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def validate_profile_name(name: str) -> str:
    if name == "project":
        return name
    if not _PROFILE_NAME.match(name) or name in _RESERVED:
        raise FastVPNError(
            "Profile names use letters, numbers, dots, underscores, and hyphens. "
            "'project' is reserved for the project credentials.txt file."
        )
    return name


def profile_path(paths: AppPaths, name: str) -> Path:
    validate_profile_name(name)
    if name == "project":
        return paths.project_credentials
    return paths.credentials_dir / f"{name}.txt"


def read_settings(paths: AppPaths) -> dict[str, object]:
    path = paths.settings_file
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            loaded = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise FastVPNError(f"Could not read {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        return {}
    return loaded


def active_profile_name(paths: AppPaths) -> str | None:
    active = read_settings(paths).get("active_profile")
    if isinstance(active, str) and active.strip():
        return active.strip()
    return None


def effective_profile_name(paths: AppPaths) -> str | None:
    selected = active_profile_name(paths)
    if selected:
        return selected
    if paths.project_credentials.is_file():
        return "project"
    if (paths.credentials_dir / "default.txt").is_file():
        return "default"
    return None


def write_active_profile(paths: AppPaths, name: str) -> None:
    validate_profile_name(name)
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    try:
        paths.config_dir.chmod(0o700)
    except OSError:
        pass
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    paths.settings_file.write_text(f'active_profile = "{escaped}"\n', encoding="utf-8")
    os.chmod(paths.settings_file, 0o600)


def clear_active_profile(paths: AppPaths, name: str) -> None:
    if active_profile_name(paths) == name and paths.settings_file.exists():
        paths.settings_file.unlink()


def load_named(paths: AppPaths, name: str, *, required: bool) -> CredentialRef | None:
    path = profile_path(paths, name)
    if not path.is_file():
        if required:
            hint = "fastvpn creds set --project" if name == "project" else f"fastvpn creds set --profile {name}"
            raise FastVPNError(f"Credential profile '{name}' was not found. Create it with: {hint}")
        return None
    source = "project" if name == "project" else "profile"
    return CredentialRef(path=path, username=inspect_file(path), source=source, profile=name)


def resolve_credentials(
    paths: AppPaths,
    *,
    explicit: Path | None,
    profile: str | None,
    no_auth: bool,
    materialize_env: bool = True,
) -> CredentialRef | None:
    """Pick the auth file OpenVPN should use.

    Order: ``--no-auth``, ``--credentials``, ``FASTVPN_CREDENTIALS``,
    ``FASTVPN_USERNAME`` plus ``FASTVPN_PASSWORD``, ``--profile``, the active
    profile, then ``credentials.txt`` in the project.
    """
    if no_auth:
        return None
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise FastVPNError(f"Credentials file not found: {path}")
        return CredentialRef(path=path, username=inspect_file(path), source="file", profile=None)

    env_file = os.environ.get("FASTVPN_CREDENTIALS")
    if env_file:
        path = Path(env_file).expanduser().resolve()
        if not path.is_file():
            raise FastVPNError(f"FASTVPN_CREDENTIALS does not point to a file: {path}")
        return CredentialRef(path=path, username=inspect_file(path), source="file", profile=None)

    env_user = os.environ.get("FASTVPN_USERNAME")
    env_password = os.environ.get("FASTVPN_PASSWORD")
    if env_user is not None or env_password is not None:
        if not env_user or not env_password:
            raise FastVPNError("Set both FASTVPN_USERNAME and FASTVPN_PASSWORD, or neither.")
        if not materialize_env:
            return CredentialRef(
                path=paths.cache_dir / "environment.txt",
                username=env_user.strip(),
                source="environment",
                profile=None,
            )
        path = _write_environment_file(paths.cache_dir, env_user, env_password)
        return CredentialRef(path=path, username=env_user.strip(), source="environment", profile=None)

    if profile:
        return load_named(paths, profile, required=True)

    selected = effective_profile_name(paths)
    if selected is None:
        return None
    return load_named(paths, selected, required=True)


def _write_environment_file(cache_dir: Path, username: str, password: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        cache_dir.chmod(0o700)
    except OSError:
        pass
    fd, name = tempfile.mkstemp(prefix="auth-", suffix=".txt", dir=cache_dir)
    os.close(fd)
    path = Path(name)
    write_file(path, username, password)
    return path


def list_profiles(paths: AppPaths) -> list[dict[str, object]]:
    effective = effective_profile_name(paths)
    rows: list[dict[str, object]] = []
    candidates: list[tuple[str, Path]] = [("project", paths.project_credentials)]
    if paths.credentials_dir.is_dir():
        for path in sorted(paths.credentials_dir.glob("*.txt"), key=lambda item: item.name.casefold()):
            candidates.append((path.stem, path))
    seen: set[str] = set()
    for name, path in candidates:
        if name in seen or not path.is_file():
            continue
        seen.add(name)
        try:
            username: str | None = inspect_file(path)
            error = None
        except FastVPNError as exc:
            username = None
            error = str(exc)
        mode = path.stat().st_mode & 0o777
        rows.append(
            {
                "profile": name,
                "username": username,
                "path": str(path),
                "active": name == effective,
                "permissions": format(mode, "03o"),
                "private": mode & 0o077 == 0,
                "error": error,
            }
        )
    return rows


def remove_profile(paths: AppPaths, name: str) -> Path:
    path = profile_path(paths, name)
    if not path.is_file():
        raise FastVPNError(f"Credential profile '{name}' was not found.")
    path.unlink()
    clear_active_profile(paths, name)
    return path
