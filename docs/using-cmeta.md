# Using cMeta

This guide walks through everyday use of the **cMeta** framework: driving it
via the `cx` CLI (or `cm.access(...)` in Python), pulling in new content
repositories, adding your own categories (plugins) and artifacts, and keeping
the local index healthy.

If you haven't installed cMeta yet, start with
[installation.md](installation.md).

---

## 1. Mental model in 60 seconds

- The **engine** is the `cmeta` Python package. It offers **one entry point**:
  `cm.access({'category': ..., 'command': ..., ...})` — mirrored on the CLI as
  `cx <category> <command> [args] [--flags]`.
- A **category** is a plugin type (`repo`, `app`, `experiment`, `note`, ...).
  Each category lives as an artifact of the `category` category and implements
  its commands in `api/v1.py`.
- An **artifact** is any content managed by a category: a config, an app, an
  experiment record, a note. Each artifact is a folder with an
  `_cmeta.yaml` (or `_cmeta.json`) sidecar carrying identity + metadata.
- A **content repository** is a directory that holds artifacts and has an
  `_cmr.yaml` at its root. cMeta indexes all plugged-in repos together.
- Every install has three tiers of repos indexed under one `<CMETA_HOME>`:
  (1) the shipped **internal repo** with foundational categories, (2) a
  **default local scratch** repo (`<CMETA_HOME>/repos/local/`) created on
  first launch, (3) any **user repos** you pull or plug in. Full detail in §7.
- `<CMETA_HOME>` is chosen from `CMETA_HOME` env → `VIRTUAL_ENV/CMETA` →
  `CONDA_PREFIX/CMETA` → `CMETA_HOME2` → `~/CMETA`. Deleting a
  `<CMETA_HOME>` is safe — the shell is recreated on next launch (see §7.4).

Environment variables worth knowing:
`CMETA_HOME` (state directory, default under user home), `CMETA_DEBUG=1`,
`CMETA_LOG=DEBUG|INFO`, `CMETA_LOG_FILE=<path>`, `CMETA_VERBOSE=yes`,
`CMETA_FAIL_ON_ERROR=yes`.

---

## 2. First checks after install

```bash
cmeta --version
cx --version                     # short alias

cx repo list                     # what repos are plugged in (starts with the built-in)
cx category list                 # what plugins are available
cx <category> --help             # list commands available in a category
cx <category> <command> --help   # per-command flags/args
```

Global CLI aliases (from `cmeta/config.py`): `add→create`, `rm→delete`,
`ls→list`, `search→find`, `mv→move`, `cp→copy`, `ren/rename→move`,
`load→read`. Use whichever reads naturally.

---

## 3. Common CLI flags

Run `cx --help` for the authoritative list; the tables below (extracted from
`cmeta/config.py`) group flags by what they do. Any of these can appear on
any command unless noted.

### 3.1 Global flags

| Flag | Type | Effect |
|------|------|--------|
| `--help`, `-h` | bool | Show help. On a category or command, prints its usage. |
| `--version`, `-V` | bool | Print cMeta version and check for a newer release. |
| `--reindex` | bool | Clean and rebuild the fast index (`<CMETA_HOME>/index/*.pkl`). Use after manual edits, `git pull`, cleared `CMETA_HOME`, or when lookups look stale. |
| `--verbose`, `-v` | bool | Verbose output — extra progress info from repo ops and package detection. |
| `--quiet`, `-q` | bool | Auto-accept the default answer for any interactive prompt (safe for scripts). |
| `--repro`, `-r` | bool | Write `cmeta-repro-input.json` (+ `-input2.json`, `-output.json`) for reproducibility of the call. |

### 3.2 Command dispatch flags

| Flag | Type | Effect |
|------|------|--------|
| `--base` | bool | Force the **base** category command (from `category_api_v1.py`) instead of the category's own override. Useful when a category wraps a base command and you want to bypass its wrapper. |
| `--api` | int | Pin a specific category API version (loads `api/v<n>.py`). Defaults to the category's `last_api_version`. |

### 3.3 Output / debug flags (apply to any command)

| Flag | Type | Effect |
|------|------|--------|
| `--con` | bool | Force console output (some commands are quiet by default when called from Python). |
| `--json`, `-j` | bool | Print the command's return dict as JSON to stdout. |
| `--json_file`, `--json-file`, `--jf` | str | Also write the JSON return dict to the given file. |
| `--dump` | bool | Dump the full request/response context to `cmeta-ctx.json` at the end of the command. |
| `--pause_at_the_end` | bool | Pause before returning — handy for double-clicking `.bat` scripts on Windows. |

### 3.4 Framework initialisation flags

These affect how the engine starts up. Also settable via env vars (in parens).

| Flag | Type | Effect |
|------|------|--------|
| `--home <path>` | str | Override `<CMETA_HOME>` for this invocation. (`CMETA_HOME`) |
| `--debug` | bool | Enable debug mode — sets `--log_level=DEBUG` **and** `--fail_on_error`. (`CMETA_DEBUG=1`) |
| `--fail_on_error`, `--fail`, `--fail-on-error` | bool | Raise an exception on first error instead of returning `{'return': >0, 'error': ...}`. Great for debugging; noisy in scripts. (`CMETA_FAIL_ON_ERROR=yes`) |
| `--log_level <lvl>`, `--log-level` | str | `DEBUG`, `INFO`, `WARNING`/`WARN`, `ERROR`, `CRITICAL`/`FATAL`. (`CMETA_LOG`) |
| `--log_file <path>`, `--log-file` | str | Send log output to this file instead of stderr. (`CMETA_LOG_FILE`) |
| `--pause_if_error`, `--pif` | bool | Pause before exiting on error (useful when running via double-click on Windows). |

### 3.5 Flag syntax rules

Parsed by `cmeta/utils/cli.py::parse_cmd`. Full rules:

**Booleans**
- `--flag` → **True** (bare presence).
- `--flag-` → **False** (trailing dash — handy when you want to explicitly
  override a default `True`).
- `--no-flag` → **False** (alternative form).
- `--flag=false` / `--flag=true` → literal string values `"false"` / `"true"`.
  (Don't rely on this for boolean semantics — use the trailing-dash / `--no-`
  forms above.)

**Strings and ints**
- `--key=value` or `--key value`.
- Repeated `--key=v1 --key=v2` → **last value wins**. For real lists, use:
- `--key,=v1,v2,v3` → list `[v1, v2, v3]`. Trailing comma on the *key*
  signals CSV split. `--key,=` alone → `[]`.

**Nested keys** (dot notation)
- `--parent.child=value` → `{'parent': {'child': 'value'}}`.
- Multiple `--k.a=1 --k.b=2 --k.c.d=3` merge into `{'k': {'a':'1','b':'2','c':{'d':'3'}}}`.

**Positional tokens** — anything not consumed as a flag becomes `arg1`, `arg2`,
... in order. First two are conventionally `<category>` and `<command>`.

**Hyphen / underscore equivalence** — `--log-level` == `--log_level`.

**Bare `key=value`** (no leading dashes) is treated the same as `--key=value`.

**`--` separator** — everything after a lone `--` is captured under `unparsed`
(rarely needed; use for pass-through to sub-processes like
`cx app run <a> -- --sub-flag`).

**`@file` inclusion (YAML or JSON)** — replace a bunch of `--k=v` flags with a
single reusable file:

