# Error handling

cMeta does not signal failures with exceptions by default. Every call through
`cm.access(...)`, every base command and every helper returns a **dictionary**
carrying the outcome, and the caller checks it. Exceptions are switched on
separately, for debugging.

This page covers the contract, the recommended way to check results, the
"soft error" mechanism, how to handle the same errors from shell scripts and CI
(the CLI exit code is the same number), and how to make cMeta raise so you can
catch failures in a debugger.

---

## 1. The return contract

Every function returns a dict with:

| Key | Meaning |
|-----|---------|
| `return` | `0` on success, `> 0` on failure. Always present. |
| `error` | Human-readable message. Present when `return > 0`. |
| ...      | Command-specific keys on success (`artifacts`, `path`, `meta`, ...). |

Return codes in use:

| Code | Meaning |
|------|---------|
| `0` | Success. |
| `1` | Generic error — the default for `_error()` and most failures. |
| `8` | Specific conflict conditions, e.g. *artifact already exists*, *category not found*. |
| **`16`** | **Soft error** — "not found" / warning. Not fatal; see §3. |
| `32` | The requested command does not exist in the category API. |
| `99` | Internal error — a category API returned something that is not a dict, or a dict with no `return` key. |

On the CLI the process **exit code equals `return`** — see §5.

### Why a dict instead of exceptions

Because the outcome is data rather than an exception hierarchy, the *same*
result is available from Python and from the shell, in the same shape, with the
same numeric codes. Nothing has to parse a traceback or scrape a message to
find out what happened.

That makes cMeta straightforward to drive from **CI pipelines** and from
**AI-agent frameworks**: a step or an agent gets a stable numeric outcome plus
a machine-readable dict, and can branch on it — including telling "this failed"
apart from "this does not exist yet" (§3), which is usually the difference
between aborting a pipeline and taking the other branch. An agent that shells
out to `cx` and an agent that calls `cm.access()` in-process handle errors
identically.

---

## 2. Checking a result

### The recommended form

```python
r = self.cm.access({'category': 'repo', 'command': 'list'})
if self.cm.catch_error(r): return r
```

Use this everywhere. It does three things the bare check cannot:

1. **It raises at the point of failure when debugging is on** (see §6), so the
   traceback points at the helper that actually failed instead of surfacing a
   dict far away from the origin.
2. **It skips soft errors** — code `16` does not stop execution (see §3).
3. It normalises `r['error']` in place, so the message that propagates upward
   is consistently formatted.

`catch_error(r)` returns `True` only when there is an error worth propagating:

```python
return ret != 0 and (ret != 16 or fail16)
```

### The simplified form

```python
r = self.cm.access({...})
if r['return'] > 0: return r
```

Fine for prototyping and short scripts — it is shorter and has no dependency
on a `CMeta` instance being at hand. The trade-off is that it has **no
debugging hook** (it never raises, so a debugger cannot break at the failure)
and it treats a soft `16` as a hard failure unless you write the guard by hand:

```python
if r['return'] > 0:
    if r['return'] != 16: return r
    # ... else fall through and handle "not found" yourself
```

Prefer `catch_error` in anything you intend to keep.

### From a plain script (no plugin context)

Outside a category `api/v1.py` you use the `CMeta` instance directly:

```python
from cmeta import CMeta

cm = CMeta()
r = cm.access({'category': 'repo', 'command': 'list'})
if cm.catch_error(r): return r          # inside a function
```

At the very top level of a CLI-style script, halt instead of propagating:

```python
cm.catch_error_and_halt(r)   # prints the error to stderr and sys.exit(r['return'])
```

`catch_error_and_halt(r)` is `catch_error(r)` plus `cm.halt(r)`; `halt()` writes
the message to `stderr` and exits with the return code.

---

## 3. Soft errors — return code 16

**Code `16` means "not found", and that is frequently a normal outcome, not a
failure.** `cx <category> find <alias>` returns `16` when nothing matches, and
callers routinely continue: they check whether an artifact exists, and take a
different branch if it does not.

This creates a conflict with debugging. If `fail_on_error` made *every* error
raise, then a perfectly normal "does this artifact exist?" probe would abort
the run. So code 16 has a **skipping mechanism**: it is exempt from raising and
from propagation unless you explicitly opt in.

The exemption is implemented in two matching places:

