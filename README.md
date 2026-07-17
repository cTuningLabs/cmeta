[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![PyPI version](https://badge.fury.io/py/cmeta.svg)](https://pepy.tech/project/cmeta)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://github.com/ctuninglabs/cmeta)
[![Test cMeta core](https://github.com/cTuningLabs/cmeta/actions/workflows/test-core.yml/badge.svg)](https://github.com/cTuningLabs/cmeta/actions/workflows/test-core.yml)
[![Author: Grigori Fursin](https://img.shields.io/badge/author-Grigori%20Fursin-1f6feb)](https://cTuning.ai/@gfursin)

# cMeta (Common Meta Framework)

**cMeta** (also known as **cX**) is a small, portable framework for unifying,
interconnecting and reusing code, data, models, agents and knowledge across
projects, platforms and time through a single uniform interface.

It is designed for collaborative and reproducible research, development and
experimentation across AI, ML, systems and other complex workloads — including
self-optimizing and self-adapting software/hardware stacks.

> Created, architected and developed by
> [Grigori Fursin](https://cTuning.ai/@gfursin) — originator of the long-term
> vision, concept, architecture and successive prototypes behind cMeta.

---

## Project status

**Personal research project — stable, low-activity, maintained in my spare time.**

cMeta is the current iteration of a my long-running personal experiment on how
to make research code, data, models, agents and knowledge composable,
portable and reusable across time. It builds on decades of iteration —
[Collective Knowledge](https://github.com/mlcommons/ck), Collective Mind,
CMX — and now takes a first pass at co-developing the framework itself
together with AI agents (see the shipped [skills](.claude/skills/),
the `ctx` dictionary, and the uniform `access()` interface documented in
[`docs/using-cmeta.md`](docs/using-cmeta.md)).

The framework is **stable in its current shape and I use it daily**, but my
active attention has moved to the downstream repositories that build on top
of it. What that means in practice:

- Few breaking changes expected in the near term.
- Slow release cadence — mostly targeted fixes.
- The design goal is a small, uniform core that AI agents can extend via
  content repositories and skills, **not** a big feature surface.

**You're very welcome to try it, fork it, or build on it.** Bug reports and
questions via GitHub issues are welcome — I answer when I can. I'm not
actively soliciting pull requests or new-feature proposals right now: the
direction is driven by what I need in the downstream projects. If you're
building something interesting on top of cMeta, feel free to reach out via
[my page](https://cTuning.ai/@gfursin).

---

## Core idea

Every part of a workflow — a program, a model, a dataset, a toolchain, a note,
an agent — is represented as a **uniform, composable, content-addressed
artifact** reached through **one interface**:

- Python: `cm.access({'category': ..., 'command': ..., ...})`
- CLI: `cx <category> <command> [args] [--flags]`

cMeta ships a tiny **engine** and a small **built-in content repository** of
foundational categories (plugins). Everything else — your projects, research
artifacts, workflows — lives in **external content repositories** that you pull
in, index and share.

### What you get

- **One uniform interface** to run programs, fetch models, prepare datasets,
  build toolchains, invoke agents, take notes, keep a journal.
- **Composable automations** — workflows are assembled from small reusable
  tasks that *declare what they use* rather than hard-coding scripts.
- **Extensible & pluggable** — new capabilities are added as self-contained
  artifacts (categories, tasks, tools) with optional Python hooks. The framework
  grows by plugging in components, not by modifying the core.
- **Metadata & tags** — structured, machine-readable identity makes anything
  discoverable and reusable by tags rather than by hard-coded paths.
- **Semantic portability via UIDs** — every category and artifact has both a
  human-friendly *alias* and a stable 16-hex-char *UID*. References written as
  `alias,UID` remain valid even if the alias is renamed (see
  [Resolving categories & artifacts](#resolving-categories--artifacts)).
- **Content-addressed caching & better reproducibility** — identical work is
  not repeated, and the full context of a run is captured to help reproduce it.
  (Full determinism across heterogeneous environments is hard; cMeta improves
  reproducibility but doesn't yet fully solve it — ongoing R&D.)
- **Virtualized portability** — toolchains, compilers, drivers and runtimes are
  detected, isolated and pinned to abstract over OS and accelerator differences.
- **Unified interface for humans and agents** — AI agents drive the same
  discovery, composition and execution surface people use.

---

## Installation

```bash
pip install cmeta
cmeta --version
cx --version
```

See [docs/installation.md](docs/installation.md) for `uv`, install-from-source,
configuration and troubleshooting.

---

## Quickstart

Command line:

```bash
cx --help
cx repo list                      # list plugged-in content repositories
cx category list                  # list available categories (plugins)
cx <category> --help              # list commands available in a category
cx <category> <command> --help    # detailed help for a specific command
```

Python:

```python
from cmeta import CMeta

cm = CMeta()
r = cm.access({'category': 'repo', 'command': 'list'})
print(r)
```

CLI alias shortcuts (from `cmeta/config.py`): `add→create`, `rm→delete`,
`ls→list`, `search→find`, `mv→move`, `cp→copy`, `ren/rename→move`,
`load→read`.

### Common CLI flags

Run `cx --help` for the full list. The most useful ones (all work on any
command):

| Flag | Meaning |
|------|---------|
| `--help`, `-h` | Show help for the framework, a category, or a command. |
| `--version`, `-V` | Print cMeta version + check for a newer release. |
| `--reindex` | Clean and rebuild `<CMETA_HOME>/index/*.pkl` when lookups look stale. |
| `--verbose`, `-v` | Verbose progress output. |
| `--quiet`, `-q` | Auto-accept default answers on any interactive prompt. |
| `--repro`, `-r` | Save inputs/outputs to `cmeta-repro-input.json` / `-output.json`. |
| `--base` | Force the shared base command instead of a category's override. |
| `--api <n>` | Pin category API version (loads `api/v<n>.py`). |
| `--con` | Force console output. |
| `--json`, `-j` | Print the return dict as JSON. |
| `--json_file <path>`, `--jf` | Also write the JSON return dict to a file. |
| `--dump` | Write full call context to `cmeta-ctx.json` at the end. |
| `--home <path>` | One-shot override for `<CMETA_HOME>` (also: `CMETA_HOME`). |
| `--debug` | `--log_level=DEBUG` + `--fail_on_error`. (`CMETA_DEBUG=1`) |
| `--fail_on_error`, `--fail` | Raise on first error instead of returning an error dict. |
| `--log_level <lvl>`, `--log-level` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`. |
| `--log_file <path>`, `--log-file` | Log to a file. (`CMETA_LOG_FILE`) |
| `--pause_if_error`, `--pif` | Pause before exit on error (useful for double-clicked `.bat`). |

### Flag syntax at a glance

- Booleans: `--flag` (True), `--flag-` (False), `--no-flag` (False).
- Strings: `--key=value` or `--key value` (repeats overwrite — last wins).
- Lists: `--key,=v1,v2,v3` (trailing comma on the key).
- Nested dicts: `--parent.child=value` merges into `{'parent': {'child': ...}}`.
- Reusable param files: `@input.yaml` / `@input.json` deep-merges into the
  parsed params (`@@input.yaml` also deletes the file after reading).
- Positional tokens → `arg1`, `arg2`, ...
- Hyphen and underscore are equivalent (`--log-level` == `--log_level`).

Full descriptions: see
[docs/using-cmeta.md §3](docs/using-cmeta.md#3-common-cli-flags).

---

## Using cMeta in one page

### 1. Find and inspect artifacts

```bash
cx <category> find <alias-or-uid>              # returns matches from index
cx <category> ls                               # list all artifacts in a category
cx <category> ls --tags=demo,gpu               # tag filter (AND-match)
cx <category> info <alias>                     # show path + cRef, copy to clipboard
cx . info                                      # auto-detect artifact in current dir
```

### 2. Read / update artifact metadata

```bash
cx <category> read <alias>                     # read _cmeta.yaml/json into a dict
cx <category> update <alias> --meta.description="..."   # merge into metadata
cx <category> tags <alias> --add=t1,t2 --remove=t3      # edit tags
```

### 3. Call one category from another (Python)

Anything reachable from the CLI is reachable from Python via `cm.access`:

```python
r = cm.access({'category': 'repo', 'command': 'list'})
if r['return'] > 0: raise Exception(r['error'])

# Load an artifact's metadata
r = cm.access({'category': 'config', 'command': 'get', 'arg1': 'default'})
config_cmeta = r['config_cmeta']

# Find with a UID for guaranteed resolution:
r = cm.access({'category': 'category,dd9ea50e7f76467f',
               'command': 'find', 'arg1': 'repo,f4f792ab40c7498f'})
```

Inside a category's `api/v1.py`, use `self.cm.access(...)`. For semantic
portability, prefer resolving other categories via `self.cmeta['uses_categories']`
declared in your `_cmeta.yaml` (see the shipped `app`, `repo`, `journal`
categories).

### 4. Get a new content repository

```bash
cx repo get cmeta://<name>                     # from the default cTuning zip mirror
cx repo get <alias> --url=https://github.com/<org>/<repo>
cx repo get <alias> --url=<git-url> --checkout=main
cx repo get <alias> --url=<zip-url>            # zip is auto-detected
cx repo get <alias> --path=<local-path> --local
cx repo list                                   # see what's plugged in
cx repo unplug <alias>                         # detach without deleting
```

Repos are cloned/extracted into `<CMETA_HOME>/repos/<alias>/` and registered in
`<CMETA_HOME>/repos.json`. Every repo folder has an `_cmr.yaml` at its root.

### 5. Add your own category (plugin) and artifacts

```bash
cx category add <alias>                        # in the default (local) repo
cx category add <repo>:<alias>                 # in a specific repo
cx <category> add <alias> --tags=t1,t2 --yaml  # create an artifact of that category
```

`cx category add` scaffolds `<repo>/<category>/<alias>/` with `_cmeta.yaml` and a
starter `api/v1.py` you can edit to add commands. See
[docs/using-cmeta.md](docs/using-cmeta.md#9-adding-a-new-category-plugin) and the
[`add-plugin` skill](.claude/skills/add-plugin/SKILL.md) for a full walkthrough
of function-name conventions (`foo_` vs `foo`) and `api_v1.py` hooks.

Repository-side workflows (pull / init / plug / unplug / zip / ...) are covered
in [docs/using-cmeta.md §7](docs/using-cmeta.md#7-cmeta-repositories) and the
[`add-repo` skill](.claude/skills/add-repo/SKILL.md).

Concise, portable **how-to-use-cMeta** references for reuse in downstream
repos: [`use-cmeta-python`](.claude/skills/use-cmeta-python/SKILL.md) and
[`use-cmeta-cli`](.claude/skills/use-cmeta-cli/SKILL.md) skills — cover
`access()`, `ctx` (including AI-agent context threading), base commands,
helpers under `cm.utils`, `cm.packages`, and CLI conventions.

### 6. Resolving categories & artifacts

Every category and artifact has:
- an **alias** — human-friendly name (e.g. `repo`)
- a **UID** — 16-hex-char stable identifier (e.g. `f4f792ab40c7498f`)

You can pass any of these three forms wherever a category or artifact reference
is expected:

| Form | Example | Notes |
|------|---------|-------|
| alias | `repo` | Convenient, but can break if renamed. |
| UID | `f4f792ab40c7498f` | Always resolves, but not human-readable. |
| `alias,UID` | `repo,f4f792ab40c7498f` | **Best.** Human-readable *and* stable — the **UID is authoritative**, the alias is advisory. Rename-safe. |

For cross-repo references, prefix with a repo name: `<repo>:<alias-or-uid>`.
For linking one artifact from another, use the full **cRef** form
`<category>::<artifact>`, e.g. `category,dd9ea50e7f76467f::repo,f4f792ab40c7498f`.

Because the `alias,UID` form ignores the alias during lookup, category and
artifact aliases can be renamed later without breaking anything that referenced
them by UID — this is what makes cMeta references **semantically portable**
across projects, forks and time.

### 7. Index & caching (when to `cx --reindex`)

cMeta keeps a **fast lookup index** at `<CMETA_HOME>/index/<category>.pkl` —
one pickle file per category — so `find`/`list`/`load` don't have to scan the
filesystem. The framework rebuilds the index automatically when repos are
added/removed via `cx repo`, and updates it in-place on
`create`/`update`/`delete`.

If you edited artifacts outside cMeta (moved folders, edited `_cmeta.yaml` by
hand, `git pull`-ed a repo, cleared `CMETA_HOME`, or things simply look
inconsistent), force a full rebuild:

```bash
cx --reindex
```

This is safe, idempotent and typically fast. Categories that opt out with
`no_index: true` in `_cmeta.yaml` are found by scanning the filesystem instead.
Task caches produced by workflows live under the `cache` category and can be
inspected/pruned with `cx cache show` / `cx cache clean` / `cx cache delete`.

---

## Built-in repository and plugins

cMeta ships a small **internal content repository** at
`cmeta/internal-repo/` (`_cmr.yaml` → `internal,21f6ce28893e4de8`) that provides
the foundational plugins. Every plugin is a folder at
`internal-repo/<category>/<artifact>/`.

The framework treats each **category** as a plugin type. New categories can be
added at any time with `cx category add <name>`.

### Foundational categories shipped in `internal-repo/`

| Category      | What it manages / provides |
|---------------|----------------------------|
| **category**  | The category system itself — `cx category add/list/find/delete/move` create and manage new plugins. |
| **repo**      | Content repositories — `get` (aka `add`), `clone`, `pull`, `checkout`, `status`, `zip`/`unzip`, `plug`/`unplug`, `space`, `list`. |
| **config**    | Named configuration artifacts — `get`, `set`, `unset`, `read`, `show`. |
| **utils**     | General helpers — UID/UUID, JSON⇄YAML conversion, clipboard helpers, artifact utilities. Skips base CRUD commands. |
| **app**       | Runnable applications. Ships the `cserver` local FastAPI web app (`cx app run cserver`). |
| **script**    | Portable shell/Python scripts. |
| **asset**     | Data/model/file assets managed as first-class artifacts. |
| **cache**     | Content-addressed cache entries — `show`, `clean`, `delete`. |
| **experiment**| Experiment records for collaborative and reproducible research. |
| **result**    | Results of experiments and runs. |
| **research**  | Research artifacts (papers, notebooks, hypotheses) — `create`. |
| **report**    | Reports generated from experiments or notes. |
| **journal**   | Chronological journal entries — `create`. |
| **note**      | Individual notes — `create`. |
| **log**       | Structured logs — `record`. |
| **docs**      | Documentation artifacts. |
| **website**   | Website builds — `build`. |
| **work**      | Work items / tasks — `create`. |

Every category above inherits the standard base commands (`find`, `list`,
`read`, `create`, `update`, `delete`, `move`, `copy`, `info`, `tags`, `get`,
`set`, `index`, `test`) from `cmeta/category_api_v1.py`, and adds its own
commands in its `api/v1.py`.

### `_cmeta.yaml` / `_cmeta.json` fields worth knowing

Every artifact has a `_cmeta.yaml` (preferred, human-editable) or `_cmeta.json`
alongside it. The framework reads whichever is present. Common fields:

| Field | Purpose |
|-------|---------|
| `artifact` | The artifact's UID (or `alias,UID`). Required. |
| `category` | Category reference in `alias,UID` form. |
| `tags` | List of strings for tag-based search. |
| `authors`, `copyright`, `creation_timestamp`, `last_update_timestamp` | Provenance. |
| `permanent: true` | Refuses `delete` (used for shipped foundational artifacts). |
| `no_index: true` | Skip the fast index for this artifact; found by filesystem scan. |
| **Category-only fields (below)** | Only meaningful on category artifacts. |
| `last_api_version: <n>` | Highest API version the category ships (loads `api/v<n>.py`). |
| `base_category_default_api_versions: {'1': 1}` | Which base API version this category inherits from, per category API version. |
| `min_cmeta_version: {'1': '0.17.4'}` | Minimum cMeta version required per API version. |
| `skip_base_category_commands: true` | Category doesn't inherit any base CRUD; only its own methods (e.g. `utils`). |
| `command_aliases: {hi: hello}` | Per-category CLI aliases (global ones live in `cmeta/config.py`). |
| `find_sort: false` | Disable default alphabetical sort for `find`. |
| `uses_categories: {<name>: <alias>,<uid>}` | Declare cross-category dependencies. Read at runtime as `self.cmeta['uses_categories'][name]` — **the recommended way to reference other categories** so renames don't break your plugin. |
| `default_env`, `param_env_prefix`, `config_name` | Used by the `app` category to run apps with pre-configured env vars merged with a named `config` artifact (see `internal-repo/app/cserver/_cmeta.yaml`). |

Extending an existing category = add a new artifact of it (`cx <cat> add ...`)
or add methods to its `api/v1.py`. Creating a new category = `cx category add
<name>` then edit the generated `api/v1.py`. Both are covered in
[docs/using-cmeta.md](docs/using-cmeta.md).

---

## Repository layout

```
cmeta/               # framework package (engine)
  core.py            # CMeta.access() — the single dispatch
  category.py        # base class for category API modules
  category_api_v1.py # standard base commands inherited by every category
  repos.py           # content-repo indexing / resolution
  packages.py        # tool detection + Python package installation
  config.py          # global cfg dict + param descriptors + command aliases
  cli.py             # console entry points (cmeta, meta, cx, cxt, cserver)
  utils/             # common helpers, files, names (ref parsing), net, sys
  internal-repo/     # built-in content repo (categories + shipped artifacts)
tests/               # pytest suite
docs/                # Sphinx docs, installation.md, using-cmeta.md
```

---

## For AI agents

If you are an AI coding agent working *on* the cMeta engine, start from
[`AGENTS.md`](AGENTS.md) (Claude Code users: also see [`CLAUDE.md`](CLAUDE.md)
and the skills under [`.claude/skills/`](.claude/skills/)).

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

This project may include minor functionality reused from
[MLCommons CK/CM](https://github.com/mlcommons/ck), developed by the same
author and licensed under the same Apache 2.0 terms.

## Copyright

Copyright (C) 2025–2026 [Grigori Fursin](https://cTuning.ai/@gfursin) and
[cTuning Labs](https://cTuning.ai).

## Links

- Author: [https://cTuning.ai/@gfursin](https://cTuning.ai/@gfursin)
- Organizations: [cTuning Labs](https://cTuning.ai) and the
  [cTuning foundation](https://cTuning.org)
- [Artifact Evaluation and Reproducibility Initiatives](https://cTuning.org/ae)

## Status

See [Project status](#project-status) at the top of this file.
