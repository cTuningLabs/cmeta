# Async and concurrency

cMeta can be driven **serially** — one call at a time from a script or the CLI
— or **asynchronously**, from an event loop inside FastAPI or any other
asyncio-based server. The same categories, artifacts and commands work in both
modes; only the way you enter the framework changes.

A deliberate goal of cMeta, and a change from its predecessors, is that
**concurrent execution is a supported mode rather than an accident**. The index
and the artifact files are protected by explicit safety guards (§4), so several
processes can create, read and update artifacts in the same `<CMETA_HOME>` at
the same time without corrupting it.

---

## 1. Two ways to run

| | Serial | Async |
|---|---|---|
| Class | `CMeta` | `CMetaAsync` |
| Call | `r = cm.access({...})` | `r = await cm.access({...})` |
| Blocks the event loop? | yes | no |
| Where the work happens | the calling process | a worker **process** from a pool |
| Use for | scripts, CLI, CI, tests, agent tools | FastAPI / asyncio servers |

Install:

```bash
pip install cmeta                 # serial use — everything below except CMetaAsync's host
pip install "cmeta[server]"       # + FastAPI, uvicorn, jinja2, starlette (pulls cmeta[async])
pip install "cmeta[all]"          # dev + async + server
```

`CMetaAsync` itself needs nothing beyond the base install — it is built on
`asyncio` and `concurrent.futures` from the standard library. The `[async]`
extra exists only so that `cmeta[server]` can reference it; the `[server]`
extra is what pulls in the web stack.

---

## 2. Serial use

Nothing special — this is the default:

```python
from cmeta import CMeta

cm = CMeta()
r = cm.access({'category': 'repo', 'command': 'list'})
if cm.catch_error(r): raise RuntimeError(r['error'])
```

Use a plain `CMeta` for scripts, CI steps, tests and agent tools. It is also
what you want inside a worker process that is already running in parallel.

---

## 3. Async use (`CMetaAsync`)

```python
import asyncio
from cmeta.core_async import CMetaAsync

async def main():
    cm = CMetaAsync(max_workers=4)

    r = await cm.access({'category': 'repo', 'command': 'list'})
    if r['return'] > 0:
        print('error:', r['error'])

    cm.shutdown()

if __name__ == "__main__":          # required on Windows/macOS (spawn)
    asyncio.run(main())
```

`CMetaAsync` subclasses `CMeta` and overrides `access()` with an `async`
version. Each call is dispatched to a **`ProcessPoolExecutor`** worker, so the
blocking filesystem work never runs on the event loop. Each worker process
lazily builds **one persistent `CMeta` instance** and reuses it for every
subsequent call, so the initialisation cost is paid once per worker, not once
per request.

Constructor arguments:

| Argument | Meaning |
|----------|---------|
| `max_workers` | Size of the process pool. `None` lets Python choose. |
| `logger` | Custom logger; defaults to the inherited `CMeta` logger. |
| `loop` | Event loop to use; defaults to the current one. |
| `**kwargs` | Anything `CMeta` accepts (`debug`, `fail_on_error`, `home`, ...) — forwarded to the `CMeta` built in each worker. |

Always call `cm.shutdown()` (it waits for pending work) when the application
stops.

### Errors cross the process boundary unchanged

The usual contract holds — you get the same dict, with the same codes, that a
serial call would return, including the soft `16`:

```python
r = await cm.access({'category': 'note', 'command': 'find', 'arg1': 'nope'})
# -> {'return': 16, 'error': 'note "nope" not found'}
```

If the *dispatch itself* fails (a worker dies, the payload cannot be pickled),
`CMetaAsync.access()` returns `{'return': 99, 'error': 'CMetaAsync internal
error: ...'}` with the traceback included. See
[error-handling.md](error-handling.md).

### Running calls in parallel

Because each call goes to its own worker, ordinary asyncio fan-out gives you
real parallelism:

```python
categories = ['repo', 'config', 'app', 'utils', 'note', 'script']

results = await asyncio.gather(*[
    cm.access({'category': 'category', 'command': 'find', 'arg1': c})
    for c in categories
])

for c, r in zip(categories, results):
    print(c, r['return'])
```

Use `asyncio.gather(..., return_exceptions=True)` if you would rather collect
failures than let the first one abort the group. To bound how much runs at
once independently of `max_workers`, wrap calls in an `asyncio.Semaphore`.

### `access_sync()` — know the limitation

`CMetaAsync` also exposes `access_sync()`, intended for code already running
inside a worker where blocking is fine.

> **Caveat:** `access_sync()` calls `CMeta.access()` with `self` still bound to
> the *async* instance. Commands whose `api/v1.py` re-enters the framework via
> `self.cm.access(...)` therefore hit the **async** override and hand back an
> un-awaited **coroutine instead of a result dict**. `cx repo list` is one such
> command; simple commands that never re-enter (e.g. `category find`,
> `utils uid`) do return a dict.
>
> Don't rely on `access_sync()` on a `CMetaAsync` object. Use `await
> cm.access(...)` on the event loop, and construct a plain `CMeta()` where you
> genuinely need synchronous calls.

### Who uses this

`CMetaAsync` is not a demo path — it is what runs cMeta's web front-ends:

- **The shipped `cserver` app** (`cmeta/internal-repo/app/cserver/src/app.py`)
  creates a single `CMetaAsync` at import time, sized from the CPU count, and
  `await`s it in every handler. Run it with `cx app run cserver` to see the
  pattern working locally — it is the reference implementation.
- **The [cTuning.ai](https://cTuning.ai) platform** (`ctuning.server`) is built
  the same way, using `await cm.access(...)` throughout its FastAPI application
  — user accounts, logging, repository search and project pages all reach cMeta
  through the async interface.

### FastAPI

The shipped `cserver` app is the reference example — create one `CMetaAsync` at
import time, sized from the CPU count, and `await` it in the handlers:

```python
import os
from fastapi import FastAPI
from cmeta.core_async import CMetaAsync

