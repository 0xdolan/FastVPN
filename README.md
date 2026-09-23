# FastVPN

FastVPN is a terminal client for OpenVPN profiles. It lists the `.ovpn` files on disk, downloads or imports more of them, stores a username and password in a locked file, and starts OpenVPN with the profile you choose.

Run it with no arguments and it prints what is installed. It does not open a connection until you use `connect` or one of the `-t`, `-u`, and `-f` shortcuts.

The command reference in [docs/cli.md](docs/cli.md) is the long form of this page: every flag, every variation, the text you see, and the exit code. This README covers the same commands so you can use the tool from here.

Examples use `fastvpn`. In this checkout, prefix them with `uv run`:

```bash
uv run fastvpn doctor
```

`python main.py` accepts the same arguments.

## Install

[uv](https://docs.astral.sh/uv/) creates the environment and installs the program.

```bash
uv venv
uv sync
uv run fastvpn
```

OpenVPN is a separate package. On Debian or Ubuntu:

```bash
sudo apt install openvpn
```

### Shell setup

If you keep a checkout at `~/FastVPN` (or any fixed path) and want `fastvpn` available from any directory, put one of these in `~/.zshrc` or `~/.bashrc`.

Preferred. Puts the real `fastvpn` binary on `PATH`, so command highlighters show it in green, and points every run at that checkout:

```zsh
export FASTVPN_ROOT=$HOME/FastVPN
path=($HOME/FastVPN/.venv/bin $path)
```

For bash, use:

```bash
export FASTVPN_ROOT=$HOME/FastVPN
export PATH="$HOME/FastVPN/.venv/bin:$PATH"
```

Alternative. An alias also works. Some highlighters leave the name red because it is not a file on `PATH`, but the command still runs:

```zsh
alias fastvpn='FASTVPN_ROOT=$HOME/FastVPN $HOME/FastVPN/.venv/bin/fastvpn'
```

Reload the shell, then check:

```bash
source ~/.zshrc
fastvpn list --limit 3
fastvpn -t
```

`FASTVPN_ROOT` is required in both forms when you are not already inside the project directory. Without it, FastVPN looks under the current directory and then `~/.local/share/fastvpn`, so a run from `~` finds no profiles.

The first panel tells you whether `openvpn` is on `PATH`, how many profiles were found, which directory will receive new profiles, and which username will be used. A fresh tree has no profiles yet. `fastvpn doctor` exits 1 in that case because the Profiles check fails. `fastvpn fetch` fills `tcp/` and `udp/`.

## Where files go

| Location | Role |
| --- | --- |
| `tcp/`, `udp/`, `imported/` in this project | Profiles used when you run the command from the checkout. |
| `credentials.txt` | Optional two-line auth file for this project. Gitignored. |
| `~/.config/fastvpn/` | `config.toml` and named credential profiles. |
| `~/.local/share/fastvpn/` | Profiles used when you are not inside a project. |
| `~/.cache/fastvpn/` | A remote `.ovpn` downloaded for one connection, and short-lived auth files built from the environment. |

`fastvpn paths` prints the paths for the current run. `--root DIR` and `FASTVPN_ROOT` select one profile root and ignore the checkout you happen to be sitting in. `--config-dir DIR` adds another directory and can be repeated. That directory can be a `tcp/` and `udp/` tree or a flat folder of `.ovpn` files. The same filename in an earlier directory wins.

`FASTVPN_CONFIG_HOME`, `FASTVPN_DATA_HOME`, and `FASTVPN_CACHE_HOME` replace the three directories above. When those are unset, FastVPN uses `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and `XDG_CACHE_HOME`.

Filenames from the public lists look like `NCVPN-US-New York-TCP.ovpn`. FastVPN reads the country code, city, protocol, and a virtual flag from that name. `UK` is the code in the lists. Searches also accept `gb`, `usa`, and `uae`. `NCVPN-IN-Virtual-TCP.ovpn` is India with no city and the virtual flag set. A file that does not match the pattern is still listed. Its protocol comes from the folder, then from a `proto` line inside the file.

## Output

Results go to stdout. Hints, download progress, prompts, and errors go to stderr, so `--format json` can be piped.

| `--format` | What you get |
| --- | --- |
| `table` | Color tables and panels. This is the default. |
| `json` | Indented JSON. Passwords are not a field. |
| `plain` | A header, then tab-separated rows. |
| `csv` | A header, then comma-separated rows. |

`--no-color`, or any value of `NO_COLOR`, turns color off. `--quiet` hides hints and the progress bar. `--verbose` lists files added by `fetch` and `import`. `--quiet` and `--verbose` together exit 1. `--dry-run` prints the action and does not download, write, connect, or signal a process.

| Exit code | Meaning |
| --- | --- |
| 0 | Finished. An empty `list` is still 0. |
| 1 | The request failed. The reason is on stderr. |
| 2 | The flags are invalid. |
| 130 | Ctrl+C. |
| OpenVPN's code | Returned by `connect` and by `-t`, `-u`, and `-f`. |

Global options work on either side of the subcommand: `fastvpn --format json list` and `fastvpn list --format json` match.

## Credentials

An OpenVPN auth file is two lines, username then password, with no comments. Copy `credentials.example.txt` to `credentials.txt` or create a named profile. The password is never printed.

`connect` picks the first source that exists:

1. `--no-auth` leaves the auth file off and OpenVPN prompts.
2. `--credentials FILE`
3. `FASTVPN_CREDENTIALS`
4. `FASTVPN_USERNAME` and `FASTVPN_PASSWORD` together. One without the other exits 1. The pair is written to a mode `600` file for the OpenVPN process and removed when it exits.
5. `--profile NAME`
6. The active profile in `~/.config/fastvpn/config.toml`
7. `credentials.txt` in the project, called the `project` profile
8. The named profile `default`

```bash
fastvpn creds set --username alice
fastvpn creds list
fastvpn creds show
fastvpn creds lock
```

`creds set` prompts for a hidden password, writes mode `600`, and makes that profile active. `--password-stdin` reads one line from stdin and requires `--username`. `--profile travel` stores `~/.config/fastvpn/credentials/travel.txt`. `--project` writes `credentials.txt` in the project root. `--project` and `--profile` together exit 1. Profile names are up to 64 characters of letters, digits, `.`, `_`, and `-`.

`creds show` prints the username, path, and mode. `creds use travel` selects an existing profile. `creds remove travel` asks before deleting. Add `--yes` in a script. `creds lock` sets the active file to mode `600`. `doctor` warns when a credentials file is readable by the group or by other users, and fails when the file is not two lines of UTF-8.

`credentials.txt` and `credentials_*.txt` are gitignored.

## Commands

### No arguments

```bash
fastvpn
```

Prints the status panel and exits 0. Nothing connects. `--format json` prints version, OpenVPN path, profile counts, roots, and the credential username.

### Shortcuts

These connect immediately and cannot be mixed with a subcommand. `-t` and `-u` together exit 1.

| Command | Result |
| --- | --- |
| `fastvpn -t` | Random TCP profile, then OpenVPN in the foreground. |
| `fastvpn -u` | Random UDP profile, then OpenVPN. |
| `fastvpn -f "NCVPN-US-New York-TCP.ovpn"` | That filename, in either protocol directory. |
| `fastvpn -t -f "NCVPN-US-New York-TCP.ovpn"` | That filename among TCP profiles. |
| `fastvpn -f ./udp/NCVPN-JP-Tokyo-UDP.ovpn` | That path, including paths outside `tcp/` and `udp/`. |
| `fastvpn -f https://example.com/server.ovpn` | Download one profile into the cache, then connect. A zip URL exits 1 and points you at `fetch`. |
| `fastvpn -t --dry-run` | Print the OpenVPN argv and exit 0. |

A missing name exits 1 and lists up to eight similar filenames or cities.

### `connect`

```bash
fastvpn connect
fastvpn connect --protocol udp
fastvpn connect --protocol any --random
fastvpn connect --country US --city "New York"
fastvpn connect --country gb -p udp
fastvpn connect -c US -c DE --city Miami
fastvpn connect --query virtual --pick
fastvpn connect --file "NCVPN-JP-Tokyo-UDP.ovpn" --dry-run
fastvpn connect --no-auth
fastvpn connect --profile travel
fastvpn connect --credentials ./credentials.txt
fastvpn connect --openvpn /usr/sbin/openvpn --no-sudo
fastvpn connect --ovpn-arg --mute --ovpn-arg 20
```

With no file and no filter, this chooses a random TCP profile. `--protocol udp` or `any` changes the pool. `--random`, `--first`, and `--pick` are mutually exclusive.

| Call | What happens |
| --- | --- |
| No filter | Random profile for the protocol. |
| One match | That profile. |
| Several matches on a terminal | A numbered table and a prompt, for up to 40 rows. |
| Several matches in a script, or with `json`, `csv`, or `plain` | Exit 1. Pass `--random` or `--first`. |
| `--first` | First row after sorting by country, city, protocol, and filename. |
| `--file` | That filename, path, or URL. Other filters are ignored. |

Country flags are combined with OR. City flags are combined with OR. Using both means both must match. `US` and `de` match the code. `united` matches every country name that contains it. `new` matches New York and New Orleans. `--query virtual` matches virtual profiles.

Stdout shows a Connecting panel: protocol, place, virtual flag, file, path, and which username will be used. Stderr shows the exact command, then tells you OpenVPN will stay in this terminal. The process is `sudo openvpn --config PROFILE --auth-user-pass FILE` when you are not root and credentials exist. Root, or `--no-sudo`, drops `sudo`. `--no-auth` and a machine with no credentials drop `--auth-user-pass`, and OpenVPN prompts. Each `--ovpn-arg` is appended in order. The shell is not used.

Ctrl+C returns 130. OpenVPN's own exit code is returned otherwise, and a non-zero code is repeated on stderr.

In a normal interactive table session, the Connecting panel stays pinned at the top of the terminal. OpenVPN logs, including the sudo password prompt, scroll underneath it. `--quiet` and `--format json` skip that pinning.

`--format json` prints `dry_run`, `server`, `credentials`, and `command` before OpenVPN starts. `--dry-run` stops after that object. `--quiet` prints a single `Connecting TCP filename` line.

### `list`

Alias: `ls`.

```bash
fastvpn list
fastvpn list london
fastvpn list --protocol udp --country US
fastvpn list -c US -c CA --city York
fastvpn list --query virtual --details
fastvpn list --summary
fastvpn list --summary --limit 10
fastvpn list --limit 5 --format json
fastvpn list --format csv
```

Prints Protocol, Code, Country, City, and File. Virtual rows put `virtual` in the City column. Source appears only when rows come from more than one directory. `--details` adds a Remotes count by reading each file up to the certificate. `--limit 0` means every row. A negative limit exits 1. Zero matches exit 0 and the table format tells you to run `fastvpn fetch`.

`--summary` replaces the file list with one row per country: Code, Country, TCP, UDP, Total. `--limit` then limits countries, not files.

JSON for a normal list is `{"matched", "count", "servers": [...]}`. `matched` is the size before `--limit`. Each server has `protocol`, `country_code`, `country`, `city`, `virtual`, `filename`, `path`, and `source`. `--details` adds `remote_count`. Summary JSON uses `countries` instead of `servers`. `csv` and `plain` add a Path column.

A positional word and a different `--query` together exit 1.

### `search`

```bash
fastvpn search london
fastvpn search "New York" --protocol tcp --limit 10
fastvpn search virtual --format json
```

This is `list` with a required search string. It also accepts `--protocol`, `--country`, `--city`, `--details`, `--limit`, and `--query`. `--query` stores the same value as the positional text, so pass one of them. If both are present, the flag is the text that is searched. There is no `--summary`. Use `fastvpn list --summary --query london` for counts.

### `show`

```bash
fastvpn show "NCVPN-JP-Tokyo-UDP.ovpn"
fastvpn show ./udp/NCVPN-JP-Tokyo-UDP.ovpn
```

The argument is an exact filename or an existing `.ovpn` path. A city or country alone exits 1 and prints up to eight close matches. Two protocols with the same filename ask you to pass the full name.

The panel shows protocol, location, virtual flag, path, source, how many `remote` lines the file has, whether `remote-random` is set, and whether `auth-user-pass` is set. A second table shows the first 15 hosts and ports. Stderr says how many hosts were left out. `--format json` includes every host under `profile.remotes`, plus `proto`, `remote_count`, `remote_random`, and `auth_user_pass`. Reading stops at the `<ca>` block, so the certificate is not shown.

### `fetch`

Aliases: `download`, `update`.

```bash
fastvpn fetch
fastvpn fetch --source tcp
fastvpn fetch --source udp
fastvpn fetch --list-sources
fastvpn fetch --url https://vpn.ncapi.io/groupedServerList.zip
fastvpn fetch --url https://example.com/one.ovpn
fastvpn fetch --dest ~/profiles --force
fastvpn fetch --dry-run
```

| `--source` | URL |
| --- | --- |
| `grouped` (default) | `https://vpn.ncapi.io/groupedServerList.zip` |
| `tcp` | `https://vpn.ncapi.io/serverListTCP.zip` |
| `udp` | `https://vpn.ncapi.io/serverListUDP.zip` |

`--list-sources` prints that table and does not download. Combining it with `--source` or `--url` exits 1. `--source` and `--url` together exit 1.

Stderr prints the URL and the destination, then a progress bar in table mode. `--quiet` hides the bar. The file is downloaded to a temporary directory. Zip members that end in `.ovpn` are installed under the destination. Paths that already start with `tcp/`, `udp/`, or `imported/` keep that folder. Other files are sorted by the protocol in the filename, then by a `proto` line, and otherwise go to `imported/`. Absolute paths, `..`, AppleDouble files, and members larger than 2 MiB are rejected and counted. Existing profiles are kept unless you pass `--force`.

The result panel is destination, added, replaced, already present, and rejected. `--verbose` lists added paths. `--format json` lists those paths under `added`, `replaced`, `skipped`, and `rejected`, plus `counts`. If no profile was added, replaced, or already present, the command exits 1. `--dry-run` prints the URL and destination and writes nothing.

### `import`

```bash
fastvpn import ./servers.zip
fastvpn import ./my-configs/
fastvpn import ./one.ovpn
fastvpn import ./servers.zip --dest ~/.local/share/fastvpn --force
fastvpn import ./servers.zip --dry-run
```

| Input | What happens |
| --- | --- |
| A zip | Same rules as `fetch`, including rejection of paths that escape the destination. |
| A directory | Copies every `.ovpn` underneath it. Directory symlinks are not followed. |
| One `.ovpn` | Copied into `tcp/`, `udp/`, or `imported/`. |
| A missing path | Exit 1. |
| The source directory is the destination | Exit 1. |

The summary, JSON, `--force`, and `--dry-run` behavior match `fetch`. A loose `*-UDP.ovpn` inside a zip is stored in `udp/` even when the archive has no folders.

### `creds`

Alias: `credentials`. `fastvpn creds` with no action lists profiles.

```bash
fastvpn creds list
fastvpn creds show
fastvpn creds show --profile travel
fastvpn creds set --username alice
fastvpn creds set --username alice --password-stdin --profile travel
fastvpn creds set --username alice --project
fastvpn creds use travel
fastvpn creds use project
fastvpn creds remove travel --yes
fastvpn creds lock
```

`list` shows profile, username, whether it is active, mode, and path. JSON rows also include `private` and `error`. An empty list exits 0 and tells you how to create one.

`set` on a terminal prompts for the username when you omit `--username`, then asks for the password twice without echoing it. A mismatch exits 1. `--password-stdin` is the script form. The new profile becomes active. `--dry-run` names the path and does not write it. JSON from `set` and `show` contains the username and path and does not contain the password.

`use` requires the profile to exist, then writes `active_profile` in `config.toml`. `remove` asks on a terminal and refuses to delete without `--yes` when there is no terminal. If you delete the active profile, the active setting is cleared. `lock` runs `chmod 600` on the active file. Environment variables are not a file, so `lock` exits 1 for those.

### `status`

```bash
fastvpn status
fastvpn status --format json
```

Lists local processes whose command is OpenVPN: PID, the `--config` path, and the command line. The auth file path can appear. The password does not. No session is a normal result: stderr says `OpenVPN is not running.` and the exit code is 0. JSON is `{"count", "sessions": [{"pid", "config", "command"}]}`.

### `disconnect`

Alias: `down`.

```bash
fastvpn disconnect
fastvpn disconnect --yes
fastvpn disconnect --force --yes
fastvpn disconnect --no-sudo --yes
fastvpn disconnect --dry-run
```

Shows the same table as `status`, then the `kill` command. The default signal is TERM. `--force` sends KILL. `sudo` is used when you are not root, unless you pass `--no-sudo`. A terminal asks `Disconnect N OpenVPN session(s)?` and the default answer is no. `--yes` skips the question. No terminal and no `--yes` exits 1. No running session exits 1. `--dry-run` prints the command and does not signal. Success prints `Disconnect requested.`

### `doctor`

Alias: `check`.

```bash
fastvpn doctor
```

| Check | Pass | Other result |
| --- | --- | --- |
| OpenVPN | The binary is on `PATH`. | Fail when it is missing. |
| Privileges | You are root, or `sudo` exists. | Warn when `sudo` is missing. |
| TUN | `/dev/net/tun` exists. | Warn when it does not. |
| Profiles | At least one `.ovpn` is visible. | Fail when the directories are empty. |
| Credentials | A private file or environment pair is set. The line includes the username. | Warn when nothing is configured, or when the file is group or world readable. Fail when the file is not two UTF-8 lines. |

Warnings still exit 0. Any failure exits 1. JSON is `{"ok", "checks": [{"name", "status", "detail"}]}`.

### `paths`

```bash
fastvpn paths
```

Prints `primary_root`, every scanned root and its label (`project`, `data`, `root`, or `extra`), `config_dir`, `credentials_dir`, `cache_dir`, the project `credentials.txt` path, and `config.toml`. It does not create the directories. `--format json` prints those keys.

### `version` and `help`

```bash
fastvpn version
fastvpn --version
fastvpn help
fastvpn help connect
fastvpn connect --help
```

`version` prints `fastvpn 1.0.0`. JSON is `{"name": "fastvpn", "version": "1.0.0"}`. `help` with no topic is the main help. `fastvpn help connect` is that command's help. Aliases work, so `fastvpn help ls` shows `list`. An unknown topic exits 2.

## Environment

| Variable | Effect |
| --- | --- |
| `FASTVPN_ROOT` | Profile root. Same as `--root`. |
| `FASTVPN_CONFIG_HOME` | Config directory itself. |
| `FASTVPN_DATA_HOME` | Data directory itself. |
| `FASTVPN_CACHE_HOME` | Cache directory itself. |
| `FASTVPN_CREDENTIALS` | Two-line auth file. |
| `FASTVPN_USERNAME` | Used together with `FASTVPN_PASSWORD`. |
| `FASTVPN_PASSWORD` | Used together with `FASTVPN_USERNAME`. |
| `NO_COLOR` | Disable color. |

## Development

```bash
uv sync
uv run pytest
uv run fastvpn doctor
```

The package lives in `src/fastvpn/`. The console script is `fastvpn`.

## License

[GPL-3.0-or-later](LICENSE)
