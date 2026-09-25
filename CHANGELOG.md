# Changelog

All notable changes to cMeta are documented here, newest first.


## DEV VERSION (0.32.1.1)
- **A repository sets the authors, copyright and generator of its new artifacts; a running task or agent
  records how it made them.** `CMETA_AUTHORS` and `CMETA_COPYRIGHT` were the only source, and they are
  global: one machine working on repositories of different owners stamped the same copyright on all of
  them. A repository's `_cmr.yaml` can now carry `artifact_defaults` (`authors`, `copyright`,
  `generator`). The repository's copyright comes before `CMETA_COPYRIGHT`; `CMETA_AUTHORS`, the person at
  work, comes before the repository's authors. The new `CMETA_GENERATOR` (a JSON object such as
  `{"method": "task", "task": "<alias>,<UID>", "model": "...", "effort": "..."}`) is written as
  `generator` when an artifact is created and as `last_generator`, with the date, when it is updated,
  so provenance is kept without every script having to write it. Keys given in the meta are never
  overwritten, and repositories without `artifact_defaults` behave as before. Documented in
  `docs/using-cmeta.md` §7.6; tests in `tests/core_tests/test_artifact_defaults.py`.
- **Install instructions are two steps - download the file, then run it - instead of piped one-liners.**
  The headers of `install.ps1` and `install.sh`, `README.md`, and `docs/installation.md` showed the website
  installer and astral's uv installer as `curl ... | sh` and `irm ... | iex`. A downloaded file can be read
  before it runs, and Microsoft Defender's machine-learning model classifies the piped `irm ... | iex` form
  as `Trojan:Win32/Commando` and blocks it. `install.ps1` now installs uv the same way: astral's installer is
  saved to a temporary file and run with `-File` in its own PowerShell, instead of being passed to
  `Invoke-Expression`, which also keeps the `exit 1` that script uses on errors from ending ours. The engine's
  headers download the website installer under another name, so it does not overwrite the local one, and the
  README and docs add the line that puts uv on `PATH` in the current shell, so the next step no longer fails
  on a fresh machine.
- **Installers (`install.ps1`, `install.sh`): the dependency step no longer stops the install.** On Windows
  `-WithDeps` ran `winget install --id Git.Git` without `--source winget`, so on a machine where winget's
  Microsoft Store source fails - `0x8a15005e: The server certificate did not match any of the expected
  values`, certificate pinning broken by an HTTPS-inspecting antivirus or proxy - winget refused to install
  the package it had just found in the winget source, and the script exited before installing cMeta at all.
  It now names `--source winget`, skips winget when git is already there, treats winget's "already
  installed" exit codes as success, brings the PATH the Git installer wrote into the running session (the
  `-Aops` step used to find no git seconds after installing it), and turns a failure into a warning with the
  command to run once git is there. A `-CmetaHome` value written for the other shell (`%USERPROFILE%` pasted
  into PowerShell, `$HOME` or `~` into cmd) is expanded instead of becoming a directory of that name, and
  the epilogue says when Windows long paths are off. On Linux and macOS `--with-deps` installs only what is
  missing - asking for `curl` next to the `curl-minimal` of RHEL-family images (Rocky, Alma 9) failed the
  whole `dnf` transaction, and root was needed even with nothing to install; on a Mac without Homebrew it now
  starts the Command Line Tools installer instead of stopping with an error, and `/usr/bin/git` is no
  longer mistaken for a working git before those Tools are installed. uv is fetched with wget where there is
  no curl, and `doas` is accepted where there is no sudo. The same changes went into the website installer.
