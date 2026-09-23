"""Command-line interface for FastVPN."""

from __future__ import annotations

import argparse
import getpass
import os
import random
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.prompt import Confirm, IntPrompt, Prompt
from rich.text import Text
from rich_argparse import RawDescriptionRichHelpFormatter

from fastvpn import distribution_version
from fastvpn.catalog import (
    ServerFilter,
    describe_server,
    load_servers,
    read_profile,
    select_servers,
    summarize,
)
from fastvpn.connect import build_command, openvpn_binary, run_openvpn, use_sudo
from fastvpn.console import (
    emit_json,
    make_console,
    pin_scroll_below,
    print_error,
    query_cursor_row,
    render_mapping,
    render_output,
    render_report,
    reset_scroll_region,
)
from fastvpn.credentials import (
    CredentialRef,
    list_profiles,
    load_named,
    profile_path,
    remove_profile,
    resolve_credentials,
    write_active_profile,
    write_file,
)
from fastvpn.errors import FastVPNError
from fastvpn.fetch import SOURCES, fetch_url, import_any, materialize_ovpn, source_records
from fastvpn.models import AppPaths, Server
from fastvpn.paths import resolve_paths
from fastvpn.sessions import list_sessions, signal_command, terminate

SERVER_COLUMNS = [
    ("protocol", "Protocol"),
    ("country_code", "Code"),
    ("country", "Country"),
    ("city", "City"),
    ("virtual", "Virtual"),
    ("filename", "File"),
    ("source", "Source"),
]
COMMAND_ALIASES = {
    "ls": "list",
    "download": "fetch",
    "update": "fetch",
    "credentials": "creds",
    "down": "disconnect",
    "check": "doctor",
}
CRED_ALIASES = {"rm": "remove", "add": "set"}
EPILOG = """
examples:
  fastvpn
  fastvpn -t
  fastvpn -u -f "NCVPN-US-New York-UDP.ovpn"
  fastvpn connect --country US --city Miami --protocol tcp
  fastvpn list --country de --format json
  fastvpn list --summary
  fastvpn search london
  fastvpn fetch
  fastvpn fetch --source tcp
  fastvpn fetch --url https://vpn.ncapi.io/groupedServerList.zip
  fastvpn import ./servers.zip
  fastvpn creds set --username alice
  fastvpn doctor
  fastvpn disconnect
"""


class HelpFormatter(RawDescriptionRichHelpFormatter):
    styles = {
        "argparse.args": "cyan",
        "argparse.groups": "bold green",
        "argparse.help": "default",
        "argparse.metavar": "yellow",
        "argparse.syntax": "bold",
        "argparse.text": "default",
        "argparse.prog": "bold cyan",
        "argparse.default": "dim",
    }


@dataclass
class Context:
    out: Any
    err: Any
    format: str
    verbose: bool
    quiet: bool
    dry_run: bool
    paths: AppPaths


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if "--no-color" in args_list or os.environ.get("NO_COLOR"):
        os.environ["NO_COLOR"] = "1"
    parser = build_parser()
    try:
        args = parser.parse_args(args_list)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 0
    try:
        return dispatch(parser, args)
    except FastVPNError as exc:
        print_error(make_console(sys.stderr, no_color=bool(os.environ.get("NO_COLOR"))), str(exc))
        return exc.code
    except KeyboardInterrupt:
        print_error(make_console(sys.stderr, no_color=bool(os.environ.get("NO_COLOR"))), "Interrupted.")
        return 130
    except BrokenPipeError:
        return 0


