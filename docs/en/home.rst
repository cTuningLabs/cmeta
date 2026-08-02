cMeta Project Home
==================

Welcome to the **Common Meta Framework** (cMeta, also known as cX).

cMeta is a small, portable framework for unifying, interconnecting and reusing
code, data, models, agents and knowledge across projects, platforms and time
through a single uniform interface.

It is designed for collaborative and reproducible research, development and
experimentation across AI, ML, systems and other complex workloads — including
**AI-driven benchmarking, modeling, optimization, adaptation and co-design of
the full software/hardware stack** end to end.

cMeta also serves as a **common engine for building "operating systems for
AI"** — a thin, uniform layer that connects, abstracts and orchestrates the
code, data, models, agents and hardware that modern AI systems are assembled
from. On that same foundation it is built to **implement and support research
assistants**: because every artifact declares its own identity, dependencies
and interface, an agent can discover what already exists, compose it into new
workflows and extend it, then hand the result back in a form a person can read
and rerun. The artifacts become durable, shareable memory of how work is
actually done; the agent is the operator.

Created and developed by
`Grigori Fursin <https://cTuning.ai/@gfursin>`_, building on earlier R&D on
reusable and portable research components — the cTuning framework, Collective
Knowledge (CK) and MLCommons Collective Mind (CM/CMX).

Core idea
---------

Every part of a workflow — a program, a model, a dataset, a toolchain, a note,
an agent — is a **uniform, composable, content-addressed artifact** reached
through **one interface**:

* Python: ``cm.access({'category': ..., 'command': ..., ...})``
* CLI: ``cx <category> <command> [args] [--flags]``

cMeta ships a tiny engine and a small built-in content repository of
foundational categories (plugins). Everything else — your projects, research
artifacts, workflows — lives in **external content repositories** that you pull
in, index and share.

What you get
------------

**One uniform interface**
   Run a program, fetch a model, prepare a dataset, build a toolchain, invoke
   an agent, take a note — all through the same surface, from Python or the
   command line.

**Composable automations**
   Workflows are assembled from small, reusable tasks that *declare what they
   use*, instead of hard-coded scripts.

**Extensible & pluggable**
   New capabilities arrive as self-contained artifacts with optional Python
   hooks, so the framework grows by plugging in components rather than by
   modifying the core.

**Semantic portability via UIDs**
   Every category and artifact has a human-friendly *alias* and a stable
   16-hex-character *UID*. References written ``alias,UID`` stay valid even if
   the alias is renamed.

**Metadata & tags**
   Structured, machine-readable identity makes anything discoverable and
   reusable by tags rather than by hard-coded paths.

**Content-addressed caching & better reproducibility**
   Identical work is not repeated, and the context of a run is captured to help
   reproduce it. Full determinism across heterogeneous environments is hard;
   cMeta improves reproducibility but does not yet fully solve it — ongoing R&D.

**Virtualized portability**
   Toolchains, compilers, drivers and runtimes are detected, isolated and
   pinned, abstracting over OS and accelerator differences.

**Unified interface for humans and agents**
   AI agents drive the same discovery, composition and execution surface people
   use.

**Serial or async, with concurrency safety guards**
   The same engine runs one call at a time from a script, or is awaited from
   FastAPI (``CMetaAsync``). Concurrent execution is a supported mode:
   cross-process file locks and atomic writes protect the index and artifact
   metadata when several processes share one ``<CMETA_HOME>``.

Use cases
---------

cMeta is the engine; what it does depends on the content repositories plugged
into it. The uses it is built for:

* **A research assistant for open science** — encode R&D as executable,
  self-describing automations rather than prose and one-off scripts, so the
  *method* travels with the result.
* **Collaborative research, development and experimentation** — share work as
  content repositories; ``alias,UID`` references survive renames, forks and
  years.
* **Reproducible benchmarking and software/hardware co-design** — portable
  toolchain setup, builds and runs across operating systems and compute targets
  (CPU, CUDA, …), with content-addressed caching.
* **AI-agent operations** — agents drive the same ``access()`` surface, with
  ``ctx`` threading session and trace state through nested calls.
* **Web services and dashboards** — the shipped ``cserver`` app and the
  `cTuning.ai <https://cTuning.ai>`_ platform both run cMeta behind FastAPI.
* **Notes, journals and knowledge** — kept alongside the automations they
  describe rather than in a separate silo.

The reference content repository is
`cmeta-aops <https://github.com/cTuningLabs/cmeta-aops>`_ — reusable ``task``,
``tool``, ``program``, ``model`` and ``dataset`` artifacts.

Quickstart
----------

Install:

.. code-block:: bash

   pip install cmeta
   cmeta --version

Command line:

.. code-block:: bash

   cx --help
   cx repo list                      # plugged-in content repositories
   cx category list                  # available categories (plugins)

Python:

.. code-block:: python

   from cmeta import CMeta

   cm = CMeta()
   r = cm.access({'category': 'repo', 'command': 'list'})
   print(r)

Documentation
-------------

The guides are listed in the sidebar under **Guides**, and individually here:

* :doc:`guides/motivation` — why cMeta exists and its design principles
* :doc:`guides/installation` — install, verify, configure (serial and async)
* :doc:`guides/common-commands` — cheatsheet of everyday commands
* :doc:`guides/using-cmeta` — the getting-started and reference guide
* :doc:`guides/error-handling` — return-dict contract, soft errors, debugging
* :doc:`guides/async-and-concurrency` — async use (FastAPI) and concurrency guards
* :doc:`guides/configuration` — working with ``config`` artifacts
* :doc:`guides/cplatform` — connecting to the cTuning.ai platform
* :doc:`guides/history` — lineage, related publications, how to cite
* :doc:`guides/known-issues` — tracked defects and planned improvements

Attribution and reuse
---------------------

cMeta is Apache-2.0, so you are free to use, modify and redistribute it.
Section 4 of the licence asks that you keep the copyright and attribution
notices and reproduce the contents of the project's ``NOTICE`` file — this
applies equally whether the code was copied by a person or generated with the
help of an AI agent or an LLM.

If you reuse the **concepts** rather than the code, a citation is very welcome —
and so is getting in touch. **Collaboration is actively invited:**
`cTuning.ai/@gfursin <https://cTuning.ai/@gfursin>`_. See
:doc:`guides/history` for the citation details and the related publications.

Project information
-------------------

* **Author**: `Grigori Fursin <https://cTuning.ai/@gfursin>`_
* **Organizations**: `cTuning Labs <https://cTuning.ai>`_ and the
  `cTuning foundation <https://cTuning.org>`_
* **License**: Apache License 2.0
* **Project type**: Python library and command-line tool with a unified API
* **Status**: A research and prototyping project — stable in its current shape,
  low-activity, maintained alongside active downstream work.

Links
-----

* Source: https://github.com/cTuningLabs/cmeta
* Author: https://cTuning.ai/@gfursin
* Organizations: `cTuning Labs <https://cTuning.ai>`_ and the
  `cTuning foundation <https://cTuning.org>`_
* `Artifact Evaluation and Reproducibility Initiatives <https://cTuning.org/ae>`_
