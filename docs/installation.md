# Installing cMeta

cMeta (CLI: `cx` / `cmeta`) is a small, portable Python package with minimal
dependencies. It runs on Linux, macOS and Windows and supports Python 3.9+.

---

> There is also an interactive installer that assembles these commands for your
> OS, shell and package manager:
> **[cTuning.ai/project/cmeta/cmeta.install](https://cTuning.ai/project/cmeta/cmeta.install/)**

---

## Requirements

- **Git** — `cx repo get --url=...` clones content repositories over git, and so
  does the install-from-source route.
- **Python 3.9 or newer** — only for the pip route. The two
  [`uv`](https://github.com/astral-sh/uv) routes below let uv fetch its own
  interpreter, so they work on a host with no usable Python and no root.

### Installing uv

astral's own installer is used on every platform in preference to whatever the
distribution packages — one command shape everywhere, and no dependency on a
distro keeping up with uv releases. It is downloaded first and then run, so it
can be read before it runs; on Windows the piped `irm ... | iex` form is what
Microsoft Defender flags as a download-and-run trojan. The last line puts uv on
`PATH` in the current shell, since the installer arranges it only for new ones.

```bash
curl -fLo uv-install.sh https://astral.sh/uv/install.sh         # Linux, macOS
sh uv-install.sh
. "$HOME/.local/bin/env"
```

```bat
curl.exe -fLo uv-install.ps1 https://astral.sh/uv/install.ps1
powershell -ExecutionPolicy ByPass -File uv-install.ps1
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
```

On a minimal Linux image install `curl` first (`apt-get install -y curl`,
`dnf install -y curl`, …).

---

## Option 1 — `uv tool` (a global `cx`, recommended)

Installs cMeta as a **standalone command**, the way uv or ripgrep are installed:
its own private environment that you never activate, real `cx` / `cmeta` /
`cxt` / `cserver` shims on `PATH`, and an interpreter uv downloads itself.

```bash
uv tool install "cmeta[server]"
uv tool update-shell          # put the shims on PATH (once per machine)
cx --version
```

The `server` extra is included because `cx app run cserver` cannot start
without it &mdash; there is no uvicorn to run it with, and a `uv tool`
environment has no pip to add one afterwards. Drop it (`uv tool install cmeta`)
if you will never run the web app.

Quote the extra. In `zsh` &mdash; the default shell on macOS &mdash; square
brackets are a filename pattern, so an unquoted `cmeta[server]` never reaches
uv: it fails with `zsh: no matches found`. `"cmeta[server]"` works in every
shell.

Installing from a branch rather than a release, to try something before it
ships:

```bash
uv tool install --force "cmeta[server] @ git+https://github.com/ctuninglabs/cmeta@dev"
```

Pick this when cMeta is a **tool you use everywhere** rather than a dependency
of one project — which is how it is normally used. It also sidesteps PEP 668
entirely, since it never touches the system interpreter, and
`uv tool upgrade cmeta` upgrades the CLI in isolation.

**Set `CMETA_HOME` alongside it** — see
[Choosing where repositories live](#choosing-where-repositories-live). A global
command does *not* by itself imply a global home.

## Option 2 — `uv` + a project virtual environment

For when cMeta is a dependency of one project, and its repositories should live
and die with that project:

```bash
uv venv cmeta-env
source cmeta-env/bin/activate            # Windows: cmeta-env\Scripts\activate.bat
uv pip install cmeta
cx --version
```

## Option 3 — pip + a project virtual environment

Using only what ships with Python 3.9+:

```bash
python3 -m venv cmeta-env
source cmeta-env/bin/activate            # Windows: cmeta-env\Scripts\activate.bat
pip install cmeta
cx --version
```

## Latest from source

Add `--force` (uv tool) or `--force-reinstall` (uv / pip): the version number
does not change between commits on `main`, so the installer would otherwise
decide there is nothing to do.

```bash
uv tool install --force "cmeta @ git+https://github.com/cTuningLabs/cmeta.git@main"
uv pip install --force-reinstall "cmeta @ git+https://github.com/cTuningLabs/cmeta.git@main"
pip install --force-reinstall "cmeta @ git+https://github.com/cTuningLabs/cmeta.git@main"
```

Extras combine with the direct reference as usual:
`"cmeta[server] @ git+https://..."`.

---

## Updating cMeta

**Start with `cx --version`.** It says how this cMeta was installed, prints the
command that updates it, and warns when a newer release is out:

```text
Installed as: uv tool, from PyPI
Update with:  uv tool upgrade cmeta
```

The update command depends on how cMeta was installed, not on the OS:

| Installed with | Update with |
|---|---|
| `uv tool install "cmeta[server]"` (Option 1, and the website installer) | `uv tool upgrade cmeta` — keeps the extras it was installed with |
| `uv tool install ... "cmeta[server] @ git+https://...@main"` | `uv tool install --force "cmeta[server] @ git+https://github.com/cTuningLabs/cmeta.git@main"` — the version number does not change between commits, so `--force` is what makes it reinstall |
| `uv pip install cmeta` in a venv (Option 2) | `uv pip install -U cmeta`, with the venv activated |
| `pip install cmeta` in a venv (Option 3) | `pip install -U cmeta`, with the venv activated (or `python -m pip install -U cmeta`) |
| `uv pip` / `pip install ... @ git+https://...` | `uv pip install --force-reinstall "cmeta @ git+https://github.com/cTuningLabs/cmeta.git@main"` (or the same with `pip install`) |
| an editable install (`pip install -e .`, `install.sh --editable`) | `git pull` in the checkout; reinstall only if the dependencies in `pyproject.toml` changed |
| `install.sh` / `install.ps1` from a copied source tree | run it again: it installs with `--force`, so it upgrades in place |

The website installer
([cTuning.ai/project/cmeta/cmeta.install](https://cTuning.ai/project/cmeta/cmeta.install/))
has an **Update** mode that turns the same choices (OS, route, version,
repositories) into these commands.

**A specific version**, to pin or to go back:

```bash
uv tool install --force "cmeta[server]==0.32.2"
pip install "cmeta==0.32.2"
```

**Moving an install from git to PyPI** (or back) is a reinstall from the other
source: `uv tool install --force "cmeta[server]"`.

### Updating the repositories you use

A content repository is updated by cMeta itself, not by pip or uv. One fetched
with `cx repo get` (a git clone) is updated with a pull, which also refreshes the
index:

```bash
cx repo list                             # what is plugged in
cx repo pull ctuninglabs@cmeta-aops      # git pull + reindex
```

A repository fetched as a zip (`cx repo get cmeta://<name>`) has no history to
pull: remove it with `cx repo delete <alias>` (this deletes the local copy,
including any local changes) and get it again — or get the git clone instead.
After a `git pull` done by hand inside a repository, run `cx --reindex`.

---

## Choosing where repositories live

One directory — the **cMeta home** — holds `repos.json`, the plugged
repositories under `repos/`, the fast lookup index under `index/`, and the task
caches. cMeta picks it the first time it runs, in this order:

| | Source | Becomes | When |
|---|---|---|---|
| 1 | `CMETA_HOME` | used as-is | Explicit, and beats everything below. |
| 2 | `$VIRTUAL_ENV` | + `/CMETA` | An activated virtual environment. |
| 3 | `$CONDA_PREFIX` | + `/CMETA` | An activated conda environment. |
| 4 | `CMETA_HOME2` | used as-is | A global default that a venv overrides. |
| 5 | `~/CMETA` | — | The fallback when nothing above is set. |

`cx --version` prints the home it resolved, and `cx --home=<path> …` overrides
it for a single command.

**Installing globally and having a global home are two separate things.** Rule 2
reads an environment variable, not the location of the `cx` you invoked — so a
`uv tool`-installed `cx`, run from a shell with a project venv activated, will
still put its repositories in `$VIRTUAL_ENV/CMETA`. If you want one home
everywhere, say so:

```bash
export CMETA_HOME="$HOME/CMETA"
echo 'export CMETA_HOME="$HOME/CMETA"' >> ~/.bashrc
```

```bat
setx CMETA_HOME "%USERPROFILE%\CMETA"
```

Use `CMETA_HOME2` instead when you want a shared default that an activated
virtual environment is still allowed to override.

> **A hand-written wrapper script is not needed.** `uv tool install` already
> creates native shims (`cx`, and `cx.exe` on Windows) and `uv tool update-shell`
> puts them on `PATH`. Wrapping `uv run cx` in a shell script and pinning
> `UV_PROJECT`/`PATH` to one project's `.venv` ties your global `cx` to that
> project: its dependency changes alter your CLI, a broken lockfile there breaks
> `cx` everywhere, and every invocation pays a project re-resolve.

---

## Serial or async — choosing extras

cMeta can be driven **serially** (a script, the CLI, a CI step) or
**asynchronously** from an event loop inside FastAPI or another asyncio server.
Both modes use the same categories, artifacts and commands.

| Install | Gives you |
|---------|-----------|
| `pip install cmeta` | Serial use — the `cx` / `cmeta` CLI and the `CMeta` Python class. |
| `pip install "cmeta[server]"` | The above **plus** FastAPI, uvicorn, jinja2, starlette and itsdangerous — needed to *host* an async app such as the shipped `cserver`. |
| `pip install "cmeta[dev]"` | pytest, pytest-cov, flake8 for working on cMeta itself. |
| `pip install "cmeta[all]"` | dev + async + server. |

The async class `CMetaAsync` needs **no extra** — it is built on `asyncio` and
`concurrent.futures` from the standard library, so the base install is enough
to `await cm.access(...)`. The `[server]` extra is only about the web stack you
run it in. (There is also an `[async]` extra; it is intentionally empty and
exists so `cmeta[server]` can reference it.)

cMeta is designed for **concurrent use**: several processes may share one
`<CMETA_HOME>`, with file locks and atomic writes protecting the index and the
artifact metadata. Details and examples in
[async-and-concurrency.md](async-and-concurrency.md).

---

## Verify the installation

```bash
cmeta --help
cmeta --version
```

or using the short alias:

```bash
cx --help
cx --version
```

A first end-to-end check — list known repositories:

```bash
cx repo list
```

Next, walk through everyday usage — pulling in more content repositories,
adding your own categories (plugins) and artifacts, and keeping the local
index healthy — in [using-cmeta.md](using-cmeta.md).

---

## Python interface

cMeta can also be driven programmatically through the same uniform `access`
interface used by the CLI:

```python
from cmeta import CMeta

cm = CMeta()
r = cm.access({'category': 'repo', 'command': 'list'})
print(r)
```

---

## Optional configuration

cMeta works out of the box, but a few settings are commonly useful — for example
redirecting the large-file/build cache to a dedicated drive, enabling version
checks for detected tools, and choosing a default Git transport:

```bash
cx config set task --meta.file_cache=/path/to/large/cache
cx config set task --meta.check_versions
cx config set default --meta.default_git=git@github.com:
```

On Windows the cache path is typically a separate drive, e.g.:

```bat
cx config set task --meta.file_cache=x:\cmeta-file-cache-windows
```

---

## Working with artifact repositories

cMeta executes **artifacts** (programs, models, datasets, tasks) that live in
content repositories. Once you have access to such a repository, you run an
artifact with:

```bash
cx <category> run <alias>,<uid> [flags]
```

Common flags include `-v` (verbose), `--clean` and `-q' (quiet)

Common flags for category `program` include 
`--compute=cpu|cuda|rocm|metal|xpu` to select a compute backend.
`--clean` to clean cache

---

## Troubleshooting

- **`cx: command not found`** — after `uv tool install`, run `uv tool update-shell`
  and open a new shell. Otherwise ensure your Python `Scripts`/`bin` directory is
  on `PATH`, or call the module directly with `python -m cmeta …`.
- **`error: externally-managed-environment`** — PEP 668: most current Linux
  distributions refuse a `pip install` into the system interpreter. Use
  **Option 1** (`uv tool`, which never touches it), a virtual environment, or add
  `--break-system-packages` deliberately.
- **`uv pip install` refuses to run** — uv will not install into an interpreter
  outside a virtual environment unless told to. Activate one, or add `--system`.
- **Repositories keep disappearing between shells** — the home moved with you. A
  venv activated in one terminal and not in another resolves to two different
  homes; see [Choosing where repositories live](#choosing-where-repositories-live),
  and `cx --version` to see which one you are in.
- **`python3 -m venv` fails on Debian/Ubuntu** — `python3-venv` is a separate
  package: `sudo apt-get install -y python3-venv`.
- **Permission or cache errors on first run** — point `--meta.file_cache` at a
  writable location with enough free space (model/build caches can be large).
- **Tool/version detection issues** — run with `-v` to see how cMeta is detecting
  compilers, Python and accelerators.
- **`cx --version` still shows the old version after an update** — another `cx`
  comes first on `PATH`: typically a `pip install` into a system Python next to a
  `uv tool` install. `which -a cx` (Linux, macOS) or `where cx` (Windows) lists
  them all, and `cx --version` prints the one that runs (its `python path` and
  `package path`). Update that one, or uninstall the one you do not use
  (`uv tool uninstall cmeta`, `pip uninstall cmeta`).
- **An update seems to do nothing** — an install from git keeps the same version
  number between commits, so a plain upgrade decides there is nothing to do: use
  `uv tool install --force ...` or `pip install --force-reinstall ...`, as
  [Updating cMeta](#updating-cmeta) shows.

---

Next steps:

- Everyday usage (repos, plugins, artifacts, reindex) —
  [using-cmeta.md](using-cmeta.md)
- Why cMeta exists and its design principles — [motivation.md](motivation.md)
- Async use (FastAPI) and concurrency guards —
  [async-and-concurrency.md](async-and-concurrency.md)
- Working with `config` artifacts — [configuration.md](configuration.md)
- Connecting to the cTuning.ai platform — [cplatform.md](cplatform.md)
- All guides — [documentation index](README.md)
