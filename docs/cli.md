# FastVPN command reference

This page lists every command, the variations of each command, what the program does, and what it prints. Examples use the command name `fastvpn`. From a source checkout, run them as `uv run fastvpn ...`. `python main.py ...` accepts the same arguments.

Data goes to standard output. Hints, progress, prompts, and errors go to standard error. `--format json` is safe to pipe. A password is never written to either stream.

## Exit codes

| Code | When |
| --- | --- |
| 0 | The command finished. `list` with zero matches is still 0. `--dry-run` is 0. |
| 1 | The request cannot be completed: missing profile, bad credentials file, both `--tcp` and `--udp`, doctor found a failing check, fetch or import found no `.ovpn` files, disconnect found no session. The reason is on stderr. |
| 2 | The arguments themselves are invalid. This is argparse, for example an unknown flag or `--random` together with `--first`. |
| 130 | You pressed Ctrl+C. The message is `Interrupted.` |
| OpenVPN's code | `connect` and the `-t`, `-u`, and `-f` shortcuts return the code OpenVPN exited with. |

A broken pipe, such as `fastvpn list | head`, exits 0.

## Global options

These options work before or after the subcommand. `fastvpn --format json list` and `fastvpn list --format json` are the same. `--quiet` and `--verbose` together exit 1.

| Option | Effect |
| --- | --- |
| `-h`, `--help` | Help for the current command, then exit 0. |
| `--version` | Print `fastvpn 1.0.0` and exit 0. |
| `--format table` | Color tables. This is the default. |
| `--format json` | Indented JSON on stdout. |
| `--format plain` | A header row, then tab-separated rows. |
| `--format csv` | A header row, then comma-separated rows. |
| `--no-color` | Disable color. `NO_COLOR` does the same when set to any value. |
| `-v`, `--verbose` | After `fetch` and `import`, list the files that were added. |
| `-q`, `--quiet` | Hide hints, the download progress bar, and the "OpenVPN stays in this terminal" line. Tables, JSON, and errors still appear. |
| `--root DIR` | Read and write profiles only in this directory, plus any `--config-dir`. |
| `--config-dir DIR` | Add another profile directory. Repeat the flag to add more than one. |
| `--dry-run` | Print the action and do not download, write credentials, start OpenVPN, or signal a process. |
| `--credentials FILE` | Use this two-line auth file for `connect` and the shortcuts. |
| `--profile NAME` | Use this named credential profile for `connect` and the shortcuts. |
| `--no-auth` | Do not pass an auth file. OpenVPN asks for a username and password itself. |

`--config-dir` may be a tree containing `tcp/` and `udp/`, or a flat folder of `.ovpn` files. When the same protocol and filename exist in more than one directory, the earliest directory wins. Repeatable `--config-dir` values are earliest, then the project or `--root`, then the user data directory.

## `fastvpn`

No subcommand and no shortcut.

FastVPN scans the profile directories and the credential configuration, then prints a panel:

- OpenVPN path, or `not installed`
- How many TCP profiles, UDP profiles, and countries were found
- The directory new profiles are written to
- The active username and where it came from, or `not configured`

It does not start a VPN. Exit 0 even when OpenVPN is missing or no profiles are installed. Hints on stderr point at `connect`, `list`, `fetch`, and `import`. `--quiet` hides those hints.

`--format json` prints the same facts as one object: `version`, `openvpn`, `sudo`, `root_user`, `tun`, `root`, `roots`, `config_dir`, `cache_dir`, `tcp`, `udp`, `countries`, `credentials`, `credentials_error`. The credentials object has `username`, `source`, `profile`, `path`, `permissions`, and `private`. It has no password field.

`--format csv` and `--format plain` print rows named `openvpn`, `tcp`, `udp`, `countries`, `root`, and `credentials`.

## Shortcuts

These are the original one-flag forms. They connect immediately. They cannot be combined with a subcommand (`fastvpn -t list` exits 1). `-t` and `-u` together exit 1.

