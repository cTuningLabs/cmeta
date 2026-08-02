---
name: use-cmeta-python
description: Use cMeta from Python — initialise CMeta, call the uniform `access()` interface, build category `api/v1.py` handlers, wire cross-category calls, use ctx to thread AI-agent state through nested calls, and reuse the utility helpers. Portable — same recipes apply in any repo that adds cMeta categories/artifacts.
---

# use-cmeta-python — programmatic use of cMeta

> **Reusable across repos.** These recipes assume nothing about the local
> project — they describe the framework's public surface. The `cx <cat> <cmd>
> --help` output and the source in `cmeta/` are the authorities; when this
> file disagrees, trust them.

## 1. Init

```python
from cmeta import CMeta

cm = CMeta()                       # defaults come from env vars + CMETA_HOME
cm = CMeta(home="/custom/home",    # one-shot override for CMETA_HOME
           debug=True,              # sets log_level=DEBUG + fail_on_error=True
           fail_on_error=True,      # raise instead of returning {'return': >0}
           log_level="INFO",
           log_file="/tmp/cm.log")
```

Env vars honoured: `CMETA_HOME`, `CMETA_DEBUG`, `CMETA_LOG`, `CMETA_LOG_FILE`,
`CMETA_FAIL_ON_ERROR`, `CMETA_VERBOSE`, `CMETA_INTERNAL_REPO_PATH`,
`CMETA_PIP_INSTALL_ARGS`.

For async / FastAPI use:

```python
from cmeta.core_async import CMetaAsync

cm = CMetaAsync(max_workers=4)     # runs access() in a ProcessPool
result = await cm.access({...})    # coroutine
cm.access_sync({...})              # synchronous fallback
cm.shutdown()
```

## 2. The one interface — `cm.access()`

Every operation goes through one dict-in/dict-out call:

```python
r = cm.access({
    'category': 'repo',            # required (unless calling --reindex etc.)
    'command':  'list',            # required
    # ... any command-specific kwargs, positional aliases arg1/arg2/...,
    # control flags con/verbose/quiet/help/base/api/json/json_file/dump,
    # and an optional 'ctx' (see §5).
})

if r['return'] != 0:
    raise RuntimeError(r['error'])
```

**Return contract**: always a dict. `return == 0` = success (with
command-specific keys); `return > 0` = failure with an `error` string. Code
`16` is soft (e.g. "not found") — treat as a warning unless you set
`fail_on_error=True`.

### 2.1 Passing positional args

The CLI turns positional tokens into `arg1`, `arg2`, `arg3`, ... From Python
just set them explicitly:

```python
r = cm.access({'category': 'category', 'command': 'find', 'arg1': 'repo'})
r = cm.access({'category': 'repo',     'command': 'checkout',
               'arg1': 'my-repo', 'arg2': 'main'})
```

### 2.2 Resolution refresher (`alias` / `UID` / `alias,UID`)

Category and artifact references accept three forms — use `alias,UID` for
anything you'll persist or share (UID is authoritative → rename-safe):

```python
r = cm.access({'category': 'category,dd9ea50e7f76467f',
               'command':  'find',
               'arg1':     'repo,f4f792ab40c7498f'})

# Cross-repo: <repo>:<name>
r = cm.access({'category': 'note', 'command': 'find',
               'arg1':     'my-repo:daily-log'})
