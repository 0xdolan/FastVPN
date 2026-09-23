"""Build and run the OpenVPN command."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from fastvpn.credentials import CredentialRef
from fastvpn.errors import FastVPNError


def openvpn_binary(explicit: str | None) -> str:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise FastVPNError(f"OpenVPN binary is not executable: {explicit}")
        return str(path)
    found = shutil.which("openvpn")
    if not found:
        raise FastVPNError(
            "OpenVPN is not installed or not on PATH. "
            "On Debian or Ubuntu: sudo apt install openvpn"
        )
    return found


def use_sudo(*, requested: bool, disabled: bool) -> bool:
    if disabled:
        return False
    if requested:
        return True
    return os.geteuid() != 0


def build_command(
    *,
    binary: str,
    config: Path,
    auth_file: Path | None,
    use_sudo_flag: bool,
    extra: list[str] | None,
) -> list[str]:
    command = [binary, "--config", str(config)]
    if auth_file is not None:
        command.extend(["--auth-user-pass", str(auth_file)])
    if extra:
        command.extend(extra)
    if use_sudo_flag:
        if shutil.which("sudo") is None and os.geteuid() != 0:
            raise FastVPNError("sudo is required to start OpenVPN and was not found. Pass --no-sudo to try anyway.")
        command.insert(0, "sudo")
    return command


def run_openvpn(command: list[str], credentials: CredentialRef | None) -> int:
    try:
        completed = subprocess.run(command, check=False)
        return completed.returncode
    finally:
        if credentials is not None and credentials.source == "environment":
            credentials.path.unlink(missing_ok=True)