| Command | What happens |
| --- | --- |
| `fastvpn -t` | Choose a random TCP profile and start OpenVPN. |
| `fastvpn --tcp` | Same as `-t`. |
| `fastvpn -u` | Choose a random UDP profile and start OpenVPN. |
| `fastvpn --udp` | Same as `-u`. |
| `fastvpn -f FILE` | Connect to that filename, path, or `http`/`https` URL. The protocol comes from the file. |
| `fastvpn -t -f FILE` | Look for that filename among TCP profiles, or use the path if it already exists. |
| `fastvpn -u -f FILE` | Same, limited to UDP when the argument is a filename. |
| `fastvpn -t --dry-run` | Print the OpenVPN command for a random TCP profile and exit 0. |

`FILE` can be:

- an exact name such as `NCVPN-US-New York-TCP.ovpn`
- a relative or absolute path ending in `.ovpn`
- an `http://` or `https://` URL of one `.ovpn` file

A URL is downloaded into the cache directory and then opened. `--dry-run` refuses to download and exits 1 with `Dry run does not download a remote profile`. A URL that points at a zip exits 1 and tells you to use `fastvpn fetch --url`.

If the name is missing, stderr lists up to eight close filename or city matches and the process exits 1.

The connection itself is the same as `fastvpn connect`. See that command for the panel, the argv, sudo, and credentials.

## `fastvpn connect`

Select one profile and start OpenVPN in the foreground.

```bash
fastvpn connect
fastvpn connect --protocol udp
fastvpn connect --protocol any --random
fastvpn connect --country US --city "New York" --protocol tcp
fastvpn connect --country gb --protocol udp
fastvpn connect -c US -c DE --city Miami
fastvpn connect --query virtual --pick
fastvpn connect --file "NCVPN-JP-Tokyo-UDP.ovpn"
fastvpn connect --file ./udp/NCVPN-JP-Tokyo-UDP.ovpn
fastvpn connect --file https://example.com/server.ovpn
fastvpn connect --first --country FR
fastvpn connect --dry-run --no-auth
fastvpn connect --credentials ./credentials.txt
fastvpn connect --profile travel
fastvpn connect --openvpn /usr/sbin/openvpn --no-sudo
fastvpn connect --ovpn-arg --mute --ovpn-arg 20
```

### How a profile is chosen

Default protocol is `tcp`. `--protocol any` searches both.

| How you called it | Selection |
| --- | --- |
| No file, country, city, or query | Random profile for the protocol. |
| `--random` | Random among the matches. |
| `--first` | First match after sorting by country, city, protocol, then filename. |
| `--pick` | Numbered list, then a prompt. |
| Filters, none of the three flags, and a terminal | Prompt when there are 2 to 40 matches. One match connects immediately. |
| Filters, and stdout is not a terminal, or the format is `json`, `csv`, or `plain` | Exit 1 and ask for `--random` or `--first`. |
| More than 40 matches in picker mode | Exit 1 and ask you to narrow the filter or pass `--random`. |
| `--file` is set | That file wins. Country, city, and query are ignored. |

`--random`, `--first`, and `--pick` are mutually exclusive.

Country filters are OR. City filters are OR. Country and city together mean both. A token of one to three letters must equal the country code (`US`, `de`, `uk`). `gb` matches `UK`, `usa` matches `US`, and `uae` matches `AE`. A longer token matches inside the country name, so `united` matches the United States, the United Kingdom, and the United Arab Emirates. A city token is a substring, so `new` matches New York and New Orleans. `--query` matches filename, city, country, code, protocol, source, and the word `virtual`.

Sort order is country, city, protocol, filename.

### What you see

For the default table format, stdout gets a Connecting panel: protocol, location, whether the profile is virtual, filename, path, and auth. Auth is `OpenVPN will prompt` or `username (source)`. Stderr gets the exact argument vector, quoted with shell rules so you can read paths that contain spaces, then `OpenVPN stays in this terminal. Press Ctrl+C to disconnect.`

OpenVPN's own log follows on the terminal. The process stays in the foreground until OpenVPN exits. Ctrl+C returns 130. Any other non-zero OpenVPN status is printed on stderr and returned as the exit code.

`--quiet` prints one stderr line, `Connecting TCP filename`, and skips the panel. `--format json` prints one object and then starts OpenVPN, so the JSON is followed by OpenVPN's log:

