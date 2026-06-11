# AGENTS.md — Working context for AI agents in the cMeta framework

> Guidance for AI coding agents working on the **cMeta framework** itself
> (the `cmeta` Python package / CLI `cx` · `cmeta`). This is the *engine*; it
> executes **artifacts** (programs, models, datasets, tasks) that live in
> separate content repositories. Keep this file short, factual and current.

---

## 1. What this project is

**cMeta** (aka **cX**) is a small, portable framework for unifying,
interconnecting and reusing code, data, models, agents and knowledge through one
uniform interface: `cm.access({'category', 'command'})` in Python and
`cx <category> <command>` on the command line.

- **License:** Apache-2.0. **Python:** 3.9–3.14.
- This repo is the framework. The artifacts it runs live elsewhere (e.g. the
  `cmeta-aops` content repo). The framework ships a built-in `internal-repo/`
  with its own categories.

---

## 2. Setup, build, test

```bash
# Dev install (editable) with dev extras
pip install -e ".[dev]"        # or: pip install -e ".[all]"
cmeta --version

# Run the test suite (pytest; testpaths = tests/, files test_*.py)
python -m pytest tests
# convenience scripts (Windows): _run_tests.bat, _run_test_cli.bat

# Lint
flake8 cmeta

# Build / docs
python -m build                # wheel/sdist (see _build_package.bat)
# Sphinx docs: docs/  (see _build_docs.bat / docs/README.md)
```

- Optional extras (from `pyproject.toml`): `dev` (pytest, pytest-cov, flake8),
  `async`, `server` (fastapi/uvicorn/jinja2/...), `all`.
- Runtime deps are intentionally minimal: pyyaml, requests, setuptools, wheel,
  tabulate, tqdm, filelock, packaging, psutil.

### Useful environment variables
`CMETA_DEBUG=1`, `CMETA_LOG=DEBUG|INFO`, `CMETA_LOG_FILE=<path>`,
`CMETA_FAIL_ON_ERROR=yes`.

---

## 3. Architecture (package `cmeta/`)

| Module | Role |
|--------|------|
| `core.py` | The `CMeta` class and the central `access()` dispatch — the single entry point everything funnels through. |
| `core_async.py` | Async variant of the core. |
| `category.py`, `category_api_v1.py` | Category + artifact management (find/load/read artifacts, invoke their `api_v1.py` hooks). |
| `repos.py` | `Repos` — index and resolve content repositories and artifacts (by alias / UID / tags). |
| `packages.py` | `Packages` — detect tools/versions and auto-install Python packages. |
| `config.py` | Settings, parameter descriptors, env handling. |
| `cli.py` | CLI entry points (see `[project.scripts]`): `main_cmeta`, `main_cx`, `main_cxt`, `main_cserver`, and `u*` unbuffered variants → consoles `cmeta`/`meta`/`cx`/`cxt`/`cserver`. |
| `version.py` | `__version__` (single source of truth; wired via dynamic version in `pyproject.toml`). |
| `utils/` | Helpers: `common`, `files`, `names`, `net`, `sys`, `cli`. |
| `internal-repo/` | Built-in repo of framework categories (`app`, `asset`, `cache`, `category`, `config`, `docs`, `experiment`, `journal`, `log`, `note`, `repo`, `report`, `result`, `script`, `utils`, `website`, `work`). Shipped as package data. |

### Core concepts the code implements
- **Uniform interface**: all operations are `access({'category', 'command', ...})`.
- **Categories**: artifact *types*; each is a folder with metadata + automation +
  optional Python hooks.
- **Artifacts**: identified by `_cmeta.json|yaml` (UID, category, tags, features)
  plus a `_desc.yaml` automation and optional `api_v1.py` (`customize*` hooks).
- **Composition**: `_desc.yaml` pipelines (`uses` → `prepend`/`append`/`update`)
  reference tasks by `alias,UID`.
- **Caching / reproducibility**: content-addressed task caches, `store_global`,
  `cache_params`. (Determinism across heterogeneous environments is improved, not
  fully solved — ongoing R&D; don't overstate it in docs.)

---

## 4. Conventions

- Keep runtime dependencies minimal — prefer the standard library; justify any new
  third-party runtime dep.
- Preserve the module docstring/copyright headers.
- The single uniform `access()` surface is load-bearing — extend behavior through
  categories/tasks/`api_v1.py` hooks and the dispatch, not ad-hoc side entry points.
- `version.py` is the one place the version lives; don't hard-code it elsewhere.
- Match the surrounding code style; add tests under `tests/` as `test_*.py`.
- Don't commit `__pycache__`/`*.pyc`.
- This is the **public, Apache-2.0** framework. Keep high-level product
  vision/strategy out of it — the public docs describe *functionality* (see
  `README.md`, `docs/installation.md`).

---

## 5. Pointers
- Public overview: `README.md`
- Install/usage/config: `docs/installation.md`
- Sphinx docs: `docs/` (`docs/README.md`)
- Changelog: `CHANGELOG.md`
- Lineage (background only): Collective Knowledge → Collective Mind → CMX → cMeta.
