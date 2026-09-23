"""Inspect and stop local OpenVPN processes."""

from __future__ import annotations

import os
import re
import shutil
import subprocess

from fastvpn.errors import FastVPNError

_PID_LINE = re.compile(r"^\s*(\d+)\s+(.*)$")
_OPENVPN = re.compile(r"(^|[\s/])openvpn(\s|$)")
_CONFIG = re.compile(r"--config(?:=|\s+)(.+?)(?=\s--|\s*$)")


def parse_ps(output: str) -> list[dict[str, object]]:
    sessions: list[dict[str, object]] = []
    for line in output.splitlines():
        match = _PID_LINE.match(line)
        if not match:
            continue
        pid = int(match.group(1))
        command = match.group(2).strip()
        if not _OPENVPN.search(command):
            continue
        config_match = _CONFIG.search(command)
        sessions.append(
            {
                "pid": pid,
                "config": config_match.group(1) if config_match else None,
                "command": command,
            }
        )
    return sessions


def list_sessions() -> list[dict[str, object]]:
    ps = shutil.which("ps")
    if ps is None:
        raise FastVPNError("ps is not available, so running OpenVPN sessions cannot be listed.")
    completed = subprocess.run([ps, "-eo", "pid=,args="], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "ps failed"
        raise FastVPNError(detail)
    return parse_ps(completed.stdout)


def signal_command(pids: list[int], *, force: bool, sudo: bool) -> list[str]:
    if not pids:
        raise FastVPNError("No OpenVPN sessions to disconnect.")
    if any(pid < 2 for pid in pids):
        raise FastVPNError("Refusing to signal a system process.")
    signal = "-KILL" if force else "-TERM"
    command = ["kill", signal, *[str(pid) for pid in pids]]
    if sudo and os.geteuid() != 0:
        if shutil.which("sudo") is None:
            raise FastVPNError("sudo is required to stop OpenVPN and was not found.")
        command.insert(0, "sudo")
    return command


def terminate(pids: list[int], *, force: bool, sudo: bool) -> list[str]:
    command = signal_command(pids, force=force, sudo=sudo)
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise FastVPNError(f"Stopping OpenVPN failed with exit code {completed.returncode}.")
    return command
