---
name: add-repo
description: Register a cMeta content repository — either by pulling an existing one (git URL, zip URL, `cmeta://` short-hand, local zip) or by creating a fresh empty local repo. Use when the user asks to "add a repo", "clone a cMeta repo", "init a new local repo", "plug an existing folder", or wants to know where repos live and how `_cmr.yaml` is generated.
---

# add-repo — get or create a cMeta repository

> **Status: first draft — review before relying on it.** `cx repo <cmd> --help`
> is the source of truth; if a step here disagrees with the CLI, trust the CLI.

A **cMeta repository** is a directory with an `_cmr.yaml` (or `_cmr.json`) at
its root plus artifacts under `<repo>/<category>/<artifact>/`. Once registered,
the framework indexes every artifact in it alongside every other plugged-in
repo. Registration lives in `<CMETA_HOME>/repos.json`; the default drop
location for repos cMeta itself pulls is `<CMETA_HOME>/repos/<alias>/`.

Every repo command below is a thin variant of one internal function
(`internal-repo/category/repo/api/v1.py::get_`) — the differences are how it's
invoked and which method it forces.

---

## 1. Decide which flavour the user needs

| Situation | Command |
|-----------|---------|
| Pull a published cMeta repo (cTuning zip mirror) | `cx repo get cmeta://<name>` |
| Clone from a git URL | `cx repo get <alias> --url=<git-url>` |
| Fetch a zip from any URL | `cx repo get <alias> --url=<zip-url>` |
| Import a local zip file | `cx repo unzip <path.zip>` |
| Start a brand-new empty local repo | `cx repo init <alias>` |
| Register an existing folder without moving anything | `cx repo plug [<path>]` |
| Unregister without deleting the folder | `cx repo unplug <alias>` |

Ask the user which one applies if it's ambiguous — the wrong choice can end up
either downloading unnecessary data or leaving stale entries in the registry.

---

## 2. Pulling an existing repo

### 2.1 cTuning short-hand (`cmeta://`)

```bash
cx repo get cmeta://<name>                     # latest release
cx repo get cmeta://<name> --checkout=<tag>    # specific version
```

Under the hood this expands to a zip URL from the `default` config
(`default_cmeta_repo_url` → falls back to `cmeta/config.py`), downloads it and
extracts under `<CMETA_HOME>/repos/<name>/`.

### 2.2 Git URL

```bash
cx repo get <alias> --url=https://github.com/<org>/<repo>
cx repo get <alias> --url=git@github.com:<org>/<repo>.git --checkout=main
cx repo clone <alias> --url=<git-url>          # equivalent (forces method=git)
```

Alias short-hand for cTuning-hosted git repos:

```bash
cx repo get <name>                             # -> default_git + default_git_repo@<name>
cx repo get <org>@<name>                       # -> default_git + <org>/<name>
```

`default_git` / `default_git_repo` come from the `default` config artifact
(configurable via `cx config set default --meta.default_git=git@github.com:`).

### 2.3 Zip URL / local zip file

```bash
cx repo get <alias> --url=https://example.com/pack.zip   # method auto-detected
cx repo unzip <path-to-zip-file>                         # method = local_zip
```

---

## 3. Creating a new local repo

```bash
cx repo init <alias>                # safe: refuses if the repo already exists
cx repo create <alias>              # same, but tolerates an existing empty folder
cx repo add <alias>                 # global alias for create (add → create)

# With a custom path (anywhere on disk):
cx repo add <alias> --path=<absolute-or-relative-path>

# With extra metadata written into _cmr.yaml:
cx repo add <alias> --path=<path> --meta.description="research notes" \
                                  --meta.subdir=data
```

What happens:

1. The folder is created (or reused, for `add`/`create` when empty).
2. If missing, `_cmr.yaml` is generated with:
   ```yaml
   artifact: <alias>,<generated-16-hex-UID>
   category: repo,f4f792ab40c7498f
   ```
   plus any `--meta.*` you passed. If present it's read and augmented (UID
   generated only if absent).
3. The path is appended to `<CMETA_HOME>/repos.json` with
   `{'meta': {'method': 'local'}}`.
4. The index is refreshed so artifacts placed in the repo become findable.

