---
name: use-cmeta-cli
description: Use cMeta from the command line (`cx` / `cmeta` / `cxt` / `cserver`) — argument model, discovery flow, global flags, output modes, aliases, `.` current-directory shortcut, `@file` includes, ctx-through-CLI patterns, and script-friendly conventions. Portable — same recipes work in any repo that ships cMeta categories/artifacts.
---

# use-cmeta-cli — using cMeta from the command line

> **Reusable across repos.** These recipes describe the CLI surface of cMeta
> itself — they don't depend on any particular content repo. `cx --help` and
> `cx <category> <command> --help` are the ultimate authorities.

## 1. Entry points

Shipped by `pyproject.toml` `[project.scripts]`:

| Command | Purpose |
|---------|---------|
| `cx` | Short-hand for `cmeta`. Most common. |
| `cmeta` | Full name — same as `cx`. |
| `meta` | Alias of `cmeta`. |
| `cxt` | Shortcut for `cx task run …`. |
| `cserver` | Shortcut for `cx app run cserver …` (local FastAPI UI). |
| `ucx` / `ucmeta` / `umeta` / `ucxt` / `ucserver` | "u" variants — force `--home` (unbuffered / alt HOME). |

All entry points call the same dispatch — they just prepend arguments.

## 2. Invocation model

```
cx [<category>] [<command>] [<arg1> <arg2> ...] [--flag ...] [--k=v ...] [-- passthrough]
```

- The **1st positional token** is `<category>`.
- The **2nd** is `<command>` (or a command alias — see §6).
- Remaining positional tokens become `arg1`, `arg2`, `arg3`, ... on the call.
- Flags (`--k`, `--k=v`, `-k`) can appear in any order.
- Everything after a lone `--` is stored in `unparsed` (rarely needed; use to
  pass args verbatim to sub-processes like `cx app run <a> -- --foo`).

Special first token: **`.`** — auto-detect the artifact under the current
directory (see §7).

## 3. Discovery — how to explore without reading source

```bash
cx --help                          # framework help + all global flags
cx category list                   # every category (plugin) known to cMeta
cx <category> --help               # commands available in a category
cx <category> <command> --help     # per-command args/flags
cx repo list                       # every registered content repository
cx --version                       # cMeta version + check for update
```

Every category also ships two built-in demo commands: `test <arg>` and
`test2 <arg>` — safe to try; they just echo the parsed params.

## 4. Global flags (from `cmeta/config.py`)

Full reference: `docs/using-cmeta.md §3`. Highest-signal subset:

| Flag | Meaning |
|------|---------|
| `--help`, `-h` | Framework/category/command help. |
| `--version`, `-V` | Version + update check. |
| `--reindex` | Rebuild `<CMETA_HOME>/index/*.pkl`. Fix stale lookups. |
| `--verbose`, `-v` | Extra progress info. |
| `--quiet`, `-q` | Auto-accept default answer to prompts (script-safe). |
| `--repro`, `-r` | Save call inputs/outputs (`cmeta-repro-*.json`). |
| `--base` | Force the shared base command instead of a category override. |
| `--api <n>` | Pin category API version. |
| `--con` | Force console output (default for CLI; needed for library calls). |
| `--json`, `-j` | Print return dict as JSON. |
| `--json_file <p>`, `--jf` | Also write JSON to a file. |
| `--dump` | Dump full call ctx to `cmeta-ctx.json`. |
| `--home <path>` | One-shot `<CMETA_HOME>` override. |
| `--debug` | `--log_level=DEBUG` + `--fail_on_error`. |
| `--fail`, `--fail_on_error` | Raise on first error instead of returning. |
| `--log_level <lvl>`, `--log_file <p>` | Standard logging knobs. |
| `--pause_if_error`, `--pif` | Pause before exiting on error (double-click friendly). |

Hyphen and underscore forms are equivalent (`--log-level` == `--log_level`).

## 5. Flag syntax cheatsheet

Parsed by `cmeta/utils/cli.py::parse_cmd`. Rules:

| Syntax | Result |
|--------|--------|
| `--key` | boolean `True` |
| `--key-` | boolean `False` |
| `--no-key` | boolean `False` |
| `--key=value` / `--key value` | string / int (repeats overwrite — last wins) |
| `--key,=v1,v2,v3` | list `[v1, v2, v3]` (trailing comma on the key requests split) |
| `--key,=` | empty list `[]` |
| `--parent.child=v` | nested dict `{'parent': {'child': v}}` |
| `key=value` (no dashes) | same as `--key=value` |
| `@somefile.yaml` | inline the YAML/JSON file as flags (deep-merged) |
| `@@somefile.yaml` | same, then delete the file |
| `--` | everything after → `unparsed` list |
| bare token | positional → `arg1`, `arg2`, ... |

