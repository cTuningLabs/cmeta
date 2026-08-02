# cMeta documentation

Start here. These guides are the full documentation for the framework; the
[project README](../README.md) is a summary that links into them.

---

## Guides

| Guide | What it covers |
|-------|----------------|
| [motivation.md](motivation.md) | Why cMeta exists, the problem it addresses, the design principles behind it. |
| [installation.md](installation.md) | Install with pip / `uv` / from source, verify, first configuration, troubleshooting. |
| [common-commands.md](common-commands.md) | **Cheatsheet** — the commands you use daily: discovery, the `cx .` current-directory shortcut, `cx . info`, artifacts, UIDs, repos, configs, index/cache, scripting and debugging flags. |
| [using-cmeta.md](using-cmeta.md) | **The getting-started and reference guide.** Mental model, first checks, CLI flags and syntax, built-in categories, working with artifacts from the CLI and Python, `ctx`, alias/UID resolution, content repositories, `config`-driven configuration, adding your own category, the artifact metadata reference, and indexing / caching. |
| [error-handling.md](error-handling.md) | The return-dict contract, checking results, soft errors (code 16), raising errors, and debugging with `fail_on_error` in VS Code / Visual Studio / PyCharm. |
| [async-and-concurrency.md](async-and-concurrency.md) | Serial vs async (`CMeta` vs `CMetaAsync`), running calls in parallel, FastAPI usage, and the locking / atomic-write guards that make a shared `<CMETA_HOME>` safe. |
| [configuration.md](configuration.md) | The `config` category in depth — how categories and apps read their settings. |
| [cplatform.md](cplatform.md) | Connecting cMeta to the cTuning.ai platform API and testing the connection. |
| [history.md](history.md) | Lineage (cTuning framework → CK → CM/CMX → cMeta), related publications, and how to cite. |
| [known-issues.md](known-issues.md) | Tracked defects and planned improvements (`KI-nnn`), with reproductions and workarounds. |

### Suggested reading order

1. [motivation.md](motivation.md) — what problem this solves (5 minutes).
2. [installation.md](installation.md) — get `cx` working.
3. [common-commands.md](common-commands.md) — the cheatsheet; keep it open.
4. [using-cmeta.md](using-cmeta.md) §1–§5 — mental model, first checks, flags,
   categories, artifacts.
5. [using-cmeta.md](using-cmeta.md) §7–§9 — repositories, configs, and adding
   your own category (plugin).
6. [error-handling.md](error-handling.md) — before you write a plugin of your
   own.

### For AI agents extending cMeta

- [`AGENTS.md`](../AGENTS.md) — the canonical agent brief for the engine.
- [`CLAUDE.md`](../CLAUDE.md) — Claude Code specific notes.
- [`.claude/skills/`](../.claude/skills/) — portable, reusable skills:
  `use-cmeta-python`, `use-cmeta-cli`, `add-plugin`, `add-repo`,
  `add-cserver-plugin`.

---

## Building the API reference

The `docs/en/` tree is a [Sphinx](https://www.sphinx-doc.org) project whose API
pages are generated from the docstrings in the `cmeta` package. `build_docs.py`
discovers the modules, writes the `.rst` files under `docs/en/api/`, and
optionally runs the Sphinx build.

Install the build dependencies:

```bash
pip install -r docs/requirements.txt
```

Generate the `.rst` files only:

```bash
python docs/build_docs.py --docs-dir docs/en --cmeta-dir cmeta
```

Generate and build HTML:

```bash
python docs/build_docs.py --build --docs-dir docs/en --cmeta-dir cmeta
```

Useful flags: `--clean` (wipe the build directory first), `--pdf`,
`--all` (HTML + PDF), `--site-dir <path>` (write the rendered site elsewhere).

On Windows, `_build_docs.bat` (which runs `_build_docs.ps1` at the repo root)
wraps the whole flow: it resolves the output site directory from the
`cmeta-api-auto` docs artifact, installs the requirements with `uv`, builds,
and archives the result.

### Layout

```
docs/
├── README.md          # this file — documentation index
├── *.md               # the guides listed above (the editable originals)
├── build_docs.py      # RST generator + guide copier + Sphinx build driver
├── requirements.txt   # Sphinx build dependencies
└── en/                # Sphinx project (English)
    ├── conf.py        # Sphinx config (version comes from cmeta/version.py)
    ├── index.rst      # site root toctree            [generated]
    ├── home.rst       # project home page
    ├── api/           # API pages, one per module    [generated]
    ├── guides/        # copies of ../*.md            [generated, gitignored]
    ├── _static/       # custom.css
    └── _templates/    # layout.html
```

Notes:

- **Edit the guides in `docs/*.md`, never in `docs/en/guides/`.** Sphinx cannot
  read sources above its root, so `build_docs.py` copies the guides into
  `docs/en/guides/` on every build (wiping it first) and rewrites their
  repo-relative links — links between guides stay relative, links to anything
  outside (`../README.md`, `../CITATION.cff`, `../.claude/skills/…`) become
  GitHub URLs. Markdown is understood thanks to the `myst_parser` extension.
- To add a guide: create `docs/<name>.md`, add it to the table above, and add
  its filename to `GUIDE_FILES` in `docs/build_docs.py` so it joins the TOC.
- `conf.py` imports `__version__` from `cmeta/version.py` — never hard-code a
  version in the Sphinx config. It imports the `cmeta` package directly, so the
  build environment must be able to `import cmeta`.
- `index.rst` and `api/*.rst` are regenerated on every build. (`build_docs.py`
  will preserve a hand-edited `index.rst` only if it contains the string
  "Download Documentation".)
- Adding a new engine module needs no configuration: the generator discovers it
  automatically. Just keep docstrings in Google or NumPy style.

See also [SPHINX_FASTAPI_INTEGRATION.md](SPHINX_FASTAPI_INTEGRATION.md) for
serving the built docs from the FastAPI app.