- **cserver: an optional shared password in front of every page.** `cx config set cserver
  --meta.password="..."` (or `--meta.password_sha256=...`) makes the server ask for one shared password
  before any page, file or AJAX call, and remember the answer in the session cookie - so a server that
  listens on a routable address is not readable by whoever finds the port. Requests from the machine itself
  are exempt by default (`password_allow_local`), a valid `api_keys` value is let through, an AJAX call gets
  a JSON `401` instead of the HTML prompt, and repeated wrong answers from one address are delayed
  (`password_max_attempts`, `password_lockout_min`). The prompt is self-contained and readable on a phone or
  a tablet, in light and dark. The config is read at startup, so the server is restarted after setting the
  key. Documented in `docs/using-cmeta.md` §8.2.1, with its limits stated: one
  shared secret, no accounts, and clear text unless the connection itself is encrypted.
- **`cx utils api_key`.** Prints random keys from `secrets.token_urlsafe` with the ready
  `cx config set ... --meta.api_keys,=` line, a count for one key per device (`cx utils api_key 3`),
  `--nbytes=` for the length, `--bare` for scripts and `--clipboard`. It also says out loud that a key travels
  in the URL and so reaches the access log and the shell history.
- **cserver: a forwarded header is no longer taken as proof of where a request came from.** A forged
  `X-Forwarded-For: 127.0.0.1` used to win the loopback exemption and open a protected server completely, and
  rotating the header gave a fresh lockout counter each time. The exemption is now granted only to a request
  that carries no proxy header at all, and every request that does carry one shares a single lockout counter
  unless the new `password_trust_proxy` says the header comes from a proxy you control. This matters because
  uvicorn itself rewrites the client address from that header when the peer is in `--forwarded-allow-ips`,
  loopback by default, so neither the header nor `request.client` could be trusted on its own.
- **cserver: `?out=json` under the password gate answers with a JSON `401`** instead of the HTML prompt, like
  the other machine-facing forms.
- **`cx utils hash_password`.** Turns a password into the SHA-256 digest a config expects, so the plain text
  never reaches disk. With no argument it asks for the password without echoing it, asks again to catch a
  typo, and prints both the digest and the ready `cx config set ...` line; `--bare` prints the digest alone,
  `--clipboard` copies it, `--config=` / `--key=` name a different target. Passing the password as an
  argument works too and says that it stays in the shell history.
- **cserver: the session cookie is no longer signed with a published key.** The secret now comes from
  `CSERVER_SESSION_SECRET` (exported by `--param.session_secret=...` or a `param:` block in the cserver
  config) and is otherwise random per start, so a session cookie can no longer be forged from the source
  code. The session lifetime became configurable through `CSERVER_SESSION_MAX_AGE` and now defaults to a
  week rather than an hour.
- **README rewritten for first-time readers.** A plain opening (what cMeta is, the two interfaces, why we
  develop it, the "second brain that runs" analogy), a two-minute try-out with the first commands, a
  where-to-go-next table (course, installer, cmeta-aops, docs, agents). The lineage paragraph moved out of
  the top: one sentence names Collective Knowledge (CK, now at MLCommons) and `docs/history.md` keeps the
  full story and the publications. The rest of the README is unchanged.
- **cserver: a busy indicator on every page.** The host template shows a thin animated bar along the top and
  a spinner in the top-right corner while any request of the page to the server (`fetch` or
  `XMLHttpRequest`) has been in flight for more than 250 ms - visible feedback when a page computes its data
  live from a large or slow repository (for example one bind-mounted into a container). Pages doing long
  work of their own can drive it with `cmetaBusy.start()` / `cmetaBusy.stop()`.

## 0.32.1
- **Documentation: the mechanism behind the aims is now stated explicitly.**
  `docs/motivation.md` gained "How: complexity becomes abstractions you can
  operate" — each toolchain, dataset, model, workflow, concept or measured number
  becomes one artifact that is *simple*, *reusable*, *live* (executable rather
  than described) and *interconnected* by `alias,UID`, so it can be operated,
  understood and built upon instead of re-derived. Because each abstraction stays
  inspectable down to its inputs, versions and provenance, a claim can be taken
  back to **first principles**. Added a matching "Complexity becomes artifacts"
  design principle, a new **"FAIR by construction"** section mapping findable /
  accessible / interoperable / reusable onto the identity, file-based access,
  uniform interface and self-description already in the design, and the same
  framing in `README.md` and `llms.txt`.
