# Known issues and planned improvements

Tracked defects, rough edges and improvements that are understood but not yet
addressed. Each entry has a stable ID (`KI-nnn`) so it can be referenced from
commit messages, code comments and discussions.

Status values: **open** (confirmed, not started) · **needs decision** (behaviour
is deliberate or ambiguous; the fix depends on a design call) · **in progress**
· **fixed** (kept for one release, then removed).

| ID | Area | Status | Summary |
|----|------|--------|---------|
| [KI-001](#ki-001) | async | open | `CMetaAsync.access_sync()` returns a coroutine instead of a result dict for re-entrant commands. |
| [KI-002](#ki-002) | error handling | needs decision | `CMeta.error(fail_on_error=False)` cannot force raising off. |
| [KI-003](#ki-003) | docs | fixed | The published documentation site carried only the API reference, not the written guides. |

---

## KI-001

**`CMetaAsync.access_sync()` returns a coroutine for commands that re-enter the
framework** — *async, open.*

`access_sync()` calls `CMeta.access()` with `self` still bound to the
**async** instance. Any command whose `api/v1.py` re-enters cMeta through
`self.cm.access(...)` therefore reaches `CMetaAsync.access()` — the `async`
override — and gets back an un-awaited coroutine, which is then returned to the
caller in place of the result dict.

Reproduce:

```python
import asyncio
from cmeta.core_async import CMetaAsync

async def main():
    cm = CMetaAsync(max_workers=2)
    print(type(cm.access_sync({'category': 'repo',     'command': 'list'})))   # coroutine  <-- wrong
    print(type(cm.access_sync({'category': 'category', 'command': 'find',
                               'arg1': 'repo'})))                              # dict       <-- fine
    cm.shutdown()

asyncio.run(main())
```

The failure is silent and depends on whether the invoked command happens to
re-enter, which makes it easy to miss: simple commands appear to work.

`await cm.access(...)` is **not** affected — worker processes build a plain
`CMeta`, so nested calls resolve to the synchronous implementation.

*Likely fix:* have `access_sync()` (or the object handed to category APIs as
`self.cm`) delegate to a plain `CMeta` instance rather than to `self`.

*Workaround:* use `await cm.access(...)` on the event loop, and construct a
separate `CMeta()` where synchronous calls are genuinely needed. Documented in
[async-and-concurrency.md](async-and-concurrency.md#access_sync--know-the-limitation).

---

## KI-002

**`CMeta.error(fail_on_error=False)` cannot force raising off** — *error
handling, needs decision.*

`CMeta.error()` resolves the flag as:

```python
if not fail_on_error:
    fail_on_error = self.fail_on_error
```

so passing `fail_on_error=False` explicitly is indistinguishable from omitting
it, and the instance flag wins. There is no per-call way to suppress raising
while `fail_on_error` is active on the instance.

Low-level helpers do not share the quirk — `utils.common._error()` takes
`fail_on_error` as a plain parameter, which is how `repos.py` deliberately
keeps aggregated search non-raising.

*Decision needed:* is the per-call override worth supporting (e.g. by
defaulting the parameter to `None` and testing `is None`), or should the
argument simply not be documented as usable? Current behaviour is documented as
a caveat in [error-handling.md](error-handling.md#4-raising-errors).

---

## KI-003

**Published documentation contained only the API reference** — *docs, fixed.*

The Sphinx project under `docs/en/` used to build just two things: the project
home page and the auto-generated API reference. The written guides lived as
Markdown in `docs/` and were not part of the built site, so readers only saw
them by browsing the repository.

The cause was mechanical: Sphinx reads from `docs/en/`, the guides sit one
level up in `docs/`, and `myst_parser` (which lets Sphinx read Markdown at all)
was listed in `docs/requirements.txt` but not enabled in `docs/en/conf.py`.

*Fixed by:* enabling `myst_parser` in `conf.py`, adding a `copy_guides()` step
to `build_docs.py` that copies `docs/*.md` into `docs/en/guides/` and rewrites
their repo-relative links, and emitting a "Guides" toctree in the generated
`index.rst`. `_build_docs.bat` / `.ps1` needed no changes. The generated
`docs/en/guides/` directory is gitignored — edit the originals in `docs/`.

---

## Adding an entry

Keep it short: what is wrong, how to reproduce or observe it, what the likely
fix is, and any workaround. Give it the next free `KI-nnn`, add a row to the
table, and link to the relevant guide if the behaviour is already documented
there as a caveat.
