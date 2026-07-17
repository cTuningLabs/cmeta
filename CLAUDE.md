# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**See `AGENTS.md` for the canonical agent brief** — it covers setup, architecture,
conventions, and env vars. This file adds Claude-Code-specific notes only.

## Commands

```bash
pip install -e ".[dev]"            # editable install with dev extras (or [all])
python -m pytest tests             # full test suite
python -m pytest tests/test_utils_obj_parse_cmeta_core.py::test_name   # single test
flake8 cmeta                       # lint
python -m build                    # build wheel/sdist
```

Windows convenience batch scripts live in the repo root (`_run_tests.bat`,
`_run_test_cli.bat`, `_build_package.bat`, `_build_docs.bat`, `_1_install_*.bat`).
Prefer the Python commands above when scripting cross-platform; the `.bat` files
are the author's local workflow.

## Architecture — the load-bearing shape

Everything funnels through **one dispatch surface**:
`CMeta.access({'category', 'command', ...})` in Python; `cx <category> <command>` on
the CLI. When adding functionality, extend it through categories / tasks /
`api_v1.py` hooks rather than side entry points. `cmeta/core.py` is the dispatch.

Key modules (`cmeta/`):
- `core.py` / `core_async.py` — `CMeta` class + `access()` dispatch.
- `category.py`, `category_api_v1.py` — find/load artifacts, invoke `api_v1.py` hooks.
- `repos.py` — `Repos`: index and resolve content repos and artifacts by alias / UID / tags.
- `packages.py` — `Packages`: detect tools/versions, auto-install Python packages.
- `cli.py` — CLI entry points wired in `pyproject.toml` `[project.scripts]`.
- `internal-repo/` — built-in categories (`app`, `asset`, `cache`, `category`,
  `config`, `docs`, `experiment`, `journal`, `log`, `note`, `repo`, `report`,
  `research`, `result`, `script`, `utils`, `website`, `work`). Shipped as
  package-data.
- `version.py` — single source of truth for `__version__` (wired via
  `[tool.setuptools.dynamic]`; do not hard-code the version anywhere else).

Artifacts are identified by `_cmeta.json|yaml` (UID, category, tags, features)
plus a `_desc.yaml` automation pipeline (`uses` → `prepend`/`append`/`update`
referencing tasks by `alias,UID`) and an optional `api_v1.py` with `customize*`
hooks. This repo is the **framework/engine**; the artifacts it runs live in
separate content repos (e.g. `cmeta-aops`).

## Conventions worth repeating

- Runtime deps are intentionally minimal (pyyaml, requests, setuptools, wheel,
  tabulate, tqdm, filelock, packaging, psutil). Justify any new one.
- Preserve module docstring/copyright headers.
- Python 3.9–3.14 supported; don't use newer-only syntax.
- Tests live in `tests/` as `test_*.py` (pytest config in `pyproject.toml`).
- This is the public Apache-2.0 framework — keep product vision/strategy prose
  out; public docs describe *functionality*.

## Resolution & reindex — two things to internalize

- **`alias,UID` references are the recommended form.** When both are given,
  the **UID is authoritative** and the alias is advisory. This makes references
  rename-safe. Categories declare cross-category deps via `uses_categories:` in
  `_cmeta.yaml` and dereference at runtime as
  `self.cmeta['uses_categories']['<name>']`.
- **Fast index lives at `<CMETA_HOME>/index/<category>.pkl`.** cMeta keeps it
  fresh automatically on `create`/`update`/`delete` and on `cx repo` ops. If
  artifacts were touched outside cMeta (manual move, `git pull`, hand-edited
  YAML, wiped `CMETA_HOME`), run `cx --reindex` — safe and idempotent.
  Categories with `no_index: true` are always found by filesystem scan.

## Debug env vars

`CMETA_DEBUG=1`, `CMETA_LOG=DEBUG|INFO`, `CMETA_LOG_FILE=<path>`,
`CMETA_FAIL_ON_ERROR=yes`, `CMETA_VERBOSE=yes`.

## More context

- User-facing walkthrough (repos, plugins, artifacts, reindex):
  `docs/using-cmeta.md`
- Add-a-plugin skill: `.claude/skills/add-plugin/SKILL.md`
