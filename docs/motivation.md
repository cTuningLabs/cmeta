# Why cMeta

## The problem

Research and engineering projects accumulate code, data, models, toolchains,
scripts, and notes — and most of it stops being usable surprisingly quickly.
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

## The aim

cMeta exists to support R&D that is **collaborative, reproducible, reusable,
scalable, portable, and sustainable** — and to do it in the simplest way that
works.

- **Collaborative.** Work is shared as content repositories that other people
  plug in and *run*, rather than as instructions to follow. References written
  as `alias,UID` keep resolving across renames, forks, machines, and years, so a
  pointer to an experiment or a dataset still means something later.
- **Reproducible — gradually, not absolutely.** The context around a run is
  recorded with the run: the toolchain, the versions, the inputs, the metadata.
  That removes most accidental differences and makes a re-run far more likely to
  match. It is an honest claim rather than a guarantee: full determinism across
  heterogeneous hardware and library versions is genuinely hard, so
  reproducibility here improves steadily and is never advertised as solved.
- **Reusable.** An artifact describes what it is instead of being wired into one
  pipeline, so the same toolchain, program, model, or dataset can be picked up by
  a different project without being rewritten for it.
- **Scalable.** More complexity is encoded by adding artifacts and categories,
  not by growing the engine. A new domain is a new category; a new capability is
  a new artifact. The framework extends sideways, in many directions at once,
  and the core stays the size it is.
- **Portable.** The same automation runs anywhere and at any time, adapting to
  whatever software and hardware the person running it happens to have —
  toolchains are detected, installed if missing, and pinned, so the description
  never names one machine's compiler.

- **Sustainable.** Work outlives the people who did it. Teams change: someone
  leaves, someone joins two years later, a project is picked up after a pause.
  If the method lived in one person's head, in a chat thread, or in a script on a
  laptop, it leaves with them and the next person restarts. Here it is recorded
  as artifacts beside the result — what was run, what it depended on, which
  version, on what date, and why — so the next person plugs in the repository,
  sees what already exists, and **resumes** rather than reconstructs. This is
  the quiet, compounding one: none of the other five aims survives staff
  turnover unless the context survives with them.

And the constraint that shapes all six: **it has to stay simple, with minimal
dependencies.** There is no database, no daemon, no service to stand up, and no
binary format. There are directories and files — a folder with a small metadata
file beside it — reached through one CLI, one Python API, and one metadata
convention. Anything cMeta stores can be read, edited, diffed, committed, and
fixed by hand, which is what lets the work outlive the tool.

### How: complexity becomes abstractions you can operate

The six aims all rest on one move. A serious project accumulates more complexity
than anyone can hold in their head — toolchains, datasets, models, workflows,
environments, measured numbers, and the concepts tying them together — and most
of it ends up encoded in scripts, in prose, or in the memory of whoever built it.
cMeta's answer is to express each piece of that complexity as one **artifact**: a
folder with a small metadata file beside it, a stable identity, and its
connections to other artifacts declared.

That yields abstractions with four properties that only matter together:

- **Simple** — a directory and a metadata file. Nothing to stand up, nothing to
  learn beyond one interface, and still readable by hand years later.
- **Reusable** — an artifact states what it *is*, not where it fits, so it
  carries into another project without being rewritten for it.
- **Live** — it is executable, not a description of something executable. You run
  it through the same interface you found it with, so the description and the
  behaviour cannot quietly drift apart.
- **Interconnected** — artifacts reference each other by `alias,UID`, so what you
  accumulate is a navigable graph rather than a pile of folders.

Once complexity is expressed this way you stop re-deriving it. You **operate**
the abstractions through one interface, **understand** them by reading what they
declare about themselves, and **build upon** them by composing them into larger
ones — which is what lets a body of work extend sideways instead of collapsing
under its own weight.

Because every abstraction stays inspectable down to its inputs, its versions, and
its provenance, a question can also be taken back to **first principles** — what
was actually measured, under what conditions, on what date, and by whom — rather
than settled by convention, by folklore, or by a number that has been copied from
slide to slide long enough to look authoritative.

### Why this matters more with AI

An AI agent is only as useful as the context it can assemble, and assembling
context is usually the expensive part of the job: finding what already exists,
working out how it was run, reconstructing the environment, guessing what a
number meant and whether it is still current. That work is repeated on almost
every task, by people and by agents alike.

cMeta removes most of it, because **the context is already recorded and already
machine-readable**. Every artifact declares its own identity, dependencies, and
interface. Connections state what relates to what, so a graph can be walked
rather than a directory guessed at. Records carry their dates and their
provenance, so "which value was current in June" is a query rather than an
excavation. An agent can therefore discover what exists, compose it into a new
workflow, run it, and hand the result back in the same form a person can read
and rerun — through the very same `access()` interface a person uses. An
automation written by a human can be extended by an agent, and the reverse.

This is the sustainability aim seen from the other side. A body of work a
newcomer can pick up in an afternoon is, for exactly the same reasons, a body of
work an agent can operate: the context does not have to be reassembled, because
it was never allowed to disperse.

## The approach

cMeta represents **every part of a workflow — a program, a model, a dataset, a
toolchain, a note, an agent — as a uniform, composable, content-addressed
artifact**, and reaches all of them through **one interface**:

- Python: `cm.access({'category': ..., 'command': ..., ...})`
- CLI: `cx <category> <command> [args] [--flags]`