```json
{
  "dry_run": false,
  "server": {
    "protocol": "tcp",
    "country_code": "US",
    "country": "United States",
    "city": "New York",
    "virtual": false,
    "filename": "NCVPN-US-New York-TCP.ovpn",
    "path": "/absolute/path/tcp/NCVPN-US-New York-TCP.ovpn",
    "source": "project"
  },
  "credentials": {
    "source": "project",
    "profile": "project",
    "path": "/absolute/path/credentials.txt",
    "username": "alice",
    "permissions": "600",
    "private": true
  },
  "command": [
    "sudo",
    "openvpn",
    "--config",
    "/absolute/path/tcp/NCVPN-US-New York-TCP.ovpn",
    "--auth-user-pass",
    "/absolute/path/credentials.txt"
  ]
}
```

`--dry-run` prints that object or the panel and does not start OpenVPN. Environment credentials are shown as the argument `<environment>` and no temporary auth file is created.

### OpenVPN process

The command is built as a list. The shell is not involved.

| Situation | Command |
| --- | --- |
| Not root | `sudo openvpn --config PROFILE` |
| Already root, or `--no-sudo` | `openvpn --config PROFILE` |
| `--sudo` | Always prefix `sudo` |
| Credentials resolved | Append `--auth-user-pass FILE` |
| `--no-auth` or no credentials | Leave the auth file off. OpenVPN prompts. |
| `--ovpn-arg ARG` | Append each argument, in order, after the auth file. |

`--sudo` and `--no-sudo` are mutually exclusive. If sudo is required and `sudo` is not installed, the command exits 1 unless you pass `--no-sudo`. `--openvpn PATH` must be an executable file when this is a real connection. During `--dry-run`, a missing binary is shown as the word `openvpn`.

If the chosen auth file is readable by the group or by other users, stderr warns you to run `fastvpn creds lock`. The connection still starts.

## `fastvpn list`

Aliases: `ls`.

Print the installed profiles. Zero matches exit 0 and, for a table, print `No profiles matched. Download the public lists with: fastvpn fetch` on stderr.

```bash
fastvpn list
fastvpn ls
fastvpn list london
fastvpn list --query london
fastvpn list --protocol udp
fastvpn list -p tcp --country US
fastvpn list -c US -c CA --city York
fastvpn list --query virtual
fastvpn list --summary
fastvpn list --summary --limit 10
fastvpn list --details --country JP
fastvpn list --limit 5 --format json
fastvpn list --format csv
fastvpn list --format plain
```

Passing both a positional query and a different `--query` exits 1.

The table columns are Protocol, Code, Country, City, and File. A virtual profile shows `virtual` in the City column, or `St. Louis · virtual` when it also has a city. Source is a column only when the rows come from more than one directory. `--details` adds a Remotes column by reading each file up to the certificate block.

`csv` and `plain` always include Path, and Remotes when `--details` is set. Booleans are `yes` and `no`.

JSON:

```json
{
  "matched": 24,
  "count": 5,
  "servers": [
    {
      "protocol": "udp",
      "country_code": "JP",
      "country": "Japan",
      "city": "Tokyo",
      "virtual": false,
      "filename": "NCVPN-JP-Tokyo-UDP.ovpn",
      "path": "/absolute/path/udp/NCVPN-JP-Tokyo-UDP.ovpn",
      "source": "project",
      "remote_count": 64
    }
  ]
}
```

`remote_count` is present only with `--details`. `matched` is the number before `--limit`. `count` is the number printed. `--limit 0` means no limit. A negative limit exits 1.

`--summary` groups by country instead of listing files. `--limit` then limits country rows, not individual files. Columns are Code, Country, TCP, UDP, and Total.

```json
{
  "matched": 296,
  "count": 10,
  "countries": [
    {"country_code": "US", "country": "United States", "tcp": 22, "udp": 22, "total": 44}
  ]
}
```

## `fastvpn search`

`fastvpn search TEXT` is `list` with a required query. It accepts `--protocol`, `--country`, `--city`, `--details`, `--limit`, and `--query`. `--query` uses the same slot as the positional text. Pass one of them. When both are present, the flag wins. There is no `--summary` on `search`. Use `fastvpn list --summary --query TEXT` for counts.

```bash
fastvpn search london
fastvpn search virtual --protocol tcp --format json
fastvpn search "New York" --limit 10
```

There is no `--summary` on `search`. Use `fastvpn list --summary --query TEXT`.

