# Changelog

All notable changes to cMeta are documented here, newest first.


## 0.32.0
- **First pass at connecting AI agents to cMeta so they can help extend and
  improve the framework itself** — ships portable, reusable guidance that
  agents in this and downstream repos can pick up automatically:
  - New Claude Code skills under `.claude/skills/`:
    `use-cmeta-python`, `use-cmeta-cli`, `add-plugin`, `add-repo`.
  - Documented the `ctx` (context) dictionary as the standard bus for
    threading agent state (session id, trace, budget, ...) through nested
    `access()` calls. Framework keys reserved; user/agent keys namespaced
    (e.g. `ctx['agent']`).
  - Documented how to seed `ctx` from the CLI via `--ctx.<key>[.<child>]=v`
    and via `@input.yaml` / `@input.json` file inclusion.
  - Encouraged the `self.cm.utils.*` idiom in category `api/v1.py` so
    agent-written code stays reusable, debuggable, portable, and composable
    (motivation + stdlib↔helper substitution table).
  - Refreshed `AGENTS.md` (framework brief) and added `CLAUDE.md`.
- New `docs/using-cmeta.md` — end-to-end walkthrough covering mental model,
  first checks, global CLI flags, working with artifacts (Python + CLI),
  alias/UID/`alias,UID` resolution, three-tier repo model (internal / default
  local scratch / user repos), `<CMETA_HOME>` env-var resolution order and
  per-project collections, `_cmr.yaml` reference, `cx repo get`/`init`/`plug`
  workflows, `config`-driven configuration (incl. the `app` and cserver/FastAPI
  patterns), adding categories and artifacts, and the fast-index + `--reindex`.
- README refreshed: quickstart, CLI-flag cheatsheet with correct list syntax
  (`--key,=v1,v2,v3`), built-in categories table, pointers to skills and docs.
- Test suite expanded from 76 → 253 tests: added coverage for
  `utils.common`/`utils.names`/`utils.cli.parse_cmd`, `packages` helpers
  (`poetry_to_pep440`, `build_spec`, `build_pip_requirement`,
  `build_cache_key`, `try_import`, `get`), `config` env-var resolution +
  precedence, and full integration tests (temp `CMETA_HOME`) covering
  first-launch layout, base CRUD lifecycle, `ctx` propagation across nested
  calls, and shipped `utils` / `config` category commands.
