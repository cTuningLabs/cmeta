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

- **File locks** are the engine's own `cmeta.utils.files.PathLock` (no library),
  using the sidecar file `<file>.lock`, so they work cross-platform, *across
  processes* and across the threads of one process. A writer waits up to
  **30 seconds** for a busy lock (`CMETA_LOCK_TIMEOUT` changes it), prints a
  notice on stderr after 3 seconds naming the holder when it left a note in the
  lock file, and then gives up with an error dict that names the holder rather
  than a corrupt file.
- **`keep_locked=True`** hands the lock back with the data so the caller can
  modify and write without ever dropping it — this is what prevents lost
  updates.
- **Atomic writes**: a JSON, YAML or pickle file is written to `<file>.tmp` and
  then `os.replace()`d into position (the default of `safe_write_file` since
  0.34.1; text is written in place), so a reader never observes a partially
  written file, and a crash mid-write leaves the previous file and no
  temporary. The mode of the target is kept, a symbolic link is written
  through, a read-only target is refused, and the replace is retried while a
  reader holds the target open (Windows) until the lock timeout.
- Locks are released in a `finally:` block, and the lock file is removed by the
  process that releases it, so repositories never keep lock files. A crash
  leaves at most the lock file of the operation in flight; it blocks nobody
  (the OS lock dies with the process) and the next holder reuses and removes it.

The same mechanism protects `<CMETA_HOME>/index/*.pkl`, `repos.json` (also
while the incremental index of `plug` / `unplug` / `repo reindex` reads and
rewrites it), and each artifact's `_cmeta.yaml` / `_cmeta.json`, including the
one a `create` writes.

### How the lock works on each platform

A lock file that is removed after use is correct only if the holder removes it
*before* releasing the OS lock and every newcomer checks, after acquiring, that
the file it holds is still the file at the path (otherwise a waiter blocked on
the removed file and a newcomer that created a new one both "hold" the lock).
`PathLock` does both. On **Windows** it takes a byte-range lock
(`msvcrt.locking`) on the lock file; an open file cannot be removed there, so a
newcomer that meets a file being deleted simply tries again. On **POSIX** it
takes `fcntl.flock` (per open file description, so threads exclude each other
too), or POSIX record locks (`fcntl.lockf`) where the file system refuses
`flock` (NFS and some network mounts), each with the identity check. Where the
file system refuses both (some FUSE, 9p and SMB mounts) it falls back to a
**soft lock**: the file is created exclusively and holds `pid host time`; a
stale one (its process dead on this host, or older than 10 minutes when left
by another host) is removed by the waiter that finds it. In every mode the
threads of one process are serialized on the path first. A busy lock is polled
with a delay that doubles from 1 ms to 25 ms until the timeout. A folder used
by two operating systems at once (a Windows tree plugged from WSL) is best
effort: each side locks with its own mechanism.

### The index lock

A full reindex (`cx --reindex`, or the first run on a home without an index)
builds the new index in `index.tmp-<pid>` and swaps it in when it is complete.
So that a record written meanwhile is not lost in the swap, the lock file
`<CMETA_HOME>/index.lock` (the sidecar of the index folder, kept through the
swap) is held by the full reindex for its whole rebuild and swap, by the
incremental index of `pull` / `plug` / `repo reindex` for its duration, and by
every write of a record (`create`, `update`, `delete`, `reindex` of an artifact)
for a moment. A writer that arrives during a reindex waits for it, prints a
notice on stderr after 3 seconds naming the reindexing process (which leaves a
note in the lock file), and gives up with an error after `CMETA_INDEX_LOCK_TIMEOUT`
seconds (600 by default); otherwise it then writes into the new index. Two
reindexes run one after the other; several processes starting on a fresh home
at once build one index. Readers never take the lock, so lookups cost what they
did; a write costs one more lock acquisition (microseconds on Linux, a fraction
of a millisecond on Windows). Under the same lock a reindex removes the
`index.tmp-*` / `index.old-*` leftovers of killed rebuilds.

### A create under the index lock

`create` takes the index lock before it makes the folder, writes the meta and
adds the record, and releases it after (`Repos.lock_index`,
`add_to_index(index_lock=...)`): a full reindex never sees a half-made
artifact, several creates of one artifact at once end with one artifact and
"already exists" errors (the second finds the folder of the first), and a
create whose record cannot be written (the lock of its index file stayed held)
removes the folder it made, so nothing is left unindexed.

### Measured behaviour

Ten `cx note add` processes run simultaneously against one `<CMETA_HOME>` all
exit `0`, and both the index and the directory listing show all ten artifacts.
Eight processes updating **the same artifact's** metadata at the same time also
all exit `0`, and **all eight fields are present afterwards** — no lost
updates, and no stale `.lock` files left behind. The lock's own tests
(`tests/core_tests/test_utils_files_path_lock.py`) run eight processes and
sixteen threads through one counter, replay the removed-file race
deterministically, kill a holder, and exercise the soft lock and its stale
files; `tests/benchmarks/benchmark_engine.py` measures the cost.

### What is *not* concurrency-safe

- **`safe_read_file_via_cache()`** keeps the in-memory cache of the index per
  `CMeta` instance, keyed by the file's modification time in nanoseconds, size
  and inode; an index file read before that is missing for a moment (a replace
  on a mount whose rename is not atomic, the swap of a full reindex) is retried
  a few times before "not found"; its dict is updated under a lock, and `find` hands out one-level
  copies of the records it returns (the record, its `cmeta` and its `tags`),
  so a caller may edit those. Anything deeper, and what the lower-level
  `find_in_index` returns, is shared with the cache and must be treated as
  read-only. `CMetaAsync` still uses
  **processes, not threads**: each worker gets its own `CMeta` and its own
  cache.
- **Do not share one `CMeta` instance across threads.** Give each thread its
  own instance, or use `CMetaAsync` and let the process pool isolate them.
- Long-running external work started by a task (builds, downloads) is *not*
  automatically serialised. Content-addressed `cache` entries make repeated
  work cheap, but two processes asked to build the same thing at the same time
  can both build it.

### Practical notes

- **Lock contention shows up as a wait, then an error, not corruption.** A
  writer waits up to `CMETA_LOCK_TIMEOUT` seconds (30) for the lock of a file
  and says so on stderr after 3. If you drive very heavy parallel updates of
  the *same* artifact, expect occasional lock timeouts; retry the call.
- **Separate `<CMETA_HOME>`s remove sharing entirely.** For fully independent
  parallel jobs, give each one its own home (`--home=<path>` or `CMETA_HOME`) —
  see [using-cmeta.md §7.4](using-cmeta.md#74-picking-cmeta_home-env-vars--per-project-collections).
- **Reindex is a whole-home operation.** Writes made while `cx --reindex` runs
  wait for it (see *The index lock* above) and land in the new index; a very
  long reindex (a huge home on a slow disk) makes them wait as long, up to
  `CMETA_INDEX_LOCK_TIMEOUT` seconds.

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
