# Installing cMeta

cMeta (CLI: `cx` / `cmeta`) is a small, portable Python package with minimal
dependencies. It runs on Linux, macOS and Windows and supports Python 3.9+.

---

## Requirements

- **Python 3.9 or newer**
- `pip` (and optionally [`uv`](https://github.com/astral-sh/uv) for fast, isolated
  environments)
- Git (only needed for installing directly from the repository)

---

## Option 1 — pip (simplest)

```bash
pip install cmeta
cmeta --version
```

## Option 2 — uv + pip (isolated environment, recommended)

```bash
uv venv
uv pip install cmeta
uv run cmeta --version
```

## Option 3 — uv + Git (latest from source)

```bash
uv venv
uv pip install --force-reinstall git+ssh://git@github.com/ctuninglabs/cmeta.git@main#egg=cmeta
uv run cmeta --version
```

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

- **`cmeta: command not found`** — ensure your Python `Scripts`/`bin` directory is
  on `PATH`, or use `uv run cmeta …` / `python -m cmeta …`.
- **Permission or cache errors on first run** — point `--meta.file_cache` at a
  writable location with enough free space (model/build caches can be large).
- **Tool/version detection issues** — run with `-v` to see how cMeta is detecting
  compilers, Python and accelerators.

---

For everyday usage (repos, plugins, artifacts, reindex), see
[using-cmeta.md](using-cmeta.md).
For *why* cMeta exists and where it is headed, see
[motivation.md](motivation.md).