```

## 3. Base commands (inherited by every category)

Implemented in `cmeta/category_api_v1.py`. Signatures shown below; call them
via `cm.access({'category': ..., 'command': <name>, ...})`.

| Command | Purpose | Key extras |
|---------|---------|------------|
| `find` | Lookup by alias/UID/tags/wildcards. | `tags=`, `match=`, `all_tags=`, `skip_uids=`, `sort=`, `load_files=` |
| `list` | Alias-only listing (prints if `con=True`). | Same filters as `find`. |
| `read` | Return `_cmeta.yaml/json` of a single artifact. | `yaml=True` to print YAML; `load_files=[...]`. |
| `create` | Create + index a new artifact. | `arg1`, `tags=`, `meta={}`, `yaml=True`, `virtual=True`, `path=...`. |
| `update` | Merge `meta=` into existing artifact (recursive, list-aware). | `new_tags=`, `replace=`, `replace_lists=`, `create=True` (create if missing). |
| `delete` | Remove artifact + de-index. | `force=`, `ignore_errors=`, respects `permanent: true`. |
| `move`   | Move/rename within/between repos. | Renaming category alias is blocked upstream. |
| `copy`   | Copy an artifact. | `arg1`→`arg2`. |
| `info`   | Print path + cRef (also puts on clipboard). | `clip=`, `url=`, `name=`. |
| `tags`   | Show unique tags across matched artifacts. | `sort=`. |
| `get`    | `read` if exists; `create` + `read` if not. | Returns `created: bool`. |
| `set`    | `update` if exists; `create` if not. | Returns `created: bool`. |
| `index`  | Re-add a virtual artifact to the index. | Wraps `create` with `index=True`. |
| `test`   | Sanity test (echoes params). | — |

**Method-name convention** — the framework strips trailing underscores and
picks call style by suffix:
- `foo_` (single `_`, not `__`) → typed kwargs incl. `ctx`. **Recommended.**
- `foo` / `foo__` / `foo___` → single positional `params` dict; trailing
  `__` / `___` are stripped from the CLI name (used to dodge Python builtins:
  `list__`, `type__`, ...).

## 4. Writing a category's `api/v1.py`

```python
# <repo>/<category>/<my-cat>/api/v1.py
from cmeta.category import InitCategory

class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    def hello_(self, ctx, arg1=None, flag1=False, name="world"):
        """Say hello. Shows up in `cx <my-cat> hello --help`."""
        self.logger.debug("hello_ called")
        print(f"Hello {name}! arg1={arg1} flag1={flag1}")
        return {'return': 0, 'greeting': name}

    def dump(self, params: dict):
        import json
        print(json.dumps(params, indent=2))
        return {'return': 0}
```

Inside methods you always have access to:

| Attribute | What it is |
|-----------|------------|
| `self.cm` | The parent `CMeta` instance — use `self.cm.access(...)` for cross-category calls. |
| `self.cmeta` | Your category's own `_cmeta.yaml` dict (read `uses_categories`, `command_aliases`, etc. from here). |
| `self.logger` | Per-category `logging.Logger`. Debug lines appear with `--debug`. |
| `self.path` / `self.module_path` | Filesystem paths (`self.path` = category dir; `self.module_path` = the `api/` dir). |
| `self.fail_on_error` | Inherited flag; forward to helpers that accept it. |
| `self._prepare_input_from_params(params, base=True)` | Build a re-entry dict that preserves category/command/control. |
| `self._prepare_input_from_ctx(ctx, base=True)` | Same, from ctx only. |
| `self.cm.utils` | All the utility modules (see §7). |
| `self.cm.packages` | Tool/package detection + install (see §8). |
| `self.cm.cfg` | Global framework config (`command_aliases`, `default_git`, `default_config_name`, ...). |

### 4.1 Re-entering `access()` from a hook

For the **base CRUD of your own category** — delegate via
`_prepare_input_from_params(..., base=True)`:

```python
def status_(self, ctx, arg1=None):
    p = self._prepare_input_from_params({'ctx': ctx, 'arg1': arg1}, base=True)
    p['command'] = 'find'
    r = self.cm.access(p)
    if self.cm.catch_error(r): return r
    return {'return': 0, 'count': len(r.get('artifacts', []))}
```

For **another category** — declare it in your `_cmeta.yaml`:

```yaml
uses_categories:
  config: config,cc6bfe174be847ed
  utils:  utils,234ce5e3262e4d52
```

Then reference by ref (rename-safe because the UID is authoritative):

```python
r = self.cm.access({'category': self.cmeta['uses_categories']['config'],
                    'command':  'get',
                    'arg1':     self.cm.cfg['default_config_name']})
