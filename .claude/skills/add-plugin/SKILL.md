---
name: add-plugin
description: Add a new cMeta plugin (category) and/or artifact under an existing content repo, wire up its api/v1.py, and verify it via `cx`. Use when the user asks to "add a new category / plugin / artifact", "scaffold a cMeta command", or "extend cMeta with a new automation".
---

# add-plugin — scaffold a cMeta plugin (category + artifacts)

> **Status: first draft — review before relying on it.** The `cx` commands
> below are the source of truth; if a step here disagrees with
> `cx <category> <command> --help`, trust the CLI.

cMeta is extended by **plugins**. A plugin is a **category** artifact (folder
under `<repo>/<category>/<name>/`) that groups a set of commands implemented in
its own `api/v1.py`. Individual **artifacts** of that category then live under
`<repo>/<category-name>/<artifact-name>/`. The framework auto-inherits standard
CRUD commands from `cmeta/category_api_v1.py`; you only add what's specific to
your plugin.

---

## 1. When to reach for this skill

- User wants a new `cx <category> <command>` surface that doesn't fit an
  existing category (`app`, `script`, `experiment`, `note`, ...).
- User wants to scaffold a new artifact under an existing category.
- User is unclear on the `foo_` vs `foo` method-name convention, on the
  `alias,UID` resolution rules, or on how to re-enter `cm.access()` from an
  api hook.

If the user just wants a *new artifact of an existing category* (e.g. a new
`note` or `experiment`), skip step 2 and jump to step 4.

---

## 2. Add a new category (plugin)

```bash
# Into the default local repo:
cx category add <alias>

# Into a specific repo (by alias, UID, or alias,UID):
cx category add <repo>:<alias>

# With tags and starting metadata:
cx category add <alias> --tags=tag1,tag2 --meta.description="What this manages"
```

Under the hood (`cmeta/internal-repo/category/category/api/v1.py::create`) this:

1. Delegates to the base `create_` in `category_api_v1.py`, which writes the
   folder and `_cmeta.yaml` (UID, category ref `category,dd9ea50e7f76467f`,
   `last_api_version: 1`, `base_category_default_api_versions: {'1': 1}`).
2. Creates `api/` and copies the starter template
   (`cmeta/internal-repo/category/category/v1-template.py`) into `api/v1.py`.

Verify:

```bash
cx category find <alias>          # confirm it's indexed
cx <alias> --help                 # lists inherited base commands + your test_/test2
cx <alias> test hello --flag1     # smoke-test the generated api/v1.py
```

If `cx <alias>` doesn't see the category, force a rebuild of the artifact
index: `cx --reindex`.

### Rename / delete

```bash
cx category mv <old> <new>        # move within/between repos (does NOT rename alias)
cx category rm <alias>            # deletes the category artifact
```

Renaming a category alias is **intentionally blocked** for backward
compatibility (see `category/api/v1.py::move`). Two ways to cope:

- Reference the category everywhere as `alias,UID` — that form uses the UID
  only, so alias renames are irrelevant.
- If you really want a different alias, create a new category and copy
  artifacts across.

---

## 3. Understand category & artifact resolution

Every category and artifact has:
- an **alias** — human-friendly name (`repo`, `cserver`, ...)
- a **UID** — stable 16-hex-char identifier (`f4f792ab40c7498f`)

References accept **three forms**:

| Form | Example | Notes |
|------|---------|-------|
| alias | `repo` | Human-friendly, breaks on rename. |
| UID | `f4f792ab40c7498f` | Always resolves, unreadable. |
| `alias,UID` | `repo,f4f792ab40c7498f` | **Best.** UID is authoritative; alias is advisory. Rename-safe. |

Cross-repo: prefix with a repo name: `<repo>:<name>`.
Full cRef: `<category>::<artifact>`, e.g.
`category,dd9ea50e7f76467f::repo,f4f792ab40c7498f`.

**In `api/v1.py`, prefer `alias,UID` (or `uses_categories`) whenever you
reference another category or artifact — it keeps your plugin working when
someone renames things later.**

---

## 4. Author `api/v1.py`

Every category API subclasses `cmeta.category.InitCategory` and exposes command
methods. Two calling conventions are supported; **the trailing underscore
matters**:

```python
from cmeta.category import InitCategory

class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    # ---- Convention A: typed kwargs + ctx (RECOMMENDED for new commands) ----
    def hello_(              # trailing single "_" — user invokes as: cx <category> hello
        self,
        ctx,                 # execution context (category, command, control)
        arg1=None,           # first positional CLI arg -> --arg1 also works
        flag1=False,         # --flag1 boolean
        name="world",        # --name=... string
    ):
        """One-line summary shown in `cx <category> hello --help`.

        Longer description also shown in the auto-generated help.
        """
        self.logger.debug("hello_ called")
        print(f"Hello {name}! arg1={arg1} flag1={flag1}")
        return {'return': 0, 'message': f'hi {name}'}

    # ---- Convention B: raw params dict (for dispatch / thin wrappers) ----
    def dump(                # NO trailing _ — user invokes as: cx <category> dump
        self,
        params: dict,        # entire request dict; ctx is params['ctx']
    ):
        import json
        print(json.dumps(params, indent=2))
        return {'return': 0}
```