```bash
cx category add @create-args.yaml       # reads YAML/JSON and merges as flags
cx experiment run e1 @run-config.json   # same, JSON
cx <cat> <cmd> @@one-shot.yaml          # `@@` deletes the file after reading
```

The included file is **deep-merged** into the parsed params. Format is
auto-detected from extension (`.yaml`, `.yml`, `.json`). Example `run-config.json`:

```json
{
  "meta": {"description": "pilot run", "hw": {"gpu": "A100"}},
  "verbose": true,
  "ctx": {"agent": {"session": "sess-42"}}
}
```

You can mix `@file` inclusions with regular flags — flags to the right override
values from the file(s) to the left. On Windows, quote paths containing
backslashes so `shlex.split` doesn't mangle them: `@"C:\path\to\file.yaml"`.

**Triple dashes rejected** — `---bogus` returns an error.

### 3.6 A few useful combinations

```bash
cx <category> <command> ... --debug              # print full dispatch trace + fail fast
cx <category> <command> ... -v --con             # noisy output for troubleshooting
cx <category> <command> ... --repro              # capture inputs/outputs for later replay
cx <category> <command> ... -j --jf=out.json     # machine-readable result to stdout + file
cx --reindex                                     # rebuild the fast index
cx --home=D:\work\cmeta-home <category> <cmd>    # one-shot alternative CMETA_HOME
```

---

## 4. Built-in categories (plugins)

All shipped in `cmeta/internal-repo/` and available immediately after install.

| Category | What it manages / provides |
|----------|----------------------------|
| **category** | The category system itself — `add`, `find`, `ls`, `rm`, `mv`. |
| **repo** | Content repositories — `get`, `clone`, `pull`, `checkout`, `status`, `zip`/`unzip`, `plug`/`unplug`, `space`, `list`. |
| **config** | Named configuration artifacts — `get`, `set`, `unset`, `read`, `show`. |
| **utils** | Helper commands — UID/UUID, JSON⇄YAML, clipboard helpers. |
| **app** | Runnable applications. Ships the `cserver` local web app. |
| **script** | Portable shell / Python scripts. |
| **asset** | Data / model / file assets. |
| **cache** | Content-addressed cache entries — `show`, `clean`, `delete`. |
| **experiment**, **result**, **research**, **report** | Records for collaborative & reproducible research. |
| **journal**, **note**, **log** | Chronological entries, notes, structured logs. |
| **docs**, **website** | Documentation artifacts and website builds. |
| **work** | Work items / tasks. |
| **tests** | Test artifacts — group and manage test cases as cMeta artifacts. |

Every category inherits the standard base commands: `find`, `list`, `read`,
`create`, `update`, `delete`, `move`, `copy`, `info`, `tags`, `get`, `set`,
`index`, `test`. Categories add their own commands on top (e.g. `repo get`,
`app run`).

---

## 5. Working with artifacts

### 5.1 Find and inspect

```bash
cx <category> find <alias-or-uid>              # returns matches from the index
cx <category> ls                               # list all artifacts of a category
cx <category> ls --tags=demo,gpu               # AND-match on tags
cx <category> info <alias>                     # show path + cRef; copies cRef to clipboard
cx . info                                      # auto-detect artifact in current dir
cx <category> read <alias>                     # parse and print _cmeta.yaml
```

### 5.2 Create, update, tag, delete

```bash
cx <category> add <alias> --yaml               # create with _cmeta.yaml
cx <category> add <repo>:<alias> --tags=t1,t2  # create in a specific repo
cx <category> update <alias> --meta.description="..."   # merge metadata
cx <category> tags <alias> --add=t1,t2 --remove=t3
cx <category> mv <old> <new>                   # move within/between repos
cx <category> rm <alias>                       # delete (blocked if permanent: true)
```

Prefer YAML sidecars (`--yaml`) — they match the shipped artifacts and are
easy to read/edit by hand.

### 5.3 From Python

Anything you can do on the CLI you can do via `cm.access(...)`:

```python
from cmeta import CMeta
cm = CMeta()

r = cm.access({'category': 'repo', 'command': 'list'})
if cm.catch_error(r): raise RuntimeError(r['error'])
# See error-handling.md — `catch_error` skips soft "not found" errors (code 16)
# and raises at the point of failure when debugging is on.

# Fetch a config artifact:
r = cm.access({'category': 'config', 'command': 'get', 'arg1': 'default'})
config_cmeta = r['config_cmeta']

# Find using a UID for guaranteed resolution:
r = cm.access({'category': 'category,dd9ea50e7f76467f',
               'command': 'find',
               'arg1':    'repo,f4f792ab40c7498f'})
```

Every response is a dict; `return == 0` means success, anything else carries an
`error` string.

### 5.4 `ctx` — thread state (and AI-agent context) through nested calls

Every `access()` call receives — or creates — a `ctx` dict. It's the
framework's shared context bus: the same object is passed down into every
nested `self.cm.access(...)` invocation, so any hook in the call tree can read
or annotate it.

**Framework-owned keys** (set/managed by `cmeta/core.py`; treat as read-only):

| Key | What it holds |
|-----|---------------|
| `origin` | Set once on the first call: `{'pwd': cwd, 'params': original_request, 'cli': {'caller','cmd'}, 'control': first_control_params}`. |
| `nested_call` | Depth counter — incremented on entry, decremented on exit. |
| `control` | Current call's control flags (`con`, `verbose`, `quiet`, `base`, `api`, `json`, ...). Swapped in per call and restored on exit. |
| `command` | Resolved command name (after alias resolution). |
| `category` | Category `cmeta_ref_parts` (`{artifact_alias, artifact_uid}`). |
| `category_artifact` | Full category artifact (`{path, cmeta, cmeta_ref_parts, ...}`). |
| `category_cmeta` | Category's own `_cmeta.yaml`. |
| `last_self_time` | Perf timing of the last call (seconds). |
| `repro` | Present when `--repro` is set. |

**Attach your own state under a namespaced key** — never touch the ones
above. Because ctx is shared across the whole call tree, you can pass
anything (session id, trace id, an AI-agent budget, tool-call breadcrumbs)
without threading extra args through every function:

CLI (nested `--ctx.<key>[.<child>]=<v>` flags parse into a dict):

```bash
cx experiment run e1 \
   --ctx.agent.session_id=sess-42 \
   --ctx.agent.trace_id=trace-abc \
   --ctx.agent.budget_tokens=20000 \
   --dump                         # writes post-call ctx to cmeta-ctx.json
```

Python:

```python
r = cm.access({
    'category': 'experiment', 'command': 'run', 'arg1': 'e1',
    'ctx': {'agent': {'session_id': 'sess-42', 'budget_tokens': 20000}},
})
```

Inside any category `api/v1.py` hook:

```python
def run_(self, ctx, arg1=None):
    agent = ctx.setdefault('agent', {})
    self.logger.info(f"agent session={agent.get('session_id')}")
    agent['budget_tokens'] = agent.get('budget_tokens', 0) - 100

    # Delegate — the same ctx is threaded down automatically.
    p = self._prepare_input_from_params({'ctx': ctx, 'arg1': arg1}, base=True)
    p['command'] = 'find'
    return self.cm.access(p)
```