## `fastvpn show`

Show one profile and the remote hosts declared in it.

```bash
fastvpn show "NCVPN-JP-Tokyo-UDP.ovpn"
fastvpn show ./udp/NCVPN-JP-Tokyo-UDP.ovpn
fastvpn show /absolute/path/tcp/NCVPN-US-New York-TCP.ovpn
```

The argument must be an exact filename or an existing `.ovpn` path. A city or country that is only a substring exits 1 and prints up to eight close matches. Two files with the same name and different protocols exit 1 and ask for a protocol-specific filename. The reading stops at the first `<ca>` block, so certificates are not printed.

The table panel shows protocol, location, virtual, path, source, remote count, whether `remote-random` is set, and whether the file contains `auth-user-pass`. A second table lists the first 15 `remote` lines as Host and Port. Stderr says how many further hosts exist. `--format json` includes every remote:

```json
{
  "server": {
    "protocol": "udp",
    "country_code": "JP",
    "country": "Japan",
    "city": "Tokyo",
    "virtual": false,
    "filename": "NCVPN-JP-Tokyo-UDP.ovpn",
    "path": "/absolute/path/udp/NCVPN-JP-Tokyo-UDP.ovpn",
    "source": "project"
  },
  "profile": {
    "proto": "udp",
    "remotes": [{"host": "nrt-c01.vpn.wlvpn.com", "port": "1194"}],
    "remote_count": 64,
    "remote_random": true,
    "auth_user_pass": false
  }
}
```

`csv` and `plain` print one server row plus `remote_count`.

## `fastvpn fetch`

Aliases: `download`, `update`.

Download a zip or a single `.ovpn` and install the profiles under the primary root, which is the project directory when you are inside this checkout.

```bash
fastvpn fetch
fastvpn fetch --source grouped
fastvpn fetch --source tcp
fastvpn fetch --source udp
fastvpn fetch --list-sources
fastvpn fetch --url https://vpn.ncapi.io/groupedServerList.zip
fastvpn fetch --url https://example.com/one.ovpn
fastvpn fetch --dest /path/to/profiles --force
fastvpn fetch --dry-run
fastvpn fetch --format json
```

Built-in sources:

| `--source` | URL |
| --- | --- |
| `grouped` | `https://vpn.ncapi.io/groupedServerList.zip` |
| `tcp` | `https://vpn.ncapi.io/serverListTCP.zip` |
| `udp` | `https://vpn.ncapi.io/serverListUDP.zip` |

With neither `--source` nor `--url`, the source is `grouped`. Stderr says which list is being used. `--source` and `--url` together exit 1. `--list-sources` prints the table above and exits 0. Combining it with `--source` or `--url` exits 1.

Before the transfer, stderr prints the URL and the install directory. In table mode, a progress bar shows bytes, speed, and time remaining. `--quiet` and non-table formats skip the bar. The download uses a 120 second timeout and a `fastvpn/<version>` user agent. HTTP failures name the status code and the URL, then exit 1.

The archive is extracted in a temporary directory and then deleted. Each `.ovpn` member is placed by these rules:

- A path that starts with `tcp/`, `udp/`, or `imported/` keeps that directory.
- Any other `.ovpn` is filed by the protocol in its filename, then by a `proto` line in the file, and otherwise into `imported/`.
- `__MACOSX`, AppleDouble `._*` files, and `.DS_Store` are ignored.
- A member larger than 2 MiB is rejected.
- Absolute paths and any `..` component are rejected and are not written.

Files that already exist are left unchanged and counted as already present. `--force` overwrites them and counts them as replaced. The summary panel shows destination, added, replaced, already present, and rejected. `--verbose` lists up to 40 added paths on stderr. If nothing was added, replaced, or already present, the command exits 1.

JSON lists every relative path:

```json
{
  "destination": "/absolute/project",
  "added": ["tcp/NCVPN-DE-Frankfurt-TCP.ovpn"],
  "replaced": [],
  "skipped": ["udp/NCVPN-JP-Tokyo-UDP.ovpn"],
  "rejected": ["../escape.ovpn"],
  "counts": {"added": 1, "replaced": 0, "skipped": 1, "rejected": 1}
}
```