```

## 5. `ctx` — thread state through nested calls (great for AI agents)

Every `access()` call receives (or creates) a `ctx` dict. It's the framework's
context bus: the same object is passed down into every nested `self.cm.access(...)`
invocation. Framework-owned keys:

| Key | Set by | Meaning |
|-----|--------|---------|
| `ctx['origin']` | Set once on first call | `{'pwd': cwd, 'params': original_request, 'cli': {caller, cmd}, 'control': first_control_params}` |
| `ctx['nested_call']` | Incremented on entry, decremented on exit | Depth of the current call. |
| `ctx['control']` | Swapped per call | Current call's control flags (`con`, `verbose`, `quiet`, `base`, `api`, `json`, ...). Restored on exit. |
| `ctx['command']` | Set on dispatch | Resolved command name (aliases already applied). |
| `ctx['category']` | Set on dispatch | Category `cmeta_ref_parts` (`{artifact_alias, artifact_uid}`). |
| `ctx['category_artifact']` | Set on dispatch | Full category artifact dict (`{path, cmeta, cmeta_ref_parts, ...}`). |
| `ctx['category_cmeta']` | Set on dispatch | Category's own `_cmeta.yaml` (same as `self.cmeta`). |
| `ctx['last_self_time']` | Set on exit | Perf timing (seconds) of the last call. |
| `ctx['repro']` | Set with `--repro` | Reproducibility payload. |

Because ctx is **shared across the whole call tree**, you can safely attach
your own state that persists across nested calls without threading extra args
through every function:

```python
# From outside — inject agent context on the first call:
r = cm.access({
    'category': 'experiment', 'command': 'run',
    'arg1': 'e1',
    'ctx': {
        'agent': {
            'session_id': 'sess-42',
            'trace_id':   'trace-abc',
            'budget_tokens_left': 20000,
            'user_note': 'debugging flaky benchmark',
        },
    },
})

# Inside any api/v1.py hook — read/mutate:
def run_(self, ctx, arg1=None):
    agent = ctx.setdefault('agent', {})
    self.logger.info(f"agent session={agent.get('session_id')} "
                     f"budget={agent.get('budget_tokens_left')}")
    agent['budget_tokens_left'] = agent.get('budget_tokens_left', 0) - 100

    # Delegate to another command; the same ctx is threaded automatically:
    p = self._prepare_input_from_params({'ctx': ctx, 'arg1': arg1}, base=True)
    p['command'] = 'update'
    return self.cm.access(p)
```

Conventions when using ctx as an agent bus:
- **Use a namespaced key** (`ctx['agent']`, `ctx['trace']`, ...) — don't touch
  framework keys listed in the table above.
- **ctx is not deep-copied per call** (only top-level of `params` is), so any
  changes you make inside a hook are visible upstream. If you want to isolate
  a subtree, `copy.deepcopy` your key before passing it down.
- **Reproducibility**: agent-added keys are dumped by `--dump` into
  `cmeta-ctx.json`, and (partially) by `--repro`. Great for tracing what an
  agent did.
- **Serialization**: put only JSON-serialisable data in ctx if you rely on
  `--dump`/`--repro` — model handles or file objects should live outside ctx.

## 6. Common patterns

### 6.1 Find, then act

```python
r = cm.access({'category': 'note', 'command': 'find',
               'arg1': 'daily-*', 'tags': 'draft', 'sort': True})
for a in r.get('artifacts', []):
    path = a['path']
    cmeta = a['cmeta']
    ref_parts = a['cmeta_ref_parts']   # {repo_alias, repo_uid, artifact_alias, ...}
```

### 6.2 Get-or-create

```python
r = cm.access({'category': 'config', 'command': 'get',
               'arg1': 'default'})
# r['created'] = True if it was just created.
config_cmeta = r['config_cmeta']       # config category returns config_cmeta
```

### 6.3 Update metadata (deep merge, list-append)

```python
r = cm.access({'category': 'experiment', 'command': 'update',
               'arg1': 'e1',
               'meta': {'results': {'accuracy': 0.91},
                        'tags':    ['gpu', 'validated']},
               'new_tags': 'gpu,validated'})   # comma-separated or list; use "-tag" to remove
```

### 6.4 Read + parse extra sidecar files

```python
r = cm.access({'category': 'script', 'command': 'read',
               'arg1': 'my-script',
               'load_files': ['README', 'config']})   # extensions auto-detected (yaml/json/md)