app = FastAPI()

max_workers = int(os.cpu_count() * 0.8 + 0.5)
cm = CMetaAsync(max_workers=max_workers)

@app.get("/repos")
async def repos():
    r = await cm.access({'category': 'repo', 'command': 'list'})
    if r['return'] > 0:
        return {'error': r['error']}
    return {'repos': r.get('artifacts', [])}

@app.on_event("shutdown")
async def _shutdown():
    cm.shutdown()
```

Run it with `cx app run cserver` (or `cserver`) to see the pattern working.
The cTuning.ai platform follows the same shape at a larger scale.

---

## 4. Concurrency safety guards

Several processes may share one `<CMETA_HOME>` — parallel CI jobs, a pool of
async workers, a server plus your terminal. The framework protects the two
things that would otherwise corrupt: the **fast index** and the **artifact
metadata files**.

### Locking + atomic writes

Anything that mutates a shared file follows the same read-modify-write cycle,
with the lock **held across the whole cycle**:

```python
r = utils.files.safe_read_file(index_file, lock=True, keep_locked=True, ...)
# ... modify the data ...
r = utils.files.safe_write_file(index_file, index_data,
                                file_lock=index_file_lock, atomic=True, ...)
```

- **File locks** come from the `filelock` package (a runtime dependency), using
  a sidecar lock file, so they work cross-platform and *across processes* —
  not just across threads. Default acquisition timeout is **3 seconds**;
  exceeding it produces an error dict rather than a corrupt file.
- **`keep_locked=True`** hands the lock back with the data so the caller can
  modify and write without ever dropping it — this is what prevents lost
  updates.
- **`atomic=True`** writes to `<file>.tmp` and then `os.replace()`s it into
  position (retried up to 10 times), so a reader never observes a partially
  written file, and a crash mid-write cannot truncate the original.
- Locks are released in a `finally:` block, and stale lock files are cleaned up
  explicitly (`filelock` does not always do so on Linux).

The same mechanism protects `<CMETA_HOME>/index/*.pkl`, `repos.json`, and each
artifact's `_cmeta.yaml` / `_cmeta.json`.

### Measured behaviour

Ten `cx note add` processes run simultaneously against one `<CMETA_HOME>` all
exit `0`, and both the index and the directory listing show all ten artifacts.
Eight processes updating **the same artifact's** metadata at the same time also
all exit `0`, and **all eight fields are present afterwards** — no lost
updates, and no stale `.lock` files left behind.

### What is *not* concurrency-safe

- **`safe_read_file_via_cache()`** — the in-memory cache dict it maintains is
  explicitly documented as *not* thread-safe. It is the fast read path for the
  index. This is precisely why `CMetaAsync` uses **processes, not threads**:
  each worker gets its own `CMeta` and its own cache.
- **Do not share one `CMeta` instance across threads.** Give each thread its
  own instance, or use `CMetaAsync` and let the process pool isolate them.
- Long-running external work started by a task (builds, downloads) is *not*
  automatically serialised. Content-addressed `cache` entries make repeated
  work cheap, but two processes asked to build the same thing at the same time
  can both build it.

### Practical notes

- **Lock contention shows up as an error, not corruption.** If you drive very
  heavy parallel updates of the *same* artifact, expect occasional lock
  timeouts; retry the call.
- **Separate `<CMETA_HOME>`s remove sharing entirely.** For fully independent
  parallel jobs, give each one its own home (`--home=<path>` or `CMETA_HOME`) —
  see [using-cmeta.md §7.4](using-cmeta.md#74-picking-cmeta_home-env-vars--per-project-collections).
- **Reindex is a whole-home operation.** Avoid running `cx --reindex` while
  other processes are writing to the same home.

---

## 5. Choosing a mode

- A script, a CI step, a test, an agent tool → **`CMeta`**, serial.
- A FastAPI/asyncio server → **`CMetaAsync`**, one instance, `await` every call.
- Parallel independent jobs → several processes, each with its own `CMeta`;
  share a `<CMETA_HOME>` only if they need to see each other's artifacts.
- Threads → give each thread its own `CMeta`, or prefer `CMetaAsync`.

---

Source of truth: `cmeta/core_async.py` (`CMetaAsync`, `_get_cmeta`,
`_access_worker`), `cmeta/utils/files.py` (`_acquire_lock`, `safe_read_file`,
`safe_write_file`), `cmeta/repos.py` (index updates), and
`cmeta/internal-repo/app/cserver/src/app.py` (working FastAPI example).

Related: [installation.md](installation.md) ·
[error-handling.md](error-handling.md) · [documentation index](README.md)