- **Documentation: the purpose of the project is now stated in one place and
  repeated consistently.** `docs/motivation.md` gained an "The aim" section naming
  the six aims cMeta serves — collaborative, reproducible, reusable, scalable,
  portable and sustainable — together with the constraint that makes them
  affordable (plain files and directories, one CLI, one Python API, minimal
  dependencies), and a "Why this matters more with AI" section explaining that an
  agent does not have to reassemble context because the context is already
  recorded and machine-readable. The README now opens with the problem this
  addresses and carries a matching summary table; `llms.txt` and the PyPI summary
  in `pyproject.toml` were updated to the same wording. Reproducibility is
  consistently described as *gradually improving*, never as a guarantee.
- **`LICENSE` is now the verbatim Apache-2.0 text.** A copyright and attribution
  preamble had been added above it and the APPENDIX was missing, which together
  left the file only 93% similar to the canonical licence, so GitHub reported the
  project as having no detectable licence. Both statements from the preamble were
  already present in [`NOTICE`](NOTICE), where they belong under Apache-2.0 §4, so
  nothing was lost. No change to the licensing of the project itself.
- **Packaging metadata for PyPI.** Added `keywords`, audience and topic
  classifiers, and `Repository` / `Documentation` / `Course` / `Issues` /
  `Changelog` project URLs.
- **`cserver`: a POST whose body is not a JSON object no longer crashes the app.**
  The `home` and `task_handler` routes returned the `{'return': 99, 'error': …}`
  dictionary of `utils.net.unify_request` as-is on an `HTMLResponse` route, so
  Starlette failed with `AttributeError: 'dict' object has no attribute 'encode'`
  and the client got a 500 with a full traceback in the server log. It happened
  every time a page was reloaded or left while a `native_action` AJAX call was
  still in flight (the browser aborts the request and the server reads a
  truncated body), and for empty or form-encoded bodies. Both routes now answer
  with the error as JSON and **HTTP 400**. `unify_request` reads the body once
  and reports precisely: an **empty POST body now means "no extra parameters"**
  (it was an error), a body that is not JSON or not a JSON object is a `return: 99`
  with a clear message (a JSON list used to crash later in the merge), and a
  client that disconnects mid-body is reported instead of raising. Valid
  requests are unchanged - same merge of query string and body, body wins.
  Unit tests: `tests/core_tests/test_utils_net_unify_request.py`.
- New **`--search_text`** and **`--search_files`** on `cx utils find_by_cid` and
  `cx utils smart_find_by_cid` — keep only artifacts that carry the given text
  inside their own files, so a content search no longer has to be a second pass
  by the caller:
  - `--search_text` takes **space-separated** words, **OR**-ed, each matched as
    a case-insensitive substring of the file content. Without it **no file is
    opened at all** and the whole stage is skipped, so `--search_files` alone
    changes nothing.
  - `--search_files` takes comma-separated glob patterns naming which files to
    read, defaulting to **`*info*.md`**. A pattern containing **`**` recurses**
    into the artifact's sub-directories (`**/*info*.md` reaches every matching
    file at any depth, top level included, since `**` also matches zero
    directories). Patterns are always relative to the artifact - a leading
    separator is stripped so a glob cannot escape it.
  - Directories are skipped, duplicates across patterns are collapsed, and a
    file that cannot be read or decoded is skipped rather than failing the
    search. Pruning everything away returns 16 ("not found").
  - **A content search answers with the files, not the directories.** When
    `--search_text` is given, the full path of every matching file is collected
    into **`files`** in the returned dictionary, and those paths are printed
    instead of the artifact directories - having searched inside files, the
    files are the answer, so a caller can open them directly. Every match is
    listed, including several files inside one artifact; a file matching the
    glob but not carrying the text is not listed. `artifacts` still holds the
    artifacts, and without `--search_text` there is no `files` key and the
    output is unchanged.