Notes:
- ctx is **not deep-copied per call** (only the top level of `params` is), so
  hook edits are visible upstream. `copy.deepcopy` a subtree before passing it
  down if you want isolation.
- Put only JSON-serialisable data in ctx if you'll rely on `--dump` /
  `--repro` — file handles or model objects should live outside ctx.
- Great primitive for AI-agent orchestration: agents inject a session/trace
  namespace once at the top-level call and read/write it from any hook the
  framework subsequently invokes.

### 5.5 Working from the current directory (`cx .`)

When you are already inside a repo, you can use `.` in place of the category.
cMeta walks up from the current directory to detect the enclosing **repo**, then
the enclosing **category**, and — if you are inside an artifact — the **artifact**
itself, so you don't have to type any of them.

**Inside a category directory** (e.g. `<repo>/log/`), the category and repo are
inferred:

```bash
cd <repo>/log

cx . add xyz             # add a new artifact 'xyz' to this category/repo
cx . find                # list artifacts in this category/repo
cx . find --tags=demo    # ...pruned by tags
```

Tip: `find` is a good universal lister — unlike a bare `ls` it also prunes by
tags and other filters, so you can use it everywhere.

**Inside an artifact directory** (e.g. `<repo>/log/xyz/`), the artifact is the
target, so no category or artifact name is needed:

```bash
cd <repo>/log/xyz

cx . load                # print this artifact's meta
cx . update --meta.description="..."   # update this artifact
cx .                     # with no command, defaults to 'info'
```

You can still pass an explicit category after `.` to override detection
(`cx . <category> <command>`). The same detection is available from Python via
`cm.utils.common.detect_cid_in_the_current_directory(cm)`.

**`cx . info` — identify whatever you are standing in.** This is the everyday
"where am I?" command. It resolves the current directory and prints the
artifact path, the full **cRef**, and the alias/UID of the artifact, its
category and its repo:

```console
$ cd <repo>/category/config
$ cx . info
Artifact path: ...\cmeta\internal-repo\category\config

cRef=category,dd9ea50e7f76467f::config,cc6bfe174be847ed

artifact_alias: config
artifact_uid:   cc6bfe174be847ed
category_alias: category
category_uid:   dd9ea50e7f76467f
repo_alias:     internal
repo_uid:       21f6ce28893e4de8
```

Useful flags:

| Flag | Effect |
|------|--------|
| *(default)* | Copies the **cRef** to the clipboard, ready to paste into meta or a message. |
| `--clip-` | Don't touch the clipboard (the boolean off-switch). |
| `--url` | Also print — and copy — a **cRef URL** pointing at the configured server, for sharing a link to the artifact. |
| `--name` | Copy the artifact **name** to the clipboard instead of the cRef. |
| `--jf=<file>` | Write the full result — including the artifact's complete `_cmeta` metadata — as JSON. |

`cx <category> info <alias>` does the same for an artifact you name explicitly,
without having to `cd` into it.

### 5.6 Generating UIDs (and other `utils` helpers)

When you create an artifact or a category by hand — `mkdir` plus a
`_cmeta.yaml`, rather than `cx <category> add` — you need a UID for the
`artifact:` field. Generate one with:

```bash
cx utils uid                 # -> 7dc971950cfe4eec  (also copied to the clipboard)
cx utils uid --clipboard-    # print only, don't touch the clipboard
cx utils uuid                # -> 7938f1d4-7187-4bed-baae-26b9345635c5 (UUID4)
```

`cx utils uid` prints a **16-hex-character** cMeta UID — the same format the
framework generates internally — and copies it to the clipboard by default, so
you can paste it straight into a `_cmeta.yaml`. Suppress that with the boolean
off-switch `--clipboard-`. For scripts, take it from the return dict:

```bash
cx utils uid --clipboard- --jf=uid.json     # {"return": 0, "uid": "29576481b25846ba"}
```

From Python the underlying helper is `cm.utils.names.generate_cmeta_uid()`.

Remember to register a hand-made artifact afterwards so it enters the index:
`cx <category> index <repo>:<artifact>` (see §11).

### 5.7 Searching across categories (`cx utils find_by_cid`)

`cx <category> find <alias>` searches **one** category. When you don't know
which category something is in — or want to sweep several at once —
`cx utils find_by_cid` searches by a full **cRef** and accepts wildcards on
both halves:

```bash
cx utils find_by_cid "<category>::<artifact>"
```

```bash
# Just a name — the category defaults to '*', so this searches everywhere
cx utils find_by_cid "config"

# Any artifact whose name contains 'server', in any category
cx utils find_by_cid "*::*server*"

# Every artifact of every category whose name starts with 'cserver'
cx utils find_by_cid "cserver*::*"

# Narrow by tags as well
cx utils find_by_cid "*::*" --tags=demo,gpu
```

It prints the path of each match (and returns them in `artifacts`). If you omit
`::`, cMeta prepends `*::` for you — so a bare name is a global search. Omitting
the argument entirely searches for `*`.

This is the tool for finding **related artifacts across categories** — the same
alias or tag used by a task, a tool and a result, for instance — which the
per-category `find` cannot express.

| Flag | Effect |
|------|--------|
| `--tags=<t1,t2>` | Filter matches by tags. |
| `--skip_non_indexed` | Skip `no_index` categories (see §12.2) — much faster when some categories are scanned rather than indexed. |
| `--web` | Accept a web-style `cmeta:///?<encoded-cid>` input and URL-decode it. |
| `--ask` | Prompt for the CID interactively. |
| `--far` | Open the first match in the FAR file manager (Windows). |

`cx utils smart_find_by_cid` is the wrapped-CID variant, for pasting a cRef that
is embedded in surrounding text.

Other frequently used `utils` commands (full list: `cx utils --help`):

| Command | What it does |
|---------|--------------|
| `cx utils uid` / `uuid` | Generate a 16-hex cMeta UID / a UUID4. |
| `cx utils yaml2json <file>` / `json2yaml` | Convert between YAML and JSON. |
| `cx utils pickle2json <file>` (`pkl2json`) / `json2pickle` | Convert between pickle and JSON — handy for inspecting `index/*.pkl`. |
| `cx utils find_by_cid <cid>` / `smart_find_by_cid` | Find artifacts by a full cRef / CID. |
| `cx utils artifacts` | Analyse all artifacts across all categories. |
| `cx utils copy_text_to_clipboard` / `copy_date_to_clipboard` | Clipboard helpers. |
| `cx utils utf8sig_to_utf8 <file>` | Strip a UTF-8 BOM. |
| `cx utils convert_old_entries <path>` | Convert legacy CK/CM/CMX entries. |

Note that `utils` sets `skip_base_category_commands: true` — it provides
helpers only and has no `find`/`create`/`delete` of its own.

---

## 6. Resolving categories & artifacts (alias / UID / `alias,UID`)

Every category and artifact has:
- an **alias** — human-friendly name (e.g. `repo`)
- a **UID** — stable 16-hex-char identifier (e.g. `f4f792ab40c7498f`)

You may pass any of these three forms wherever a category or artifact reference
is expected:

| Form | Example | Notes |
|------|---------|-------|
| alias | `repo` | Human-friendly, may break on rename. |
| UID | `f4f792ab40c7498f` | Always resolves, not readable. |
| `alias,UID` | `repo,f4f792ab40c7498f` | **Best.** The **UID is authoritative**; the alias is advisory. Rename-safe. |