def build_parser() -> argparse.ArgumentParser:
    shared = _shared_parser()
    auth = _auth_parser()
    parser = argparse.ArgumentParser(
        prog="fastvpn",
        description=(
            "Find, download, and connect OpenVPN profiles. "
            "Profiles live in tcp/ and udp/. Credentials stay in a two-line file "
            "or a named profile and are never printed."
        ),
        epilog=EPILOG,
        formatter_class=HelpFormatter,
        parents=[shared, auth],
    )
    parser.add_argument("--version", action="version", version=f"fastvpn {distribution_version()}")
    parser.add_argument("-t", "--tcp", action="store_true", help="Connect to a random TCP profile")
    parser.add_argument("-u", "--udp", action="store_true", help="Connect to a random UDP profile")
    parser.add_argument("-f", "--file", help="Connect using a profile name, local path, or http(s) URL")
    commands = parser.add_subparsers(title="commands", dest="command", metavar="COMMAND")

    connect = _add_command(commands, "connect", "Connect to a matching profile", parents=[shared, auth])
    connect.add_argument("--protocol", "-p", choices=("tcp", "udp", "any"), default="tcp", help="Protocol. Default: tcp")
    connect.add_argument(
        "--file",
        "-f",
        default=argparse.SUPPRESS,
        help="Profile name, local .ovpn path, or http(s) URL",
    )
    _add_location_filters(connect)
    selection = connect.add_mutually_exclusive_group()
    selection.add_argument("--random", action="store_true", help="Choose randomly when several profiles match")
    selection.add_argument("--first", action="store_true", help="Choose the first profile after sorting")
    selection.add_argument("--pick", action="store_true", help="Choose from a numbered list")
    connect.add_argument("--openvpn", help="Path to the openvpn binary")
    sudo_flags = connect.add_mutually_exclusive_group()
    sudo_flags.add_argument("--sudo", action="store_true", help="Run OpenVPN through sudo")
    sudo_flags.add_argument("--no-sudo", action="store_true", help="Run OpenVPN directly")
    connect.add_argument("--ovpn-arg", action="append", default=None, metavar="ARG", help="Extra OpenVPN argument. Repeatable")

    listing = _add_command(commands, "list", "List installed profiles", aliases=["ls"], parents=[shared])
    listing.add_argument("query_pos", nargs="?", metavar="QUERY", help="Free-text filter")
    listing.add_argument("--protocol", "-p", choices=("tcp", "udp", "any"), help="Protocol to include")
    _add_location_filters(listing)
    listing.add_argument("--summary", action="store_true", help="Show a count per country")
    listing.add_argument("--details", action="store_true", help="Read each file and include remote counts")
    listing.add_argument("--limit", type=int, default=0, help="Maximum rows. 0 lists everything")

    search = _add_command(commands, "search", "Search profiles by city, country, or filename", parents=[shared])
    search.add_argument("query", help="Text to match")
    search.add_argument("--protocol", "-p", choices=("tcp", "udp", "any"), help="Protocol to include")
    _add_location_filters(search)
    search.add_argument("--details", action="store_true", help="Include remote counts")
    search.add_argument("--limit", type=int, default=0, help="Maximum rows. 0 lists everything")

    show = _add_command(commands, "show", "Show one profile and its remote hosts", parents=[shared])
    show.add_argument("server", help="Exact filename or .ovpn path. Other text prints close matches")

    fetch = _add_command(
        commands,
        "fetch",
        "Download a server list and install its .ovpn files",
        aliases=["download", "update"],
        parents=[shared],
    )
    fetch.add_argument("--source", choices=tuple(SOURCES), help="Built-in list. Default: grouped")
    fetch.add_argument("--url", help="Zip or .ovpn URL. Overrides --source")
    fetch.add_argument("--dest", type=Path, help="Directory that should contain tcp/ and udp/")
    fetch.add_argument("--force", action="store_true", help="Replace profiles that already exist")
    fetch.add_argument("--list-sources", action="store_true", help="Print the built-in download URLs")

    importer = _add_command(commands, "import", "Import a local .ovpn file, directory, or zip", parents=[shared])
    importer.add_argument("path", type=Path, help="File, directory, or zip archive")
    importer.add_argument("--dest", type=Path, help="Directory that should contain tcp/ and udp/")
    importer.add_argument("--force", action="store_true", help="Replace profiles that already exist")

    creds = _add_command(
        commands,
        "creds",
        "Manage username/password profiles",
        aliases=["credentials"],
        parents=[shared],
    )
    cred_commands = creds.add_subparsers(title="credential commands", dest="creds_command", metavar="ACTION")
    _add_command(cred_commands, "list", "List credential profiles", parents=[shared])
    cred_show = _add_command(cred_commands, "show", "Show the active credentials without the password", parents=[shared])
    cred_show.add_argument("--profile", default=argparse.SUPPRESS, help="Profile to inspect")
    cred_set = _add_command(cred_commands, "set", "Save a username and password", aliases=["add"], parents=[shared])
    cred_set.add_argument("--profile", default=argparse.SUPPRESS, help="Profile name. Default: default")
    cred_set.add_argument("--username", help="Username. Prompt when omitted")
    cred_set.add_argument("--password-stdin", action="store_true", help="Read the password from stdin")
    cred_set.add_argument("--project", action="store_true", help="Write credentials.txt in the project root")
    cred_use = _add_command(cred_commands, "use", "Select the profile used for new connections", parents=[shared])
    cred_use.add_argument("profile_name", help="Profile name, or 'project' for credentials.txt")
    cred_remove = _add_command(cred_commands, "remove", "Delete a credential profile", aliases=["rm"], parents=[shared])
    cred_remove.add_argument("profile_name", help="Profile name, or 'project'")
    cred_remove.add_argument("--yes", action="store_true", help="Delete without a confirmation prompt")
    _add_command(cred_commands, "lock", "Set the active credentials file to mode 600", parents=[shared])

    _add_command(commands, "status", "Show OpenVPN processes started on this machine", parents=[shared])
    disconnect = _add_command(
        commands,
        "disconnect",
        "Stop running OpenVPN sessions",
        aliases=["down"],
        parents=[shared],
    )
    disconnect.add_argument("--yes", action="store_true", help="Stop sessions without a confirmation prompt")
    disconnect.add_argument("--force", action="store_true", help="Send SIGKILL instead of SIGTERM")
    disconnect.add_argument("--no-sudo", action="store_true", help="Signal the process without sudo")

    _add_command(commands, "doctor", "Check OpenVPN, profiles, and credentials", aliases=["check"], parents=[shared])
    _add_command(commands, "paths", "Show the directories FastVPN is using", parents=[shared])
    _add_command(commands, "version", "Print the FastVPN version", parents=[shared])
    help_command = _add_command(commands, "help", "Show help for a command", parents=[shared])
    help_command.add_argument("topic", nargs="?", help="Command name")
    return parser


def _shared_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--format",
        choices=("table", "json", "plain", "csv"),
        default=argparse.SUPPRESS,
        help="Output format: table, json, plain, or csv",
    )
    parser.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS, help="Disable color")
    parser.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS, help="Show extra detail")
    parser.add_argument("-q", "--quiet", action="store_true", default=argparse.SUPPRESS, help="Hide hints and progress")
    parser.add_argument("--root", type=Path, default=argparse.SUPPRESS, help="Project root that contains tcp/ and udp/")
    parser.add_argument(
        "--config-dir",
        action="append",
        type=Path,
        default=argparse.SUPPRESS,
        metavar="DIR",
        help="Extra profile directory. Repeatable",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Print the action without connecting, downloading, or stopping processes",
    )
    return parser


def _auth_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--credentials", type=Path, default=argparse.SUPPRESS, help="Two-line username/password file")
    parser.add_argument("--profile", default=argparse.SUPPRESS, help="Named credential profile")
    parser.add_argument(
        "--no-auth",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Do not pass an auth file. OpenVPN prompts instead",
    )
    return parser