Use `init` for the "safe first time" case; use `add`/`create` when you want to
attach to an existing empty directory (or already know it's not registered).

---

## 4. Attaching / detaching an existing directory

`plug` = register an existing folder as a cMeta repo without touching its
contents. `unplug` = the reverse — unregister without deleting.

```bash
cx repo plug                       # register the current directory
cx repo plug <path>                # register the given path (absolute or relative)
cx repo plug <alias> --path=<path> # register with a specific alias

cx repo unplug <alias>             # unregister
cx repo unplug                     # unregister whatever repo owns the current dir
```

Use `plug` for repos on shared drives, USB sticks, network mounts, or existing
git checkouts. Combine with `--meta.keep=true` (or edit `_cmr.yaml`) if the
path is intermittently offline and you want registration preserved across
`--reindex`.

---

## 5. Everyday repo housekeeping

```bash
cx repo list                       # list registered repos (insertion order)
cx repo find <alias-or-uid>        # find a repo
cx repo status <alias>             # git status + remote URL for git-backed repos
cx repo pull <alias>               # git pull; also refreshes the index
cx repo update <alias>             # equivalent to pull
cx repo checkout <alias> <ref>     # git checkout branch/tag/commit
cx repo space <alias>              # disk usage
cx repo zip <alias>                # dump to cmr-<alias>-YYYYMMDD-HHMMSS.zip
cx repo delete <alias>             # unregister AND delete files (unless permanent)
```

`cx repo move` is intentionally **not supported** — renaming a repo would break
`alias,UID` references written elsewhere. If you truly need a different name,
create a new repo, copy artifacts across, then delete the old one.

---

## 6. Verify

After adding a repo, sanity-check:

- [ ] `cx repo list` shows the new repo with the expected path.
- [ ] `cat <repo>/_cmr.yaml` shows `artifact: <alias>,<UID>` and
      `category: repo,f4f792ab40c7498f`.
- [ ] `cx repo find <alias>` returns exactly one match.
- [ ] `cx category list` (or `cx <cat> ls`) now includes the new repo's
      artifacts.
- [ ] `<CMETA_HOME>/repos.json` contains the repo's path.

If a repo is registered but its artifacts don't show up in `find`/`ls`, the
fast index is stale — force a rebuild:

```bash
cx --reindex
```

---

## 7. Common gotchas

- **Folder already exists and isn't empty.** `cx repo add/get` refuses to
  clobber a non-empty directory (except when `--local` is set on an existing
  registered repo). Move the content out or pick a different path.
- **`fatal: destination path '...' already exists and is not an empty directory.`**
  Same as above but from `git clone`. `cx repo delete <alias>` first, or use
  `--path=<fresh-dir>`.
- **Wrong URL guess.** cMeta guesses `git` vs `zip` from the URL. Force with
  `cx repo clone` (git) or a `.zip` suffix / `--url=<zip>`.
- **`cx repo pull` did nothing.** The repo isn't registered as `method: git`
  (check `<CMETA_HOME>/repos.json`). For non-git repos, re-fetch with the
  original method.
- **Registered path outside `<CMETA_HOME>/repos/`.** Fine — it just needs an
  `_cmr.yaml`. `cx repo unplug` doesn't touch the files; `cx repo delete`
  does.
- **Renaming a repo alias.** Not supported. Reference repos by `alias,UID` in
  cross-repo references so alias renames wouldn't matter anyway.
- **`_cmr.yaml` edited by hand and things look off.** `cx --reindex` to
  rebuild `<CMETA_HOME>/index/*.pkl`.
- **`permanent: true` in `_cmr.yaml`.** `cx repo delete` refuses. Remove the
  flag first if you truly want to delete.
- **`subdir:` in `_cmr.yaml`.** Only that sub-tree is scanned for artifacts —
  useful for git repos where cMeta content lives under one folder alongside
  other code.

---

## 8. Programmatic (Python) equivalents

```python
from cmeta import CMeta
cm = CMeta()

# Init a new local repo at a custom path:
r = cm.access({'category': 'repo', 'command': 'init',
               'arg1':    'my-notes',
               'path':    '/data/my-notes'})

# Clone a git repo:
r = cm.access({'category': 'repo', 'command': 'get',
               'arg1':     'cmeta-aops',
               'url':      'https://github.com/ctuninglabs/cmeta-aops',
               'checkout': 'main'})

# Register an existing folder:
r = cm.access({'category': 'repo', 'command': 'plug',
               'arg1':     '/mnt/shared/team-repo'})

# Detach without deleting:
r = cm.access({'category': 'repo', 'command': 'unplug',
               'arg1':     'team-repo'})
```

All calls return `{'return': 0, ...}` on success; `{'return': >0, 'error':
'...'}` on failure — same contract as every other cMeta command.

---

## 9. Source of truth

- Repo command implementations: `cmeta/internal-repo/category/repo/api/v1.py`
  (the common core is `get_`; `pull`, `clone`, `init`, `create`, `plug`,
  `unplug`, `unzip`, `checkout`, `status`, `update` are all thin wrappers).
- Registry file & index handling: `cmeta/repos.py`.
- Global URL / config defaults (`default_git`, `default_git_repo`,
  `default_cmeta_repo_url`): `cmeta/config.py`.
- Repo descriptor filename constant (`_cmr.yaml`): `cmeta/config.py`
  (`repo_meta_desc`).
- User-facing walkthrough: `docs/using-cmeta.md` §6.
- Framework-wide agent brief: `AGENTS.md`.
