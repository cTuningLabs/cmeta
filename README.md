[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![PyPI version](https://badge.fury.io/py/cmeta.svg)](https://pepy.tech/project/cmeta)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://github.com/ctuninglabs/cmeta)
[![Test cMeta core](https://github.com/cTuningLabs/cmeta/actions/workflows/test-core.yml/badge.svg)](https://github.com/cTuningLabs/cmeta/actions/workflows/test-core.yml)
[![Author: Grigori Fursin](https://img.shields.io/badge/author-Grigori%20Fursin-1f6feb)](https://cTuning.ai/@gfursin)

# cMeta (Common Meta Framework)

**cMeta** (also known as **cX**) is a small, portable framework that turns the pieces
of research and engineering work — code, data, models, toolchains, workflows, agents,
notes and results — into **uniform, reusable artifacts**: plain directories with one
metadata file, linked to each other by stable identifiers and reached through **one
interface**:

```bash
cx <category> <command> [args] [--flags]          # from a terminal
```

```python
cm.access({'category': ..., 'command': ..., ...})   # from Python
```

We develop cMeta to make R&D **collaborative, reproducible, reusable, scalable,
portable and sustainable**: work that colleagues and their AI agents can pick up,
run, understand and build upon years later, in the simplest way that works — no
database, no daemon, no service to stand up, just files, one CLI, one Python API and
minimal dependencies. It is free and open source under Apache-2.0.

If you know **Obsidian** or other "second brain" tools, the idea will feel familiar:
local plain files, links between everything, an open format you are never locked
into, and plugins. cMeta applies that idea to R&D work and adds one thing — the
artifacts are **live**. A toolchain, a benchmark, a model, a dataset, a measured
number or a report is something you *run* or *query* through the same interface,
not only something you read, and an AI agent can do it exactly as a person does.

Created and developed by [Grigori Fursin](https://cTuning.ai/@gfursin) at cTuning
Labs. cMeta is the next generation of the **Collective Knowledge** technology
([CK, now hosted by MLCommons](https://github.com/mlcommons/ck)); the story and the
publications are in [docs/history.md](docs/history.md).

## Try it in two minutes

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # uv, if you have none (Windows: see Installation below)
uv tool install "cmeta[server]"                    # cx / cmeta / cserver on PATH, in their own environment
export CMETA_HOME="$HOME/CMETA"                    # one home for all your content repositories

cx --version                                       # the engine version and the home it resolved
cx repo get ctuninglabs@cmeta-aops                 # pull the reusable automations from GitHub
cx tool setup python                               # detect (or install) a tool and pin its version
cx program run test-nmm-c-cpu cpu                  # compile and run a small matmul benchmark
cx task run test-python -j                         # run a task; the trace shows every step it reused
cx app run cserver                                 # browse everything at http://127.0.0.1:8004
```

The same from Python:

```python
from cmeta import CMeta

cm = CMeta()
r = cm.access({'category': 'program', 'command': 'run', 'arg1': 'test-nmm-c-cpu', 'arg2': 'cpu'})
if r['return'] > 0:
    raise Exception(r['error'])
```

## Where to go next

| You want to ... | Go to |
|-----------------|-------|
| understand the idea step by step | the [course from 0 to 1](https://cTuning.ai/project/cmeta/cmeta.course/) |
| install on your OS with your package manager | the [interactive installer](https://cTuning.ai/project/cmeta/cmeta.install/), or [docs/installation.md](docs/installation.md) |
| see what you can run today | [cmeta-aops](https://github.com/cTuningLabs/cmeta-aops) — tools, tasks, programs, models, datasets — and the [catalogues on cTuning.ai](https://cTuning.ai/project/cmeta) |
| learn the CLI and the Python API | [docs/common-commands.md](docs/common-commands.md), then [docs/using-cmeta.md](docs/using-cmeta.md) |
| add your own category, artifacts or repository | [Using cMeta in one page](#using-cmeta-in-one-page) below, and the shipped [skills](.claude/skills/) |
| point an AI agent at the project | [AGENTS.md](AGENTS.md) and [llms.txt](llms.txt) |

cMeta works with the tools people already use: any operating system and target
platform, from the data center to edge and mobile devices; AI coding assistants
and agents such as Claude Code, OpenAI Codex and OpenClaw; automation and
workflow frameworks, through the same `cx` CLI and `access()` API; and
knowledge-management systems such as Notion and Obsidian.

---

## Why — what cMeta is for

Shared research stops working for ordinary reasons: a path breaks, an environment
drifts, the context that made a run work is lost, and what a component was actually
for lives in someone's head rather than in the component. None of that is a hard
research problem — it is bookkeeping, and it is why work gets redone instead of
reused. Removing that whole class of problem is what this project is for
([docs/motivation.md](docs/motivation.md)). cMeta exists to support R&D that is
**collaborative, reproducible, reusable, scalable, portable and sustainable**, in
the simplest way that works:

| Aim | What it means here |
|-----|--------------------|
| **Collaborative** | Share work as content repositories others plug in and *run*, not as instructions to follow. `alias,UID` references survive renames, forks, machines and years. |
| **Reproducible** | The context of a run is recorded with the run. This improves *gradually* and is deliberately not claimed as a guarantee — full determinism across heterogeneous environments is hard and remains ongoing R&D. |
| **Reusable** | An artifact describes what it is rather than being wired into one pipeline, so the same toolchain, program, model or dataset carries over to another project unchanged. |
| **Scalable** | Encode more complexity by adding artifacts and categories, not by growing the engine. The framework extends sideways, in many directions; the core stays small. |
| **Portable** | The same automation runs anywhere, any time, adapting to the software and hardware the user actually has — toolchains are detected, installed if missing, and pinned. |
| **Sustainable** | Work outlives the people who did it. The method, the dependencies, the versions and the provenance are recorded beside the result, so whoever picks it up next — in six months, or after the author has left — *resumes* instead of reconstructing. |

**And it has to stay simple, with minimal dependencies.** No database, no
daemon, no service to stand up, no binary format: just a directory and file
structure, reached through one CLI, one Python API and one metadata convention.
Everything cMeta stores can be read, edited, diffed and fixed by hand — which is
what lets the work outlive the tool.

**How it does that: complexity becomes abstractions you can operate.** A serious
project accumulates more complexity than anyone can hold in their head. cMeta
expresses each piece of it — a toolchain, a dataset, a model, a workflow, a
measured number, a concept — as one artifact that is **simple** (a folder and a
metadata file), **reusable** (it states what it is, not where it fits), **live**
(you run it, rather than read about running it) and **interconnected** (artifacts
reference each other by `alias,UID`, forming a graph rather than a pile). You then
*operate* those abstractions through one interface, *understand* them by reading
what they declare, and *build upon* them by composing them into larger ones.
Because each stays inspectable down to its inputs, versions and provenance, a
question can be taken back to **first principles** — what was measured, under what
conditions, on what date — instead of being settled by folklore. The same design
is what makes the work [FAIR](https://www.go-fair.org/fair-principles/) —
findable, accessible, interoperable, reusable — by construction rather than by
extra effort; see
[docs/motivation.md](docs/motivation.md#fair-by-construction).

**That same recorded context is what makes AI-powered R&D work.** An agent is only as good
as the context it can assemble, and assembling context is usually the expensive
part: what exists, how it was run, in which environment, and whether a number is
still current. In cMeta that context is already recorded and already
machine-readable — identity, declared dependencies, connections between
artifacts, dates and provenance on records — so an agent can discover, compose,
run and hand back work through the **same `access()` interface a person uses**.
A graph a newcomer can pick up is, for the same reasons, a graph an agent can
operate.

**Two ways people describe it.** As a *common engine for "operating systems for
AI"*: a thin, uniform layer that connects, abstracts and orchestrates the code,
data, models, agents and hardware that modern AI systems are assembled from, much
as an operating system manages the resources of a machine. And as the *substrate
of a research assistant*: AI agents operating a growing body of machine-readable,
self-describing automations instead of improvised scripts, discovering what
exists, composing it, extending it and handing the result back in a form a person
can read and rerun. The aim is deliberately modest — not a system that invents
science, but one that lets experiments, builds and benchmarks be set up, varied and
repeated without re-deriving the same work each time.

More detail in [docs/motivation.md](docs/motivation.md).

---

## Project status

**A research and prototyping project by Grigori Fursin and cTuning Labs —
stable, low-activity, and maintained alongside active downstream work.**

cMeta also takes a first pass at co-developing the framework itself together
with AI agents (see the shipped [skills](.claude/skills/), the `ctx`
dictionary, and the uniform `access()` interface documented in
[`docs/using-cmeta.md`](docs/using-cmeta.md)).

The framework is **stable in its current shape and I use it daily**, but my
active attention has moved to the downstream repositories that build on top
of it. What that means in practice:

- Few breaking changes expected in the near term.
- Slow release cadence — mostly targeted fixes.
- The design goal is a small, uniform core that AI agents can extend via
  content repositories and skills, **not** a big feature surface.

Known defects and rough edges that are understood but not yet fixed are tracked
in [docs/known-issues.md](docs/known-issues.md).

**You're very welcome to try it, fork it, build on it — and to send a pull
request.** Contributing is deliberately low-ceremony: Apache 2.0, no CLA to
sign, and a one-flag `git commit -s` sign-off (DCO) that certifies you have the
right to submit the change. See [`CONTRIBUTING.md`](CONTRIBUTING.md) — the whole
flow is five steps.

Bug reports and questions via GitHub issues are welcome too; I answer when I
can. Large new-feature proposals are best raised as an issue first, since the
direction is driven by what the downstream projects need and the design goal is
a small core. If you're building something interesting on top of cMeta, do reach
out via [my page](https://cTuning.ai/@gfursin).

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
  [Resolving categories & artifacts](#6-resolving-categories--artifacts)).
- **Content-addressed caching & better reproducibility** — identical work is
  not repeated, and the full context of a run is captured to help reproduce it.
  (Full determinism across heterogeneous environments is hard; cMeta improves
  reproducibility but doesn't yet fully solve it — ongoing R&D.)
- **Virtualized portability** — toolchains, compilers, drivers and runtimes are
  detected, isolated and pinned to abstract over OS and accelerator differences.
- **Unified interface for humans and agents** — AI agents drive the same
  discovery, composition and execution surface people use.
- **Serial or async, with concurrency safety guards** — the same engine runs
  one call at a time from a script or `await`s from FastAPI (`CMetaAsync`).
  Unlike the earlier frameworks in this line, concurrent execution is a
  supported mode: cross-process file locks and atomic writes protect the index
  and artifact metadata when several processes share one `<CMETA_HOME>`
  (see [docs/async-and-concurrency.md](docs/async-and-concurrency.md)).

---

## Use cases

cMeta is the engine; what it does depends on the content repositories plugged
into it. The uses it is built for:

- **A research assistant for open science.** Encode R&D as executable,
  self-describing automations rather than prose, one-off scripts and remembered
  command lines — so the *method* travels with the result, inspectable,
  shareable and rerunnable by other people and by their agents.
- **Collaborative research, development and experimentation.** Share work as
  content repositories that others plug in and run. `alias,UID` references stay
  valid across renames, forks and years, so results, experiments and the
  workflows that produced them remain referenceable over time.
- **Reproducible benchmarking and software/hardware co-design.** Detect and
  install toolchains, build and run programs across operating systems and
  compute targets (CPU, CUDA, …), and reuse installs, downloads and builds
  through content-addressed caching — so an experiment can be repeated and
  varied without re-deriving the setup.
- **AI-agent operations.** Agents drive the same `access()` surface as humans,
  with `ctx` threading session/trace state through nested calls and skills
  describing how to extend the framework itself.
- **Web services and dashboards.** `CMetaAsync` runs cMeta behind FastAPI — the
  shipped `cserver` app and the [cTuning.ai](https://cTuning.ai) platform are
  both built this way.
- **Notes, journals and knowledge.** The same artifact model covers notes,
  journals, logs and reports, so knowledge lives next to the automations it
  describes rather than in a separate silo.

The reference content repository is
**[cmeta-aops](https://github.com/cTuningLabs/cmeta-aops)** — reusable `task`,
`tool`, `program`, `model` and `dataset` artifacts for portable setup, builds
and benchmarking. More background in
[docs/motivation.md](docs/motivation.md#what-people-use-it-for).

---

## Installation

cMeta is normally a tool you use everywhere rather than a dependency of one
project, so the recommended route installs it as a **standalone command** — its
own private environment that you never activate, `cx` / `cmeta` / `cxt` /
`cserver` on `PATH`, and an interpreter [uv](https://github.com/astral-sh/uv)
downloads itself. No system Python, no root, and PEP 668 never enters the
picture:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # uv, if you have none
uv tool install "cmeta[server]"
uv tool update-shell                               # put the shims on PATH

export CMETA_HOME="$HOME/CMETA"                    # one home for every project
cx --version                                       # also prints the home it resolved
```

On Windows, the same three steps:

```bat
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv tool install "cmeta[server]"
uv tool update-shell
setx CMETA_HOME "%USERPROFILE%\CMETA"
```

Installing globally and having a global home are two separate things: with no
`CMETA_HOME` set, an activated virtual environment still captures the home, even
for a globally installed `cx`. And `pip install cmeta` inside a project virtual
environment stays perfectly good when cMeta *is* a dependency of that project.

An interactive installer that assembles the commands for your OS, shell and
package manager lives at
**[cTuning.ai/project/cmeta/cmeta.install](https://cTuning.ai/project/cmeta/cmeta.install/)**;
[docs/installation.md](docs/installation.md) covers every route,
install-from-source, where repositories live, configuration and troubleshooting.

---

## Documentation

The full documentation lives in **[`docs/`](docs/README.md)** — this README is
a summary of it.

| Guide | What it covers |
|-------|----------------|
| [Motivation](docs/motivation.md) | Why cMeta exists, the problem it addresses, design principles. |
| [Installation](docs/installation.md) | pip / `uv` / from source, verification, first configuration, troubleshooting. |
| [Common commands](docs/common-commands.md) | Cheatsheet of everyday commands, incl. the `cx .` current-directory shortcut and `cx . info`. |
| [Using cMeta](docs/using-cmeta.md) | **The getting-started and reference guide** — mental model, CLI flags, artifacts, `ctx`, alias/UID resolution, repositories, configs, adding categories, metadata reference, indexing. |
| [Error handling](docs/error-handling.md) | The return-dict contract, soft errors (code 16), raising errors, and debugging with `fail_on_error` in an IDE. |
| [Async & concurrency](docs/async-and-concurrency.md) | `CMeta` vs `CMetaAsync`, parallel calls, FastAPI, and the safety guards for a shared `<CMETA_HOME>`. |
| [Working with configs](docs/configuration.md) | The `config` category and how categories and apps read their settings. |
| [cTuning.ai platform](docs/cplatform.md) | Connecting cMeta to the hosted platform API. |
| [History & background](docs/history.md) | Lineage (CK → CM/CMX → cMeta), related publications, how to cite. |

API reference for the engine modules is generated with Sphinx — see
[docs/README.md](docs/README.md#building-the-api-reference).

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
| **tests**     | Test artifacts — group and manage test cases as cMeta artifacts. |

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
| `no_index: true` | Skip the fast index for this artifact; found by filesystem scan. Used for categories with very many artifacts. |
| `sharding_slices: [2, 2]` | Category-only. Spread artifacts into nested sub-directories by slicing the alias (`example` → `ex/am/example`), so no single directory holds tens of thousands of entries. Can be overridden per repo in `_cmr.yaml`. |
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

## Background & how to cite

cMeta is the next generation of the **Collective Knowledge** technology: the
cTuning framework and MILEPOST (2006-), [Collective Knowledge (CK)](https://github.com/mlcommons/ck)
with its community Artifact Evaluation at ACM and IEEE conferences, and MLCommons
Collective Mind (CM/CMX) behind the MLPerf automations — the same idea, research and
engineering as reusable, content-addressed components behind one common interface,
with a deliberately smaller engine this time. **[docs/history.md](docs/history.md)**
tells that story with the talks and publications, and explains how to cite cMeta
(GitHub's **"Cite this repository"** button, generated from
[`CITATION.cff`](CITATION.cff), produces APA and BibTeX automatically).

---

## Attribution & reuse

You are free to use, modify and redistribute cMeta under Apache 2.0. Section 4
of the licence asks that you keep the copyright and attribution notices and
reproduce the contents of [`NOTICE`](NOTICE) in your distribution — this
applies equally whether the code was copied by a person or generated with the
help of an AI agent or an LLM.

If you reuse the **concepts** rather than the code, a citation is very welcome —
and so is getting in touch. **Collaboration is actively invited:**
[cTuning.ai/@gfursin](https://cTuning.ai/@gfursin). See
[docs/history.md](docs/history.md#reusing-the-code-or-the-concepts).

AI agents working *on* this repository: see [`AGENTS.md`](AGENTS.md) §5.1 for
the attribution and provenance rules. The repo also ships an **experimental**
[`llms.txt`](llms.txt) (the proposed [llmstxt.org](https://llmstxt.org)
convention) giving agents a curated map of the project — a research/testing
feature; it overrides nothing in `LICENSE` or `NOTICE`.

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

- Project page: [https://cTuning.ai/project/cmeta](https://cTuning.ai/project/cmeta) —
  the [course from 0 to 1](https://cTuning.ai/project/cmeta/cmeta.course/) and the
  [interactive installer](https://cTuning.ai/project/cmeta/cmeta.install/)
- Author: [https://cTuning.ai/@gfursin](https://cTuning.ai/@gfursin)
- Organizations: [cTuning Labs](https://cTuning.ai) and the
  [cTuning foundation](https://cTuning.org)
- [Artifact Evaluation and Reproducibility Initiatives](https://cTuning.org/ae)

If cMeta is useful to you, a ⭐ on GitHub helps other people find it —
[cmeta](https://github.com/cTuningLabs/cmeta) (the engine) and
[cmeta-aops](https://github.com/cTuningLabs/cmeta-aops) (the automations).

## Status

See [Project status](#project-status) at the top of this file.