def _add_location_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--country", "-c", action="append", default=None, metavar="COUNTRY", help="Country name or code. Repeatable")
    parser.add_argument("--city", action="append", default=None, metavar="CITY", help="City substring. Repeatable")
    parser.add_argument("--query", "-Q", help="Match filename, city, country, or the word virtual")


def _add_command(
    commands: argparse._SubParsersAction,  # type: ignore[type-arg]
    name: str,
    help_text: str,
    *,
    aliases: list[str] | tuple[str, ...] = (),
    parents: list[argparse.ArgumentParser] | None = None,
) -> argparse.ArgumentParser:
    return commands.add_parser(
        name,
        help=help_text,
        description=help_text,
        aliases=list(aliases),
        parents=parents or [],
        formatter_class=HelpFormatter,
    )


def dispatch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    command = COMMAND_ALIASES.get(args.command, args.command)
    if command == "help":
        return help_command(parser, getattr(args, "topic", None))
    ctx = make_context(args)
    if command and (args.tcp or args.udp or args.file):
        raise FastVPNError("Use a shortcut or a subcommand. Examples: fastvpn -t    fastvpn connect --country US")
    if command is None:
        if args.tcp and args.udp:
            raise FastVPNError("Choose either --tcp or --udp.")
        if args.tcp or args.udp or args.file:
            protocol = "tcp" if args.tcp else "udp" if args.udp else "any"
            return connect_command(
                ctx,
                protocol=protocol,
                file=args.file,
                countries=None,
                cities=None,
                query=None,
                mode="auto" if args.file else "random",
                credentials=_opt(args, "credentials"),
                profile=_opt(args, "profile"),
                no_auth=bool(_opt(args, "no_auth", False)),
                openvpn=None,
                sudo=False,
                no_sudo=False,
                ovpn_args=None,
            )
        return home_command(ctx)

    handlers = {
        "connect": lambda: connect_command(
            ctx,
            protocol=args.protocol,
            file=args.file,
            countries=args.country,
            cities=args.city,
            query=args.query,
            mode=_selection_mode(args),
            credentials=_opt(args, "credentials"),
            profile=_opt(args, "profile"),
            no_auth=bool(_opt(args, "no_auth", False)),
            openvpn=args.openvpn,
            sudo=args.sudo,
            no_sudo=args.no_sudo,
            ovpn_args=args.ovpn_arg,
        ),
        "list": lambda: list_command(
            ctx,
            protocol=args.protocol,
            countries=args.country,
            cities=args.city,
            query=_one_query(args.query, args.query_pos),
            summary=args.summary,
            details=args.details,
            limit=args.limit,
        ),
        "search": lambda: list_command(
            ctx,
            protocol=args.protocol,
            countries=args.country,
            cities=args.city,
            query=args.query,
            summary=False,
            details=args.details,
            limit=args.limit,
        ),
        "show": lambda: show_command(ctx, args.server),
        "fetch": lambda: fetch_command(ctx, args),
        "import": lambda: import_command(ctx, args.path, args.dest, args.force),
        "creds": lambda: creds_command(ctx, args),
        "status": lambda: status_command(ctx),
        "disconnect": lambda: disconnect_command(ctx, yes=args.yes, force=args.force, no_sudo=args.no_sudo),
        "doctor": lambda: doctor_command(ctx),
        "paths": lambda: paths_command(ctx),
        "version": lambda: version_command(ctx),
    }
    handler = handlers.get(command)
    if handler is None:
        raise FastVPNError(f"Unknown command '{args.command}'. Run fastvpn --help.")
    return handler()


def make_context(args: argparse.Namespace) -> Context:
    quiet = bool(_opt(args, "quiet", False))
    verbose = bool(_opt(args, "verbose", False))
    if quiet and verbose:
        raise FastVPNError("Choose either --quiet or --verbose.")
    no_color = bool(_opt(args, "no_color", False) or os.environ.get("NO_COLOR"))
    return Context(
        out=make_console(sys.stdout, no_color=no_color),
        err=make_console(sys.stderr, no_color=no_color),
        format=str(_opt(args, "format", "table")),
        verbose=verbose,
        quiet=quiet,
        dry_run=bool(_opt(args, "dry_run", False)),
        paths=resolve_paths(_opt(args, "root"), _opt(args, "config_dir") or []),
    )


def _opt(args: argparse.Namespace, name: str, default: Any = None) -> Any:
    return getattr(args, name, default)


def _one_query(flag: str | None, positional: str | None) -> str | None:
    if flag and positional and flag != positional:
        raise FastVPNError("Pass the search text once, either as an argument or with --query.")
    return flag or positional


def _selection_mode(args: argparse.Namespace) -> str:
    if args.random:
        return "random"
    if args.first:
        return "first"
    if args.pick:
        return "pick"
    narrowed = bool(args.file or args.country or args.city or args.query)
    return "auto" if narrowed else "random"


def help_command(parser: argparse.ArgumentParser, topic: str | None) -> int:
    if not topic:
        parser.print_help()
        return 0
    canonical = COMMAND_ALIASES.get(topic, topic)
    try:
        parser.parse_args([canonical, "--help"])
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 0
    return 0