```python
# cmeta/utils/common.py::_error  — never raises on 16 unless fail_on_16
if (return_code != 16 or fail_on_16) and fail_on_error:
    raise ...

# cmeta/core.py::CMeta.catch_error — never propagates 16 unless fail16
return ret != 0 and (ret != 16 or fail16)
```

So, with the recommended form:

```python
r = self.cm.access({'category': 'note', 'command': 'find', 'arg1': 'my-note'})
if self.cm.catch_error(r): return r     # a 16 does NOT return here — execution continues

if r['return'] == 16 or len(r.get('artifacts', [])) == 0:
    # not found — handle it as a normal branch
    ...
```

### Escalating a soft error

When a missing artifact *is* fatal at a given call site, pass `fail16=True` to
turn 16 back into a normal error — it then propagates, and raises under
`fail_on_error`:

```python
r = self.repos.find(cmeta_ref_parts)
if self.cm.catch_error(r, fail16=True): return r
```

The engine does exactly this when resolving a **category**: a missing category
is unrecoverable, so `core.py` escalates the 16 and reports it as code `8`.

The same switch exists on the lower-level helpers:

```python
self.cm.error(msg, 16, fail16=True)                       # raise/propagate a 16
utils.common._error(msg, 16, None, fail_on_error, fail_on_16=True)
```

### One deliberate exception

Aggregated search across repositories (`cmeta/repos.py`) passes
`fail_on_error=False` explicitly when a match is missing, so a multi-repo
search **never raises even under `--debug`**. Individual repos are expected to
miss while the aggregate still succeeds. Do not "fix" this to inherit
`self.fail_on_error`.

---

## 4. Raising errors

### From a plugin (`api/v1.py`)

```python
return self.cm.error(f'file "{path}" is not readable')          # code 1
return self.cm.error(f'"{name}" not found', 16)                 # soft error
return self.cm.error('conversion failed', 1, exception=e)       # attach the exception
return self.cm.error('bad input', 1, extra={'input': raw})      # extra keys in the dict
```

Signature: `self.cm.error(error_msg, return_code=1, exception=None,
fail16=False, fail_on_error=None, extra={})`. It returns an error dict — or
raises, if `fail_on_error` is active.

> **Note:** `error()` resolves `fail_on_error` as
> `if not fail_on_error: fail_on_error = self.fail_on_error`. Passing
> `fail_on_error=False` explicitly therefore does **not** disable raising — it
> falls back to the instance flag. Omit the argument to inherit; there is no
> per-call way to force it off.

### From low-level code with no `CMeta` instance

Utility modules (`cmeta/utils/files.py`, `utils/names.py`, `utils/cli.py`)
cannot reach `self.cm`, so they call the underlying helper directly and take
`fail_on_error` as an explicit parameter that callers forward:

```python
from .common import _error

def my_helper(path, fail_on_error=False):
    if not os.path.isfile(path):
        return _error(f'file not found: {path}', 16, None, fail_on_error)
```

When calling such a helper from a plugin, always forward the flag so debugging
propagates all the way down:

```python
r = self.cm.utils.files.load_json(path, fail_on_error=self.fail_on_error)
if self.cm.catch_error(r): return r
```

### When to `raise` instead

Raise a real exception only for genuinely exceptional conditions that are not
part of the command contract — the engine does this in `packages.py` (tool
installation) and in the async `cserver` app, where a returned dict cannot be
threaded through. Everything reachable from `access()` should return a dict.

---

## 5. Handling errors from the CLI (scripts, CI, agents)

**The exit code of `cx` / `cmeta` is exactly the `return` value of the
corresponding `access()` call.** The mapping is direct, with no translation:

```bash
cx repo list          ; echo $?    # 0  — success
cx note find nope-zzz ; echo $?    # 16 — soft "not found"
cx note nosuchcommand ; echo $?    # 32 — command does not exist in the category
```

Error text goes to **stderr**, prefixed with `cMeta notice: ` and suffixed with
`!`; normal output goes to stdout, so the two can be redirected separately.

### Machine-readable output

`--json` / `-j` prints the return dict — but *after* the normal console output
and a separator line, so it is **not** safe to pipe straight into `jq`. For CI
and agents use **`--json_file` / `--jf`**, which writes clean JSON to a file:

```bash
cx note find my-note --jf=out.json
code=$?
jq -r '.error // "ok"' out.json
```

`--quiet` / `-q` auto-accepts interactive prompts, which any unattended script
should set.