`--dry-run` prints the URL and destination, writes nothing, and exits 0. JSON is `{"dry_run": true, "url": "...", "destination": "...", "force": false}`.

## `fastvpn import`

Copy profiles from a local path into the primary root, or into `--dest`.

```bash
fastvpn import ./servers.zip
fastvpn import ./tcp
fastvpn import ./one.ovpn
fastvpn import /path/to/configs --dest ~/.local/share/fastvpn --force
fastvpn import ./servers.zip --dry-run --format json
```

| Input | Result |
| --- | --- |
| `.zip` file | Same placement rules as `fetch`, including traversal rejection. |
| Directory | Every `.ovpn` under it is copied. Symbolic links to directories are not followed. `.git`, `__pycache__`, and `.venv` are skipped. |
| One `.ovpn` file | Copied into `tcp/`, `udp/`, or `imported/` using the same protocol rules. |
| Missing path | Exit 1, `Path not found`. |
| Source and destination are the same directory | Exit 1. |
| Nothing importable | Exit 1 after the summary. |

Existing files are skipped unless `--force`. The summary and JSON match `fetch`. `--dry-run` prints `Would import SOURCE into DESTINATION` and writes nothing.

A zip that already uses `tcp/` and `udp/` folders keeps those folders. A loose `NCVPN-US-Miami-UDP.ovpn` inside a TCP-only zip still lands in `udp/` because the filename says UDP.

## `fastvpn creds`

Alias: `credentials`. With no action, this lists profiles.

Auth files are exactly two lines: username, then password. OpenVPN does not treat `#` as a comment. The password is read from the terminal or from stdin and stored in the file. It is not printed, not put in JSON, and not passed as a command-line argument.

### `creds list`

```bash
fastvpn creds list
fastvpn credentials list --format json
```

The table columns are Profile, Username, Active, Mode, and Path. The project file is the profile named `project` when `credentials.txt` exists in the primary root. Named profiles are the `*.txt` files in the credentials directory. A file that does not have two lines shows an empty username. In JSON that row also has `"error"` with the reason. Exit 0 when there are no profiles. The stderr hint is `Create one with: fastvpn creds set --username NAME`.

```json
{
  "profiles": [
    {
      "profile": "travel",
      "username": "alice",
      "path": "/home/you/.config/fastvpn/credentials/travel.txt",
      "active": true,
      "permissions": "600",
      "private": true,
      "error": null
    }
  ]
}
```

### `creds show`

```bash
fastvpn creds show
fastvpn creds show --profile travel
fastvpn creds show --format json
```

Shows the active credentials, or `--profile` when given. The panel contains source, profile, username, path, and mode. No profile at all exits 1. A missing named profile exits 1 and tells you the `creds set` command that would create it.

Environment credentials (`FASTVPN_USERNAME` and `FASTVPN_PASSWORD`) show source `environment`, an empty path, and username only.

### `creds set`

Alias: `add`.

```bash
fastvpn creds set --username alice
fastvpn creds set
fastvpn creds set --username alice --password-stdin --profile travel
printf '%s\n' 'secret' | fastvpn creds set --username alice --password-stdin
fastvpn creds set --username alice --project
fastvpn creds set --username alice --profile travel --dry-run
```

| Variation | What happens |
| --- | --- |
| `--username` omitted on a terminal | Prompt `Username` on stderr. |
| `--username` omitted and stdin is not a terminal | Exit 1. |
| Password prompt | `Password:` and `Confirm password:` through `getpass`. They do not echo. A mismatch or an empty password exits 1. |
| `--password-stdin` | One line from stdin, without the trailing newline. Requires `--username`. An empty line exits 1. |
| No `--profile` and no `--project` | Writes `default` in the credentials directory. |
| `--profile NAME` | Writes `NAME.txt`. Names are 1 to 64 characters: letters, digits, `.`, `_`, and `-`, starting with a letter or digit. |
| `--project` | Writes `credentials.txt` in the primary root. The profile name is `project`. |
| `--project` and `--profile` together | Exit 1. |
| After a successful write | The file and its directory are mode `600` / `700`, and that profile becomes the active one. |
| `--dry-run` | Prints `Would write profile NAME to PATH` and does not create the file. |
| `--format json` | `{"profile", "path", "username", "active": true}` and no password. |