- New **`--after_date`** and **`--before_date`** on the same two commands —
  keep only artifacts dated within the range, judged from the artifact itself:
  - **Where the date comes from, in order:** a date at the **start of the
    artifact name** (naming a folder `20260503.something` is a deliberate
    statement, so it wins), then **`last_update_timestamp`** in the meta, then
    **`creation_timestamp`**. An artifact with no date at all cannot be shown
    to be in range, so it is filtered out.
  - Names are read as `YYYY`, `YYYYMM`, `YYYYMMDD`, `YYYYMMDD-HHMM` or
    `YYYY-MM-DD`, each followed by `.`, `-`, `_`, a space or the end of the
    name — matching how these artifacts are actually named
    (`20251206.far manager…`, `202512.gfursin…`, `20250814 - cTuning Labs`).
    Values are validated, so `20261301.something` is not read as a date.
  - The bounds accept the same forms plus a full ISO timestamp **with a
    timezone** (`2026-05-03T14:30:00+02:00`, trailing `Z` allowed), with `.`
    `-` `_` `/` `T` `:` ignored between the digits. Everything is normalized to
    naive UTC so name dates and tz-aware meta stamps compare correctly. A
    shorter form means the start of that period, and both bounds are
    **inclusive**. A bound that cannot be read is an **error** (return 1), not
    an empty result — a typo should not look like "nothing found".
  - Applied **before** any file is opened, so narrowing by date makes a content
    search cheaper rather than more expensive.
  - Implemented as `_parse_date_value()`, `_date_from_name()`, `_artifact_date()`
    and `_as_naive_utc()` in the `utils` category's own `api/common.py`, with
    33 new tests.
- New **`--search_file_names`** on the same two commands — keep only artifacts
  holding a file whose **name** contains every one of the given strings:
  - Space-separated, **AND**-ed (all parts must appear), each a
    case-insensitive substring of the **file name alone** — never of the
    directories above it, and directory names are never matched.
  - **Always recursive**: naming parts of a file name is a name-based selector
    in its own right, so it walks the whole artifact and **replaces**
    `--search_files` when both are given, rather than intersecting with it.
  - Composes with `--search_text`, which then narrows whatever the name filter
    selected. Like a text search, it fills **`files`** and prints the matching
    files instead of the artifact directories.
  - Implemented as `_files_matching_name_parts()` in the `utils` category's own
    `api/common.py`; the text filter became `_files_containing_any_text()`,
    which now takes a candidate list so either selector can feed it.
  - Twelve new integration tests covering AND semantics, recursion, case,
    directory names and parent paths not matching, composition with
    `--search_text`, and precedence over `--search_files`.
  - Twenty new integration tests covering the default pattern, non-recursive
    vs recursive globs, OR semantics, case-insensitivity, multiple globs,
    composition with the other filters, that a pattern cannot escape the
    artifact directory, and the contents of `files`.
- New **`--smart_match`** on `cx utils find_by_cid` and
  `cx utils smart_find_by_cid` — prune found artifacts down to those holding
  any of the given values **under any meta key**, without having to name the
  key. `--match.<key>=` answers *"which artifacts have this key set to that?"*;
  `--smart_match` answers *"which artifacts mention this at all?"*, which is
  what an interactive search box needs when the key is not known in advance:
  - Comma-separated (a list works too), **OR**-ed — one hit is enough, so
    adding values widens the result. Each value is matched as a
    **case-insensitive substring** of a meta value, so `cuda` finds
    `cuda-12.4`. Note the consequence: `red` also matches `shared`.
  - Every value is visited at any depth, walking into nested dicts and lists.
    **Keys are never matched** — only the values they hold — so `--smart_match=tags`
    does not match every artifact just because they all have a `tags` key.
  - Runs after `find`, over meta already in memory, so it costs no extra
    lookup. Pruning everything away returns 16 ("not found"), the same empty
    result the other filters give. An empty or whitespace-only value keeps
    everything.
  - Implemented as `_matches_any_value()` / `_iter_values()` in the `utils`
    category's own `api/common.py`, so it lives in the live-loaded internal
    repo and needs no reinstall.
  - Twelve new integration tests in
    `tests/internal_repo_tests/test_integration_categories.py`, including the
    nested-structure walk, the key-vs-value distinction, OR semantics, and the
    documented `red`-inside-`shared` substring case.
