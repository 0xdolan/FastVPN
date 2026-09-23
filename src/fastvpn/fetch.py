"""Download and import OpenVPN profiles from zips, directories, files, and URLs."""

from __future__ import annotations

import os
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from fastvpn import distribution_version
from fastvpn.catalog import protocol_from_bytes
from fastvpn.errors import FastVPNError

SOURCES: dict[str, str] = {
    "grouped": "https://vpn.ncapi.io/groupedServerList.zip",
    "tcp": "https://vpn.ncapi.io/serverListTCP.zip",
    "udp": "https://vpn.ncapi.io/serverListUDP.zip",
}

_MAX_MEMBER = 2 * 1024 * 1024
_LAYOUT_PREFIXES = {"tcp", "udp", "imported"}


@dataclass
class ImportReport:
    destination: Path
    added: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "destination": str(self.destination),
            "added": self.added,
            "replaced": self.replaced,
            "skipped": self.skipped,
            "rejected": self.rejected,
            "counts": {
                "added": len(self.added),
                "replaced": len(self.replaced),
                "skipped": len(self.skipped),
                "rejected": len(self.rejected),
            },
        }


def source_records() -> list[dict[str, str]]:
    return [{"name": name, "url": url} for name, url in SOURCES.items()]


def import_any(source: Path, dest_root: Path, *, force: bool) -> ImportReport:
    if not source.exists():
        raise FastVPNError(f"Path not found: {source}")
    if source.resolve() == dest_root.resolve():
        raise FastVPNError("Import source and destination are the same directory.")
    if source.is_dir():
        return import_tree(source, dest_root, force=force)
    if zipfile.is_zipfile(source):
        return import_archive(source, dest_root, force=force)
    if source.suffix.lower() == ".ovpn" or source.is_file():
        report = ImportReport(destination=dest_root)
        _commit(report, dest_root, source.name, source.read_bytes(), force)
        if not any((report.added, report.replaced, report.skipped, report.rejected)):
            raise FastVPNError(f"No OpenVPN profile found in {source}")
        return report
    raise FastVPNError(f"Give a .ovpn file, a directory, or a zip archive. Got: {source}")


def import_tree(source: Path, dest_root: Path, *, force: bool) -> ImportReport:
    report = ImportReport(destination=dest_root)
    source = source.resolve()
    for dirpath, dirnames, filenames in os.walk(source, followlinks=False):
        dirnames[:] = [name for name in dirnames if name not in {".git", "__pycache__", ".venv"}]
        for filename in filenames:
            if not filename.lower().endswith(".ovpn"):
                continue
            path = Path(dirpath) / filename
            try:
                relative = path.relative_to(source).as_posix()
            except ValueError:
                report.rejected.append(str(path))
                continue
            try:
                data = path.read_bytes()
            except OSError as exc:
                report.rejected.append(f"{relative} ({exc.strerror})")
                continue
            _commit(report, dest_root, relative, data, force)
    return report


def import_archive(archive: Path, dest_root: Path, *, force: bool) -> ImportReport:
    if not zipfile.is_zipfile(archive):
        raise FastVPNError(f"Not a zip archive: {archive}")
    report = ImportReport(destination=dest_root)
    with zipfile.ZipFile(archive) as handle:
        for info in handle.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            basename = Path(name).name
            if name.startswith("__MACOSX/") or basename.startswith("._") or basename == ".DS_Store":
                continue
            if not name.lower().endswith(".ovpn"):
                continue
            with handle.open(info) as member:
                data = member.read(_MAX_MEMBER + 1)
            if len(data) > _MAX_MEMBER:
                report.rejected.append(f"{name} (larger than {_MAX_MEMBER} bytes)")
                continue
            _commit(report, dest_root, name, data, force)
    return report


def fetch_url(
    url: str,
    dest_root: Path,
    *,
    force: bool,
    console: object | None,
    dry_run: bool,
    show_progress: bool,
) -> ImportReport | None:
    if dry_run:
        return None
    dest_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fastvpn-") as tmp:
        payload = Path(tmp) / "payload"
        download(url, payload, console=console, show_progress=show_progress)
        if zipfile.is_zipfile(payload):
            return import_archive(payload, dest_root, force=force)
        data = payload.read_bytes()
        name = Path(urllib.parse.urlparse(url).path).name or "downloaded.ovpn"
        if not name.lower().endswith(".ovpn"):
            name = "downloaded.ovpn"
        report = ImportReport(destination=dest_root)
        _commit(report, dest_root, name, data, force)
        return report


def materialize_ovpn(url: str, cache_dir: Path, *, console: object | None, show_progress: bool) -> Path:
    """Download one remote .ovpn into the cache and return its path."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fastvpn-") as tmp:
        payload = Path(tmp) / "payload"
        download(url, payload, console=console, show_progress=show_progress)
        if zipfile.is_zipfile(payload):
            raise FastVPNError("That URL is a zip archive. Import it with: fastvpn fetch --url URL")
        name = Path(urllib.parse.urlparse(url).path).name or "remote.ovpn"
        if not name.lower().endswith(".ovpn"):
            name += ".ovpn"
        name = Path(name).name
        if name in {"", ".", ".."}:
            name = "remote.ovpn"
        destination = cache_dir / "remote" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload.read_bytes())
        return destination


def download(url: str, destination: Path, *, console: object | None, show_progress: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"fastvpn/{distribution_version()}"},
    )
    partial = destination.with_name(destination.name + ".partial")
    try:
        try:
            response = urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as exc:
            raise FastVPNError(f"Download failed ({exc.code}) for {url}") from exc
        except urllib.error.URLError as exc:
            raise FastVPNError(f"Download failed for {url}: {exc.reason}") from exc
        with response:
            total_header = response.headers.get("Content-Length")
            total = int(total_header) if total_header and total_header.isdigit() else None
            if show_progress and console is not None:
                _download_with_progress(response, partial, total, console)
            else:
                with partial.open("wb") as handle:
                    while True:
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _download_with_progress(response: object, partial: Path, total: int | None, console: object) -> None:
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )

    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )
    with progress, partial.open("wb") as handle:
        task = progress.add_task("Downloading", total=total)
        while True:
            chunk = response.read(64 * 1024)  # type: ignore[attr-defined]
            if not chunk:
                break
            handle.write(chunk)
            progress.update(task, advance=len(chunk))


def _commit(report: ImportReport, dest_root: Path, arcname: str, data: bytes, force: bool) -> None:
    target = _destination(dest_root, arcname, data)
    label = arcname.replace("\\", "/")
    if target is None:
        report.rejected.append(label)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        report.skipped.append(str(target.relative_to(dest_root)))
        return
    status = report.replaced if target.exists() else report.added
    target.write_bytes(data)
    status.append(str(target.relative_to(dest_root)))


def _destination(dest_root: Path, arcname: str, data: bytes) -> Path | None:
    normalized = arcname.replace("\\", "/").lstrip("/")
    pure = Path(normalized)
    if pure.is_absolute() or ".." in pure.parts or pure.name in {"", ".", ".."}:
        return None
    if pure.parts and pure.parts[0].lower() in _LAYOUT_PREFIXES:
        relative = Path(*pure.parts)
    else:
        relative = Path(protocol_from_bytes(pure.name, data)) / pure.name
    root = dest_root.resolve()
    target = (dest_root / relative).resolve()
    if target != root and root not in target.parents:
        return None
    if target.suffix.lower() != ".ovpn":
        return None
    return target