Additional forms:
- Cross-repo reference: `<repo>:<name>`, e.g. `cmeta-aops:my-script`.
- Full cMeta ref (`cRef`): `<category>::<artifact>`, e.g.
  `category,dd9ea50e7f76467f::repo,f4f792ab40c7498f`.

Because `alias,UID` resolution only looks at the UID, references written in
that form remain valid even if the alias is later renamed. This is what makes
cMeta references **semantically portable** across projects, forks and time —
recommended for anything you share, publish, or automate against.

---

## 7. cMeta repositories

### 7.1 What a cMeta repo is

A **cMeta repository** is a directory that:

1. Has an `_cmr.yaml` (or `_cmr.json`) at its root — the *repo descriptor*.
2. Contains artifacts under `<repo>/<category>/<artifact>/`, each with its own
   `_cmeta.yaml`.

### 7.2 The three tiers you always have

Every cMeta install starts with three tiers of repositories, indexed together
under a single `<CMETA_HOME>`:

| Tier | Path | Editable? | Purpose |
|------|------|-----------|---------|
| **1. Internal (shipped)** | `<pkg>/cmeta/internal-repo/` (package data) — override with `CMETA_INTERNAL_REPO_PATH` | Read-only (part of the pip package) | Foundational categories: `category`, `repo`, `config`, `utils`, `app`, `cache`, `experiment`, `note`, `journal`, `log`, ... See the built-in-plugins table in §4. |
| **2. Default local scratch** | `<CMETA_HOME>/repos/local/` — created on first launch | Yes | A ready-to-use scratch pad. Anything you create with `cx <cat> add <alias>` (no `<repo>:` prefix) lands here. Safe to delete the whole `<CMETA_HOME>` to start from scratch. |
| **3. User repos** | Wherever you pull/init them — registered in `<CMETA_HOME>/repos.json` | Yes | Repos you `cx repo get`, `init`, `plug` from git/zip/`cmeta://` — plus any local folder you register. See §7.5. |

`repos.json` is an **ordered map**; the framework reads it top-to-bottom, so
the built-in local repo is checked first when resolving refs (and the internal
repo is always present as tier 1).

### 7.3 Where things live under `<CMETA_HOME>`

```
<CMETA_HOME>/
├── repos.json                # registry (ordered map path → {'meta': {...}})
├── repos/
│   └── local/                # the default local scratch repo (tier 2)
│       └── _cmr.yaml
│   └── <alias>/              # each `cx repo get` / `init` lands here by default
│       └── _cmr.yaml
└── index/
    └── <category>.pkl        # fast per-category index (rebuild with cx --reindex)
```

### 7.4 Picking `<CMETA_HOME>` (env vars + per-project collections)

`<CMETA_HOME>` is resolved by `cmeta/config.py::check_init_vars_from_env()` in
this order (first match wins):

1. `$CMETA_HOME` env var (or `--home=<path>` on the CLI, or `home=` in Python).
2. `$VIRTUAL_ENV/CMETA` — auto-lives inside your active venv.
3. `$CONDA_PREFIX/CMETA` — auto-lives inside your active conda env.
4. `$CMETA_HOME2` env var (secondary fallback, useful for team-wide defaults).
5. `~/CMETA` — your user home.

> **Installing `cx` globally does not give you a global home.** Rule 2 reads an
> environment variable, not the location of the `cx` you invoked — so a `cx`
> installed as a standalone command (`uv tool install cmeta`, see
> [installation.md](installation.md)) still resolves `<CMETA_HOME>` to
> `$VIRTUAL_ENV/CMETA` whenever it runs in a shell with a project venv
> activated. Export `CMETA_HOME` if you want one home regardless, or
> `CMETA_HOME2` if an activated venv should still be allowed to win.

Because each `<CMETA_HOME>` has its own `repos.json`, its own local scratch
repo, and its own index, you can maintain **multiple independent collections
of repos** and switch between them just by changing an env var. Typical setups:

```bash
# Per-project collection (Bash / zsh):
export CMETA_HOME=/data/projects/proj-a/cmeta
cx repo list       # sees only proj-a repos

export CMETA_HOME=/data/projects/proj-b/cmeta
cx repo list       # sees only proj-b repos

# One-shot override (no export):
cx --home=D:\work\clientX <category> <command>

# Windows batch:
set CMETA_HOME=D:\my-cmeta-home
uv run cx repo list
```

Related env vars:

| Env var | Purpose |
|---------|---------|
| `CMETA_HOME` | Primary override. Any string path. |
| `CMETA_HOME2` | Secondary fallback used only if none of `CMETA_HOME`/`VIRTUAL_ENV`/`CONDA_PREFIX` are set. |
| `CMETA_INTERNAL_REPO_PATH` | Override tier 1 — point the internal repo at a different path (used to hack on the shipped categories). |
| `VIRTUAL_ENV`, `CONDA_PREFIX` | If set (and `CMETA_HOME` isn't), `<CMETA_HOME>` becomes `<venv>/CMETA` — a nice way to keep repo state co-located with a Python env. |

Deleting a `<CMETA_HOME>` directory is safe — cMeta will recreate the shell
(default local repo, registry, index) on next launch. Only your custom
artifacts inside `<CMETA_HOME>/repos/` would be lost; external user repos
registered via `cx repo plug` live wherever you told them to and are not
affected.

### 7.5 Registered repos on disk

Registered repos live in **two places**:

- `<CMETA_HOME>/repos.json` — the registry (an ordered map of
  `path → {"meta": {"method": "...", "subdir": "...", ...}}`).
- `<CMETA_HOME>/repos/<alias>/` — the default drop location when cMeta itself
  clones or extracts a repo. You can put a repo anywhere else and register it
  via `--path=` (see §7.6, `plug`).

Adding, removing or updating repos triggers an index refresh automatically. If
you changed things outside cMeta, see §10.

### 7.6 `_cmr.yaml` — the repo descriptor

Every repo has an `_cmr.yaml` at its root. Example from
`cmeta/internal-repo/_cmr.yaml`:

```yaml
artifact:  internal,21f6ce28893e4de8       # repo alias + stable UID
category:  repo,f4f792ab40c7498f           # always the "repo" category
authors:   "[Grigori Fursin](https://cKnowledge.org/gfursin)"
copyright: "..."
permanent: true                            # cx repo delete refuses this repo
version:   0.29.0
```

Fields worth knowing:

| Field | Purpose |
|-------|---------|
| `artifact` | Repo identity — `<alias>,<UID>`. Generated for you if you omit it on `cx repo add`. |
| `category` | Always `repo,f4f792ab40c7498f` (repos are themselves artifacts of the `repo` category). |
| `permanent: true` | Refuse `cx repo delete` (used for shipped/foundational repos). |
| `subdir` | Optional — if set, only that subdirectory of the repo is scanned for artifacts. Handy when a git repo carries mixed content. |
| `method` | Set at registration time — `git`, `zip`, `local`, `local_zip`. Tells the framework how the repo was obtained. |
| `keep: true` | Keep the descriptor and registration on `--reindex` even if the path is temporarily missing (useful for USB / network drives). |
| `version`, `authors`, `copyright` | Provenance. |

Everything else you'd want to attach to the repo (tags, description, ...) is
just extra YAML keys — they are preserved and returned by `cx repo find`.

### 7.7 Getting a repo (pull existing)

```bash
# From the default cTuning zip mirror (short-hand):
cx repo get cmeta://<name>                        # latest
cx repo get cmeta://<name> --checkout=<tag>       # specific tag/version

# By git URL (method auto-detected as "git"):
cx repo get <alias> --url=https://github.com/<org>/<repo>
cx repo get <alias> --url=git@github.com:<org>/<repo>.git --checkout=main

# By zip URL (auto-detected from .zip suffix, method = "zip"):
cx repo get <alias> --url=https://example.com/<name>.zip

# By local zip file:
cx repo unzip <path-to-zip>            # method = "local_zip"

# Short-hand for cTuning-hosted git repos:
cx repo get <name>                     # -> https://github.com/ctuninglabs/<name>
cx repo get <org>@<name>               # -> https://github.com/<org>/<name>
```

Where things end up:
- Git clone / zip extract → `<CMETA_HOME>/repos/<alias>/` (unless you pass
  `--path=<other-dir>` or `--folder=<name>`).
- Registration entry appended to `<CMETA_HOME>/repos.json`.
- If `_cmr.yaml` is missing at the root it's created; if present it's read and
  augmented (UID generated when absent).

### 7.8 Creating a new local repo

Use when you're starting a fresh repo of your own artifacts (no upstream):

```bash
cx repo add <alias>              # alias for create (via global alias add→create)
cx repo create <alias>           # create <CMETA_HOME>/repos/<alias>/ with _cmr.yaml
cx repo init <alias>             # same, but errors if the repo already exists
```

Or point the new repo at any path you like:

```bash
cx repo add <alias> --path=<absolute-or-relative-path>
cx repo add <alias> --path=<path> --meta.description="research notes"
```

`init` is the "safe first-time" variant — it refuses to reuse an existing
folder that's already registered. `add`/`create` will happily attach to an
existing empty folder.

### 7.9 Attaching / detaching an existing directory

Already have a directory (git-cloned by hand, cloned by a colleague, sitting
on a shared drive)? Register it without moving files:

```bash
cx repo plug                     # register the current directory as a repo
cx repo plug <path>              # register the given directory
cx repo plug <alias> --path=<path>

# Detach without deleting the files:
cx repo unplug <alias>           # unregister a repo
cx repo unplug                   # unregister repo detected in current directory
```

`plug` is `get_` with `--local --path=...`. `unplug` is `delete` with the
`--unplug` flag, which unregisters without touching the folder.

### 7.10 Everyday repo commands

```bash
cx repo list                     # list registered repos (unsorted, insertion order)
cx repo find <alias-or-uid>      # find a repo by alias/UID
cx repo status <alias>           # git status + remote URL for git-backed repos
cx repo pull <alias>             # git pull; also refreshes the index
cx repo update <alias>           # same as pull
cx repo checkout <alias> <ref>   # git checkout branch/tag/commit
cx repo space <alias>            # disk usage for the repo
cx repo zip <alias>              # dump repo to cmr-<alias>-YYYYMMDD-HHMMSS.zip
cx repo unzip <path.zip>         # inverse of the above (see §6.3)
cx repo delete <alias>           # unregister AND delete files (unless permanent)
```

`cx repo move` is intentionally **not supported** (renaming a repo would break
`alias,UID` references written elsewhere) — create a new repo, copy/move
artifacts, and delete the old one if truly needed.

### 7.11 Programmatic use

Everything above is available from Python too:

```python
r = cm.access({'category': 'repo', 'command': 'add',
               'arg1': 'my-notes',
               'path': '/data/my-notes'})

r = cm.access({'category': 'repo', 'command': 'get',
               'arg1': 'cmeta-aops',
               'url':  'https://github.com/ctuninglabs/cmeta-aops',
               'checkout': 'main'})

r = cm.access({'category': 'repo', 'command': 'list'})
```

---

## 8. Configuring categories via `config` artifacts

Any tunable value (server URLs, API keys, default repos, cache locations,
tool paths, ...) belongs in a **`config` artifact** — an artifact of the
built-in `config` category whose payload lives in a `data.json` sidecar next
to `_cmeta.yaml`.

Categories and apps pick up config artifacts by name via `cm.access(...)`,
so you (or another agent) can change behavior at runtime without touching
any code.

### 8.1 The `config` category — five commands

| Command | Behavior |
|---------|----------|
| `cx config get <name>` | Return the config (`config_cmeta` key on the response). Reads `<config>/<name>/data.json`. |
| `cx config read <name>` | Same as `get`, follows the base-read semantics. |
| `cx config show <name>` | Pretty-print as flat `--meta.a.b=c` lines — ready to copy into a `set`. |
| `cx config set <name> --meta.<key>[.<child>]=<value>` | Deep-merge the given keys into `data.json` (creates the config artifact if missing). |
| `cx config unset <name> --meta.<key>[.<child>]` | Deep-remove the given keys. |

Notes:
- Configs are just artifacts — everything else works too: `cx config ls`,
  `cx config find <name>`, `cx config rm <name>`, `cx config info <name>`.
- Multiple named configs coexist under `<repo>/config/`. Conventions the
  shipped code already uses: `default` (framework defaults), `cserver` (the
  local FastAPI app), `ctuning_server` (external API creds), `task` (cache /
  version checks).
- Values live in JSON, but you edit them from the CLI using dot-notation.

### 8.2 Everyday examples

```bash
# Point cMeta at your own git org for `cx repo get <name>` short-hand:
cx config set default --meta.default_git_repo=my-org --meta.default_git=git@github.com:

# Move the big file / build cache off the system drive:
cx config set task --meta.file_cache=D:\cmeta-file-cache --meta.check_versions

# Store credentials for the cTuning zip mirror once:
cx config set ctuning_server --meta.api_key=$CTUNING_API_KEY --meta.skip_ssl_certificate-

# Configure the local web server (used by `cserver` / `cx app run cserver`):
cx config set cserver --meta.api_keys,=key1,key2
cx config set cserver --meta.default_page=/repos

# Ask for one shared password before showing any page (§8.2.1):
cx config set cserver --meta.password="a passphrase of your own"

# Inspect and confirm:
cx config show default
cx config show cserver

# Remove a single key or a whole subtree:
cx config unset cserver --meta.api_keys
cx config unset default --meta.default_git_repo
```

### 8.2.1 A shared password in front of `cserver`

By default `cserver` listens on `127.0.0.1` and anyone who can reach the port
can read every page. As soon as it listens on a routable address — so that a
phone or a tablet can open it, directly or through a private overlay network —
it is worth putting one shared password in front of it:

```bash
cx config set cserver --meta.password="a passphrase of your own"
cx config unset cserver --meta.password          # open again
```

The next request from a browser shows a small prompt instead of the page. A
correct answer is remembered in the session cookie, so the password is asked
once per browser and not again on every page.

| Key | Default | What it does |
|---|---|---|
| `password` | — | The shared password. Any value here turns the prompt on. |
| `password_sha256` | — | The same, as a SHA-256 digest, so the plain text is not stored on disk. Takes precedence over `password`. |
| `password_allow_local` | `yes` | Requests from the machine itself skip the prompt, so the CLI and local development are untouched. Set to `no` to be asked locally too. |
| `password_realm` | `cMeta server` | The heading shown on the prompt. |
| `password_max_attempts` | `10` | Wrong answers from one address before it is told to wait. |
| `password_lockout_min` | `5` | How many minutes that wait lasts. |

```bash
# store only the digest:
cx config set cserver --meta.password_sha256=$(python -c \
  "import hashlib,getpass;print(hashlib.sha256(getpass.getpass().encode()).hexdigest())")
```

Two related settings are read from the environment rather than the config,
because the cookie is signed before any config is loaded. Both are exported by
`cx app run cserver --param.<key>=<value>` and by a `param:` block in this same
config:

| Environment variable | Default | What it does |
|---|---|---|
| `CSERVER_SESSION_SECRET` | random per start | The key that signs the session cookie. Left unset, restarting the server asks everyone for the password again; pin it to a long random string to keep sessions across restarts. |
| `CSERVER_SESSION_MAX_AGE` | `604800` (a week) | How long a session cookie stays valid, in seconds. |

What this is and is not. It is a door with a lock: one shared secret, no
accounts, no password reset, and a naive per-address delay after repeated wrong
answers. It keeps port scanners and curious passers-by out of a server that
answers on a routable address. It is not a login system, and unless the server
is reached over HTTPS or through an encrypted overlay network the password
travels in clear text — so use a passphrase you do not use anywhere else.

A request carrying a valid `api_keys` value is let through without the prompt,
so existing automation keeps working; an AJAX call is answered with a JSON
`401` rather than the HTML prompt, so a page can report it instead of rendering
a form into its own data.

### 8.3 The pattern from Python — reading a config from any category

Every category that needs configuration should declare `config` under
`uses_categories:` in its own `_cmeta.yaml` and dereference by
alias-and-UID at call time (rename-safe):

```yaml
# <repo>/<category>/<my-cat>/_cmeta.yaml
uses_categories:
  config: config,cc6bfe174be847ed
```

```python
# <repo>/<category>/<my-cat>/api/v1.py

class Category(InitCategory):
    def do_something_(self, ctx, arg1=None):
        # Load a specific config artifact by name
        r = self.cm.access({
            'category': self.cmeta['uses_categories']['config'],
            'command':  'get',
            'arg1':     'my-cat',          # or self.cm.cfg['default_config_name']
        })
        if self.cm.catch_error(r): return r

        cfg = r['config_cmeta']
        endpoint = cfg.get('endpoint', 'https://default.example')
        timeout  = cfg.get('timeout',  30)
        # ... use cfg values ...

        return {'return': 0}
```

Real examples in the shipped code:
- `internal-repo/category/repo/api/v1.py` reads the `default` config for
  `default_git`, `default_git_repo`, `default_cmeta_repo_url` and the
  `ctuning_server` config for `api_key` + `skip_ssl_certificate`.
- `internal-repo/category/app/api/v1.py` reads the config named in an app's
  `_cmeta.yaml::config_name` (if set) and merges `env`, `param`, `vars` into
  the process env before running `_run.bat` / `_run.sh`.

### 8.4 Configuring a shipped app (the `app` convention)

An artifact of category `app` can declare a linked config in its
`_cmeta.yaml`:

```yaml
# <repo>/app/<my-app>/_cmeta.yaml
category:         app,554a9a2199104713
config_name:      my-app                     # links to config,<uid>::my-app
default_env:                                  # baseline env vars merged first
  MYAPP_HOST: 127.0.0.1
  MYAPP_PORT: '8080'
param_env_prefix: MYAPP_                      # --param.PORT=9000 → MYAPP_PORT=9000
run_script:       _run                        # default; picks .bat / .sh
```

At runtime `cx app run <my-app>` (or the entry-point convenience script if
one is defined) does:

1. `cm.access({'category': 'config,cc6bfe174be847ed', 'command': 'get',
   'arg1': 'my-app'})` → `config_cmeta`.
2. Merges `config_cmeta.env` **first** (config-provided baseline), then
   `default_env` from the app artifact (overlay).
3. Merges `config_cmeta.param` and CLI `--param.*` flags → env vars using
   `param_env_prefix + <KEY.UPPER()>`.
4. cd's into the artifact dir and runs `_run.bat` / `_run.sh`.

So you can retune a shipped app without editing any files:

```bash
cx config set my-app --meta.env.MYAPP_HOST=0.0.0.0 --meta.env.MYAPP_PORT=9090
cx config set my-app --meta.param.debug=1
cx app run my-app
```

### 8.5 The `cserver` (FastAPI) example — configs consumed by async server code

The shipped `cserver` app is a FastAPI service that reads its config on
startup and uses it in request handlers. Distilled from
`cmeta/internal-repo/app/cserver/src/app.py`:

```python
from fastapi import FastAPI
from cmeta.core_async import CMetaAsync

app = FastAPI()
cm  = CMetaAsync(max_workers=8)
cfg = {}

@app.on_event("startup")
async def load_config():
    global cfg
    r = await cm.access({
        'category': 'config,cc6bfe174be847ed',  # `config` category by UID
        'command':  'get',
        'arg1':     'cserver',
    })
    if r['return'] > 0:
        raise RuntimeError(r['error'])
    cfg = r['config_cmeta']

@app.get("/health")
async def health(request):
    # Live-read a config value on every request:
    allowed = cfg.get('api_keys', [])
    return {"ok": True, "requires_auth": bool(allowed)}
```

Update `cserver`'s config at any time from the CLI — the running server will
pick up new values on the next call because `cfg` is a live dict populated
from a single mutable source of truth:

```bash
cx config set cserver --meta.api_keys,=k1,k2
```

Tips:
- Reference the `config` category by `alias,UID` (or `uses_categories`) so
  your server keeps working if the `config` alias is ever renamed.
- Use `CMetaAsync` in FastAPI/anything asyncio — it delegates `access()` to
  a `ProcessPoolExecutor` so a long CLI-style call can't block the event
  loop.
- Keep per-run overrides in `ctx['agent']` (see §5.4) — they don't leak into
  the persisted config.

### 8.6 Where config artifacts live on disk

- Default local scratch: `<CMETA_HOME>/repos/local/config/<name>/`
- Any other repo: `<repo>/config/<name>/`

Each folder contains a `_cmeta.yaml` (identity) and a `data.json` (payload).
You can hand-edit either; run `cx --reindex` if you moved things around
outside cMeta.

---

## 9. Adding a new category (plugin)

A **category** groups a set of commands and is itself an artifact of the
`category` category.

```bash
# Into the default local repo:
cx category add <alias>

# Into a specific repo:
cx category add <repo>:<alias>

# With extras:
cx category add <alias> --tags=tag1,tag2 --meta.description="What this manages"
```

This creates:

```
<repo>/<alias>/
├── _cmeta.yaml           # UID, category ref, api version, ...
└── api/
    └── v1.py             # copied from v1-template.py — edit this
```

Verify:

```bash
cx category find <alias>          # confirm it's indexed
cx <alias> --help                 # lists inherited base commands + your test_/test2
cx <alias> test hello --flag1     # smoke-test the generated api/v1.py
```

### 9.1 Editing `api/v1.py`

Every category API subclasses `cmeta.category.InitCategory`. The **trailing
underscore on a method name matters**:

```python
from cmeta.category import InitCategory

class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    # Convention A — typed kwargs + ctx (RECOMMENDED for new commands)
    def hello_(self, ctx, arg1=None, flag1=False, name="world"):
        """One-line summary shown in `cx <category> hello --help`."""
        print(f"Hello {name}! arg1={arg1} flag1={flag1}")
        return {'return': 0}

    # Convention B — raw params dict (for dispatch / thin wrappers)
    def dump(self, params: dict):
        import json
        print(json.dumps(params, indent=2))
        return {'return': 0}
```

- `foo_` (single trailing `_`, not `__`) → called with `**command_params`
  (typed kwargs, incl. `ctx`). User invokes it as `foo`.
- `foo`, `foo__`, `foo___` → called with **one positional `params` dict**.
  Trailing `__`/`___` are stripped from the CLI name (used to avoid clashing
  with Python builtins like `list`, `type`).

Return contract: `{'return': 0, ...}` on success; `{'return': >0, 'error':
'...'}` on failure. The CLI turns non-zero into a stderr message + exit code.

### 9.2 Prefer `self.cm.utils.*` over stdlib re-implementations

Every hook has `self.cm.utils` bound to the framework helpers (`common`,
`files`, `names`, `net`, `sys`, `cli`). **Default to these.** Every shipped
category (`repo`, `config`, `app`, `utils`, `note`, `experiment`, ...) is
written this way, and there are strong reasons for you to follow suit:

- **Reusability & composability** — helpers return the same
  `{'return': 0, ...}` dict as `access()`, so errors propagate with a plain
  `if r['return'] > 0: return r`; no adapters, no wrappers.
- **Portability** — cross-platform path quoting, Windows process-tree kill,
  extended-path support for `rm -rf`, file locks that work on all OSes,
  atomic writes.
- **Debuggability** — helpers log through `self.logger` and honour
  `--debug` / `CMETA_DEBUG=1` and `self.fail_on_error` — consistent behavior
  across every category.
- **Safety** — `safe_read_file` / `safe_write_file` do file locking, atomic
  rename, retries, and format auto-detection (YAML/JSON). Rolling your own
  with `open()` risks partial writes and races.
- **Reproducibility** — `sys.run(..., save_script='...', capture_env=True,
  hide_in_cmd=[...], hide_in_env=[...])` writes the exact command that ran,
  captures its env delta, and masks secrets — for free.

Common substitutions to reach for first:

| Instead of | Use |
|------------|-----|
| `open(p).read()` + `json/yaml.load` | `self.cm.utils.files.safe_read_file(p, lock=True)` |
| `open(p, 'w').write(...)` | `self.cm.utils.files.safe_write_file(p, obj, atomic=True)` |
| `shutil.rmtree(p)` | `self.cm.utils.files.remove_files_and_dirs_in_path(p)` |
| `subprocess.run([...])` | `self.cm.utils.sys.run(cmd, env=..., envs=..., capture_env=True, hide_in_cmd=[...], save_script='...')` |
| Manual dict recursion | `self.cm.utils.common.deep_merge(target, source, append_lists=..., ignore_root_keys=...)` |
| `del d[k]` / manual pruning | `self.cm.utils.common.deep_remove(target, spec)` |
| `d.get('a', {}).get('b')` | `self.cm.utils.common.smart_get(d, 'a.b')` |
| `d.setdefault('a', {})['b'] = v` | `self.cm.utils.common.smart_set(d, 'a.b', v)` |
| `s.split(',')` for tags | `self.cm.utils.common.normalize_tags(s)` |
| `str(uuid.uuid4())[:16]` | `self.cm.utils.names.generate_cmeta_uid()` |
| `urllib.request.urlopen` | `self.cm.utils.net.download(url, path=..., api_key=..., skip_ssl_certificate=...)` |
| `requests.post` (for cMeta APIs) | `self.cm.utils.net.access_api(url, params)` |

Also on `self.cm` itself: `self.cm.j`, `self.cm.jj`, `self.cm.js` (safe JSON
print), `self.cm.q` / `self.cm.qq` (path quoting), `self.cm.error(...)`,
`self.cm.catch_error(r)`.

Concrete example from `internal-repo/category/config/api/v1.py::set_`:

```python
r = utils.files.safe_read_file(path, lock=True, keep_locked=True,
                               fail_on_error=self.fail_on_error,
                               logger=self.logger)
if r['return'] > 0 and r['return'] != 16: return r
config_data      = r.get('data', {})
config_file_lock = r.get('file_lock')

if unset:
    config_data = self.cm.utils.common.deep_remove(config_data, meta)
else:
    config_data = self.cm.utils.common.deep_merge(config_data, meta,
                                                  append_lists=False)

r = utils.files.safe_write_file(path, config_data,
                                file_lock=config_file_lock, atomic=True,
                                fail_on_error=self.fail_on_error,
                                logger=self.logger, sort_keys=False)
if r['return'] > 0: return r
```

Six lines of helper calls replace ~40 lines of `open`/`json`/lock/rename
boilerplate — and behave identically on Windows.

Full catalog of `cm.utils.*` in [`.claude/skills/use-cmeta-python/SKILL.md`
§6.6 and §7](../.claude/skills/use-cmeta-python/SKILL.md).

### 9.3 Calling other categories from your plugin

Use `self.cm.access(...)`. For **cross-category** calls, declare dependencies
in your `_cmeta.yaml`:

```yaml
uses_categories:
  config: config,cc6bfe174be847ed
  utils:  utils,234ce5e3262e4d52
```

Then reference them semantically — this is rename-safe because the UID is
authoritative:

```python
r = self.cm.access({'category': self.cmeta['uses_categories']['config'],
                    'command':  'get',
                    'arg1':     self.cm.cfg['default_config_name']})
```

For the **base CRUD of your own category**, use
`_prepare_input_from_params(..., base=True)` and set `command`:

```python
def status_(self, ctx, arg1=None):
    p = self._prepare_input_from_params({'ctx': ctx, 'arg1': arg1}, base=True)
    p['command'] = 'find'
    return self.cm.access(p)
```

Add per-category CLI aliases in `_cmeta.yaml`:

```yaml
command_aliases:
  hi: hello
  greet: hello
```

---

## 10. Adding artifacts of a category

Any category (that doesn't set `skip_base_category_commands: true`) supports:

```bash
cx <category> add <alias> --yaml --tags=t1,t2
cx <category> add <repo>:<alias> --meta.owner="me"
cx <category> add <alias> --virtual --path=<existing-dir>   # register w/o moving files
```

For each artifact, cMeta writes a `_cmeta.yaml`. Useful fields:

| Field | Purpose |
|-------|---------|
| `artifact` | UID (or `alias,UID`). Required. |
| `category` | Category reference in `alias,UID`. |
| `tags` | List of strings for tag search. |
| `authors`, `copyright`, `creation_timestamp` | Provenance. |
| `permanent: true` | Refuses `delete` (shipped foundational artifacts). |
| `no_index: true` | Skip the fast index; find by filesystem scan (useful for very large / ephemeral artifacts — see §12.2). |
| `sharding_slices: [2, 2]` | Category-level: spread artifacts into nested sub-directories by slicing the alias, for categories with very many artifacts (see §12.1). |
| **Category-only fields** | Only meaningful on category artifacts. |
| `last_api_version: <n>` | Highest API version the category ships. |
| `base_category_default_api_versions: {'1': 1}` | Base API version to inherit per category API version. |
| `min_cmeta_version: {'1': '0.30.0'}` | Minimum cMeta version per API version. |
| `skip_base_category_commands: true` | Category doesn't inherit base CRUD. |
| `command_aliases` | Per-category CLI aliases. |
| `find_sort: false` | Disable default alpha-sort for `find`. |
| `uses_categories` | Cross-category dependencies (see §9.3). |
| `default_env`, `param_env_prefix`, `config_name` | Used by the `app` category to run apps with pre-configured env vars + a named `config` artifact. |

For advanced needs (per-artifact automation), an artifact can ship its own
`api_v1.py` with `customize*` hooks called at defined lifecycle points from a
`_desc.yaml` automation pipeline.

---

## 11. Fast index & when to `cx --reindex`

cMeta keeps a **per-category fast index** at
`<CMETA_HOME>/index/<category>.pkl` so `find`/`list`/`load` don't have to scan
the filesystem. The framework refreshes it automatically:

- when you `create`/`update`/`delete` artifacts,
- when repos are added/removed via `cx repo` operations,
- on first launch if the index is missing.

Force a full clean rebuild when things look inconsistent — after a manual move,
a hand-edit of `_cmeta.yaml`, a `git pull` inside a repo, a `CMETA_HOME` wipe,
or if `cx <category> find <alias>` returns something surprising:

```bash
cx --reindex
```

It's safe, idempotent and typically fast. Categories that set `no_index: true`
in their `_cmeta.yaml` are always found by filesystem scan and are never
written to the index.

Task-level content caches produced by workflows live under the `cache`
category and are managed separately:

```bash
cx cache show                # list cache entries (with --tags= filters, etc.)
cx cache clean               # prune according to policy
cx cache delete <alias-or-uid>
```

Reproducibility helpers:

```bash
cx <category> <command> ... --repro    # writes cmeta-repro-input.json / -output.json
cx <category> <command> ... --dump     # writes cmeta-ctx.json (full ctx)
```

---

## 12. Scaling a category to very many artifacts

A category normally stores each artifact as one directory directly under
`<repo>/<category>/`. That is fine for hundreds of artifacts. At tens or
hundreds of thousands it stops being fine: filesystems slow down with huge flat
directories, and the per-category index pickle grows until loading it costs
more than the lookup saves.

Two independent mechanisms handle this — **sharding** (spread artifacts into
sub-directories) and **`no_index`** (don't index the category at all). They can
be used separately or together.

### 12.1 Sharding — `sharding_slices`

`sharding_slices` is a list of integers that splits the artifact's directory
name into nested sub-directories. Each number is how many characters to take
for that level:

```yaml
# in the category's _cmeta.yaml
sharding_slices: [2, 2]
```

```
shard_name('example', [2, 2])  ->  ex/am/example
```

so the artifact lands at `<repo>/<category>/ex/am/example/` instead of
`<repo>/<category>/example/`. With `[2, 2]` you get at most 256×256 leaf
directories at two levels, which keeps any single directory small.

The **name being sharded is the artifact's alias** — or its UID when the
artifact has no alias. That is what makes the "by year" layout work: if your
aliases are date-prefixed (as the `note` category's are, e.g.
`20260802.my-note`), then

```yaml
sharding_slices: [4, 2]
```

gives `2026/08/20260802.my-note` — artifacts grouped by year, then month.

Names shorter than the slices are padded with underscores so the depth stays
predictable:

| Alias | `sharding_slices` | Path |
|-------|-------------------|------|
| `example` | `[2, 2]` | `ex/am/example` |
| `example` | `[3, 2]` | `exa/mp/example` |
| `example` | `[1]` | `e/example` |
| `ab` | `[2, 2]` | `ab/__/ab` |
| `a` | `[2, 2]` | `a_/__/a` |
| `20260802.my-note` | `[4, 2]` | `2026/08/20260802.my-note` |

**Where to declare it.** Two places, with the repo winning:

```yaml
# 1. On the category (default for every repo) — <repo>/category/<name>/_cmeta.yaml
sharding_slices: [2, 2]
```

```yaml
# 2. On a repo, per category UID (overrides the category default) — _cmr.yaml
sharding_slices:
  <category-uid>: [4, 2]
```

The per-repo form lets one repo shard a category deeply while another keeps it
flat — useful when only your bulk-data repo has the volume problem.

**What cMeta handles for you.** `create`, `move`/`copy` and `delete` all apply
the same sharding when computing paths, the index record stores
`sharding_slices_num` so lookups know how deep to look, and deleting an
artifact prunes shard directories that have become empty. You keep referring to
artifacts by `alias` / `UID` / `alias,UID` exactly as before — the layout is an
implementation detail.

> Change `sharding_slices` only on an empty (or freshly migrated) category.
> Existing artifacts are **not** relocated automatically, and the old paths
> won't match the new scheme.

### 12.2 Skipping the index — `no_index`

```yaml
# in the category's (or artifact's) _cmeta.yaml
no_index: true
```

Artifacts of a `no_index` category are never written to
`<CMETA_HOME>/index/<category>.pkl`. Lookups fall back to scanning the
filesystem (`Repos.find_in_file_system`), which still supports wildcards on the
alias.

Use it when:

- the category holds so many artifacts that maintaining and loading the index
  costs more than it saves;
- artifacts are created and deleted constantly (logs, scratch results), so the
  index would be rewritten continuously;
- the artifacts are managed by something outside cMeta and the index would go
  stale anyway.

The trade-off: **you rely on the alias (or the directory layout) to find
things**, so aliases must be unique and predictable within the category — the
index is what normally makes UID lookups fast. Filesystem scanning is slower
for broad queries but avoids the index entirely, which is the point.

`cx --reindex` skips these categories, and a lookup can skip them explicitly
with `skip_non_indexed` (exposed by `cx utils find_by_cid --skip_non_indexed`).

### 12.3 Combining them

Sharding and `no_index` solve different halves of the problem and compose well:
sharding keeps the *filesystem* fast, `no_index` keeps the *index* from
becoming the bottleneck. A large archive category with date-prefixed aliases
might use both:

```yaml
sharding_slices: [4, 2]   # <category>/2026/08/<alias>/
no_index: true            # find by scanning, alias is the key
```

---

## 13. Where to look next

Other guides ([documentation index](README.md)):

- Why cMeta exists and its design principles: [motivation.md](motivation.md)
- Installing and verifying: [installation.md](installation.md)
- Error handling and debugging: [error-handling.md](error-handling.md)
- Async use and concurrency:
  [async-and-concurrency.md](async-and-concurrency.md)
- The `config` category in depth: [configuration.md](configuration.md)
- Connecting to the cTuning.ai platform: [cplatform.md](cplatform.md)
- Lineage, publications and citation: [history.md](history.md)

Source of truth in the code:

- Framework agent guide: [`AGENTS.md`](../AGENTS.md)
- Add-a-plugin walkthrough for AI agents:
  [`.claude/skills/add-plugin/SKILL.md`](../.claude/skills/add-plugin/SKILL.md)
- Base commands (source of truth for signatures): `cmeta/category_api_v1.py`
- Alias/UID parsing: `cmeta/utils/names.py`
- Repo/index internals: `cmeta/repos.py`
- Global config & CLI aliases: `cmeta/config.py`