Examples:

```bash
# Nested meta from CLI:
cx experiment add e1 --meta.description="pilot run" --meta.hw.gpu=A100

# List value (base commands split on ',' automatically for tags):
cx repo find --tags=demo,gpu

# Explicit list (works for any flag, not just tags):
cx <cat> <cmd> --files,=a.txt,b.txt,c.txt

# Positional arg + flag mix:
cx repo checkout my-repo main --verbose

# Load params from a file (see §5.1 below):
cx category add --debug @create-args.yaml
```

### 5.1 `@input.yaml` / `@input.json` — reusable parameter files

Any positional token starting with `@` is treated as a **YAML or JSON file
whose contents are deep-merged into the parsed params**. Great for capturing
long invocations, sharing recipes with a team, or driving repeated runs from
CI:

```bash
cx category add @create-args.yaml
cx experiment run e1 @run-config.json
cx <cat> <cmd> @@one-shot.yaml     # `@@` also deletes the file after reading
```

Format is auto-detected from the extension (`.yaml`, `.yml`, `.json`).
Example `run-config.json`:

```json
{
  "meta":    {"description": "pilot run", "hw": {"gpu": "A100"}},
  "verbose": true,
  "ctx":     {"agent": {"session": "sess-42"}}
}
```

You can mix multiple `@file` inclusions and regular flags on the same command
— later values (further right on the command line) override earlier ones. On
Windows, quote paths containing backslashes so `shlex.split` doesn't mangle
them: `cx <cat> <cmd> @"C:\path\to\file.yaml"`.

Use cases:
- **Team recipes** — commit a `run-experiment.yaml` in your repo and share
  `cx experiment run @run-experiment.yaml`.
- **CI matrices** — generate per-row JSON files and fire `cx <cat> <cmd> @row.json`.
- **Agent hand-off** — an agent writes a `@@call.yaml` and invokes cMeta once
  with all its assembled state; the `@@` auto-cleans the temp file.

## 6. Command aliases (built-in)

Global (from `cmeta/config.py`) — work on any category:

| Alias | Real command |
|-------|--------------|
| `add` | `create` |
| `rm`, `remove`, `del` | `delete` |
| `ren`, `rename`, `mv` | `move` |
| `cp` | `copy` |
| `ls` | `list` |
| `search` | `find` |
| `load` | `read` |

Per-category aliases live under `command_aliases:` in a category's `_cmeta.yaml`.

## 7. Current-directory shortcut (`cx .`)

`cx .` inspects the current working directory, walks up to find the enclosing
repo (`_cmr.yaml`), then the enclosing artifact (`_cmeta.yaml`), and injects
the matching category + artifact ref:

```bash
cd /path/to/some/repo/experiment/e1

cx . info                 # → cx experiment info e1  (auto-detected)
cx .                      # → cx experiment info e1  (info is the default when . resolves)
cx . <command>            # → cx experiment <command> e1
cx . <cat> <command>      # override the detected category
```

Same detection is available programmatically via
`cm.utils.common.detect_cid_in_the_current_directory(cm)`.

## 8. Output modes for scripts and agents

Machine-readable stdout:

```bash
cx repo list --json                          # print JSON return dict to stdout
cx <cat> read <alias> -j                     # same, short form
cx <cat> find <alias> --jf=out.json          # ALSO write JSON to file
cx <cat> find <alias> --json --json_file=out.json
```

Muffle output when scripting:

```bash
cx <cat> <cmd> ... --quiet                   # auto-accept prompts
cx <cat> <cmd> ... --con-                    # suppress the default console output
```

Full call context for downstream tooling:

```bash
cx <cat> <cmd> ... --dump                    # writes cmeta-ctx.json (ctx after call)
cx <cat> <cmd> ... --repro                   # writes cmeta-repro-input.json + -output.json
```

Exit codes: `0` on success, non-zero equals the returned `return` code
(useful in `Makefile` / CI).

## 9. Passing `ctx` (context) from the CLI — good for AI agents

`ctx` is a dict that the framework threads through every nested `access()`
call. It carries framework-owned keys (see the Python skill §5) plus anything
you attach yourself. CLI flags can seed the initial ctx via
`--ctx.<key>[.<child>]=<value>` (parsed as a nested dict):

```bash
# Attach agent metadata that any hook in the call tree can read:
cx experiment run e1 \
   --ctx.agent.session_id=sess-42 \
   --ctx.agent.trace_id=trace-abc \
   --ctx.agent.budget_tokens=20000

# Or load from a file:
cx experiment run e1 @agent-ctx.yaml
```

Guidelines when using ctx from the CLI:
- Namespace your keys (`--ctx.agent.*`, `--ctx.trace.*`) — never overwrite
  framework keys (`origin`, `nested_call`, `control`, `command`, `category*`,
  `category_artifact`, `last_self_time`, `repro`).
