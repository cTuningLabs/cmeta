# Why cMeta

## The problem

Research and engineering projects accumulate code, data, models, toolchains,
scripts and notes — and most of it stops being usable surprisingly quickly.
The typical failure modes:

- **Everything is addressed by path.** A workflow hard-codes
  `../../models/resnet50/model.onnx`, so moving or renaming anything breaks it.
- **Every project invents its own interface.** One tool is a `Makefile`, the
  next a `run.sh`, the next a notebook, the next a REST endpoint. Composing
  them means writing glue that only works in one place.
- **Environment assumptions are implicit.** A script works because a specific
  compiler, CUDA version or Python package happens to be present on one
  machine.
- **Results are hard to re-run.** The commands are recorded, but not the
  context that made them work — so reproducing a run a year later means
  archaeology.
- **Knowledge lives outside the artifacts.** What a component is for, what it
  depends on, and how it relates to other components is in a README, a paper,
  or someone's head — not in machine-readable form.

None of these are hard problems individually. Together they mean work has to be
redone rather than reused.

## The approach

cMeta represents **every part of a workflow — a program, a model, a dataset, a
toolchain, a note, an agent — as a uniform, composable, content-addressed
artifact**, and reaches all of them through **one interface**:

- Python: `cm.access({'category': ..., 'command': ..., ...})`
- CLI: `cx <category> <command> [args] [--flags]`

An artifact is a plain directory with a `_cmeta.yaml` sidecar that carries its
identity and metadata. A **category** is a plugin type that knows how to
operate on artifacts of its kind, implemented in an `api/v1.py`. Categories and
artifacts live in **content repositories** that you pull in, index and share.

That is nearly the whole model. The engine stays small on purpose; capability
comes from the repositories plugged into it.

## Design principles

**One uniform interface.** Anything reachable from the CLI is reachable from
Python and vice versa. New capability is added behind the same `access()`
surface rather than as a new entry point — which is what keeps automations
composable, and what lets AI agents drive the same surface people use.

**Identity that survives renaming.** Every category and artifact has both a
human-friendly *alias* and a stable 16-hex-character *UID*. References written
as `alias,UID` stay valid when the alias changes, because the UID is
authoritative and the alias is advisory. This is what makes references portable
across projects, forks and time.

**Discovery by metadata, not by path.** Structured tags and metadata make
components findable by what they are, rather than by where they happen to sit
on disk.

**Declared dependencies over hard-coded scripts.** Automations are assembled
from small reusable tasks that state what they use (`uses_categories`, `uses`
pipelines), so a workflow can be recomposed instead of rewritten.

**Extend by plugging in, not by patching the core.** New capability arrives as
self-contained artifacts with optional Python hooks. The framework grows
sideways; the engine does not.

**Virtualized portability.** Toolchains, compilers, drivers and runtimes are
detected, isolated and pinned, so the same automation abstracts over OS and
accelerator differences.

**Content-addressed caching and better reproducibility.** Identical work is not
repeated, and the context of a run is captured to help reproduce it. Full
determinism across heterogeneous environments is genuinely hard — cMeta
improves reproducibility rather than claiming to solve it. That is ongoing R&D.

**Concurrency as a supported mode.** Unlike the earlier frameworks in this
line, which assumed one operation at a time, cMeta is built so that several
processes can work in the same `<CMETA_HOME>` simultaneously — parallel CI
jobs, a pool of async workers serving a web app, a server plus your terminal.
The fast index and the artifact metadata files are protected by explicit
guards: cross-process file locks held across each read-modify-write cycle, and
atomic temp-file-plus-rename writes, so readers never see a half-written file
and concurrent updates do not overwrite each other. The same engine is
therefore usable serially from a script and asynchronously from FastAPI. See
[async-and-concurrency.md](async-and-concurrency.md).

**Humans and agents on the same surface.** AI agents use the same discovery,
composition and execution interface people do, so an automation written by a
person can be extended by an agent and vice versa. See the `ctx` dictionary in
[using-cmeta.md §5.4](using-cmeta.md#54-ctx--thread-state-and-ai-agent-context-through-nested-calls).

## What people use it for

cMeta is an engine; what it actually does depends on the content repositories
plugged into it. These are the uses it is designed around.

**A research assistant for open science.** The recurring problem in research
engineering is that knowledge about *how* something was done lives in prose,
one-off scripts and remembered command lines — and decays. cMeta's answer is to encode
that practice as executable, self-describing artifacts: how to detect and
install a toolchain, how to build and benchmark a program on a given target,
how to fetch a model. Because each artifact carries machine-readable metadata
and declares what it uses, an AI agent can discover, compose and extend them
through the same interface a person uses. The artifacts are the accumulated
memory; the agent — or the person — is the operator. This is a deliberately
modest reading of "research assistant": not a system that invents science, but
one that stops you re-deriving the same setup every time.

**Collaborative research, development and experimentation.** Work is shared as
content repositories that others plug in and run, not as instructions to
follow. Because references use `alias,UID` and the UID is authoritative, a
pointer to an experiment, a dataset or the workflow that produced a result
stays valid across renames, forks and years — which is what makes collaboration
across groups and across time practical.

**Reproducible benchmarking and software/hardware co-design.** Detect, install
and pin toolchains; build and run programs across operating systems and compute
targets (CPU, CUDA, and others); reuse installs, downloads and builds through
content-addressed caching. An experiment can then be repeated, varied and
compared without rebuilding its scaffolding each time.

**AI-agent operations.** Agents drive the same `access()` surface humans do,
with `ctx` carrying session, trace and budget state through nested calls, and
shipped skills describing how to extend the framework itself.

**Web services and dashboards.** `CMetaAsync` runs cMeta behind FastAPI. The
shipped `cserver` app and the [cTuning.ai](https://cTuning.ai) platform are both
built this way — see [async-and-concurrency.md](async-and-concurrency.md).

**Notes, journals and knowledge.** Notes, journals, logs and reports are
artifacts like everything else, so the knowledge sits next to the automations
it describes instead of in a separate tool.

The reference content repository is
[cmeta-aops](https://github.com/cTuningLabs/cmeta-aops) — reusable `task`,
`tool`, `program`, `model` and `dataset` artifacts for portable setup, builds
and benchmarking.

## What it is not

- **Not a workflow engine competing with Airflow, Snakemake or Nextflow.**
  Those can be plugged in behind the same uniform interface.
- **Not a package manager.** It detects and pins what is already installable,
  and installs Python packages when a task needs them.
- **Not a large feature surface.** The design goal is a small, uniform core
  that content repositories and agents extend.

## Where this came from

cMeta is the current iteration of a longer line of work on the same idea — the
cTuning framework, Collective Knowledge (CK), and MLCommons Collective Mind
(CM/CMX). See [history.md](history.md) for the lineage and the related
publications.

## Next

- [installation.md](installation.md) — get `cx` running.
- [using-cmeta.md](using-cmeta.md) — the getting-started and reference guide.