Why the underscore matters (`cmeta/core.py`):

- `foo_` (single trailing `_`, **not** `__`) → called with `**command_params`
  (typed kwargs incl. `ctx`).
- `foo`, `foo__`, `foo___` → called with **one positional `params` dict**.
  Trailing `__` / `___` are stripped from the CLI name (used to avoid clashing
  with Python builtins like `list`, `type`, `input`).

### Return contract

Always return a dict:

- Success: `{'return': 0, ...extra keys...}`
- Failure: `{'return': <int > 0>, 'error': '<message>'}` — or call
  `return self.cm.error("...")`.

The CLI turns this into stdout + non-zero exit code automatically.

### Prefer `self.cm.utils.*` over stdlib re-implementations

Every hook has `self.cm.utils` bound to the framework's helpers (`common`,
`files`, `names`, `net`, `sys`, `cli`). **Default to these** — every shipped
category uses them, and they give you cross-platform behavior, file locks +
atomic writes, secret masking, uniform `{'return': 0, ...}` returns, and
`--debug`-aware logging for free. Common substitutions:

- `open(p).read()` + `json/yaml.loads` → `self.cm.utils.files.safe_read_file(p, lock=True)`
- `open(p, 'w').write(...)` → `self.cm.utils.files.safe_write_file(p, obj, atomic=True)`
- `subprocess.run(...)` → `self.cm.utils.sys.run(cmd, env=..., envs=..., capture_env=True, hide_in_cmd=[...], save_script='...')`
- `dict.update` recursion → `self.cm.utils.common.deep_merge(target, source, append_lists=..., ignore_root_keys=...)`
- `s.split(',')` for tags → `self.cm.utils.common.normalize_tags(s)`
- `d.get('a', {}).get('b')` → `self.cm.utils.common.smart_get(d, 'a.b')`
- `str(uuid.uuid4())[:16]` → `self.cm.utils.names.generate_cmeta_uid()`
- Ad-hoc HTTP → `self.cm.utils.net.access_api(url, params)` / `download(url, ...)`

Full catalog and reasoning in `.claude/skills/use-cmeta-python/SKILL.md` §6.6
and §7.

### Re-entering the framework (calling other categories)

Use `self.cm.access(...)` to invoke any other command from inside a hook.

For the **base CRUD** of the same category, prefer
`_prepare_input_from_params(..., base=True)` so the current
category/command/control flags carry through:

```python
def status_(self, ctx, arg1=None):
    p = self._prepare_input_from_params({'ctx': ctx, 'arg1': arg1}, base=True)
    p['command'] = 'find'
    r = self.cm.access(p)
    if r['return'] > 0: return r
    return {'return': 0, 'count': len(r.get('artifacts', []))}
```

For **other categories**, declare them in your `_cmeta.yaml`:

```yaml
uses_categories:
  config:   config,cc6bfe174be847ed
  utils:    utils,234ce5e3262e4d52
```

Then reference them semantically (rename-safe):

```python
r = self.cm.access({'category': self.cmeta['uses_categories']['config'],
                    'command': 'get',
                    'arg1': self.cm.cfg['default_config_name']})
```

The `alias,UID` form ensures the call keeps working even if `config` is
renamed later. See real usage in `internal-repo/category/app/api/v1.py`,
`internal-repo/category/repo/api/v1.py`.

### Command aliases

Global aliases live in `cmeta/config.py` (`add→create`, `rm→delete`, `ls→list`,
`search→find`, `mv→move`, `cp→copy`, `ren/rename→move`, `load→read`).
Add per-category aliases via `command_aliases:` in `_cmeta.yaml`:

```yaml
command_aliases:
  hi: hello
  greet: hello
```

### Logging & debug

`self.logger` is a per-category child logger. Run with `--debug` or
`CMETA_DEBUG=1` to see the full dispatch trace including the exact file/line of
the resolved command function.

---

## 5. Add an artifact of a category

Base commands (from `cmeta/category_api_v1.py`) are inherited by every
category unless it sets `skip_base_category_commands: true`:

```bash
cx <category> add <alias>                    # create artifact in default repo
cx <category> add <repo>:<alias> --tags=t1,t2 --yaml
cx <category> ls                             # list artifacts
cx <category> find <alias-or-uid>
cx <category> info <alias>                   # show path + cRef, copy to clipboard
cx <category> read <alias>                   # print/parse _cmeta.yaml
cx <category> update <alias> --meta.k=v      # merge into metadata
cx <category> tags <alias> --add=t1 --remove=t2
cx <category> rm <alias>
cx <category> mv <old> <new>
```