- Combine with `--dump` to capture the post-call ctx (with any state a hook
  wrote back) into `cmeta-ctx.json`.
- ctx is shared across nested calls — a hook can mutate it and later hooks
  see the update.

## 10. Working recipes

### 10.1 Everyday exploration

```bash
cx repo list
cx category list
cx <category> ls
cx <category> ls --tags=demo,gpu
cx <category> find <alias-or-uid>
cx <category> info <alias>            # prints path + cRef, copies to clipboard
cx <category> read <alias>            # print _cmeta.yaml
cx <category> read <alias> -j --jf=meta.json
```

### 10.2 Get / create / update artifacts

```bash
cx <category> add <alias> --yaml --tags=t1,t2
cx <category> add <repo>:<alias> --meta.description="..." --meta.owner=me
cx <category> update <alias> --meta.results.accuracy=0.91 --new-tags=validated
cx <category> tags <alias> --add=t1,t2 --remove=t3
cx <category> mv <old> <new>
cx <category> rm <alias>              # blocked if permanent: true
```

### 10.3 Add a new content repo

```bash
cx repo get cmeta://<name>                       # cTuning zip mirror
cx repo get <alias> --url=https://github.com/<org>/<repo>
cx repo get <alias> --url=<git-url> --checkout=main
cx repo init <alias>                             # brand-new local repo
cx repo plug                                     # register current dir as repo
cx repo unplug <alias>                           # unregister (keep files)
```

More detail: `.claude/skills/add-repo/SKILL.md`.

### 10.4 Add a new plugin (category)

```bash
cx category add <alias>
cx <alias> --help                                # inherited base + your test_/test2
cx <alias> test hello --flag1
# then edit <repo>/<alias>/api/v1.py
```

More detail: `.claude/skills/add-plugin/SKILL.md`.

### 10.5 Run a shipped app (the `app` convention)

Artifacts of category `app` ship a `_run.bat` (Windows) and `_run.sh` (Unix)
alongside their `_cmeta.yaml`. `cx app run` sets env vars from `default_env`
+ any linked `config` artifact, cd's into the artifact dir, and executes the
script:

```bash
cx app run <app-alias>                       # runs _run.bat / _run.sh
cx app run <app-alias> --param.PORT=9000     # merges into env as <PREFIX>PORT
cserver                                      # shortcut for `cx app run cserver`
```

Relevant `_cmeta.yaml` fields for an app artifact: `default_env: {...}`,
`param_env_prefix: <PREFIX>_`, `config_name: <config-alias>`, `run_script: _run`
(default), `skip_chdir: true|false`.

### 10.6 Debugging a call

```bash
cx <cat> <cmd> ... --debug                       # full dispatch trace + fail fast
cx <cat> <cmd> ... -v --con                      # verbose, force console
cx <cat> <cmd> ... --log_file=cx.log --log_level=DEBUG
cx <cat> <cmd> ... --repro                       # capture inputs/outputs
cx <cat> <cmd> ... --dump                        # capture full ctx
```

### 10.7 Reindex when things look stale

```bash
cx --reindex
```

Needed after: manual moves, hand-edited `_cmeta.yaml`, `git pull` in a repo,
`CMETA_HOME` wipe. Safe, idempotent, usually fast.

## 11. Scripting the CLI

**Bash:**

```bash
set -euo pipefail
out=$(cx repo list --json)
count=$(python -c "import json,sys; print(len(json.loads(sys.stdin.read())['repos']))" <<<"$out")
```

**PowerShell:**

```powershell
$out = cx repo list --json | ConvertFrom-Json
Write-Host "repos: $($out.repos.Count)"
```

**Windows `.bat`** (see this repo's root for examples like `_run_tests.bat`,
`_2_run_cm_with_global_repos.bat`, `_test_get_ctuninglabs_cmeta_ops.bat`):

```bat
@echo off
set CMETA_HOME=D:\my-cmeta-home
uv run cx %*
```

Always check exit codes (`errorlevel` on Windows, `$?` on POSIX) —
non-zero equals the `return` value of the call.

## 12. Source of truth

- Global flags + descriptors: `cmeta/config.py`
  (`params_desc`, `params_command*_desc`, `params_init_desc`).
- Command-line parser: `cmeta/utils/cli.py::parse_cmd`.
- CLI entry points: `cmeta/cli.py`.
- Current-dir detection (`cx .`): `cmeta/utils/common.py::detect_cid_in_the_current_directory`.
- App-run convention: `cmeta/internal-repo/category/app/api/v1.py`.
- Companion Python skill: `.claude/skills/use-cmeta-python/SKILL.md`.
- User walkthrough: `docs/using-cmeta.md`.