### Linux / macOS (bash)

```bash
#!/usr/bin/env bash
set -uo pipefail          # NOTE: not `set -e` — see below

cx note find my-note --quiet
code=$?

case $code in
  0)  echo "found — continuing" ;;
  16) echo "not found — creating it"
      cx note add my-note --quiet || exit $? ;;
  *)  echo "cMeta failed with code $code" >&2
      exit $code ;;
esac
```

`set -e` aborts on *any* non-zero exit, which would kill the script on a soft
`16`. Either leave it off, or guard the call:

```bash
set -e
code=0
cx note find my-note --quiet || code=$?      # `||` protects it from set -e
[ "$code" -eq 0 ] || [ "$code" -eq 16 ] || exit "$code"
```

Capturing the message as well as the code:

```bash
err=$(cx note find my-note 2>&1 1>/dev/null)  # stderr only
code=$?
[ $code -ne 0 ] && echo "cx exited $code: $err" >&2
```

A CI gate that fails on real errors but tolerates "not found":

```bash
cx <category> <command> --quiet --jf=result.json
code=$?
if [ $code -ne 0 ] && [ $code -ne 16 ]; then
    jq -r '.error' result.json >&2
    exit $code
fi
```

### Windows (batch / `cmd.exe`)

```bat
@echo off
setlocal

cx note find my-note --quiet
set CODE=%ERRORLEVEL%

if "%CODE%"=="0"  goto :found
if "%CODE%"=="16" goto :missing

echo cMeta failed with code %CODE% 1>&2
exit /b %CODE%

:missing
echo not found - creating it
cx note add my-note --quiet
if errorlevel 1 exit /b %ERRORLEVEL%
goto :eof

:found
echo found - continuing
goto :eof
```

> **Gotcha:** `if errorlevel N` in batch means "errorlevel is **N or
> greater**", so `if errorlevel 16` is also true for 32 and 99. To test one
> specific code, compare the variable — `if "%ERRORLEVEL%"=="16"` — as above.
> Also capture `%ERRORLEVEL%` into your own variable immediately: almost any
> subsequent command overwrites it.

For a `.bat` you double-click, add `--pause_if_error` (`--pif`) so the console
stays open long enough to read the message.

### Windows (PowerShell)

```powershell
$ErrorActionPreference = "Stop"

cx note find my-note --quiet
$code = $LASTEXITCODE

switch ($code) {
    0       { Write-Output "found - continuing" }
    16      { Write-Output "not found - creating it"
              cx note add my-note --quiet
              if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
    default { Write-Error "cMeta failed with code $code"
              exit $code }
}
```

Notes for PowerShell:

- Use **`$LASTEXITCODE`** for `cx` — it is a native executable, so `$?` only
  reports "did it look like it succeeded" and `$ErrorActionPreference` does not
  apply to its exit code.
- Read `$LASTEXITCODE` into a variable straight away; the next command
  replaces it.
- Do **not** redirect `cx`'s stderr with `2>&1` in Windows PowerShell 5.1 — it
  wraps each stderr line in an `ErrorRecord` and can make a successful run look
  failed. Read the exit code instead.

Parsing the JSON result:

```powershell
cx note find my-note --quiet --jf=result.json
$code = $LASTEXITCODE
if ($code -ne 0 -and $code -ne 16) {
    $r = Get-Content result.json -Raw | ConvertFrom-Json
    Write-Error $r.error
    exit $code
}
```

---

## 6. Debugging — making cMeta raise

By default a failure returns a dict, which is awkward under a debugger: by the
time you see `{'return': 1, ...}` you are far from where it happened. Turning
on **`fail_on_error`** makes `_error()` raise at the origin instead:

- with an `exception` attached → the original exception is re-raised
- otherwise → `RuntimeError(error_msg)`
- **never for code 16**, unless `fail_on_16` / `fail16` is set (§3)

### Ways to turn it on

| Where | How |
|-------|-----|
| Python | `CMeta(fail_on_error=True)` |
| Python | `CMeta(debug=True)` — also sets `log_level='DEBUG'` |
| Python | `from cmeta import set_fail_on_error; set_fail_on_error(True)` |
| CLI | `cx <cat> <cmd> --fail` (aliases `--fail_on_error`, `--fail-on-error`) |
| CLI | `cx <cat> <cmd> --debug` — `--log_level=DEBUG` **and** `--fail_on_error` |
| Env | `CMETA_FAIL_ON_ERROR=yes` |
| Env | `CMETA_DEBUG=1` — same combined effect as `--debug` |