An artifact is a plain directory with a `_cmeta.yaml` sidecar that carries its
identity and metadata. A **category** is a plugin type that knows how to
operate on artifacts of its kind, implemented in an `api/v1.py`. Categories and
artifacts live in **content repositories** that you pull in, index, and share.

That is nearly the whole model. The engine stays small on purpose; capability
comes from the repositories plugged into it.

## Design principles

**Complexity becomes artifacts.** The unit of everything is one small,
self-describing, runnable abstraction with a stable identity and declared
connections. A body of work grows by gaining artifacts and relations between
them, not by gaining special cases — so what a newcomer has to understand at any
moment stays the size of one artifact plus the graph immediately around it.

**One uniform interface.** Anything reachable from the CLI is reachable from
Python and vice versa. New capability is added behind the same `access()`
surface rather than as a new entry point — which is what keeps automations
composable, and what lets AI agents drive the same surface people use.

**Identity that survives renaming.** Every category and artifact has both a
human-friendly *alias* and a stable 16-hex-character *UID*. References written
as `alias,UID` stay valid when the alias changes, because the UID is
authoritative and the alias is advisory. This is what makes references portable
across projects, forks, and time.

**Discovery by metadata, not by path.** Structured tags and metadata make
components findable by what they are, rather than by where they happen to sit
on disk.

**Declared dependencies over hard-coded scripts.** Automations are assembled
from small reusable tasks that state what they use (`uses_categories`, `uses`
pipelines), so a workflow can be recomposed instead of rewritten.

**Extend by plugging in, not by patching the core.** New capability arrives as
self-contained artifacts with optional Python hooks. The framework grows
sideways; the engine does not.

**Virtualized portability.** Toolchains, compilers, drivers, and runtimes are
detected, isolated, and pinned, so the same automation abstracts over OS and
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
composition, and execution interface people do, so an automation written by a
person can be extended by an agent and vice versa. See the `ctx` dictionary in
[using-cmeta.md §5.4](using-cmeta.md#54-ctx--thread-state-and-ai-agent-context-through-nested-calls).

## FAIR by construction

The [FAIR principles](https://www.go-fair.org/fair-principles/) — findable,
accessible, interoperable, reusable — were formulated for research data, and they
apply just as directly to the code, models, workflows, and results around it.
cMeta is shaped so that following them is the default rather than extra work:

| FAIR | How it falls out of the design |
|------|--------------------------------|
| **Findable** | Every artifact carries a stable `alias,UID` identity plus structured tags and metadata, and a fast index makes it searchable by *what it is* rather than by where it happens to sit on disk. |
| **Accessible** | Plain directories and files, reached through one CLI and one Python API. No database, daemon, service, or binary format stands between a person and their own content. |
| **Interoperable** | One `access()` interface and one metadata convention across every domain, with dependencies and relations declared rather than implied — so components from unrelated projects still compose. |
| **Reusable** | An artifact describes itself and carries its provenance, licence, and declared dependencies, so another project — or another person years later — can pick it up unchanged and know what it is. |

The point is not compliance. It is that these four properties are precisely what
a collaborator, a newcomer or an AI agent needs in order to use work they did not
create themselves — which is why they reappear behind every aim above.

## What people use it for

cMeta is an engine; what it actually does depends on the content repositories
plugged into it. These are the uses it is designed around.

**A research assistant for open science.** The recurring problem in research
engineering is that knowledge about *how* something was done lives in prose,
one-off scripts, and remembered command lines — and decays. cMeta's answer is to encode
that practice as executable, self-describing artifacts: how to detect and
install a toolchain, how to build and benchmark a program on a given target,
how to fetch a model. Because each artifact carries machine-readable metadata
and declares what it uses, an AI agent can discover, compose, and extend them
through the same interface a person uses. The artifacts are the accumulated
memory; the agent — or the person — is the operator. This is a deliberately
modest reading of "research assistant": not a system that invents science, but
one that stops you re-deriving the same setup every time.

**Collaborative research, development, and experimentation.** Work is shared as
content repositories that others plug in and run, not as instructions to
follow. Because references use `alias,UID` and the UID is authoritative, a
pointer to an experiment, a dataset, or the workflow that produced a result
stays valid across renames, forks, and years — which is what makes collaboration
across groups and across time practical.

**Reproducible benchmarking and software/hardware co-design.** Detect, install,
and pin toolchains; build and run programs across operating systems and compute
targets (CPU, CUDA, and others); reuse installs, downloads, and builds through
content-addressed caching. An experiment can then be repeated, varied, and
compared without rebuilding its scaffolding each time.

**AI-agent operations.** Agents drive the same `access()` surface humans do,
with `ctx` carrying session, trace, and budget state through nested calls, and
shipped skills describing how to extend the framework itself.

**Web services and dashboards.** `CMetaAsync` runs cMeta behind FastAPI. The
shipped `cserver` app and the [cTuning.ai](https://cTuning.ai) platform are both
built this way — see [async-and-concurrency.md](async-and-concurrency.md).

**Notes, journals, and knowledge.** Notes, journals, logs, and reports are
artifacts like everything else, so the knowledge sits next to the automations
it describes instead of in a separate tool.

The reference content repository is
[cmeta-aops](https://github.com/cTuningLabs/cmeta-aops) — reusable `task`,
`tool`, `program`, `model`, and `dataset` artifacts for portable setup, builds,
and benchmarking.

## What it is not

- **Not a workflow engine competing with Airflow, Snakemake, or Nextflow.**
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
