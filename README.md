[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![PyPI version](https://badge.fury.io/py/cmeta.svg)](https://pepy.tech/project/cmeta)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://github.com/ctuninglabs/cmeta)
[![Test cMeta core](https://github.com/cTuningLabs/cmeta/actions/workflows/test-core.yml/badge.svg)](https://github.com/cTuningLabs/cmeta/actions/workflows/test-core.yml)
[![Author: Grigori Fursin](https://img.shields.io/badge/author-Grigori%20Fursin-1f6feb)](https://cTuning.ai/@gfursin)

# cMeta (Common Meta Framework)

**cMeta** (also known as **cX**) is a small, portable framework for unifying,
interconnecting and reusing **code, data, models, agents and knowledge** across
projects, platforms and time, through one uniform interface.

> **Created, architected and developed by
> [Grigori Fursin](https://cTuning.ai/@gfursin)** — originator of the long-term
> vision, concept, architecture and successive prototypes behind cMeta.

---

## Author & vision

cMeta is the latest in a line of reproducible-research and automation frameworks
that **[Grigori Fursin](https://cTuning.ai/@gfursin)** has envisioned, architected
and prototyped over more than 15 years:
**Collective Knowledge (CK) → Collective Mind (CM) → CMX → cMeta**.

He developed and donated the CM / CM4MLOps and MLPerf automations to
[MLCommons](https://mlcommons.org), and pioneered community
[Artifact Evaluation and reproducibility initiatives](https://cTuning.org/ae) for
ACM/IEEE conferences and journals. cMeta is the foundation for his ongoing,
long-term work on self-optimizing and reproducible AI systems and AI-driven
extreme software/hardware co-design.

If cMeta is useful in your work, you may cite:

> Grigori Fursin. *Enabling more efficient and cost-effective AI/ML systems with
> Collective Mind, virtualized MLOps, MLPerf, Collective Knowledge Playground and
> reproducible optimization tournaments.* arXiv:2406.16791.
> https://arxiv.org/abs/2406.16791

and the earlier foundational work:

> Grigori Fursin. *Collective knowledge: organizing research projects as a
> database of reusable components and portable workflows with common interfaces.*
> Philosophical Transactions of the Royal Society A, 379(2197):20200211, 2021.
> https://doi.org/10.1098/rsta.2020.0211

---

## Core features

cMeta represents each part of a workflow as a **uniform, composable,
content-addressed, reproducible artifact**, reachable through a single interface:

- **One uniform interface** — `cm.access({'category', 'command'})` in Python and
  `cx <category> <command>` on the command line reach everything: run a program,
  fetch a model, prepare a dataset, build a toolchain, invoke an agent.
- **Composable automations** — workflows are assembled from small, reusable tasks
  that *declare what they use*, instead of hard-coded scripts.
- **Extensible & pluggable** — new capabilities are added as self-contained
  artifacts (categories, tasks, tools) with optional Python hooks, so the
  framework grows by plugging in components rather than modifying the core.
- **Metadata & tags** — structured, machine-readable identity makes any component
  discoverable and reusable, by tags rather than by hard-coded paths.
- **Content-addressed caching & better reproducibility** — identical work is not
  repeated, and the full context of a run is captured to help reproduce it. Full
  determinism across heterogeneous environments is hard; cMeta improves
  reproducibility but does not yet fully solve it — this remains ongoing
  community R&D.
- **Virtualized portability** — toolchains, compilers, drivers and runtimes are
  detected, isolated and pinned, abstracting away OS and accelerator differences.
- **Unifying agents** — AI agents operate the same discovery, composition and
  execution surface that humans do, so automations can be driven by people and by
  agents through one interface.

---

## Installation

```bash
pip install cmeta
cmeta --version
```

See **[docs/installation.md](docs/installation.md)** for uv, install-from-source,
configuration and troubleshooting.

---

## Quickstart

Command line:

```bash
cx --help
cx repo list
```

Python:

```python
from cmeta import CMeta

cm = CMeta()
r = cm.access({'category': 'repo', 'command': 'list'})
print(r)
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

This project may include minor functionality reused from
[MLCommons CK/CM](https://github.com/mlcommons/ck), developed by the same author
and licensed under the same Apache 2.0 terms.

## Copyright

Copyright (C) 2025–2026 [Grigori Fursin](https://cTuning.ai/@gfursin) and
[cTuning Labs](https://cTuning.ai).

## Links

- Author: [https://cTuning.ai/@gfursin](https://cTuning.ai/@gfursin)
- Organizations: [cTuning Labs](https://cTuning.ai) and the
  [cTuning foundation](https://cTuning.org)
- [Artifact Evaluation and Reproducibility Initiatives](https://cTuning.org/ae)

## Status

*Under active development.*