Environment variables are the useful ones for IDEs, because they need no
change to the code or to the command being run.

### Related debug flags

| Flag / env | Effect |
|------------|--------|
| `--log_level=DEBUG` / `CMETA_LOG=DEBUG` | Verbose framework logging. |
| `--log_file=<path>` / `CMETA_LOG_FILE=<path>` | Send the log to a file. |
| `--verbose`, `-v` / `CMETA_VERBOSE=yes` | Verbose progress output. |
| `--pause_if_error`, `--pif` | Pause before exiting on error — so a double-clicked `.bat` does not close its console before you can read the message. |
| `--repro`, `-r` | Write `cmeta-repro-input.json` / `-output.json` to reproduce the call. |
| `--dump` | Write the full post-call context to `cmeta-ctx.json`. |

---

## 7. Debugging in an IDE

Because `fail_on_error` converts failures into raised exceptions, any Python
debugger can break exactly where the framework gave up.

### Visual Studio Code

`.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "cx (debug)",
      "type": "debugpy",
      "request": "launch",
      "module": "cmeta.cli",
      "args": ["repo", "list"],
      "console": "integratedTerminal",
      "justMyCode": false,
      "env": { "CMETA_DEBUG": "1" }
    }
  ]
}
```

- `"justMyCode": false` is important — without it the debugger will not step
  into the installed `cmeta` package or into a category's `api/v1.py`.
- In **Run → Breakpoints**, tick **Raised Exceptions** to stop at the
  `raise` inside `_error()` rather than at the top-level handler.
- To debug your own script instead, point `"program"` at it and keep the
  `CMETA_DEBUG` env var — or construct `CMeta(debug=True)` in the script.

### Visual Studio

- Set the environment variable in the project's debug properties
  (`CMETA_DEBUG=1`), or call `CMeta(debug=True)` in the entry script.
- **Debug → Windows → Exception Settings → Python Exceptions**: enable
  `RuntimeError` so execution breaks when cMeta raises.
- Disable *Just My Code* under **Tools → Options → Debugging** to step into the
  `cmeta` package.

### PyCharm

- Add `CMETA_DEBUG=1` to the run configuration's *Environment variables*.
- **Run → View Breakpoints → Python Exception Breakpoint** → `RuntimeError`.

### Reading the traceback

With `fail_on_error` on, the raise happens inside
`cmeta/utils/common.py::_error`. The frame you want is usually **one or two
levels up** — the helper or the category `api/v1.py` command that produced the
message. If a soft `16` is being swallowed and you want to see it, re-run the
call with `fail16=True` at the site you suspect (§3).

---

## 8. Quick reference

```python
# check (recommended)
if self.cm.catch_error(r): return r

# check, treating "not found" as fatal here
if self.cm.catch_error(r, fail16=True): return r

# check (simplified, prototyping only)
if r['return'] > 0: return r

# check at top level of a script — print and exit
self.cm.catch_error_and_halt(r)

# raise / build an error
return self.cm.error('message')                  # code 1
return self.cm.error('not found', 16)            # soft error
return self.cm.error('failed', 1, exception=e)   # with the original exception

# in low-level utils with no CMeta instance
return _error('message', 1, None, fail_on_error)
```

```bash
cx <cat> <cmd> --debug            # raise on first error + DEBUG logging
cx <cat> <cmd> --fail             # raise on first error only
CMETA_DEBUG=1 cx <cat> <cmd>      # same, via environment (useful in IDEs)
```

From a shell — the exit code is the same number as `r['return']` (§5):

```bash
cx <cat> <cmd> --quiet --jf=out.json ; code=$?        # bash
```
```bat
cx <cat> <cmd> --quiet & set CODE=%ERRORLEVEL%        :: cmd.exe
```
```powershell
cx <cat> <cmd> --quiet ; $code = $LASTEXITCODE        # PowerShell
```

---

Source of truth: `cmeta/utils/common.py::_error`, `cmeta/core.py::CMeta.error`
/ `catch_error` / `catch_error_and_halt` / `halt`, and the flag definitions in
`cmeta/config.py`.

Related: [using-cmeta.md](using-cmeta.md) for the wider Python and CLI
interface, and [documentation index](README.md) for the other guides.
