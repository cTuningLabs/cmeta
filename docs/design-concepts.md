# Design concepts: what every change keeps

cMeta is extended all the time: new categories, commands, tools and pages, by people and by AI agents. Five
concepts decide **how** a change is made, so that what worked before keeps working. They come from the author
of cMeta. A change that cannot keep one of them is discussed with the maintainers first (an issue or a pull
request that says so); it is not settled silently in code.

The same five, as a working brief for AI agents, are in [`AGENTS.md`](../AGENTS.md) §5.3.

---

## 1. A layer over everything: a connector and an adaptor

cMeta gives one interface (`access()` in Python, `cx` on the command line) to what already exists: tools, AI
harnesses, operating systems, hardware, repositories, and the artifacts made in the past. It adapts to them.
It does not ask them to change first, and it does not drop the older ones when newer ones arrive.

## 2. Backwards compatible, by extension

New functionality is **added beside** what exists. It does not take its place.

| Add | Do not |
|-----|--------|
| a new key in a meta (`_cmeta`, `_desc`) or in a returned dict | change what an existing key means, or remove one a caller may read |
| a new command, a new flag | change what an existing command or flag does by default |
| a new API version of a category (`api/v2.py` beside `api/v1.py`) | rewrite `api/v1.py` in a way its callers notice |
| a new dated record, folder or file | move or rename what artifacts and scripts already point to |

Older artifacts and older callers keep working as they are. A conversion may be offered, it is never required.
Some of what the engine does for this today:

- an artifact's meta is read from `_cmeta.yaml` or `_cmeta.json`, whichever the artifact has;
- `cx <category> migrate <artifact> <new alias>` renames an artifact and leaves a stub under the old alias, so
  that a lookup by the old alias still finds it;
- an artifact keeps its UID through a rename or a move, so `alias,UID` and UID references stay valid;
- every release is tested as an upgrade in place from earlier released versions (`tests/release_tests`),
  and by CI on Linux, macOS and Windows with the oldest and the newest supported Python (3.9 to 3.15).

## 3. An adaptor follows the version of what it wraps

Code that depends on another program (a tool, a harness, an OS command, a driver) asks cMeta which version is
there and takes the mechanism for that version. When the program changes, a mechanism is **added** for its
newer versions. The mechanisms for the older versions stay, and stay tested. Never "the newest only": the
machines that still run the older version are users too.

## 4. Works everywhere: old, current and not yet seen

Every operating system, Python version, hardware and version of a dependency, including ones nobody has tried.
Where something is missing or too old, cMeta does what still works and says plainly what does not (reduced
functionality), rather than fail.

Failing is right in three cases: a real bug, a security issue, and what the user explicitly forced. A forced
version or configuration that is not available is an error; it is never quietly replaced by another.

## 5. Never guess

cMeta's own decisions are deterministic. A repository, a category, an artifact, a folder or a file is found the
way cMeta itself defines it:

| What | How it is found |
|------|-----------------|
| an artifact | `alias,UID`; the UID decides |
| a repository | its record: `cx repo find <alias>` (its full path, the `subdir` of its `_cmr.yaml` included) |
| an artifact's folder | as `create` builds it: `<repository full path>/<category alias>/<shard folders>/<artifact>` |
| `.` on the command line (the artifact of the current directory) | the path is matched against the records: the deepest plugged repository that holds it, the category folder right under that repository, then the index's artifacts of that category |

Never from the names of the folders on a path, a "first" or "last" match, the order of a listing, or a second
heuristic when the first one fails. When the defined way does not hold, the command stops with an error that
says what was expected and changes nothing. Two candidates are an error that lists them, not a choice.

> This is about how cMeta resolves and decides. Whether a whole workflow gives the same result on two different
> machines depends on more than cMeta (compilers, drivers, hardware): cMeta records and narrows those
> differences, it does not remove them.

---

## Before you propose a change

1. Does it replace something instead of adding beside it?
2. Does it stop an older artifact, caller, operating system, Python or tool version from working?
3. Does any step guess?

If one answer is yes, say so in the pull request and ask before going further.