- **`cx utils find_by_cid` and `cx utils smart_find_by_cid` now take the same
  filters as `cx <category> find`** — `--tags`, `--all_tags`, `--match.<key>=`,
  `--match_empty_version` and `--match_empty_values`. `repos.find()` already
  implemented all of them; the two CID commands simply did not pass them on, so
  a caller had to fetch every match and prune the list itself:
  - `find_by_cid` accepted `tags` but forwarded nothing else. It now forwards
    `match`, `match_empty_version`, `match_empty_values` and `all_tags` too.
  - `smart_find_by_cid` accepted **no** filters at all and called
    `find_by_cid_` bare, so `--tags` failed with *"unexpected keyword argument
    'tags'"*. It now accepts and forwards the whole set.
  - Filtering happens inside the single `repos.find()` index pass, so a filtered
    lookup stays one call — no second query and no client-side pruning. Tags
    keep their usual semantics: comma-separated, whitespace-tolerant,
    case-insensitive, combined with **AND**, and `-tag` excludes. Nothing
    matching returns 16 ("not found"), an empty result rather than a failure.
  - Thirteen new integration tests in
    `tests/internal_repo_tests/test_integration_categories.py` cover single and
    multiple tags, exclusion, list-valued tags, an unknown tag, `all_tags`
    exact-set semantics, `match` on a meta key, and that `smart_find_by_cid`
    really forwards both `tags` and `match`.
- New **`cx utils detect_category`** and **`cx utils detect_repo`** commands —
  report the category and the repository of the current (or a given) directory
  using the same detection that backs `cx . <command>`
  (`utils.common.detect_cid_in_the_current_directory`), so external tools no
  longer have to re-derive the repo/category layout themselves or scrape the
  output of `cx .`:
  - `detect_category` prints the category as `alias,UID` inside an artifact
    directory, and as just the alias when standing in the category directory
    itself (where no single artifact pins the UID).
  - `detect_repo` prints the repository as `alias,UID`. It resolves in more
    places than the category does — including a repository root, which belongs
    to no category.
  - Both print nothing when there is nothing to report. **Detecting nothing is
    not an error**: they return 0 with `category` / `repo` set to `None`, so a
    caller can fall back to a wider search. Pass `--fail_if_not_found` to turn
    it into an error instead.
  - Both take an optional directory as `arg1` instead of using the current one.
    `detect_category` returns `category`, `category_alias`, `category_uid`,
    `artifact_name`, `artifact_repo_name`; `detect_repo` returns `repo`,
    `repo_alias`, `repo_uid` and `artifact_path` (the path relative to the
    repository root). Both return the inspected `path`.
  - Shared detection and directory normalization live in one private helper,
    so the two commands cannot drift apart.
  - Thirteen new integration tests in
    `tests/internal_repo_tests/test_integration_categories.py` cover detection
    inside an artifact, in a category directory, via an explicit path, outside
    any repository (not an error), `--fail_if_not_found`, a missing directory,
    and that the two commands agree on the repository.
- Fixed `KeyError: 'repo_uid'` when searching a **wildcard category with a
  repository filter** (e.g. `cx utils find_by_cid *::<repo>:<artifact>`): such a
  search also visits the built-in `repo` category, whose index entries carry no
  `repo_uid` because repositories are not themselves inside a repository.
  `Repos.find_in_index` now prunes those entries instead of crashing — a repo
  artifact can never match a repo filter.
- New integration tests for repo-filtered searches
  (`tests/internal_repo_tests/test_integration_repo_filter.py`): the `repo`
  category under a repo filter, a wildcard-category search end to end, and a
  guard that the filter really prunes rather than being ignored.


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
