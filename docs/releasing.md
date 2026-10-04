# Releasing cMeta

The release procedure of the `cmeta` package, for maintainers. People and AI agents follow the same steps:
[`AGENTS.md`](../AGENTS.md) points here, so does the agent skill `release-cmeta`
(`.claude/skills/release-cmeta/`).

**Who does what.** The maintainer picks the version, merges into `main`, uploads to PyPI and decides
when users are told about the new version. An agent prepares everything else, on request, and never does
those four steps on its own.

| Step | Who |
|---|---|
| 1. Check that `dev` is ready | agent or maintainer |
| 2. Bump the version | agent or maintainer |
| 3. Build check | agent or maintainer |
| 4. PR `dev` → `main` | agent opens it, **the maintainer merges** |
| 5. Tag and GitHub release, fast-forward `dev` | agent or maintainer |
| 6. PyPI upload | **the maintainer** (PyPI token) |
| 7. Docs | maintainer |
| 8. Tell `cx --version` about it | **the maintainer** decides; anyone can make the change |

Below, `X.Y.Z` is the new version, `YYYY-MM-DD` / `YYYYMMDD` the release date.

---

## 1. Check that `dev` is ready

```bash
git switch dev && git pull --ff-only
python -m pytest tests                                         # all pass
gh workflow run test-core.yml --repo cTuningLabs/cmeta --ref dev
gh run list --repo cTuningLabs/cmeta --workflow test-core.yml --limit 1   # then: gh run watch <id> --repo cTuningLabs/cmeta
```

The CI workflow runs only on request; it covers Linux, Windows and macOS with Python 3.9 and 3.14.

## 2. Bump the version

One commit on `dev`. `cmeta/version.py` is the single source of the package version; the other files
carry it for people and for other tools:

| File | Change |
|---|---|
| `cmeta/version.py` | `__version__ = "X.Y.Z"`, `__release_date__ = "YYYY-MM-DD"` (`pyproject.toml` reads the version from here) |
| `cmeta/versions.json` | append `{"version": "X.Y.Z", "version_date": "YYYYMMDD"}` |
| `CHANGELOG.md` | `## DEV VERSION (...)` → `## X.Y.Z` |
| `CITATION.cff` | `version`, `date-released` |
| `docs/history.md` | the BibTeX `version = {X.Y.Z}` (and `year`) |
| `docs/installation.md` | the pinned examples (`cmeta[server]==X.Y.Z`, `cmeta==X.Y.Z`) |
| `docs/en/index.rst`, `docs/en/api/index.rst` | the version in their titles (the docs build regenerates both from `version.py`) |
| `cmeta/internal-repo/_cmr.yaml` | `version`, `version_date` |

Then look for anything left behind; only history should still name the previous version:

```bash
git grep -n -F "<previous version>" -- . ':!CHANGELOG.md' ':!cmeta/versions.json' ':!uv.lock'
```

## 3. Build check

Nothing is published here. Remove `build/`, `dist/` and `cmeta.egg-info/` first, because `uv build` adds
to `dist/` and does not clean it:

```bash
uv build                  # dist/cmeta-X.Y.Z.tar.gz, dist/cmeta-X.Y.Z-py3-none-any.whl
uvx twine check dist/*    # PASSED for both
```

Run twine with `uvx`, in its own environment, not with `uv run twine`. `uv run` first syncs `.venv` with
`uv.lock`. The lock pins an older `packaging` than recent twine needs, and twine then fails with
`ImportError: cannot import name 'errors' from 'packaging'`.

## 4. PR `dev` → `main`

```bash
git commit -s -m "cMeta vX.Y.Z"           # sign-off: a DCO check runs on every PR
git push origin dev
gh pr create --repo cTuningLabs/cmeta --base main --head dev \
  --title "YYYYMMDD - cMeta vX.Y.Z: <what is new, in a few words>" --body "<summary; see CHANGELOG.md>"
```

The maintainer merges it with a **merge commit**, not a squash, so that `dev` only needs a
fast-forward afterwards.

## 5. Tag and GitHub release

After the merge:

```bash
sha=$(gh pr view <PR number> --repo cTuningLabs/cmeta --json mergeCommit --jq .mergeCommit.oid)
gh release create vX.Y.Z --repo cTuningLabs/cmeta --target "$sha" \
  --title "cMeta vX.Y.Z: stable release" \
  --notes "See https://github.com/cTuningLabs/cmeta/blob/main/CHANGELOG.md#xyz ."
git fetch origin && git switch dev && git merge --ff-only origin/main && git push origin dev
```

`#xyz` is the version without its dots: `## 0.32.4` is `#0324` on GitHub.

## 6. PyPI upload

From the released commit (`dev` after step 5 is that commit) and a clean tree. The maintainer runs this,
with their PyPI token:

```bash
git describe --tags --exact-match    # vX.Y.Z
# remove build/, dist/ and cmeta.egg-info/
uv build
uvx twine check dist/*
uvx twine upload dist/*
```

Check: <https://pypi.org/project/cmeta/X.Y.Z/> exists, and `pip install "cmeta==X.Y.Z"` in a fresh
environment, then `cx --version`, prints `X.Y.Z`.

## 7. Docs

```bash
pip install -r docs/requirements.txt
python docs/build_docs.py --build --docs-dir docs/en --cmeta-dir cmeta --site-dir <site dir>
```

The build writes the HTML of this version and its `_cmeta.yaml` stamp, which the cTuning.ai releases page
reads. It also rewrites the tracked `.rst` files under `docs/en/`; commit them on `dev` only if
`git status` shows that their text changed.

## 8. Tell `cx --version` about it

`cx --version` asks the cTuning.ai API (`default_ctuning_api`, command `get-last-cmeta-version`) for the
latest version. It warns when the installed one is older. The API answers the newer of two versions:
the platform's `cmeta_last_version` setting and the cMeta that the platform server itself runs.

This is deliberate: users are told to update only when the maintainer says so. Change the setting only
**after** the PyPI upload. Before it, `cx --version` would tell people to update to a version that pip
cannot find.

- **Set it.** In the cTuning platform, set `cmeta_last_version` to `X.Y.Z` in
  `repo/app/ctuning.server/dev/config.py` (`DEF_ENV_VALUES`). The environment variable
  `CTUNING_SERVER_CMETA_LAST_VERSION` on the server overrides it.
- **Deploy.** Deploy the platform and restart it; the setting is read when the server starts.
- **Check.**

  ```bash
  python -c "import requests; print(requests.post('https://cTuning.ai/api/v1', json={'command': 'get-last-cmeta-version'}, timeout=10).json())"
  ```

  It should answer `last_cmeta_version: X.Y.Z`. An older install then prints
  `WARNING: Your cMeta version (...) is outdated.`, with the command that updates it.

## After the release

- `dev` equals `main` (fast-forwarded in step 5).
- The next change on `dev` opens `## DEV VERSION (X.Y.Z.1)` at the top of `CHANGELOG.md`.
- `cmeta/version.py` keeps `X.Y.Z` until the next release bumps it.
- cMeta AOps (`cTuningLabs/cmeta-aops`) has its own version, `CHANGELOG.md` and releases; this procedure
  does not cover it.
