"""Tests for profile discovery, imports, credentials, and the CLI."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

from fastvpn.catalog import load_servers, parse_filename, select_servers, ServerFilter
from fastvpn.cli import main
from fastvpn.connect import build_command
from fastvpn.credentials import inspect_file, write_file
from fastvpn.errors import FastVPNError
from fastvpn.fetch import fetch_url, import_archive
from fastvpn.models import AppPaths
from fastvpn.sessions import parse_ps


def _paths(root: Path) -> AppPaths:
    config = root / "config"
    return AppPaths(
        primary_root=root,
        scan_roots=((root, "project"),),
        config_dir=config,
        credentials_dir=config / "credentials",
        cache_dir=root / "cache",
        project_credentials=root / "credentials.txt",
    )


def _write_profile(root: Path, protocol: str, name: str, body: str = "client\nproto tcp\nremote example.test 443\n") -> None:
    directory = root / protocol
    directory.mkdir(parents=True, exist_ok=True)
    text = body.replace("proto tcp", f"proto {protocol}")
    (directory / name).write_text(text, encoding="utf-8")


def test_parse_filename_marks_virtual_profiles() -> None:
    assert parse_filename("NCVPN-US-St. Louis - Virtual-TCP.ovpn") == ("US", "St. Louis", "tcp", True)
    assert parse_filename("NCVPN-IN-Virtual-UDP.ovpn") == ("IN", None, "udp", True)
    assert parse_filename("NCVPN-DE-Frankfurt-TCP.ovpn") == ("DE", "Frankfurt", "tcp", False)


def test_country_alias_and_city_filter(tmp_path: Path) -> None:
    _write_profile(tmp_path, "tcp", "NCVPN-UK-London-TCP.ovpn")
    _write_profile(tmp_path, "udp", "NCVPN-US-Miami-UDP.ovpn")
    servers = load_servers(_paths(tmp_path))
    uk = select_servers(servers, ServerFilter(countries=("gb",)))
    assert [server.filename for server in uk] == ["NCVPN-UK-London-TCP.ovpn"]
    miami = select_servers(servers, ServerFilter(cities=("miami",), protocol="udp"))
    assert [server.city for server in miami] == ["Miami"]


def test_duplicate_names_keep_the_first_root(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_profile(first, "tcp", "NCVPN-DE-Frankfurt-TCP.ovpn", "client\nproto tcp\nremote one.test 443\n")
    _write_profile(second, "tcp", "NCVPN-DE-Frankfurt-TCP.ovpn", "client\nproto tcp\nremote two.test 443\n")
    paths = _paths(first)
    paths = AppPaths(
        primary_root=first,
        scan_roots=((first, "project"), (second, "extra")),
        config_dir=paths.config_dir,
        credentials_dir=paths.credentials_dir,
        cache_dir=paths.cache_dir,
        project_credentials=paths.project_credentials,
    )
    servers = load_servers(paths)
    assert len(servers) == 1
    assert servers[0].source == "project"


def test_archive_import_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "servers.zip"
    dest = tmp_path / "out"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("tcp/NCVPN-DE-Frankfurt-TCP.ovpn", "client\nproto tcp\n")
        handle.writestr("NCVPN-US-Miami-UDP.ovpn", "client\nproto udp\n")
        handle.writestr("../escape.ovpn", "client\n")
        handle.writestr("tcp/../../escape.ovpn", "client\n")
    report = import_archive(archive, dest, force=False)
    assert (dest / "tcp" / "NCVPN-DE-Frankfurt-TCP.ovpn").is_file()
    assert (dest / "udp" / "NCVPN-US-Miami-UDP.ovpn").is_file()
    assert not (tmp_path / "escape.ovpn").exists()
    assert not (dest / "escape.ovpn").exists()
    assert len(report.rejected) == 2
    again = import_archive(archive, dest, force=False)
    assert again.skipped
    assert again.added == []


def test_fetch_file_url(tmp_path: Path) -> None:
    archive = tmp_path / "servers.zip"
    dest = tmp_path / "out"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("udp/NCVPN-JP-Tokyo-UDP.ovpn", "client\nproto udp\n")
    report = fetch_url(archive.as_uri(), dest, force=False, console=None, dry_run=False, show_progress=False)
    assert report is not None
    assert (dest / "udp" / "NCVPN-JP-Tokyo-UDP.ovpn").is_file()


def test_credentials_round_trip_never_returns_the_password(tmp_path: Path) -> None:
    path = tmp_path / "credentials.txt"
    write_file(path, "alice", "super-secret-password")
    assert path.stat().st_mode & 0o777 == 0o600
    assert inspect_file(path) == "alice"
    with pytest.raises(FastVPNError):
        inspect_file(tmp_path / "missing.txt")
    broken = tmp_path / "broken.txt"
    broken.write_text("only-a-name\n", encoding="utf-8")
    with pytest.raises(FastVPNError) as caught:
        inspect_file(broken)
    assert "super-secret-password" not in str(caught.value)


def test_build_command_keeps_paths_as_arguments() -> None:
    command = build_command(
        binary="/usr/sbin/openvpn",
        config=Path("/tmp/NCVPN-US-New York-TCP.ovpn"),
        auth_file=Path("/tmp/credentials.txt"),
        use_sudo_flag=True,
        extra=["--mute", "20"],
    )
    assert command == [
        "sudo",
        "/usr/sbin/openvpn",
        "--config",
        "/tmp/NCVPN-US-New York-TCP.ovpn",
        "--auth-user-pass",
        "/tmp/credentials.txt",
        "--mute",
        "20",
    ]


def test_parse_ps_finds_openvpn_config_with_spaces() -> None:
    output = (
        "  4242 sudo openvpn --config /tmp/tcp/NCVPN-US-New York-TCP.ovpn --auth-user-pass /tmp/credentials.txt\n"
        "  99 python -m fastvpn status\n"
    )
    sessions = parse_ps(output)
    assert len(sessions) == 1
    assert sessions[0]["pid"] == 4242
    assert str(sessions[0]["config"]).endswith("New York-TCP.ovpn")


def test_help_and_list_and_connect(capsys: pytest.CaptureFixture[str], project: Path) -> None:
    assert main(["--help"]) == 0
    help_text = capsys.readouterr().out
    assert "fetch" in help_text
    assert "creds" in help_text

    _write_profile(project, "tcp", "NCVPN-US-New York-TCP.ovpn")
    _write_profile(project, "udp", "NCVPN-UK-London-UDP.ovpn")
    assert main(["list", "--country", "gb", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["servers"][0]["city"] == "London"

    write_file(project / "credentials.txt", "alice", "super-secret-password")
    assert main(["-t", "--dry-run", "--format", "json"]) == 0
    dry_run = capsys.readouterr().out
    assert "super-secret-password" not in dry_run
    document = json.loads(dry_run)
    assert document["dry_run"] is True
    assert "--config" in document["command"]
    assert "super-secret-password" not in document["command"]

    assert main(["-t", "-u"]) == 1
    assert "either --tcp or --udp" in capsys.readouterr().err


def test_creds_show_hides_password(capsys: pytest.CaptureFixture[str], project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("super-secret-password\n"))
    assert main(["creds", "set", "--username", "alice", "--password-stdin", "--profile", "work"]) == 0
    capsys.readouterr()
    assert main(["creds", "show", "--format", "json"]) == 0
    output = capsys.readouterr().out
    assert "alice" in output
    assert "super-secret-password" not in output
    assert "password" not in json.loads(output)


def test_env_root_ignores_the_working_tree(capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir("/home/dolan/Documents/FastVPN")
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("FASTVPN_ROOT", str(empty))
    assert main(["list", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 0


def test_doctor_fails_when_no_profiles_are_installed(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor", "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert any(check["name"] == "Profiles" and check["status"] == "fail" for check in payload["checks"])
