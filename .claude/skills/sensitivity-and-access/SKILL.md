---
name: sensitivity-and-access
description: Use cMeta's sensitivity labels and the scope of a call (cMeta 0.44+) - label a repository or an artifact (public, general, confidential, highly-confidential, personal), serve people through a door (a website with users, an API, an MCP server, an agent's key) with clearance / allow_repos / hide_repos / write_repos / default_sensitivity, turn a person's record into those keys with scope_for, show what a person reads and writes with `cx repo scope`, and write server or category code that respects the scope. Use when the user asks who may see or change what, to label or reclassify information, to give someone access, to build a page / API / MCP tool that serves several people, or why an artifact is "not found" for one caller and found for another.
---

# sensitivity-and-access — labels, people and the scope of a call

The guide is [`docs/sensitivity.md`](../../../docs/sensitivity.md) (cMeta for organisations); the reference is
[`docs/using-cmeta.md`](../../../docs/using-cmeta.md) §5.3; the code is `cmeta/repos.py` (`Repos.push_scope`,
`repo_hidden`, `write_refused`, `scope_table`, `scope_for`). If this skill and the code disagree, the code wins.

**First principle: nothing changes unless the keys are used.** A shell, a script, the local `cserver` without users
pass no scope and read and write what the machine holds - as before 0.44. Labels matter only where a server passes a
scope for a person.

---

## 1. Label information

| where | how | effect |
|---|---|---|
| a repository | `sensitivity: confidential` in its `_cmr.yaml` | every artifact in it carries the label |
| one artifact | `sensitivity: highly-confidential` in its `_cmeta` | raises the label of that artifact only (never lowers it) |

Labels: `public`, `general`, `confidential`, `highly-confidential` (Microsoft 365's; `internal`/`private` = general,
`conf` = confidential, `conf-high`/`restricted` = highly-confidential), and `personal`.

- **No label = public.** Never add `sensitivity: public` to a repository just to be explicit - the user's rule: keep
  repositories as they are; labels are added where an organisation needs them.
- Ranked with `personal` without being labelled: a word that is no label (a typo hides, never shows), a repository
  with `secrets: true`, the machine's `local` repository. The engine's `internal` repository is public.
- An edit of `_cmr.yaml` counts at the next call: no reindex.
- **Reclassify** by moving the artifact to the repository of the right label, from a shell
  (`cx <category> move <artifact> <repo>:<artifact>`): under a clearance a move never lowers a label.

## 2. Pass a scope (a door: website, API, MCP, an agent's key)

```python
from cmeta.repos import scope_for

scope = scope_for({'clearance': 'general', 'repos': {'<repo UID>': 'read', '<inbox UID>': 'write'}},
                  default_sensitivity='general')
r = cm.access(dict(request, **scope))      # this call and every call it makes
```

| key | meaning |
|---|---|
| `clearance` | highest label read; `personal` = the server owner's, reads everything (owner only) |
| `allow_repos` | repositories read whatever their label (named grant); the way to another person's personal repository |
| `hide_repos` | never read (wins over both) |
| `write_repos` | the only repositories written into; `none` = no write |
| `default_sensitivity` | the label of unlabelled repositories on this server (`general` on an organisation's site) |

Rules a door must keep:

- Take the scope from the person's record on the server, **never from the request** (a caller must not send its own
  `clearance`).
- Name repositories by UID in records (aliases change on rename or transfer).
- A key never exceeds its owner: a key's own narrower scope is applied as a nested scope (a nested call only
  narrows - a wider clearance, a grant or a lower default inside a cleared call count for nothing).
- Write grants go to repositories of **data** (an inbox), never to one that defines categories, tasks or pages:
  that would let a person run code on the server.

## 3. Check what a person gets

```bash
cx repo scope --clearance=general --allow_repos=<repo> --write_repos=<inbox>     # every repository: label, read, write, why
cx <category> find '*' --clearance=general                                       # what such a call finds
```

`cm.repos.scope_table(scope)` returns the same rows for an administrators' page. It names every repository: show it
to administrators, and a person their own rows only.

"Not found" for one caller and found from a shell is the scope at work: run `cx repo scope` with that caller's keys
and read the `why` column (`above the clearance`, `hidden by name`).

## 4. Write code that runs inside a scoped call

- **Reading and writing for the person**: just call `cm.access` - the engine applies the scope to every nested call
  (find, read, create, update, delete, move, copy, `--connect`).
- **The server's own bookkeeping** (a cache built for every viewer, state in `local`, a trash): wrap it -
  ```python
  saved = cm.repos.suspend_scope()
  try:
      ...                                   # never what the person asked for
  finally:
      cm.repos.pop_scope(saved)
  ```
- **Settings**: a `config` call made by code (no scope keys of its own) is not scoped - nothing to do.
- **Files written directly** (a page that saves a file): ask `cm.repos.write_refused(repo_alias, repo_uid)` first
  (None = allowed), beside the page's own rules; test `cm.repos.scoped` (not `hidden_repos` alone) to know whether
  something is hidden.
- Use `getattr(cm.repos, 'suspend_scope', None)` and the like in code that must also run on an engine before 0.44.
- Connections: under a clearance a link between labels is written on the higher side only (`--ct` from the higher
  artifact); a call with a write scope manages no repository (`cx repo pull/create/delete` refused).

## 5. Test it

Write tests with a fresh `CMETA_HOME` in `tmp_path`, one repository per label, as
`tests/internal_repo_tests/test_integration_sensitivity_scope.py` does: assert both what is found and what is not,
both what is written and what is refused, and that `cm.repos` is clean after the call (no scope left behind).

## 6. Do not

- Treat a label as encryption: whoever has a shell on a machine reads its disk. Put a repository only on machines
  whose administrators may read it; keep a personal repository off shared servers unless that is acceptable.
- Put private names (people, hosts, organisations) of the user into public repositories or examples.
- Change labels of the user's repositories, or add a `default_sensitivity` to a server, without being asked.