Stderr on success: `Saved profile travel for alice. It is now the active profile.`

### `creds use`

```bash
fastvpn creds use travel
fastvpn creds use project
fastvpn creds use travel --dry-run
```

The profile must already exist. This writes `active_profile` to `config.toml` in the config directory and prints `Active profile: travel`. `--dry-run` prints `Would activate: travel` and leaves the file unchanged. JSON is `{"profile": "travel", "active": true, "dry_run": false}`.

### `creds remove`

Alias: `rm`.

```bash
fastvpn creds remove travel
fastvpn creds rm travel --yes
fastvpn creds remove project --yes
fastvpn creds remove travel --dry-run
```

On a terminal, asks `Delete credential profile travel?` and defaults to no. Declining prints `Kept the profile.` and exits 0. `--yes` deletes without asking. With no terminal and no `--yes`, exits 1. `--dry-run` prints `Would delete PATH` and does not delete.

Deletion removes the file. If that profile was active, `config.toml` is removed too. The next connection then falls through to `credentials.txt` or the `default` profile if one of those exists. Stderr: `Deleted credential profile travel.`

### `creds lock`

```bash
fastvpn creds lock
fastvpn creds lock --dry-run
```

Sets the active auth file to mode `600` and prints the path. There is nothing to lock when credentials are missing or when they come only from the environment. Both cases exit 1. `--dry-run` prints `Would set mode 600 on PATH`.

### Which credentials `connect` uses

The first match wins:

1. `--no-auth` skips the auth file.
2. `--credentials FILE` must exist and contain two lines.
3. `FASTVPN_CREDENTIALS` is that same kind of file.
4. `FASTVPN_USERNAME` and `FASTVPN_PASSWORD` must both be set. They are written to a mode `600` temporary file for the life of the OpenVPN process, then the file is removed. Setting only one of them exits 1.
5. `--profile NAME`.
6. `active_profile` in `config.toml`.
7. `credentials.txt` in the primary root, reported as the profile `project`.
8. `default.txt` in the credentials directory.
9. Otherwise OpenVPN prompts.

## `fastvpn status`

```bash
fastvpn status
fastvpn status --format json
```

Runs `ps -eo pid=,args=` and keeps processes whose command contains the OpenVPN binary. The table columns are PID, Config, and Command. Config is the `--config` path, including paths that contain spaces. When nothing is running, stderr says `OpenVPN is not running.` and the exit code is 0.

```json
{
  "count": 1,
  "sessions": [
    {
      "pid": 4242,
      "config": "/absolute/path/tcp/NCVPN-US-New York-TCP.ovpn",
      "command": "sudo openvpn --config /absolute/path/tcp/NCVPN-US-New York-TCP.ovpn --auth-user-pass /absolute/path/credentials.txt"
    }
  ]
}
```

The command line can include the auth file path. It does not include the password.

## `fastvpn disconnect`

Alias: `down`.

```bash
fastvpn disconnect
fastvpn disconnect --yes
fastvpn disconnect --force --yes
fastvpn disconnect --no-sudo --yes
fastvpn disconnect --dry-run
```

Lists the same sessions as `status`. When none are running, exits 1 with `No OpenVPN session is running.` Otherwise it prints the `kill` command. The default signal is `SIGTERM`. `--force` uses `SIGKILL`. The default is to run `sudo kill` when you are not root. `--no-sudo` signals the process directly.

On a terminal, asks `Disconnect N OpenVPN session(s)?` and defaults to no. Declining exits 0 and leaves the sessions running. `--yes` skips the question. No terminal and no `--yes` exits 1. `--dry-run` prints the command and does not signal. After a real signal, stderr says `Disconnect requested.` and the exit code is 0 when `kill` succeeds.

## `fastvpn doctor`

Alias: `check`.

```bash
fastvpn doctor
fastvpn check --format json
```

Runs five checks. `ok` is green, `warn` is yellow, `fail` is red. Exit 0 when every check is `ok` or `warn`. Exit 1 when any check is `fail`.

