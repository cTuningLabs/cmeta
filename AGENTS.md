# AGENTS.md — Working context for AI agents on the cMeta framework

> Guidance for AI coding agents working on **cMeta** itself (the `cmeta` Python
> package / CLI `cx` · `cmeta`). This is the *engine*; it executes **artifacts**
> (programs, models, datasets, tasks, notes, ...) that live in content
> repositories. Keep this file short, factual and current.

---

## 1. What this project is

**cMeta** (aka **cX**) is a small, portable framework for unifying,
interconnecting and reusing code, data, models, agents and knowledge through one
uniform interface:

- Python: `cm.access({'category': ..., 'command': ..., ...})`
- CLI: `cx <category> <command> [args] [--flags]`

**License:** Apache-2.0. **Python:** 3.9–3.14.

This repo ships the framework and a built-in content repository
(`cmeta/internal-repo/`) with foundational categories. All other artifacts live
in external repos (e.g. `cmeta-aops`).

**What it is used for** — worth knowing when you judge whether a change fits:
a research assistant for open science (R&D encoded as executable,
self-describing artifacts that agents and people both discover, compose and
extend); collaborative research, development and experimentation (shared
content repos, rename-safe `alias,UID` references that survive forks and time);
reproducible benchmarking and software/hardware co-design (portable toolchain
setup, builds and runs across OS and compute targets, content-addressed
caching); AI-agent operations; FastAPI services (`CMetaAsync` — the `cserver`
app and the cTuning.ai platform); and notes/journals/logs kept alongside the
automations they describe. Reference content repo:
[`cmeta-aops`](https://github.com/cTuningLabs/cmeta-aops). Fuller version:
`docs/motivation.md`.

Practical consequence: prefer changes that keep the core small and uniform and
push capability into categories/artifacts — that is what lets agents extend the
system without modifying the engine.

---

## 2. Setup, build, test

```bash
pip install -e ".[dev]"        # editable install with dev extras (or [all])
cmeta --version

python -m pytest tests         # tests (pytest; testpaths=tests/, files test_*.py)
python -m pytest tests/test_utils_obj_parse_cmeta_core.py::test_name   # single test
flake8 cmeta                   # lint
python -m build                # build wheel + sdist
```

The commands above are cross-platform truth. Any Windows `.bat` wrappers around
them are the author's local workflow and are not tracked in this repository.

Runtime deps are intentionally minimal: pyyaml, requests, setuptools, wheel,
tabulate, tqdm, filelock, packaging, psutil.

### Useful environment variables
`CMETA_HOME`, `CMETA_DEBUG=1`, `CMETA_LOG=DEBUG|INFO`, `CMETA_LOG_FILE=<path>`,
`CMETA_FAIL_ON_ERROR=yes`, `CMETA_VERBOSE=yes`, `CMETA_INTERNAL_REPO_PATH`,
`CMETA_PIP_INSTALL_ARGS`, and the provenance stamped on new artifacts: `CMETA_AUTHORS`, `CMETA_COPYRIGHT`,
`CMETA_GENERATOR` (JSON: how the artifact was made; with the `artifact_defaults` of a repository's
`_cmr.yaml` - docs/using-cmeta.md §7.6).

---

## 3. Architecture (package `cmeta/`)

| Module | Role |
|--------|------|
| `core.py` | `CMeta` class + `access()` — the one dispatch every request funnels through. Resolves the category artifact, loads its API module, calls the matching command function. |
| `core_async.py` | Async variant of `access()`. |
| `category.py` | `InitCategory` base class every category API subclasses. Provides `_prepare_input_from_params/ctx` helpers used to re-enter `cm.access()`. |
| `category_api_v1.py` | Standard **base** category — implements the shared CRUD commands every category inherits: `find`/`list`/`read`/`update`/`create`/`delete`/`move`/`copy`/`info`/`tags`/`get`/`set`/`index`/`test`. |
| `repos.py` | `Repos` — index and resolve content repositories + artifacts (by alias / UID / tags / wildcards). Owns the per-category `.pkl` index files. |
| `packages.py` | `Packages` — detect installed tools/versions and auto-install Python packages. |
| `config.py` | Global `cfg` dict, param descriptors, env-var handling, command aliases (`add→create`, `rm→delete`, `ls→list`, `search→find`, `mv→move`, ...). |
| `cli.py` | CLI entry points wired in `pyproject.toml` `[project.scripts]`: `main_cmeta`/`main_meta`/`main_cx`/`main_cxt`/`main_cserver` + `u*` unbuffered variants. |
| `version.py` | `__version__` — single source of truth (wired via dynamic version in `pyproject.toml`). |
| `utils/` | Helpers: `common`, `files`, `names` (cmeta ref parsing), `net`, `sys`, `cli`. |
| `internal-repo/` | Built-in content repo shipped as package data (see §4). |

### Core concepts implemented by the code

- **Uniform interface.** Every operation is
  `access({'category': ..., 'command': ..., ...})`. Add functionality by
  extending categories/commands/hooks — not side entry points.
- **`ctx` (context) dict.** Created (or accepted) on the first `access()`,
  threaded through every nested call as a shared bus. Framework keys:
  `origin`, `nested_call`, `control`, `command`, `category`,
  `category_artifact`, `category_cmeta`, `last_self_time`, `repro`. External
  callers (esp. AI agents) may attach namespaced state under their own key
  (`ctx['agent']`, `ctx['trace']`, ...); it survives across nested calls and
  is captured by `--dump`. See `docs/using-cmeta.md §5.4`.
- **Category.** An artifact type; a folder with `_cmeta.yaml`
  (`category: category,dd9ea50e7f76467f`) + `api/v1.py`.
- **Artifact.** Any content identified by `_cmeta.yaml` or `_cmeta.json` (UID,
  category ref, tags, features) inside a content repo. Optional `_desc.yaml` =
  automation pipeline (`uses` → `prepend`/`append`/`update`, referencing tasks
  by `alias,UID`). Optional per-artifact `api_v1.py` for hooks.
- **Content repo.** Directory with `_cmr.yaml` (repo metadata). The framework
  indexes multiple repos and resolves refs across them.
- **Three repo tiers per `<CMETA_HOME>`:** (1) the shipped internal repo
  (`cmeta/internal-repo/`; overridable via `CMETA_INTERNAL_REPO_PATH`),
  (2) a default local scratch repo auto-created at `<CMETA_HOME>/repos/local/`,
  (3) any user repos pulled/plugged in and listed in `<CMETA_HOME>/repos.json`.
  `<CMETA_HOME>` resolves in order: `CMETA_HOME` → `VIRTUAL_ENV/CMETA` →
  `CONDA_PREFIX/CMETA` → `CMETA_HOME2` → `~/CMETA` — swap the env var to
  keep separate collections per project.
- **Base vs. specific commands.** A category inherits from
  `category_api_v1.py` and adds/overrides in its own `api/v1.py`. Pass `--base`
  to force the base command; a category `api/v1.py` method can delegate via
  `self._prepare_input_from_params(params, base=True)` then `self.cm.access(...)`.
- **Command function naming (load-bearing).** `core.py` strips trailing
  underscores from method names and picks call style by suffix:
    - `foo_` (single trailing `_`, not `__`) → called with `**command_params`
      (typed kwargs incl. `ctx`). User invokes as `foo`. Use this whenever you
      want typed args + `ctx`.
    - `foo` / `foo__` / `foo___` → called with one positional `params` dict.
      Trailing `__`/`___` are stripped for the CLI name (used to avoid Python
      keyword/builtin clashes: `list__`, `type__`, ...).
- **Command aliases.** Global map in `config.cfg['command_aliases']`;
  per-category overrides via `command_aliases:` in `_cmeta.yaml`.
- **Global CLI flags** are declared in `cmeta/config.py`
  (`params_desc` / `params_command_desc` / `params_command2_desc` /
  `params_command3_desc` / `params_init_desc`). Full user-facing reference in
  `docs/using-cmeta.md` §3 and `README.md`.
- **Resolution model (alias / UID / `alias,UID`).** Every category and artifact
  has an alias *and* a stable 16-hex UID. References accept all three forms;
  when both are given (`alias,UID`), the **UID is authoritative** (see
  `repos.py::find_in_index` and `utils/names.py::parse_cmeta_name`). This makes
  `alias,UID` refs rename-safe — safe for automations, cross-repo links and
  long-lived recipes. Cross-repo: `<repo>:<name>`. Full cRef:
  `<category>::<artifact>`.
- **Fast index + `--reindex`.** Per-category pickles at
  `<CMETA_HOME>/index/<category>.pkl` back `find`/`list`/`load`. The framework
  refreshes automatically on `create`/`update`/`delete` and on `cx repo`
  changes. If artifacts were touched outside cMeta, reindex with the narrowest
  command: `cx <category> index <repo>:<artifact>` registers a single folder you
  created by hand (`mkdir` + `_cmeta.*`); `cx <category> update <repo>:<artifact>`
  refreshes the entry after you edit an existing artifact's `_cmeta.*` meta;
  `cx --reindex` rebuilds every pickle and is slow — keep it for manual moves,
  bulk `git pull`, or a cleared `CMETA_HOME`. Payload-only edits (`api/`,
  `files/`, `src/`, `_desc.yaml`) need no reindex. Categories with
  `no_index: true` in `_cmeta.yaml` are always found by filesystem scan.
- **Content-addressed task caching / reproducibility.** Workflow caches keyed
  by content live under the `cache` category (`cx cache show|clean|delete`).
  `--repro` writes `cmeta-repro-input.json` / `-output.json`; `--dump` writes
  `cmeta-ctx.json`. Determinism across heterogeneous environments is
  *improved, not solved* — ongoing R&D; don't overstate it in docs.

---

## 4. `cmeta/internal-repo/` — the built-in content repo

`_cmr.yaml` → `artifact: internal,21f6ce28893e4de8`. Shipped as package data.
Artifacts live under `internal-repo/<category>/<artifact>/`. Categories
present:

`app`, `asset`, `cache`, `category`, `config`, `docs`, `experiment`, `journal`,
`log`, `note`, `repo`, `report`, `research`, `result`, `script`, `tests`,
`utils`, `website`, `work`.

Notable shipped artifacts:
- `app/cserver/` — FastAPI-based local server (`cx app run cserver`, or the
  `cserver` console script). Uses `CSERVER_HOST`/`CSERVER_PORT`/`CSERVER_FLAGS`
  env vars (see `default_env` + `param_env_prefix` in its `_cmeta.yaml`), plus
  `CSERVER_SESSION_SECRET` / `CSERVER_SESSION_MAX_AGE` for the session cookie.
  Access control is read from the `cserver` **config** artifact, not from the
  environment: `api_keys` (a key per request or session) and `password` /
  `password_sha256` (one shared password asked once per browser, exempting
  loopback unless `password_allow_local` says otherwise). The password check is
  an HTTP middleware, so it covers pages, artifact files and AJAX alike; note
  that Starlette runs the most recently added middleware first, which is why
  `SessionMiddleware` is registered *after* it in `src/app.py`. Details:
  `docs/using-cmeta.md` §8.2.1.
- `category/category/` — the *category* category itself (UID
  `dd9ea50e7f76467f`). Its `create` is what `cx category add <name>` invokes; it
  also copies `v1-template.py` into the new category as `api/v1.py`.
- `category/repo/` — repository management: `get`, `clone`, `pull`, `checkout`,
  `status`, `unzip`, `zip`, `plug`, `unplug`, `space`, `list`.
- `category/utils/` — sets `skip_base_category_commands: true`; exposes helper
  commands only (uid, uuid, json↔yaml, clipboard helpers, etc.).
- `category/config/` — `get`/`set`/`unset`/`read`/`show` for cMeta config
  artifacts.

### `_cmeta.yaml` / `_cmeta.json` fields (quick reference)

| Field | Meaning |
|-------|---------|
| `artifact` | Artifact UID (or `alias,UID`). Required. |
| `category` | Category reference (`alias,UID`). |
| `tags` | List of strings for tag search. |
| `authors`, `copyright`, `creation_timestamp`, `last_update_timestamp` | Provenance. |
| `permanent: true` | Refuses `delete` (used for shipped foundational artifacts). |
| `no_index: true` | Skip fast index; found by filesystem scan. |
| `last_api_version` | Highest API version the category ships (loads `api/v<n>.py`). |
| `base_category_default_api_versions` | Which base API version this category inherits from, per category API version. |
| `min_cmeta_version` | Minimum cMeta version per category API version. |
| `skip_base_category_commands: true` | Category doesn't inherit any base CRUD. |
| `command_aliases` | Per-category CLI aliases (global ones in `config.py`). |
| `find_sort: false` | Disable default alphabetical sort for `find`. |
| `uses_categories` | Mapping `<local-name>: <alias>,<UID>` declaring cross-category dependencies. Read at runtime as `self.cmeta['uses_categories'][name]` — **the recommended way** for one category to reference another (rename-safe). |
| `default_env`, `param_env_prefix`, `config_name` | Used by the `app` category to run applications with pre-configured env vars + a named `config` artifact. |

---

## 5. Conventions

- Keep runtime deps minimal — prefer stdlib; justify any new runtime dep.
- **Preserve module docstring / copyright headers — never strip or rewrite
  them.** See §5.1 below for the full attribution rule.
- The single uniform `access()` surface is load-bearing — extend via
  categories/commands/`api/v1.py` hooks and the dispatch, not ad-hoc entry
  points.
- `version.py` is the one place the version lives; don't hard-code it elsewhere.
- **Command return contract.** Always a dict `{'return': 0, ...}` on success,
  `{'return': >0, 'error': '...'}` on failure. Use `self.cm.error(...)` or
  return the dict directly; callers check with `self.cm.catch_error(r)`.
- **Cross-category calls.** Inside `api/v1.py`, use `self.cm.access(...)`. Refer
  to other categories via `self.cmeta['uses_categories']['<name>']` declared in
  your `_cmeta.yaml`, not by hard-coded alias.
- Python 3.9–3.14 supported; avoid newer-only syntax.
- Tests: `tests/`, files `test_*.py`, pytest config in `pyproject.toml`.
- Public Apache-2.0 framework — keep product vision/strategy prose out; public
  docs describe *functionality* (`README.md`, `docs/installation.md`,
  `docs/using-cmeta.md`).

### 5.0 Git workflow — sign-off, branch naming, PR titles

These rules hold for **every** commit, branch and pull request here, including
those an AI agent creates on the author's behalf:

- **Sign off every commit: `git commit -s -m "…"`.** The `-s`/`--signoff` flag
  appends the DCO `Signed-off-by:` line certifying the Developer Certificate of
  Origin 1.1 (see [`CONTRIBUTING.md`](CONTRIBUTING.md) and the [`DCO`](DCO)
  file). A DCO check runs on every pull request and an unsigned commit blocks the
  merge. If one slipped through, repair it *before* pushing:
  `git commit --amend -s --no-edit` for the last commit, or
  `git rebase --signoff <base>` for a range.
- **Name PR branches `YYYYMMDD-<short-branch-name>`.** Creation date first, then
  a short kebab-case topic — e.g. `20260808-fix-repo-resolution`,
  `20260808-add-repo-zip-support`. The date prefix keeps branches chronologically
  sortable and makes a pile of open PRs analyzable. Always branch before
  committing; don't push work directly to the default branch.
- **Prefix the PR title the same way: `YYYYMMDD - <Title of PR>`.** The date, a
  spaced hyphen, then the normal human-readable title — e.g.
  `20260808 - Fix repo resolution for mixed-case aliases`. This is the subject
  line visible on GitHub, so the same date ordering that helps on branches also
  helps when scanning or scripting over the PR list
  (`gh pr create --title "20260808 - …"`, `gh pr list`). Use the same date as the
  branch prefix — the day the work was branched, not the day it merges.

### 5.1 Attribution, provenance and citation

cMeta is Apache-2.0, created and developed by **Grigori Fursin** and
**cTuning Labs**. This applies to work done by AI agents and LLM-based tools
exactly as it does to work done by people. See `NOTICE`, `COPYRIGHT`,
`LICENSE`, `CITATION.cff`.

When you generate, modify or move code, metadata or scripts in this project:

- **Never remove or rewrite an existing copyright header or attribution.** If
  you split a module, carry its header into the new file. If you move an
  artifact, keep its `authors` / `copyright` fields intact.
- **New source files** get the project's standard module docstring header:

  ```python
  """
  <short module description>

  cMeta author and developer: (C) 2025-2026 Grigori Fursin

  See the cMeta COPYRIGHT and LICENSE files in the project root for details.
  """
  ```

- **New artifacts and categories** record provenance in their `_cmeta.yaml`,
  the same way the shipped ones do:

  ```yaml
  authors: '[Grigori Fursin](https://cTuning.ai/@gfursin)'
  copyright: 2025-2026 Grigori Fursin and cTuning Labs. See the cMeta COPYRIGHT
    and LICENSE files for details.
  ```

  In a **downstream** content repo, set `authors` / `copyright` to that repo's
  own owner instead — but keep any cMeta-derived material's original notices.

- **Reusing this code elsewhere.** Apache-2.0 §4 requires retaining the
  copyright, patent, trademark and attribution notices and reproducing the
  `NOTICE` file contents in the distribution. That obligation is not waived
  because the copying was done by an agent rather than a person.

- **Citing.** If the work is research, or reuses the *concepts* (the uniform
  `access()` interface, alias+UID identity, content-addressed artifacts and
  caching, the plugin/category model), cite the project — `CITATION.cff` and
  `docs/history.md` carry the BibTeX and the related publications. The author
  welcomes citation and collaboration: https://cTuning.ai/@gfursin

The repo also ships an **experimental** `llms.txt` (the proposed
[llmstxt.org](https://llmstxt.org) convention) giving agents a curated map of
the project plus this attribution summary. It is a research/testing feature —
tool support is inconsistent and it overrides nothing in `LICENSE`, `NOTICE` or
this file.

---

## 6. Pointers
- Public overview: `README.md`
- Install: `docs/installation.md`
- Using cMeta (repos, plugins, artifacts, reindex): `docs/using-cmeta.md`
- Sphinx docs source: `docs/`
- Changelog: `CHANGELOG.md`
- Skills for agents extending cMeta: `.claude/skills/`
  - `use-cmeta-python` — programmatic API surface, `access()`, `ctx` (agent
    state), base commands, `cm.utils`, `cm.packages`
  - `use-cmeta-cli` — command-line usage, discovery, flags, `ctx` from CLI,
    scripting patterns
  - `add-plugin` — scaffold a new category & artifacts
  - `add-repo` — pull / init / plug content repositories
- Lineage (background only): Collective Knowledge → Collective Mind → CMX → cMeta.