def home_command(ctx: Context) -> int:
    report = environment_report(ctx)
    if ctx.format == "json":
        emit_json(report)
        return 0
    if ctx.format in {"csv", "plain"}:
        records = [
            {"item": "openvpn", "value": report["openvpn"] or ""},
            {"item": "tcp", "value": report["tcp"]},
            {"item": "udp", "value": report["udp"]},
            {"item": "countries", "value": report["countries"]},
            {"item": "root", "value": report["root"]},
            {"item": "credentials", "value": _credential_line(report)},
        ]
        render_output(
            ctx.out,
            ctx.err,
            ctx.format,
            records,
            [("item", "Item"), ("value", "Value")],
            title="FastVPN",
            empty_message="FastVPN",
            json_payload=report,
        )
        return 0
    render_mapping(
        ctx.out,
        f"FastVPN {report['version']}",
        [
            ("OpenVPN", report["openvpn"] or "not installed"),
            ("Profiles", f"{report['tcp']} TCP, {report['udp']} UDP, {report['countries']} countries"),
            ("Root", str(report["root"])),
            ("Credentials", _credential_line(report)),
        ],
    )
    if not ctx.quiet:
        ctx.err.print(Text("Connect:  fastvpn -t    or    fastvpn connect --country US --city Miami", style="muted"))
        ctx.err.print(Text("Profiles: fastvpn list    fastvpn fetch    fastvpn import PATH", style="muted"))
    return 0


def list_command(
    ctx: Context,
    *,
    protocol: str | None,
    countries: list[str] | None,
    cities: list[str] | None,
    query: str | None,
    summary: bool,
    details: bool,
    limit: int,
) -> int:
    if limit < 0:
        raise FastVPNError("--limit must be zero or greater.")
    servers = select_servers(
        load_servers(ctx.paths),
        ServerFilter(
            protocol=protocol,
            countries=tuple(countries or ()),
            cities=tuple(cities or ()),
            query=query,
        ),
    )
    matched = len(servers)
    if summary:
        records = summarize(servers)
        if limit:
            records = records[:limit]
        payload = {"matched": matched, "count": len(records), "countries": records}
        columns = [
            ("country_code", "Code"),
            ("country", "Country"),
            ("tcp", "TCP"),
            ("udp", "UDP"),
            ("total", "Total"),
        ]
        render_output(
            ctx.out,
            ctx.err,
            ctx.format,
            records,
            columns,
            title="Countries",
            empty_message="No profiles matched. Download the public lists with: fastvpn fetch",
            json_payload=payload,
        )
        return 0
    if limit:
        servers = servers[:limit]
    records = [server.to_dict() for server in servers]
    if details:
        for record, server in zip(records, servers, strict=True):
            record["remote_count"] = read_profile(server.path)["remote_count"]
    if ctx.format == "table":
        view, columns = _server_table(records)
    else:
        view = records
        columns = [*SERVER_COLUMNS, ("path", "Path")]
        if details:
            columns.append(("remote_count", "Remotes"))
    if details and ctx.format == "table":
        columns.append(("remote_count", "Remotes"))
    render_output(
        ctx.out,
        ctx.err,
        ctx.format,
        view,
        columns,
        title="Profiles",
        empty_message="No profiles matched. Download the public lists with: fastvpn fetch",
        json_payload={"matched": matched, "count": len(records), "servers": records},
    )
    return 0


