cMeta Project Home
==================

Welcome to the **Common Meta Framework** (cMeta, also known as cX).

cMeta is a small, portable framework for unifying,
interconnecting, and reusing code, data, models, agents, and knowledge
across projects, platforms, and time through a uniform interface.
It enables collaborative research and experimentation for developing
self-optimizing and self-adapting software and hardware that automatically 
identify the most efficient and cost-effective ways to execute AI, ML, 
and other complex workloads.

Created, architected and developed by
`Grigori Fursin <https://cTuning.ai/@gfursin>`_ — originator of the long-term
vision, concept, architecture and successive prototypes behind cMeta.

Core features
-------------

cMeta represents each part of a workflow as a **uniform, composable,
content-addressed, reproducible artifact**, reachable through a single
interface:

**One uniform interface**
   ``cm.access({'category', 'command'})`` in Python and ``cx <category>
   <command>`` on the command line reach everything: run a program, fetch a
   model, prepare a dataset, build a toolchain, invoke an agent.

**Composable automations**
   Workflows are assembled from small, reusable tasks that *declare what they
   use*, instead of hard-coded scripts.

**Extensible & pluggable**
   New capabilities are added as self-contained artifacts (categories, tasks,
   tools) with optional Python hooks, so the framework grows by plugging in
   components rather than modifying the core.

**Metadata & tags**
   Structured, machine-readable identity makes any component discoverable and
   reusable, by tags rather than by hard-coded paths.

**Content-addressed caching & better reproducibility**
   Identical work is not repeated, and the full context of a run is captured to
   help reproduce it. Full determinism across heterogeneous environments is
   hard; cMeta improves reproducibility but does not yet fully solve it — this
   remains ongoing community R&D.

**Virtualized portability**
   Toolchains, compilers, drivers and runtimes are detected, isolated and
   pinned, abstracting away OS and accelerator differences.

**Unifying agents**
   AI agents operate the same discovery, composition and execution surface that
   humans do, so automations can be driven by people and by agents through one
   interface.

Quickstart
----------

Install:

.. code-block:: bash

   pip install cmeta
   cmeta --version

Command line:

.. code-block:: bash

   cx --help
   cx repo list

Python:

.. code-block:: python

   from cmeta import CMeta

   cm = CMeta()
   r = cm.access({'category': 'repo', 'command': 'list'})
   print(r)

Project information
-------------------

* **Author**: `Grigori Fursin <https://cTuning.ai/@gfursin>`_
* **Organizations**: `cTuning Labs <https://cTuning.ai>`_ and the
  `cTuning foundation <https://cTuning.org>`_
* **License**: Apache License 2.0
* **Project type**: Python library and command-line tool with a unified API
* **Status**: Under active development

Author & vision
---------------

cMeta is the latest in a line of reproducible-research and automation frameworks
that `Grigori Fursin <https://cTuning.ai/@gfursin>`_ has envisioned, architected
and prototyped over more than 15 years:
**Collective Knowledge (CK) → Collective Mind (CM) → CMX → cMeta**.

He developed and donated the CM / CM4MLOps and MLPerf automations to
`MLCommons <https://mlcommons.org>`_, and pioneered community
`Artifact Evaluation and reproducibility initiatives <https://cTuning.org/ae>`_
for ACM/IEEE conferences and journals. cMeta is the foundation for his ongoing,
long-term work on self-optimizing and reproducible AI systems and AI-driven
extreme software/hardware co-design.

If cMeta is useful in your work, you may cite:

   Grigori Fursin. *Enabling more efficient and cost-effective AI/ML systems
   with Collective Mind, virtualized MLOps, MLPerf, Collective Knowledge
   Playground and reproducible optimization tournaments.* arXiv:2406.16791.
   https://arxiv.org/abs/2406.16791

and the earlier foundational work:

   Grigori Fursin. *Collective knowledge: organizing research projects as a
   database of reusable components and portable workflows with common
   interfaces.* Philosophical Transactions of the Royal Society A,
   379(2197):20200211, 2021. https://doi.org/10.1098/rsta.2020.0211

Links
-----

* Author: https://cTuning.ai/@gfursin
* Organizations: `cTuning Labs <https://cTuning.ai>`_ and the
  `cTuning foundation <https://cTuning.org>`_
* `Artifact Evaluation and Reproducibility Initiatives <https://cTuning.org/ae>`_
