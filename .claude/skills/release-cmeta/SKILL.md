---
name: release-cmeta
description: Release a new version of the cMeta package (cTuningLabs/cmeta) - check dev, bump the version in every file that carries it, build check, PR dev to main, tag and GitHub release, PyPI upload, docs, and the cmeta_last_version setting that makes `cx --version` announce it. Use when the user asks to "release cMeta", "bump the version", "tag", "publish to PyPI" or "announce a new version".
---

# release-cmeta — release the cMeta package

The procedure is [`docs/releasing.md`](../../../docs/releasing.md). Read it and follow it step by step. This
skill holds no steps of its own, so that every tool (Claude Code, Codex, OpenCode, a person) follows the
same file; `AGENTS.md` §5.2 points there too.

What the maintainer does, never the agent on its own:

- pick the version;
- merge the PR into `main`;
- upload to PyPI;
- decide when users are told: the `cmeta_last_version` setting of the cTuning platform, which
  `cx --version` reads through the cTuning.ai API. Change it only after the PyPI upload.

The rest - the checks, the version bump in all its files, the build check, the PR, the tag and the GitHub
release, the fast-forward of `dev` - an agent does when asked. Sign off every commit (`git commit -s`).