- **Prepared the repository for public open-source release:**
  - Added a DCO-based contribution policy — `CONTRIBUTING.md`, the verbatim
    `DCO` (Developer Certificate of Origin 1.1), and a self-contained
    `.github/workflows/dco.yml` that checks every pull-request commit is signed
    off.
  - Added `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1) and `MAINTAINERS.md`.
  - Added `CITATION.cff` (machine-readable citation powering GitHub's "Cite this
    repository"), including a `references` list of the author's prior work the
    framework builds on (Collective Knowledge, MLCommons Collective Mind / CMX).
  - Contributor License Agreement templates (dormant individual ICLA, corporate
    CCLA) are maintained separately in the `cTuningLabs/cla` repository.
- README refreshed for the public release.
- New docs: `docs/cplatform.md` (connecting to the cTuning.ai platform and
  testing the API) and `docs/configuration.md` (working with `config`
  artifacts).
- Documented the current-directory shortcut `cx .` — infers the repo and
  category, and the artifact when run inside one — in `docs/using-cmeta.md`
  and the `use-cmeta-cli` skill.
- **Documentation restructured so `docs/` is the systematic source and the
  README is a summary that links into it:**
  - `docs/README.md` is now the documentation index (guide table, suggested
    reading order, agent pointers) instead of stale Sphinx notes; its build
    instructions were corrected to the real layout (`docs/en/`,
    `docs/build_docs.py`, `docs/requirements.txt`, `_build_docs.bat`).
  - `docs/motivation.md` written up (was a `TBD` stub): the problem, the
    approach, design principles, and what cMeta is not.
  - `docs/history.md` is now the single home for the lineage (cTuning
    framework → CK → CM/CMX → cMeta), the related publications and talks, and
    the citation guidance. The duplicated copies of that prose were removed
    from `README.md` and `docs/en/home.rst`, which now link here.
  - README gained a Documentation section linking every guide; cross-links
    added between the guides; broken `README.md` anchor and a stale
    `uses_categories` cross-reference in `docs/using-cmeta.md` fixed.
  - New `docs/error-handling.md`: the return-dict contract and return codes,
    `if self.cm.catch_error(r): return r` as the recommended check (raises at
    the point of failure under `fail_on_error`) versus the simplified
    `if r['return'] > 0: return r` for prototyping, the **soft-error (code 16)
    skipping mechanism** and how to escalate it with `fail16=True`, how to
    raise errors from plugins and from low-level utils, every way to enable
    `fail_on_error`, and debugger setup for VS Code / Visual Studio / PyCharm.
    The `use-cmeta-python` skill §9 now matches this guidance.
  - `docs/error-handling.md` also documents the uniform contract as a **CI /
    AI-agent integration surface**: the `cx` / `cmeta` exit code is exactly the
    `return` value of the equivalent `access()` call, so shell callers branch
    on the same numbers (notably telling a soft 16 apart from a real failure).
    Includes worked examples for bash, `cmd.exe` batch and PowerShell, the
    `--json` vs `--json_file` distinction for machine-readable output, and the
    `if errorlevel N` ("N or greater") pitfall in batch.
  - New `docs/async-and-concurrency.md`: serial (`CMeta`) vs async
    (`CMetaAsync`) use, the `ProcessPoolExecutor` model with one persistent
    `CMeta` per worker, running calls in parallel with `asyncio.gather`, a
    FastAPI example matching the shipped `cserver` app, and the **concurrency
    safety guards** — cross-process `filelock` locks held across each
    read-modify-write cycle plus atomic temp-file+rename writes protecting
    `index/*.pkl`, `repos.json` and every `_cmeta.yaml`. Also records what is
    *not* concurrency-safe (the cached read path; sharing one `CMeta` across
    threads). `docs/installation.md` gained a serial-vs-async extras table, and
    concurrency is now stated as a design principle in `docs/motivation.md`
    and the README feature list.
  - New `docs/known-issues.md` — a tracker for understood-but-unfixed defects
    and planned improvements, with stable `KI-nnn` ids, reproductions and
    workarounds. Seeded with the `CMetaAsync.access_sync()` coroutine bug
    (KI-001), the `CMeta.error(fail_on_error=False)` override quirk (KI-002),
    and the guides-missing-from-the-published-site issue (KI-003). Linked from
    the README project-status section.
  - Documented `cx utils uid` / `cx utils uuid` (generating a 16-hex cMeta UID
    for hand-made artifacts, `--clipboard-`, reading it from `--jf` output)
    plus a table of the other `utils` helper commands — new
    `docs/using-cmeta.md` §5.6. Previously only the Python-level
    `generate_cmeta_uid()` was mentioned anywhere.
  - **The written guides are now part of the published documentation site.**
    `myst_parser` is enabled in `docs/en/conf.py`, and `docs/build_docs.py`
    gained a `copy_guides()` step that copies `docs/*.md` into
    `docs/en/guides/` on every build, rewrites their repo-relative links
    (links between guides stay relative; links outside become GitHub URLs),
    and emits a dedicated "Guides" toctree in the generated `index.rst`.
    `_build_docs.bat` / `_build_docs.ps1` need no changes — `myst-parser` was
    already in `docs/requirements.txt`. Verified with a full local build:
    11 guide pages in both the latest and the versioned (`v<version>`) output,
    zero Sphinx warnings from the guides, and all cross-document anchors
    resolving. `docs/en/guides/` is generated and gitignored — edit the
    originals in `docs/`.
  - New `docs/common-commands.md` — a practical cheatsheet: discovery, the
    `cx .` current-directory shortcut, `cx . info` and its `--clip-` / `--url`
    / `--name` / `--jf` flags, artifacts, UIDs, repos, configs, index/cache,
    scripting and debugging flags, flag syntax, and handy one-liners.
  - `docs/using-cmeta.md` §5.5 now documents what `cx . info` actually prints
    (path, cRef, artifact/category/repo alias+UID) and its flags.
- **Attribution, provenance and citation made explicit — including for AI
  agents and LLM-based tools:**
  - Added a `NOTICE` file, the vehicle Apache-2.0 §4(d) requires downstream
    redistributors to reproduce. It states the required attribution, spells out
    that the obligation covers code, `_cmeta.*` metadata, `_desc.yaml`
    pipelines and scripts regardless of whether they were copied by a person or
    produced with the help of an AI agent, and adds a clearly-labelled
    *requests* section (cite the project; cite and get in touch if reusing the
    concepts) marked as NOT conditions of the licence.
  - `NOTICE` is now shipped in the distribution via `license-files` in
    `pyproject.toml` (verified: it lands in the built wheel's `dist-info`).
  - New `AGENTS.md` §5.1 "Attribution, provenance and citation" — never strip
    copyright headers, carry them when splitting modules, the standard module
    header for new files, `authors`/`copyright` in new artifacts' `_cmeta.yaml`
    (and what to use in downstream repos), the Apache-2.0 §4 obligation when
    reusing code, and how to cite. `CLAUDE.md` points at it.
  - The `add-plugin` skill now tells agents to record provenance in the
    scaffolded `_cmeta.yaml` (the scaffold itself leaves authorship blank).
  - README gained an "Attribution & reuse" section and `docs/history.md` a
    "Reusing the code or the concepts" section, both inviting citation and
    collaboration.
  - Documented **`cx utils find_by_cid`** — cross-category search by cRef with
    wildcards on both halves (`*::*server*`, `cserver*::*`; a bare name gets an
    implicit `*::`), plus `--tags`, `--skip_non_indexed`, `--web`, `--ask`,
    `--far`. This is the way to find related artifacts across categories, which
    the per-category `find` cannot express. New `docs/using-cmeta.md` §5.7 and
    a section in the cheatsheet.
  - New `docs/using-cmeta.md` §12 "Scaling a category to very many artifacts":
    **`sharding_slices`** (slice the alias into nested sub-directories —
    `[2,2]` gives `ex/am/example`, `[4,2]` on date-prefixed aliases gives
    `2026/08/...`; underscore padding for short names; category default with a
    per-repo override keyed by category UID in `_cmr.yaml`; create/move/delete
    all apply it and prune empty shard dirs) and **`no_index: true`** (skip the
    index, find by filesystem scan, alias becomes the practical key), plus when
    to combine them. Both fields added to the `_cmeta.yaml` reference tables.
  - `docs/async-and-concurrency.md` now records who actually runs `CMetaAsync`:
    the shipped `cserver` app and the cTuning.ai platform (`ctuning.server`),
    both of which create one instance and `await cm.access(...)` throughout.
  - Added an **experimental** `llms.txt` (the proposed llmstxt.org convention):
    a curated project map for LLMs and agents, leading with the attribution and
    citation summary. Explicitly marked as a research/testing feature with
    inconsistent tool support that overrides nothing in `LICENSE`/`NOTICE`;
    referenced from `README.md` and `AGENTS.md` §5.1.
  - Added a **Use cases** section to `README.md` and a fuller "What people use
    it for" section to `docs/motivation.md`, aligned with the `cmeta-aops`
    positioning: a research assistant for open science, collaborative research
    and experimentation, reproducible benchmarking and software/hardware
    co-design, AI-agent operations, FastAPI services, and notes/journals kept
    with the automations they describe. `AGENTS.md` §1 gained a short version so
    agents can judge whether a change fits, and `llms.txt` mirrors it.
    `cmeta-aops` is now named as the reference content repository.
  - All five `.claude/skills/` now teach the same contract: the `add-plugin`
    and `use-cmeta-python` code templates use `catch_error` (they previously
    scaffolded the simplified check), `use-cmeta-cli` documents the exit-code
    mapping / soft-16 / `--json_file` conventions, and `add-repo` and
    `add-cserver-plugin` point at the guide.

## 0.30.0
- Improved handling of sharded artifacts

## 0.29.0
- Fixed various bugs and added more basic functionality for agents, tasks and contexts
- Fixed repo indexing when getting new repos

## 0.28.0
- Fixed bug and added safe dump of agents/tasks context

## 0.27.0
- Fixed bug in handling repos with mixed upper and lower case characters

## 0.26.0
- Started new clean version based on 0.25.14
- Added `last_update_timestamp`

## 0.25.0
- Changed API version handling logic (now using the last one by default)
- Many minor updates and improvements for cMeta tasks

## 0.24.0
- Simplified error and logging handling logic
- Updated `state` -> `ctx` (context)

## 0.23.0
- Many improvements and minor bug fixes

## 0.22.0
- Added state extensions for reproducibility
- Fixed and extended `load_files` in artifact read/find logic
- Improved sub-package installation
- Added `uses_categories` to cmeta
- Added advanced `match_version` to packages for tools

## 0.21.0
- Many various bug fixes and important extensions

## 0.20.0
- Many regular improvements and some serious bug fixes

## 0.19.0
- Many improvements and bug fixes

## 0.18.0
- Various improvements including `cx repo plug`/`unplug` USB repos

## 0.17.0
- Many updates
- Added `cx {category} read --load_files,=`

## 0.16.0
- Extended `cx note create`, `cx work create`, `cx experiment create`
- Extended `cx config`

## 0.15.0
- Added cms - common meta server
- Added `app run`

## 0.14.0
- Fixed bug in mixed case artifact handling

## 0.13.0
- Added `state['deps']` for python packages

## 0.12.0
- Added new categories to support CK

## 0.11.0
- Updated documentation for all functions

## 0.10.0
- Fixed more bugs; added on-the-fly package management; added common functions

## 0.9.0
- Fixed bugs in sharding schema

## 0.8.0
- Simplified sharding schema
- Changed default API handling

## 0.7.0
- Added `no_index` artifacts

## 0.6.0
- Added sharding for artifacts

## 0.4.0
- Fixed another major bug in the category module loader

## 0.3.0
- Fixed a major bug in the category module loader

## 0.2.0
- Added async support for FastAPI

## 0.1.0
- Removed explicit UID ordering from the index. Dictionary key insertion order
  (Python 3.10+) now defines the ordering