def _server_table(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    view: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        if item.get("virtual"):
            city = item.get("city")
            item["city"] = f"{city} · virtual" if city else "virtual"
        view.append(item)
    columns = [
        ("protocol", "Protocol"),
        ("country_code", "Code"),
        ("country", "Country"),
        ("city", "City"),
        ("filename", "File"),
    ]
    if len({str(record.get("source")) for record in records}) > 1:
        columns.append(("source", "Source"))
    return view, columns


def show_command(ctx: Context, value: str) -> int:
    server = resolve_server(ctx, value, protocol=None)
    profile = read_profile(server.path)
    payload = {"server": server.to_dict(), "profile": profile}
    if ctx.format == "json":
        emit_json(payload)
        return 0
    if ctx.format in {"csv", "plain"}:
        record = server.to_dict()
        record["remote_count"] = profile["remote_count"]
        columns = [*SERVER_COLUMNS, ("path", "Path"), ("remote_count", "Remotes")]
        render_output(
            ctx.out,
            ctx.err,
            ctx.format,
            [record],
            columns,
            title="Profile",
            empty_message="Profile",
            json_payload=payload,
        )
        return 0
    location = ", ".join(part for part in (server.city, server.country) if part) or "Unknown location"
    render_mapping(
        ctx.out,
        server.filename,
        [
            ("Protocol", server.protocol.upper()),
            ("Location", location),
            ("Virtual", "yes" if server.virtual else "no"),
            ("Path", str(server.path)),
            ("Source", server.source),
            ("Remotes", str(profile["remote_count"])),
            ("Random remote", "yes" if profile["remote_random"] else "no"),
            ("Auth directive", "yes" if profile["auth_user_pass"] else "no"),
        ],
    )
    remotes = list(profile["remotes"])
    assert isinstance(remotes, list)
    preview = remotes[:15]
    if preview:
        render_output(
            ctx.out,
            ctx.err,
            "table",
            preview,
            [("host", "Host"), ("port", "Port")],
            title="Remote hosts",
            empty_message="No remote hosts",
            json_payload=payload,
        )
        if len(remotes) > len(preview) and not ctx.quiet:
            ctx.err.print(Text(f"{len(remotes) - len(preview)} more hosts are included in --format json.", style="muted"))
    return 0


def connect_command(
    ctx: Context,
    *,
    protocol: str,
    file: str | None,
    countries: list[str] | None,
    cities: list[str] | None,
    query: str | None,
    mode: str,
    credentials: Path | None,
    profile: str | None,
    no_auth: bool,
    openvpn: str | None,
    sudo: bool,
    no_sudo: bool,
    ovpn_args: list[str] | None,
) -> int:
    if file:
        server = resolve_server(ctx, file, protocol=protocol)
    else:
        servers = select_servers(
            load_servers(ctx.paths),
            ServerFilter(
                protocol=protocol,
                countries=tuple(countries or ()),
                cities=tuple(cities or ()),
                query=query,
            ),
        )
        server = choose_server(ctx, servers, mode)
    credentials_ref = resolve_credentials(
        ctx.paths,
        explicit=credentials,
        profile=profile,
        no_auth=no_auth,
        materialize_env=not ctx.dry_run,
    )
    if credentials_ref and credentials_ref.path.exists():
        info = credentials_ref.public()
        if not info["private"] and not ctx.quiet:
            ctx.err.print(
                Text(
                    f"Credentials are readable by other users ({credentials_ref.path}). Run: fastvpn creds lock",
                    style="warn",
                )
            )
    binary = openvpn if ctx.dry_run and openvpn else None
    if binary is None and ctx.dry_run:
        binary = shutil.which("openvpn") or "openvpn"
    if binary is None:
        binary = openvpn_binary(openvpn)
    auth_file = _auth_path(credentials_ref, dry_run=ctx.dry_run)
    command = build_command(
        binary=binary,
        config=server.path,
        auth_file=auth_file,
        use_sudo_flag=use_sudo(requested=sudo, disabled=no_sudo),
        extra=ovpn_args,
    )
    payload = {
        "dry_run": ctx.dry_run,
        "server": server.to_dict(),
        "credentials": _public_credentials(credentials_ref),
        "command": command,
    }
    if ctx.format == "json":
        emit_json(payload)
    elif ctx.quiet:
        ctx.err.print(Text(f"Connecting {server.protocol.upper()} {server.filename}"))
    else:
        location = ", ".join(part for part in (server.city, server.country) if part) or "Unknown location"
        auth = "OpenVPN will prompt"
        if credentials_ref is not None:
            auth = f"{credentials_ref.username} ({credentials_ref.source})"
        render_mapping(
            ctx.out,
            "Connecting",
            [
                ("Protocol", server.protocol.upper()),
                ("Location", location),
                ("Virtual", "yes" if server.virtual else "no"),
                ("File", server.filename),
                ("Path", str(server.path)),
                ("Auth", auth),
            ],
            border=server.protocol if server.protocol in {"tcp", "udp"} else "cyan",
        )
        ctx.err.print(Text(shlex.join(command), style="muted"))
    if ctx.dry_run:
        return 0
    if not ctx.quiet and ctx.format != "json":
        ctx.err.print(Text("OpenVPN stays in this terminal. Press Ctrl+C to disconnect.", style="muted"))
    pinned = False
    if not ctx.quiet and ctx.format == "table":
        ctx.out.file.flush()
        ctx.err.file.flush()
        row = query_cursor_row()
        if row is not None:
            pinned = pin_scroll_below(row)
    try:
        code = run_openvpn(command, credentials_ref)
    finally:
        if pinned:
            reset_scroll_region()
    if code != 0 and not ctx.quiet:
        ctx.err.print(Text(f"OpenVPN exited with status {code}.", style="warn"))
    return code


def fetch_command(ctx: Context, args: argparse.Namespace) -> int:
    if args.list_sources:
        if args.url or args.source:
            raise FastVPNError("--list-sources prints the built-in URLs and does not download them.")
        records = source_records()
        render_output(
            ctx.out,
            ctx.err,
            ctx.format,
            records,
            [("name", "Source"), ("url", "URL")],
            title="Server lists",
            empty_message="No built-in sources.",
            json_payload={"sources": records},
        )
        return 0
    if args.url and args.source:
        raise FastVPNError("Pass either --source or --url.")
    source = args.source
    url = args.url
    if url is None:
        source = source or "grouped"
        url = SOURCES[source]
        if not ctx.quiet and ctx.format == "table":
            ctx.err.print(Text(f"Using the {source} server list.", style="muted"))
    dest = args.dest.expanduser().resolve() if args.dest else ctx.paths.primary_root
    if not ctx.quiet and ctx.format == "table":
        ctx.err.print(Text(f"Source  {url}", style="title"))
        ctx.err.print(Text(f"Install {dest}", style="muted"))
    if ctx.dry_run:
        payload = {"dry_run": True, "url": url, "destination": str(dest), "force": args.force}
        if ctx.format == "json":
            emit_json(payload)
        elif not ctx.quiet:
            ctx.err.print(Text("Dry run: nothing was downloaded.", style="muted"))
        return 0
    report = fetch_url(
        url,
        dest,
        force=args.force,
        console=ctx.err,
        dry_run=False,
        show_progress=ctx.format == "table" and not ctx.quiet,
    )
    if report is None:
        return 0
    if not (report.added or report.replaced or report.skipped):
        render_report(ctx.out, ctx.err, ctx.format, report, verbose=ctx.verbose)
        raise FastVPNError(f"No .ovpn profiles were found at {url}")
    render_report(ctx.out, ctx.err, ctx.format, report, verbose=ctx.verbose)
    return 0


def import_command(ctx: Context, path: Path, dest: Path | None, force: bool) -> int:
    source = path.expanduser().resolve()
    destination = dest.expanduser().resolve() if dest else ctx.paths.primary_root
    if ctx.dry_run:
        payload = {"dry_run": True, "source": str(source), "destination": str(destination), "force": force}
        if ctx.format == "json":
            emit_json(payload)
        else:
            ctx.err.print(Text(f"Would import {source} into {destination}", style="muted"))
        return 0
    if not ctx.quiet and ctx.format == "table":
        ctx.err.print(Text(f"Importing {source}", style="title"))
        ctx.err.print(Text(f"Into {destination}", style="muted"))
    destination.mkdir(parents=True, exist_ok=True)
    report = import_any(source, destination, force=force)
    if not (report.added or report.replaced or report.skipped):
        render_report(ctx.out, ctx.err, ctx.format, report, verbose=ctx.verbose)
        raise FastVPNError(f"No .ovpn profiles were imported from {source}")
    render_report(ctx.out, ctx.err, ctx.format, report, verbose=ctx.verbose)
    return 0


def creds_command(ctx: Context, args: argparse.Namespace) -> int:
    action = CRED_ALIASES.get(args.creds_command, args.creds_command) or "list"
    if action == "list":
        return creds_list(ctx)
    if action == "show":
        return creds_show(ctx, _opt(args, "profile"))
    if action == "set":
        if args.project and _opt(args, "profile"):
            raise FastVPNError("Use either --project or --profile.")
        name = "project" if args.project else str(_opt(args, "profile", "default"))
        return creds_set(ctx, name=name, username=args.username, password_stdin=args.password_stdin)
    if action == "use":
        return creds_use(ctx, args.profile_name)
    if action == "remove":
        return creds_remove(ctx, args.profile_name, yes=args.yes)
    if action == "lock":
        return creds_lock(ctx)
    raise FastVPNError(f"Unknown credential action '{args.creds_command}'. Run fastvpn creds --help.")


def creds_list(ctx: Context) -> int:
    records = list_profiles(ctx.paths)
    render_output(
        ctx.out,
        ctx.err,
        ctx.format,
        records,
        [
            ("profile", "Profile"),
            ("username", "Username"),
            ("active", "Active"),
            ("permissions", "Mode"),
            ("path", "Path"),
        ],
        title="Credentials",
        empty_message="No credential profiles yet. Create one with: fastvpn creds set --username NAME",
        json_payload={"profiles": records},
    )
    return 0


def creds_show(ctx: Context, profile: str | None) -> int:
    if profile:
        ref = load_named(ctx.paths, profile, required=True)
    else:
        ref = resolve_credentials(
            ctx.paths,
            explicit=None,
            profile=None,
            no_auth=False,
            materialize_env=False,
        )
    if ref is None:
        raise FastVPNError("No credentials are configured. Create some with: fastvpn creds set --username NAME")
    payload = _public_credentials(ref)
    if ctx.format == "json":
        emit_json(payload)
        return 0
    if ctx.format in {"csv", "plain"}:
        render_output(
            ctx.out,
            ctx.err,
            ctx.format,
            [payload or {}],
            [("source", "Source"), ("profile", "Profile"), ("username", "Username"), ("path", "Path"), ("permissions", "Mode")],
            title="Credentials",
            empty_message="No credentials",
            json_payload=payload or {},
        )
        return 0
    assert payload is not None
    render_mapping(
        ctx.out,
        "Credentials",
        [
            ("Source", str(payload["source"])),
            ("Profile", str(payload["profile"] or "")),
            ("Username", str(payload["username"])),
            ("Path", str(payload["path"] or "")),
            ("Mode", str(payload["permissions"] or "")),
        ],
    )
    return 0


def creds_set(ctx: Context, *, name: str, username: str | None, password_stdin: bool) -> int:
    if password_stdin and not username:
        raise FastVPNError("Pass --username together with --password-stdin.")
    resolved_username = _prompt_username(ctx, username)
    password = _prompt_password(password_stdin)
    path = profile_path(ctx.paths, name)
    if ctx.dry_run:
        ctx.err.print(Text(f"Would write profile {name} to {path}", style="muted"))
        return 0
    write_file(path, resolved_username, password)
    write_active_profile(ctx.paths, name)
    if ctx.format == "json":
        emit_json({"profile": name, "path": str(path), "username": resolved_username, "active": True})
    else:
        ctx.err.print(Text(f"Saved profile {name} for {resolved_username}. It is now the active profile.", style="ok"))
    return 0


def creds_use(ctx: Context, name: str) -> int:
    load_named(ctx.paths, name, required=True)
    if not ctx.dry_run:
        write_active_profile(ctx.paths, name)
    payload = {"profile": name, "active": True, "dry_run": ctx.dry_run}
    if ctx.format == "json":
        emit_json(payload)
    else:
        verb = "Would activate" if ctx.dry_run else "Active profile"
        ctx.err.print(Text(f"{verb}: {name}", style="ok"))
    return 0


def creds_remove(ctx: Context, name: str, *, yes: bool) -> int:
    path = profile_path(ctx.paths, name)
    if not path.is_file():
        raise FastVPNError(f"Credential profile '{name}' was not found.")
    if ctx.dry_run:
        ctx.err.print(Text(f"Would delete {path}", style="muted"))
        return 0
    if not yes:
        if not sys.stderr.isatty():
            raise FastVPNError("Pass --yes to delete a credential profile.")
        if not Confirm.ask(f"Delete credential profile {name}?", console=ctx.err, default=False):
            ctx.err.print(Text("Kept the profile.", style="muted"))
            return 0
    remove_profile(ctx.paths, name)
    ctx.err.print(Text(f"Deleted credential profile {name}.", style="ok"))
    return 0


def creds_lock(ctx: Context) -> int:
    ref = resolve_credentials(ctx.paths, explicit=None, profile=None, no_auth=False, materialize_env=False)
    if ref is None:
        raise FastVPNError("No credentials are configured.")
    if ref.source == "environment":
        raise FastVPNError("Environment credentials are not stored in a file.")
    if ctx.dry_run:
        ctx.err.print(Text(f"Would set mode 600 on {ref.path}", style="muted"))
        return 0
    os.chmod(ref.path, 0o600)
    ctx.err.print(Text(f"Restricted {ref.path} to mode 600.", style="ok"))
    return 0


def status_command(ctx: Context) -> int:
    sessions = list_sessions()
    render_output(
        ctx.out,
        ctx.err,
        ctx.format,
        sessions,
        [("pid", "PID"), ("config", "Config"), ("command", "Command")],
        title="OpenVPN",
        empty_message="OpenVPN is not running.",
        json_payload={"count": len(sessions), "sessions": sessions},
    )
    return 0


def disconnect_command(ctx: Context, *, yes: bool, force: bool, no_sudo: bool) -> int:
    sessions = list_sessions()
    if not sessions:
        raise FastVPNError("No OpenVPN session is running.")
    pids = [int(session["pid"]) for session in sessions]
    command = signal_command(pids, force=force, sudo=not no_sudo)
    if ctx.format == "json":
        emit_json({"dry_run": ctx.dry_run, "sessions": sessions, "command": command})
    else:
        render_output(
            ctx.out,
            ctx.err,
            "table" if ctx.format == "table" else ctx.format,
            sessions,
            [("pid", "PID"), ("config", "Config"), ("command", "Command")],
            title="OpenVPN",
            empty_message="OpenVPN is not running.",
            json_payload={"sessions": sessions},
        )
        ctx.err.print(Text(shlex.join(command), style="muted"))
    if ctx.dry_run:
        return 0
    if not yes:
        if not sys.stderr.isatty():
            raise FastVPNError("Pass --yes to disconnect when there is no terminal.")
        if not Confirm.ask(f"Disconnect {len(sessions)} OpenVPN session(s)?", console=ctx.err, default=False):
            ctx.err.print(Text("Left the sessions running.", style="muted"))
            return 0
    terminate(pids, force=force, sudo=not no_sudo)
    ctx.err.print(Text("Disconnect requested.", style="ok"))
    return 0


def doctor_command(ctx: Context) -> int:
    report = environment_report(ctx)
    checks = _doctor_checks(report)
    failed = any(check["status"] == "fail" for check in checks)
    payload = {"ok": not failed, "checks": checks}
    render_output(
        ctx.out,
        ctx.err,
        ctx.format,
        checks,
        [("name", "Check"), ("status", "Status"), ("detail", "Detail")],
        title="Doctor",
        empty_message="No checks ran.",
        json_payload=payload,
    )
    return 1 if failed else 0


def paths_command(ctx: Context) -> int:
    payload = {
        "primary_root": str(ctx.paths.primary_root),
        "scan_roots": [{"path": str(path), "label": label} for path, label in ctx.paths.scan_roots],
        "config_dir": str(ctx.paths.config_dir),
        "credentials_dir": str(ctx.paths.credentials_dir),
        "cache_dir": str(ctx.paths.cache_dir),
        "project_credentials": str(ctx.paths.project_credentials),
        "settings_file": str(ctx.paths.settings_file),
    }
    if ctx.format == "json":
        emit_json(payload)
        return 0
    records = []
    for key, value in payload.items():
        rendered = value if isinstance(value, str) else ", ".join(f"{item['label']}={item['path']}" for item in value)
        records.append({"item": key, "value": rendered})
    render_output(
        ctx.out,
        ctx.err,
        ctx.format,
        records,
        [("item", "Path"), ("value", "Location")],
        title="Paths",
        empty_message="No paths.",
        json_payload=payload,
    )
    return 0


def version_command(ctx: Context) -> int:
    payload = {"name": "fastvpn", "version": distribution_version()}
    if ctx.format == "json":
        emit_json(payload)
    else:
        ctx.out.print(f"fastvpn {payload['version']}")
    return 0


def environment_report(ctx: Context) -> dict[str, Any]:
    servers = load_servers(ctx.paths)
    credentials = None
    credentials_error = None
    try:
        ref = resolve_credentials(
            ctx.paths,
            explicit=None,
            profile=None,
            no_auth=False,
            materialize_env=False,
        )
        if ref is not None:
            credentials = _public_credentials(ref)
    except FastVPNError as exc:
        credentials_error = str(exc)
    return {
        "version": distribution_version(),
        "openvpn": shutil.which("openvpn"),
        "sudo": os.geteuid() == 0 or shutil.which("sudo") is not None,
        "root_user": os.geteuid() == 0,
        "tun": Path("/dev/net/tun").exists(),
        "root": str(ctx.paths.primary_root),
        "roots": [{"path": str(path), "label": label} for path, label in ctx.paths.scan_roots],
        "config_dir": str(ctx.paths.config_dir),
        "cache_dir": str(ctx.paths.cache_dir),
        "tcp": sum(1 for server in servers if server.protocol == "tcp"),
        "udp": sum(1 for server in servers if server.protocol == "udp"),
        "countries": len({server.country_code for server in servers if server.country_code}),
        "credentials": credentials,
        "credentials_error": credentials_error,
    }


def _doctor_checks(report: dict[str, Any]) -> list[dict[str, str]]:
    credentials = report["credentials"]
    if report["credentials_error"]:
        cred_status, cred_detail = "fail", str(report["credentials_error"])
    elif not isinstance(credentials, dict):
        cred_status = "warn"
        cred_detail = "No auth file. OpenVPN will prompt, or run: fastvpn creds set --username NAME"
    elif credentials.get("source") == "environment":
        cred_status = "ok"
        cred_detail = f"{credentials['username']} from the environment"
    elif not credentials.get("private", False):
        cred_status = "warn"
        cred_detail = (
            f"{credentials['username']} at {credentials['path']} is group or world readable. "
            "Run: fastvpn creds lock"
        )
    else:
        cred_status = "ok"
        cred_detail = f"{credentials['username']} at {credentials['path']}"
    total = int(report["tcp"]) + int(report["udp"])
    return [
        {
            "name": "OpenVPN",
            "status": "ok" if report["openvpn"] else "fail",
            "detail": str(report["openvpn"] or "Install openvpn and make sure it is on PATH"),
        },
        {
            "name": "Privileges",
            "status": "ok" if report["sudo"] else "warn",
            "detail": "root" if report["root_user"] else ("sudo available" if report["sudo"] else "sudo was not found"),
        },
        {
            "name": "TUN",
            "status": "ok" if report["tun"] else "warn",
            "detail": "/dev/net/tun" if report["tun"] else "/dev/net/tun is missing",
        },
        {
            "name": "Profiles",
            "status": "ok" if total else "fail",
            "detail": f"{report['tcp']} TCP, {report['udp']} UDP in {report['root']}",
        },
        {"name": "Credentials", "status": cred_status, "detail": cred_detail},
    ]


def _credential_line(report: dict[str, Any]) -> str:
    if report["credentials_error"]:
        return str(report["credentials_error"])
    credentials = report["credentials"]
    if not isinstance(credentials, dict):
        return "not configured"
    return f"{credentials['username']} via {credentials['source']}"


def resolve_server(ctx: Context, value: str, protocol: str | None) -> Server:
    if value.startswith(("http://", "https://")):
        if ctx.dry_run:
            raise FastVPNError("Dry run does not download a remote profile. Pass a local file, or drop --dry-run.")
        if not ctx.quiet:
            ctx.err.print(Text(f"Downloading profile {value}", style="title"))
        path = materialize_ovpn(
            value,
            ctx.paths.cache_dir,
            console=ctx.err,
            show_progress=ctx.format == "table" and not ctx.quiet,
        )
        return describe_server(path, "remote", None)
    candidate = Path(value).expanduser()
    if candidate.is_file():
        if candidate.suffix.lower() != ".ovpn":
            raise FastVPNError(f"{candidate} is not an .ovpn file.")
        parent = candidate.parent.name.lower()
        parent_proto = parent if parent in {"tcp", "udp"} else None
        return describe_server(candidate.resolve(), "file", parent_proto)
    servers = load_servers(ctx.paths)
    exact = [server for server in servers if server.filename == candidate.name]
    if protocol and protocol != "any":
        scoped = [server for server in exact if server.protocol == protocol]
        if scoped:
            exact = scoped
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise FastVPNError("That name exists for more than one protocol. Pass --protocol tcp or --protocol udp.")
    needle = value.casefold()
    suggestions = [
        server.filename
        for server in servers
        if needle in server.filename.casefold() or needle in (server.city or "").casefold()
    ][:8]
    message = f"No configuration named '{value}'."
    if suggestions:
        message += " Close matches: " + ", ".join(suggestions)
    else:
        message += " Run fastvpn list to see what is installed."
    raise FastVPNError(message)


def choose_server(ctx: Context, servers: list[Server], mode: str) -> Server:
    if not servers:
        raise FastVPNError("No configuration matched. See what is installed with: fastvpn list")
    if len(servers) == 1:
        return servers[0]
    if mode == "random":
        return random.choice(servers)
    if mode == "first":
        return servers[0]
    if mode == "auto" and (ctx.format != "table" or not sys.stderr.isatty()):
        raise FastVPNError(
            f"{len(servers)} configurations matched. Narrow the filter, or pass --random or --first."
        )
    if mode == "auto":
        mode = "pick"
    if mode != "pick":
        raise FastVPNError(f"Unknown selection mode '{mode}'.")
    if len(servers) > 40:
        raise FastVPNError(f"{len(servers)} configurations matched. Refine the filter or pass --random.")
    records = []
    for index, server in enumerate(servers, start=1):
        record = server.to_dict()
        record["index"] = index
        records.append(record)
    view, columns = _server_table(records)
    for item, record in zip(view, records, strict=True):
        item["index"] = record["index"]
    render_output(
        ctx.err,
        ctx.err,
        "table",
        view,
        [("index", "#"), *columns],
        title="Matching profiles",
        empty_message="No profiles",
        json_payload={},
    )
    try:
        answer = IntPrompt.ask(
            "Select a server",
            choices=[str(index) for index in range(1, len(servers) + 1)],
            console=ctx.err,
        )
    except EOFError as exc:
        raise FastVPNError("No server was selected.") from exc
    return servers[int(answer) - 1]


def _prompt_username(ctx: Context, username: str | None) -> str:
    if username:
        if not username.strip():
            raise FastVPNError("Username is required.")
        return username.strip()
    if not sys.stdin.isatty():
        raise FastVPNError("Pass --username when stdin is not a terminal.")
    value = Prompt.ask("Username", console=ctx.err).strip()
    if not value:
        raise FastVPNError("Username is required.")
    return value


def _prompt_password(password_stdin: bool) -> str:
    if password_stdin:
        line = sys.stdin.readline()
        if line.endswith("\n"):
            line = line[:-1]
        if line.endswith("\r"):
            line = line[:-1]
        if line == "":
            raise FastVPNError("Password from stdin was empty.")
        return line
    if not sys.stdin.isatty():
        raise FastVPNError("Pass --password-stdin when stdin is not a terminal.")
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise FastVPNError("Passwords did not match.")
    if first == "":
        raise FastVPNError("Password is required.")
    return first


def _auth_path(credentials: CredentialRef | None, *, dry_run: bool) -> Path | None:
    if credentials is None:
        return None
    if dry_run and credentials.source == "environment":
        return Path("<environment>")
    return credentials.path


def _public_credentials(credentials: CredentialRef | None) -> dict[str, object] | None:
    if credentials is None:
        return None
    if credentials.source == "environment":
        return {
            "source": "environment",
            "profile": None,
            "path": None,
            "username": credentials.username,
            "permissions": None,
            "private": True,
        }
    return credentials.public()
