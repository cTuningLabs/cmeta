# Sensitivity labels and access: cMeta for organisations

cMeta reads and writes whatever its machine holds. That stays true for a shell and for everything that worked
before. When a server lets people in - a website with users, an API, an MCP server, an agent's key - each person
should get only part of it. This page shows the three things an organisation adds for that: **labels** on its
repositories, a **record** per person, and the **scope** a server passes with every request it makes for that
person. The engine enforces the scope; nothing changes for a call that passes none.

Available since cMeta 0.44.0.

---

## 1. Label the repositories

A repository declares its label in its `_cmr.yaml`:

```yaml
alias: deals
uid: 4f0c2b9e1a7d4c3e
sensitivity: confidential
```

| label | for | synonyms read |
|---|---|---|
| `public` | approved for anyone, inside and outside | |
| `general` | day-to-day internal work, fine to share inside the organisation | `internal`, `private` |
| `confidential` | contracts, finances, customer data, HR - for the people who need it | `conf` |
| `highly-confidential` | strategy, legal matters, personal data - strict access | `conf-high`, `restricted` |
| `personal` | what belongs to one person | |

These are the four labels of Microsoft 365, which most organisations use under these or similar words, plus
`personal`.

- **A repository without a label is public.** Labels are added repository by repository; a server chooses another
  default for the unlabelled ones it serves (`default_sensitivity`, below).
- **Ranked with `personal` without saying so:** a word that is no label (a typing mistake hides, never shows), a
  repository of secrets (`secrets: true`) and the machine's own `local` repository (its logs, caches and config
  artifacts). The engine's `internal` repository is public: the categories live there.
- **An artifact can raise its own label** with `sensitivity:` in its `_cmeta` - one sensitive note in a general
  repository. It never lowers it.
- A label edited in `_cmr.yaml` counts at the next call: no reindex, no restart.

---

## 2. The scope of a call

A server passes these keys with every request it makes for a person - control keys of `cm.access`, flags of every
command:

| key | what it does |
|---|---|
| `clearance` | the highest label the call reads: `public`, `general`, `confidential`, `highly-confidential`, or `personal` - the server owner's, which reads everything |
| `allow_repos` | repositories read whatever their label: a named grant (aliases, UIDs, patterns) |
| `hide_repos` | repositories never read, whatever the clearance or the grants |
| `write_repos` | the only repositories the call may write into; `none`: no write at all |
| `default_sensitivity` | the label of the repositories that declare none (`general` on a site of an organisation) |

```python
r = cm.access({'category': 'note', 'command': 'find', 'arg1': '*',
               'clearance': 'general', 'allow_repos': 'deals', 'write_repos': 'inbox',
               'default_sensitivity': 'general'})
```

```bash
cx note find '*' --clearance=general --allow_repos=deals --write_repos=inbox
```

What is above the clearance is not found, listed, searched, drawn or read - by alias, by UID, by tag, by a page -
and not written into. The scope holds for every call the request makes; a nested call can narrow it, never widen
it.

---

## 3. A person's record

A server keeps per person a record like this one and turns it into the keys with `scope_for`:

```python
from cmeta.repos import scope_for

record = {'clearance': 'general',
          'repos': {'deals': 'read', 'inbox': 'write', 'drafts': 'none'}}

scope = scope_for(record, default_sensitivity='general')
# {'clearance': 'general', 'hide_repos': ['drafts'], 'allow_repos': ['deals', 'inbox'],
#  'write_repos': ['inbox'], 'default_sensitivity': 'general'}

r = cm.access(dict(request, **scope))
```

- A record without a clearance reads `general`; one with no write grant writes nowhere.
- `personal` as a clearance is for the server's owner alone: it reads every person's personal repositories too.
  Another person reads a personal repository by a grant of that repository.
- Name repositories by their UIDs where they may be renamed or moved to another owner: a denial by an alias that
  changed no longer denies.

---

## 4. What a person gets

`cx repo scope` takes the same flags and prints, for every repository, its label and whether such a call reads it
and writes into it - what a page of users shows per person (`cm.repos.scope_table(scope)` from Python):

```text
$ cx repo scope --clearance=general --allow_repos=deals --write_repos=inbox

REPOSITORY   SENSITIVITY              READ  WRITE
deals        confidential             yes   -      above the clearance, granted by name
inbox        general                  yes   yes    within the clearance
plans        highly-confidential      -     -      above the clearance
team-notes   public (no label)        yes   -      within the clearance
local        personal (this machine)  -     -      above the clearance
```

---

## 5. Writes under a scope

| | |
|---|---|
| create, update, delete, move, copy | only into `write_repos`, never into a repository the call does not read; refused before anything is touched |
| a connection (`--connect`) | a write on both sides (`--ct`: this side only); under a clearance written on the higher label's side only - the name of a confidential artifact never lands in a general one |
| move, copy | under a clearance never to a lower label; reclassifying down is done from a shell |
| repositories | a call with a write scope pulls, creates, unzips, unplugs and deletes none |

---

## 6. For the code of a server

- The machine's settings are read by the code that serves a request: a call into the `config` category that carries
  no scope keys itself is not scoped. The request a server forwards for a person carries them, and is.
- A server's own bookkeeping inside a request - a model built once for every viewer, its state in `local` - goes
  between `saved = cm.repos.suspend_scope()` and `cm.repos.pop_scope(saved)`; never around what the person asked
  for.
- A page that writes files itself asks `cm.repos.write_refused(alias, uid)` (None: allowed) beside its own rules.
- The scope is per `CMeta` object: a server that serves several people at once gives each request its own
  (`CMetaAsync`'s workers have one each).
- Cost: a clearance reads each repository's `_cmr.yaml` status once per request - about 0.3 ms for 18 repositories;
  without a clearance nothing is added.

---

## 7. Organising repositories

- **One repository per label and audience** - `general`, `confidential`, `highly-confidential`, one per customer or
  topic where the audience differs. A label belongs to a repository; people belong to records.
- **One writing machine per repository.** Curated repositories are written where they are curated; what people
  write through a server goes to an inbox repository written only on that server, curated and moved from there.
- **Keep what people write through a door in repositories of data.** A repository that defines categories, tasks or
  pages holds code the server runs: a write grant there lets a person run code. A scope is no sandbox.
- **Git access must agree with the labels.** A repository cloned to people's machines has a second access list - the
  git server's teams. Confidential and highly-confidential repositories can stay off git entirely and be reached
  through the server only.
- **A label is not encryption.** Whoever has a shell on a machine reads its disk; put a repository only on machines
  whose administrators may read it.

---

## 8. A checklist for a server

1. Label the repositories it serves; decide its `default_sensitivity` (`general` for an organisation).
2. Keep a record per person: a clearance, grants by repository UID, write grants to inbox repositories.
3. Pass `scope_for(record, default_sensitivity=...)` with every request - pages, API, MCP; never let a request set
   its own scope keys.
4. Keep the owner's `personal` clearance for the owner; administrators see the rights of everyone with
   `cx repo scope` / `scope_table`.
5. Hide what a person must not even see the name of (`hide_repos`), and check which repositories each machine holds.
