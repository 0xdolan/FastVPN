"""Scan and filter local OpenVPN profiles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from fastvpn.countries import CODE_ALIASES, country_name
from fastvpn.errors import FastVPNError
from fastvpn.models import AppPaths, Server

_FILENAME = re.compile(
    r"^NCVPN-(?P<code>[A-Za-z]{2})-(?P<city>.+)-(?P<proto>TCP|UDP)\.ovpn$",
    re.IGNORECASE,
)
_LAYOUT = ("tcp", "udp", "imported")


def parse_filename(name: str) -> tuple[str | None, str | None, str | None, bool]:
    """Return country code, city, protocol, and whether the profile is virtual."""
    match = _FILENAME.match(name)
    if not match:
        return None, None, None, False
    city = match.group("city").strip()
    virtual = city.casefold().endswith(" - virtual")
    if virtual:
        city = city[: -len(" - virtual")].strip()
    if city.casefold() == "virtual":
        return match.group("code").upper(), None, match.group("proto").lower(), True
    return match.group("code").upper(), city, match.group("proto").lower(), virtual


def sniff_proto(path: Path) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    return _proto_in_lines(lines)


def protocol_from_bytes(filename: str, data: bytes) -> str:
    _code, _city, proto, _virtual = parse_filename(filename)
    if proto in {"tcp", "udp"}:
        return proto
    text = data[:8000].decode("utf-8", errors="ignore")
    sniffed = _proto_in_lines(text.splitlines())
    if sniffed:
        return sniffed
    return "imported"


def _proto_in_lines(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        if index > 80:
            break
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("<"):
            break
        parts = stripped.split()
        if parts and parts[0] == "proto" and len(parts) > 1 and parts[1].lower() in {"tcp", "udp"}:
            return parts[1].lower()
    return None


def read_profile(path: Path) -> dict[str, object]:
    """Read connection metadata, stopping before embedded certificates."""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        raise FastVPNError(f"Could not read {path}: {exc.strerror}") from exc

    proto: str | None = None
    remotes: list[dict[str, str]] = []
    remote_random = False
    auth_user_pass = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("<"):
            break
        parts = stripped.split()
        command = parts[0]
        if command == "proto" and len(parts) > 1:
            proto = parts[1].lower()
        elif command == "remote" and len(parts) > 1:
            port = parts[2] if len(parts) > 2 and parts[2].isdigit() else ""
            remotes.append({"host": parts[1], "port": port})
        elif command == "remote-random":
            remote_random = True
        elif command == "auth-user-pass":
            auth_user_pass = True
    return {
        "proto": proto,
        "remotes": remotes,
        "remote_count": len(remotes),
        "remote_random": remote_random,
        "auth_user_pass": auth_user_pass,
    }


def describe_server(path: Path, source: str, parent_proto: str | None) -> Server:
    code, city, file_proto, virtual = parse_filename(path.name)
    protocol = parent_proto or file_proto
    if protocol is None:
        protocol = sniff_proto(path) or "tcp"
    return Server(
        path=path.resolve(),
        filename=path.name,
        protocol=protocol,
        country_code=code,
        country=country_name(code),
        city=city,
        virtual=virtual,
        source=source,
    )


def _iter_profiles(root: Path) -> list[tuple[Path, str | None]]:
    if not root.is_dir():
        return []
    has_layout = any((root / name).is_dir() for name in _LAYOUT)
    found: list[tuple[Path, str | None]] = []
    if has_layout:
        folders = [(name, name if name in {"tcp", "udp"} else None) for name in _LAYOUT]
    else:
        folders = [(".", None)]
    for folder, parent_proto in folders:
        directory = root if folder == "." else root / folder
        if not directory.is_dir():
            continue
        try:
            entries = list(directory.iterdir())
        except OSError as exc:
            raise FastVPNError(f"Could not read {directory}: {exc.strerror}") from exc
        for path in entries:
            if path.is_file() and path.suffix.lower() == ".ovpn":
                found.append((path, parent_proto))
    return found


def load_servers(paths: AppPaths) -> list[Server]:
    servers: list[Server] = []
    seen: set[tuple[str, str]] = set()
    for root, label in paths.scan_roots:
        for path, parent_proto in _iter_profiles(root):
            server = describe_server(path, label, parent_proto)
            key = (server.protocol, server.filename)
            if key in seen:
                continue
            seen.add(key)
            servers.append(server)
    servers.sort(key=_sort_key)
    return servers


def _sort_key(server: Server) -> tuple[str, str, str, str]:
    return (
        (server.country or server.country_code or "").casefold(),
        (server.city or "").casefold(),
        server.protocol,
        server.filename.casefold(),
    )


@dataclass(frozen=True)
class ServerFilter:
    protocol: str | None = None
    countries: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    query: str | None = None


def select_servers(servers: list[Server], server_filter: ServerFilter) -> list[Server]:
    protocol = server_filter.protocol
    if protocol == "any":
        protocol = None
    chosen = [
        server
        for server in servers
        if _matches(server, protocol, server_filter.countries, server_filter.cities, server_filter.query)
    ]
    chosen.sort(key=_sort_key)
    return chosen


def _matches(
    server: Server,
    protocol: str | None,
    countries: tuple[str, ...],
    cities: tuple[str, ...],
    query: str | None,
) -> bool:
    if protocol and server.protocol != protocol:
        return False
    if countries and not any(_country_matches(server, token) for token in countries):
        return False
    if cities and not any(_city_matches(server, token) for token in cities):
        return False
    if query and not _query_matches(server, query):
        return False
    return True


def _country_matches(server: Server, token: str) -> bool:
    raw = token.strip().casefold()
    if not raw:
        return True
    code = CODE_ALIASES.get(raw, raw)
    server_code = (server.country_code or "").casefold()
    server_name = (server.country or "").casefold()
    if len(code) <= 3 and code.isalpha():
        return code == server_code or code == server_name
    return code == server_code or code in server_name


def _city_matches(server: Server, token: str) -> bool:
    return token.strip().casefold() in (server.city or "").casefold()


def _query_matches(server: Server, query: str) -> bool:
    needle = query.strip().casefold()
    if not needle:
        return True
    haystack = " ".join(
        part
        for part in (
            server.filename,
            server.city or "",
            server.country or "",
            server.country_code or "",
            server.protocol,
            "virtual" if server.virtual else "",
            server.source,
        )
        if part
    )
    return needle in haystack.casefold()


def summarize(servers: list[Server]) -> list[dict[str, object]]:
    buckets: dict[str, dict[str, object]] = {}
    for server in servers:
        code = server.country_code or "??"
        row = buckets.get(code)
        if row is None:
            row = {
                "country_code": code,
                "country": server.country or code,
                "tcp": 0,
                "udp": 0,
                "total": 0,
            }
            buckets[code] = row
        if server.protocol in {"tcp", "udp"}:
            row[server.protocol] = int(row[server.protocol]) + 1
        row["total"] = int(row["total"]) + 1
    return sorted(buckets.values(), key=lambda item: str(item["country"]).casefold())