loaded = r['artifact']['loaded_files']
```

### 6.5 Reindex on-demand

```python
cm.repos.reindex(con=False)             # or: cm.access({'reindex': True})
```

## 6.6 Use `cm.utils.*` from category code — **recommended**

Every hook has `self.cm.utils` bound to the framework's helper modules
(`common`, `files`, `names`, `net`, `sys`, `cli`). **Prefer them over stdlib
re-implementations** whenever they exist. Every category shipped in
`internal-repo/` follows this convention — you'll see the same idioms across
`repo`, `app`, `config`, `utils`, `note`, `experiment`, etc.

**Why it matters**

- **Reusability.** These helpers are already the "cMeta way" — one call
  handles YAML *and* JSON, one call adds a file lock, one call captures env
  changes from a subprocess. New categories composed of these helpers plug
  into every other category the same way.
- **Debuggability.** They log through `self.logger` and integrate with
  `--debug` / `CMETA_DEBUG=1`, and they honour `self.fail_on_error` so
  behavior is consistent across all categories.
- **Portability.** They abstract Windows / Linux / macOS differences —
  path quoting (`quote_path`, `quote_path2`), process trees
  (`sys.run` kills the whole tree on Windows), file locks, path safety
  (`is_path_within`), atomic writes, secret masking, env-diff capture.
- **Composability.** They return the standard `{'return': 0, ...}` dict —
  the same contract as `access()` — so you can propagate errors with
  `if self.cm.catch_error(r): return r` without adapters.
- **Safety.** `safe_read_file` / `safe_write_file` use file locks, atomic
  temp-file rename, retries, and proper YAML/JSON detection. Rolling your
  own with `open()` risks partial writes and races.
- **Reproducibility.** `sys.run(..., save_script='...', hide_in_cmd=[...],
  hide_in_env=[...], capture_env=True)` writes the exact command that ran
  and captures its env delta — for free — while masking secrets from the
  repro dump.
- **Consistency for AI agents.** An agent inspecting a category sees the
  same idioms everywhere and can generalize.

**Idiom mapping (stdlib vs. `cm.utils.*`)** — reach for the right column:

| Stdlib approach | Prefer this |
|-----------------|-------------|
| `open(path).read()` + `json.loads()` / `yaml.safe_load()` | `self.cm.utils.files.safe_read_file(path, lock=True)` — auto-detects YAML/JSON, file-locked, retries. |
| `open(path, 'w').write(json.dumps(...))` | `self.cm.utils.files.safe_write_file(path, obj, atomic=True)` — atomic + locked; preserves key order with `sort_keys=False`. |
| `shutil.rmtree` | `self.cm.utils.files.remove_files_and_dirs_in_path(path)` — Windows read-only handling, extended path support. |
| `subprocess.run([...])` | `self.cm.utils.sys.run(cmd, env=..., envs=..., capture_env=True, hide_in_cmd=[...], hide_in_env=[...], save_script='...')` — tree-kill on Windows, secret masking, env-diff, script dump, unified return dict. |
| `dict.update` / manual recursion | `self.cm.utils.common.deep_merge(target, source, append_lists=..., prepend_lists=..., ignore_root_keys=..., remove_if_none=...)`. |
| `del dict[key]` / manual pruning | `self.cm.utils.common.deep_remove(target, spec)`. |
| `d.get(a, {}).get(b, default)` | `self.cm.utils.common.smart_get(d, 'a.b', default)`. |
| `d.setdefault(a, {}).setdefault(b, {})['c'] = v` | `self.cm.utils.common.smart_set(d, 'a.b.c', v)`. |
| Ad-hoc `s.split(',')` for tags | `self.cm.utils.common.normalize_tags(s)` (returns `{'return', 'tags'}`). |
| `str(uuid.uuid4())[:16]` | `self.cm.utils.names.generate_cmeta_uid()` (16-hex, project convention). |
| Manual `packaging` version compare | `self.cm.utils.common.compare_versions(v1, v2)` (returns `{'comparison': '<'\|'='\|'>'}`) or `sort_versions([...])`. |
| Hand-rolled arg parse in a hook | `self.cm.utils.cli.parse_cmd(argv)` — same rules as the top-level `cx` CLI (nested keys, `@file`, `--no-key`, `--k,=csv`, ...). |
| `urllib.request` boilerplate | `self.cm.utils.net.download(url, path=..., show_progress=..., api_key=..., skip_ssl_certificate=...)` and `self.cm.utils.net.access_api(url, params, ...)`. |
| `import requests; requests.post(...)` for cMeta APIs | `self.cm.utils.net.access_api(url, params)` — matches the `{'return', 'response'}` contract. |
| Category-to-category calls with hard-coded aliases | `self.cm.access({'category': self.cmeta['uses_categories']['<name>'], ...})` — rename-safe via UID. |

**Also on `self.cm` itself** — convenience wrappers for debugging inside hooks:

| Name | Does |
|------|------|
| `self.cm.j(obj)` | Safe-print `obj` as JSON. |
| `self.cm.jj(obj)` | Same + trailing blank line. |
| `self.cm.jv(module)` | Print module's public vars. |
| `self.cm.js(obj)` | Return JSON string (for logs). |
| `self.cm.q(path)`, `self.cm.qq(path)` | Cross-platform path quoting for shell commands. |
| `self.cm.error(msg, return_code=1, exception=None)` | Build/raise a standard error dict. |
| `self.cm.catch_error(r)` | **The standard check** — True when there's an error to propagate; skips soft 16; raises at the failure point under `fail_on_error`. |
| `self.cm.catch_error(r, fail16=True)` | Same, but treat a soft "not found" (16) as fatal here. |

**Example — from `internal-repo/category/config/api/v1.py::set_`** (this is
the actual shipped code):

```python
# Load with lock
r = utils.files.safe_read_file(path, lock=True, keep_locked=True,
                               fail_on_error=self.fail_on_error,
                               logger=self.logger)