`--yaml` writes `_cmeta.yaml` instead of `_cmeta.json` (prefer YAML — it's
what shipped artifacts use). Use `--virtual --path=<dir>` to register an
existing directory as an artifact without moving files (external repos, in-tree
code).

### Per-artifact hooks (`api_v1.py`)

An individual artifact can ship its own `api_v1.py` at
`<repo>/<category>/<artifact>/api_v1.py` with `customize*` hooks invoked at
well-defined lifecycle points (typically wired via a `_desc.yaml` in the
artifact). Use these only when a category-level command isn't the right home
for the logic.

---

## 6. Useful `_cmeta.yaml` fields to know when authoring

| Field | When to use |
|-------|-------------|
| `permanent: true` | Mark foundational artifacts that must not be deleted. |
| `no_index: true` | Very large / ephemeral artifacts you don't want in the fast index (found by filesystem scan instead). |
| `last_api_version: 1` | Highest API version shipped by this category (`api/v1.py`). Bump when you add `api/v2.py`. |
| `base_category_default_api_versions: {'1': 1}` | Base API version to inherit per your category's API version. |
| `min_cmeta_version: {'1': '0.30.0'}` | Minimum framework version required per API version. |
| `skip_base_category_commands: true` | Category doesn't want inherited CRUD (rare — see `utils`). |
| `find_sort: false` | Don't alpha-sort `find` results (rare — see `repo`, `category`). |
| `command_aliases: {...}` | Per-category CLI aliases. |
| `uses_categories: {...}` | Declare cross-category dependencies (see §4). |
| `tags: [...]` | Tag your artifact for discovery. |

---

## 7. Cache & reindex — quick sanity check

If something looks stale (renames, `git pull` on a repo, hand-edited YAML, or
`CMETA_HOME` was wiped):

```bash
cx --reindex        # cleans and rebuilds <CMETA_HOME>/index/*.pkl
```

The framework normally keeps the index consistent automatically on
`create`/`update`/`delete` and on `cx repo` operations. Category-level content
caches (task results, downloaded blobs) live under the `cache` category:

```bash
cx cache show
cx cache clean
cx cache delete <alias-or-uid>
```

---

## 8. Verification checklist

Before reporting the plugin as done:

- [ ] `cx category find <alias>` returns exactly one match.
- [ ] `cx <alias> --help` lists inherited base commands and your new commands,
      each with a one-line summary from the docstring.
- [ ] `cx <alias> <your-command> --help` shows typed args/flags.
- [ ] `cx <alias> <your-command> ...` runs and returns exit 0.
- [ ] If your plugin references other categories, they resolve without
      `--reindex`.
- [ ] References to other categories use `alias,UID` (via `uses_categories`),
      not bare alias — plugin survives renames.
- [ ] `python -m pytest tests` still passes (or a new test you added does).

---

## 9. Common gotchas

- **Forgot the trailing `_`.** A method named `foo` gets one positional dict;
  if you defined typed kwargs Python raises
  `TypeError: foo() takes 2 positional arguments but ...`. Rename to `foo_`.
- **Command name clashes with a Python builtin** (`list`, `type`, ...). Name
  the method `list__` — the CLI name is still `list`.
- **New category isn't found.** The artifact index is cached; run `cx --reindex`.
- **Base command not exposed.** The category's `_cmeta.yaml` sets
  `skip_base_category_commands: true` (e.g. `utils`). Remove that flag or
  reimplement the command.
- **Renaming a category alias.** Blocked on purpose. Reference by `alias,UID`
  instead — or create a new category and migrate.
- **Hard-coded bare aliases across categories.** Use `uses_categories` +
  `alias,UID`; otherwise your plugin breaks the day someone renames the target.

---

## 10. Pointers to source of truth

- Base commands & signatures: `cmeta/category_api_v1.py`
- Category `create`/`move`/`delete` implementation: `cmeta/internal-repo/category/category/api/v1.py`
- Starter template copied on create: `cmeta/internal-repo/category/category/v1-template.py`
- Command-name convention (`foo_` vs `foo`): `cmeta/core.py` around lines
  ~710 and ~820 (help rendering + dispatch).
- Alias/UID resolution: `cmeta/utils/names.py::parse_cmeta_name` and
  `cmeta/repos.py::find_in_index`.
- Index rebuild: `cmeta/repos.py::reindex` / `index`.
- Global aliases & config keys: `cmeta/config.py`.
- Broader agent guidance for the framework: `AGENTS.md`.
- User-facing walkthrough: `docs/using-cmeta.md`.