| Check | ok | warn | fail |
| --- | --- | --- | --- |
| OpenVPN | Binary is on `PATH`. The detail is its path. |  | Binary is missing. |
| Privileges | `sudo` is installed, or you are root. | `sudo` is missing. |  |
| TUN | `/dev/net/tun` exists. | The device file is missing. |  |
| Profiles | At least one `.ovpn` is visible. The detail is the TCP count, UDP count, and root. |  | No profiles. This is the usual result of a fresh checkout before `fetch`. |
| Credentials | A private auth file or environment pair is in use. The detail includes the username and path. | No credentials, so OpenVPN will prompt. Or the file mode allows group or world read, with a hint to run `creds lock`. | The selected file exists but is not two UTF-8 lines. |

JSON is `{"ok": true, "checks": [{"name", "status", "detail"}]}`. `ok` is false when the process will exit 1.

## `fastvpn paths`

```bash
fastvpn paths
fastvpn paths --format json
```

Prints the directories for this invocation. It does not create them.

| Key | Meaning |
| --- | --- |
| `primary_root` | Where `fetch` and `import` write, and where `credentials.txt` is read. |
| `scan_roots` | Every directory that `list` reads, with a label: `extra`, `root`, `project`, or `data`. |
| `config_dir` | `config.toml` lives here. |
| `credentials_dir` | Named `*.txt` profiles. |
| `cache_dir` | Temporary auth files and downloaded single profiles. |
| `project_credentials` | `<primary_root>/credentials.txt`. |
| `settings_file` | `<config_dir>/config.toml`. |

`--root` or `FASTVPN_ROOT` makes `primary_root` that directory and stops the scan from also including the checkout you happen to be in. Without them, a directory that contains `tcp/` or `udp/`, or a `pyproject.toml` named `fastvpn`, is the project. The user data directory is scanned as well. Parent directories are searched when you start the command from a subdirectory of the project.

## `fastvpn version`

```bash
fastvpn version
fastvpn --version
fastvpn version --format json
```

Prints `fastvpn 1.0.0`. JSON is `{"name": "fastvpn", "version": "1.0.0"}`. `--version` exits from argparse before the subcommands run.

## `fastvpn help`

```bash
fastvpn help
fastvpn help connect
fastvpn help fetch
fastvpn --help
fastvpn connect --help
```

`help` with no topic prints the main help. `help connect` prints that command's help. Aliases work, so `fastvpn help ls` shows `list`. An unknown topic exits 2.

## Environment variables

| Variable | Effect |
| --- | --- |
| `FASTVPN_ROOT` | The only profile root, unless you also pass `--config-dir`. Same role as `--root`. |
| `FASTVPN_CONFIG_HOME` | The config directory itself, not its parent. Overrides `XDG_CONFIG_HOME/fastvpn`. |
| `FASTVPN_DATA_HOME` | The data directory itself. Overrides `XDG_DATA_HOME/fastvpn`. |
| `FASTVPN_CACHE_HOME` | The cache directory itself. Overrides `XDG_CACHE_HOME/fastvpn`. |
| `FASTVPN_CREDENTIALS` | Path of a two-line auth file. |
| `FASTVPN_USERNAME` | Used only together with `FASTVPN_PASSWORD`. |
| `FASTVPN_PASSWORD` | Used only together with `FASTVPN_USERNAME`. |
| `XDG_CONFIG_HOME` | Parent of `fastvpn/` when `FASTVPN_CONFIG_HOME` is unset. Default `~/.config`. |
| `XDG_DATA_HOME` | Parent of `fastvpn/` when `FASTVPN_DATA_HOME` is unset. Default `~/.local/share`. |
| `XDG_CACHE_HOME` | Parent of `fastvpn/` when `FASTVPN_CACHE_HOME` is unset. Default `~/.cache`. |
| `NO_COLOR` | Any value disables color. |

## Filename fields

`NCVPN-US-New York-TCP.ovpn` becomes code `US`, country `United States`, city `New York`, protocol `tcp`, virtual `no`.

`NCVPN-US-St. Louis - Virtual-TCP.ovpn` becomes city `St. Louis` and virtual `yes`.

`NCVPN-IN-Virtual-TCP.ovpn` becomes country `India`, an empty city, and virtual `yes`.

A file that does not match that pattern still appears. Its protocol is the folder it is in (`tcp` or `udp`), then a `proto` line, then `tcp`. Its country and city are empty. `show` still reads its `remote` lines.