if r['return'] > 0:
    if r['return'] != 16: return r
    config_data = {}
    config_file_lock = None
else:
    config_data = r['data']
    config_file_lock = r['file_lock']

# Update
if unset:
    config_data = self.cm.utils.common.deep_remove(config_data, meta)
else:
    config_data = self.cm.utils.common.deep_merge(
        config_data, meta, append_lists=False
    )

# Save and release lock atomically
r = utils.files.safe_write_file(path, config_data,
                                file_lock=config_file_lock, atomic=True,
                                fail_on_error=self.fail_on_error,
                                logger=self.logger, sort_keys=False)
if r['return'] > 0: return r
```

Six lines of framework helpers instead of ~40 lines of `open`/`json`/`fcntl`
/`os.replace` boilerplate — and it works identically on Windows.

Note the explicit `if r['return'] != 16` guard in that example: a missing file
is a **soft error** and this command has to *do* something specific in that
branch (start from an empty config). Where you have no such branch, the plain
`if self.cm.catch_error(r): return r` is preferred — it skips 16 for you. See
§9 and `docs/error-handling.md`.

**When it's OK to skip a helper.** If you truly need something not in
`cm.utils` (very domain-specific parsing, a third-party client library that
already handles everything, hot inner loop where a helper's overhead
matters), reach past it. But default to the helper — future you (and every
agent reading your code) will thank you.

## 7. Utilities under `cm.utils`

All modules are directly usable — many of them return the same `{'return': 0, ...}` contract.

**`cm.utils.names`** — the ref parser/restorer used by the framework.
- `generate_cmeta_uid()` → 16-hex UID.
- `parse_cmeta_name("alias,UID")` / `parse_cmeta_obj` / `parse_cmeta_ref`.
- `restore_cmeta_name` / `restore_cmeta_obj` / `restore_cmeta_ref`.
- `is_valid_cmeta_uid` / `is_valid_cmeta_alias` / `is_valid_category_alias`.

**`cm.utils.common`** — dict, tag, version helpers.
- `deep_merge(target, source, append_lists=, prepend_lists=, ignore_root_keys=, remove_if_none=)`
- `deep_remove(target, source)`
- `normalize_tags("a,b,c")` → list.
- `compare_versions("1.2.3", "1.2.4")` → `{'comparison': '<'|'='|'>'}`.
- `flatten_dict`, `smart_get(dict, "a.b.c")`, `smart_set(dict, "a.b.c", v)`, `smart_merge`.
- `matches_query(cmeta, query)` for `--match` filtering.
- `safe_print_json*`, `safe_serialize_json`, `expand_string("{{VAR}}")`.
- `detect_cid_in_the_current_directory(cm)` — the engine of `cx . info`.
- `copy_text_to_clipboard(text)`.

**`cm.utils.files`** — safe I/O for artifact metadata.
- `read_file` / `write_file` / `safe_read_file` (with file-lock) /
  `safe_write_file` (atomic + lock) / `safe_read_file_via_cache` /
  `safe_read_yaml_or_json`.
- `unzip` / `zip_directory`.
- `remove_files_and_dirs_in_path`, `safe_delete_directory`, `is_dir_empty`,
  `ask_to_delete(con, force, path, ...)`.
- `load_files(path, [...])` — used by `read`/`find` for `load_files=`.
- `md5sum(path)`, `get_latest_tree_modification_time(path)`, `get_creation_time`.
- `quote_path` / `quote_path2` — cross-platform path quoting for shell commands.
- `parse_env_dump` / `diff_env` for capturing environment deltas.

**`cm.utils.sys`** — process, host info, module loading.
- `run(cmd, work_dir=, env=, envs=, con=, verbose=, capture_env=, hide_in_cmd=, hide_in_env=, save_script=, ...)`
  returns `{'return', 'returncode', 'stdout', 'stderr'}`. Handles Windows tree
  kill, env-diff capture, secret masking, and script dumping for reproducibility.
- `get_min_host_info()`, `get_disk_space(path, unit='GB', nice=True)`,
  `get_dir_size`, `format_size`.
- `load_module(path, cache, init_class="Category", ...)` — how the framework
  loads `api/v1.py`.
- `find_command_func`, `get_api_info`, `get_api_text` — help rendering.

**`cm.utils.net`**
- `access_api(url, params, headers=, timeout=)` — POST JSON to an API and get
  parsed JSON back.
- `download(url, filename=, path=, show_progress=, headers=, api_key=, skip_ssl_certificate=)`.

**`cm.utils.cli`**
- `parse_cmd(cmd_list, fail_on_error=)` — parses CLI flags (`--k=v`, `--no-k`,
  `--k.child=v` nested, `@file`, `--` separator, positional `args`).
- `check_params`, `print_params_help`.

Also convenience aliases exposed on `CMeta` itself: `cm.j`, `cm.jj`, `cm.jv`,
`cm.js` (JSON printing helpers), `cm.q`, `cm.qq` (path quoting).

## 8. Auto-install / detect Python packages: `cm.packages`

```python
r = cm.packages.get('fastapi', version_min='0.100')
if r['return'] != 0: raise RuntimeError(r['error'])
pkg = r['package']         # PackageResult(module=<module>, name, version, satisfies, specifier, installed_now)
FastAPI = pkg.module.FastAPI

