"""Rich rendering for tables, panels, and machine-readable output."""

from __future__ import annotations

import csv
import json
import sys
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from fastvpn.fetch import ImportReport

THEME = Theme(
    {
        "tcp": "bold bright_cyan",
        "udp": "bold bright_magenta",
        "ok": "bold green",
        "warn": "bold yellow",
        "err": "bold red",
        "muted": "dim",
        "title": "bold white",
    }
)


def make_console(stream: Any, *, no_color: bool) -> Console:
    return Console(
        file=stream,
        theme=THEME,
        no_color=no_color,
        soft_wrap=True,
        highlight=False,
    )


def emit_json(payload: object) -> None:
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")


def text_cell(value: object, style: str | None = None) -> Text:
    rendered = "" if value is None else str(value)
    return Text(rendered, style=style)


def print_error(console: Console, message: str) -> None:
    console.print(Text(message, style="err"))


_COLUMN_RATIO = {
    "File": 4,
    "Country": 3,
    "City": 2,
    "Command": 4,
    "Detail": 4,
    "Path": 3,
    "Location": 3,
    "URL": 4,
    "Username": 2,
}
_NO_WRAP = {
    "Protocol",
    "Code",
    "Virtual",
    "TCP",
    "UDP",
    "Total",
    "Mode",
    "PID",
    "Status",
    "#",
    "Active",
    "Port",
    "File",
    "Source",
    "City",
    "Country",
}


def render_records(
    out: Console,
    records: list[dict[str, Any]],
    columns: list[tuple[str, str]],
    *,
    title: str,
    caption: str | None = None,
) -> None:
    table = Table(
        title=title,
        caption=caption,
        box=box.ROUNDED,
        header_style="bold cyan",
        border_style="bright_black",
        expand=False,
        show_lines=False,
    )
    for _key, header in columns:
        column_kwargs: dict[str, Any] = {
            "overflow": "fold",
            "ratio": _COLUMN_RATIO.get(header, 1),
            "no_wrap": header in _NO_WRAP or header == "File",
        }
        if header == "File":
            column_kwargs["min_width"] = 24
        table.add_column(header, **column_kwargs)
    for record in records:
        table.add_row(*[_table_cell(key, record) for key, _header in columns])
    out.print(table)


def _table_cell(key: str, record: dict[str, Any]) -> Text:
    value = record.get(key)
    if key in {"virtual", "active", "private"}:
        value = "yes" if value else "no"
    if key == "protocol" and value in {"tcp", "udp"}:
        return text_cell(str(value).upper(), style=str(value))
    if key == "status":
        style = {"ok": "ok", "warn": "warn", "fail": "err"}.get(str(value), None)
        return text_cell(str(value).upper(), style=style)
    return text_cell("" if value is None else value)


def write_delimited(
    records: list[dict[str, Any]],
    columns: list[tuple[str, str]],
    *,
    delimiter: str,
) -> None:
    writer = csv.writer(sys.stdout, delimiter=delimiter, lineterminator="\n")
    writer.writerow([header for _key, header in columns])
    for record in records:
        writer.writerow([_plain(record.get(key)) for key, _header in columns])


def _plain(value: object) -> object:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return ""
    return value


def render_output(
    out: Console,
    err: Console,
    fmt: str,
    records: list[dict[str, Any]],
    columns: list[tuple[str, str]],
    *,
    title: str,
    empty_message: str,
    json_payload: dict[str, Any],
) -> None:
    if fmt == "json":
        emit_json(json_payload)
        return
    if not records:
        err.print(Text(empty_message, style="warn"))
        if fmt == "csv":
            write_delimited(records, columns, delimiter=",")
        return
    if fmt == "csv":
        write_delimited(records, columns, delimiter=",")
        return
    if fmt == "plain":
        write_delimited(records, columns, delimiter="\t")
        return
    render_records(out, records, columns, title=title, caption=f"{len(records)} shown")


def render_mapping(
    out: Console,
    title: str,
    rows: list[tuple[str, str]],
    *,
    border: str = "cyan",
) -> None:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="muted", justify="right")
    table.add_column(overflow="fold")
    for key, value in rows:
        table.add_row(key, text_cell(value))
    out.print(Panel(table, title=title, border_style=border, expand=False))


def render_report(out: Console, err: Console, fmt: str, report: ImportReport, *, verbose: bool) -> None:
    payload = report.to_dict()
    if fmt == "json":
        emit_json(payload)
        return
    counts = payload["counts"]
    assert isinstance(counts, dict)
    if fmt in {"csv", "plain"}:
        records = [{"item": key, "count": value} for key, value in counts.items()]
        columns = [("item", "Item"), ("count", "Count")]
        delimiter = "," if fmt == "csv" else "\t"
        write_delimited(records, columns, delimiter=delimiter)
        return
    border = "yellow" if report.rejected else "green"
    render_mapping(
        out,
        "Profiles",
        [
            ("Destination", str(report.destination)),
            ("Added", str(len(report.added))),
            ("Replaced", str(len(report.replaced))),
            ("Already present", str(len(report.skipped))),
            ("Rejected", str(len(report.rejected))),
        ],
        border=border,
    )
    if report.rejected:
        preview = ", ".join(report.rejected[:8])
        err.print(Text(f"Rejected paths: {preview}", style="warn"))
    if verbose:
        for name in report.added[:40]:
            err.print(Text(f"added {name}", style="ok"))
        if len(report.added) > 40:
            err.print(Text(f"... {len(report.added) - 40} more added", style="muted"))
    elif report.added or report.replaced:
        err.print(Text("Pass --verbose to list every file.", style="muted"))
