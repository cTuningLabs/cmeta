[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![PyPI version](https://badge.fury.io/py/cmeta.svg)](https://pepy.tech/project/cmeta)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://github.com/ctuninglabs/cmeta)
[![Test cMeta core](https://github.com/cTuningLabs/cmeta/actions/workflows/test-core.yml/badge.svg)](https://github.com/cTuningLabs/cmeta/actions/workflows/test-core.yml)
[![Author: Grigori Fursin](https://img.shields.io/badge/author-Grigori%20Fursin-1f6feb)](https://cTuning.ai/@gfursin)

# cMeta (Common Meta Framework)

**cMeta** (also known as **cX**) is a small, portable framework for unifying,
interconnecting, and reusing code, data, models, agents, and knowledge
across projects, platforms, and time through a uniform interface.
It enables collaborative research and experimentation for developing
self-optimizing and self-adapting software and hardware systems that
automatically identify the most efficient and cost-effective ways
to execute AI, ML, and other complex workloads.

> **Created, architected and developed by
> [Grigori Fursin](https://cTuning.ai/@gfursin)** — originator of the long-term
> vision, concept, architecture and successive prototypes behind cMeta.

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
cx --version
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