# Bulk resolution:
r = cm.packages.get_all({
    'requests':  {'version_min': '2.30'},
    'tqdm':      None,                    # any version
    'pydantic':  {'specifier': '>=2,<3'},
})
```

- Honours the `--allow-install`/instance flag; if disabled and missing → error.
- Version specs accept `version`, `version_min`, `version_max`, `specifier`
  (PEP 440 or Poetry-style — auto-converted).
- Cached in-process; safe to call in hot paths.
- Set `CMETA_PIP_INSTALL_ARGS` (or `add_install_args=`) to inject extra pip
  flags (`--index-url=...`, `--proxy=...`).

## 9. Error handling contract

**Use this form everywhere:**

```python
r = self.cm.access({...})
if self.cm.catch_error(r): return r
```

It raises at the point of failure when `fail_on_error` is on (real traceback
under a debugger), and it **skips code 16** — the soft "not found" that `find`
returns and that callers routinely continue past.

`if r['return'] > 0: return r` is the simplified form: acceptable for
prototyping, but it has no debugging hook and treats a soft 16 as fatal.

```python
if self.cm.catch_error(r, fail16=True): return r   # a missing artifact IS fatal here
return self.cm.error('message', 1, exception=e)    # build (or raise) an error dict
self.cm.catch_error_and_halt(r)                    # top-level scripts: print + sys.exit
```

Low-level helpers with no `self.cm` use `_error(msg, code, exc, fail_on_error)`
directly and take `fail_on_error` as a forwarded parameter.

Full guide, incl. return codes and IDE debugger setup: `docs/error-handling.md`.

## 10. Reproducibility hooks

- `--repro` (or `params['repro']=True`) writes `cmeta-repro-input.json`,
  `cmeta-repro-input2.json`, and `cmeta-repro-output.json` in `cwd`.
- `--dump` (or `params['dump']=True`) writes `cmeta-ctx.json` — the full
  post-call ctx (useful with the agent-namespaced keys from §5).
- `--json` / `--jf=<file>` for machine-readable stdout / file.
- Wrap secrets you pass to `cm.utils.sys.run(...)` with `hide_in_cmd=[...]` and
  `hide_in_env=[...]` so they don't land in the repro dumps.

## 11. Source-of-truth pointers

- Dispatch + ctx assembly: `cmeta/core.py::CMeta.access()`.
- Base commands: `cmeta/category_api_v1.py`.
- Category base class: `cmeta/category.py::InitCategory`.
- Ref parsing: `cmeta/utils/names.py`.
- Repos + index: `cmeta/repos.py`.
- Packages / auto-install: `cmeta/packages.py`.
- Global config, params descriptors, aliases: `cmeta/config.py`.
- Async wrapper: `cmeta/core_async.py`.
- Companion CLI skill: `.claude/skills/use-cmeta-cli/SKILL.md`.
- User walkthrough: `docs/using-cmeta.md`.
- Adding categories / repos: `.claude/skills/add-plugin/`, `.claude/skills/add-repo/`.
