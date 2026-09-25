# History and background

cMeta did not start from scratch. It is the current iteration of a line of
frameworks by [Grigori Fursin](https://cTuning.ai/@gfursin) built around one
recurring idea: represent code, data, models and knowledge as **reusable,
content-addressed components with a common interface**, so that research and
engineering results stay usable across projects, platforms and time.

This page is the single place where that lineage, the related publications and
the citation guidance live — the [README](../README.md) links here rather than
repeating it.

---

## Lineage

**cTuning framework / MILEPOST** — the starting point: machine-learning-based
program and compiler autotuning, backed by a shared repository of optimization
data collected from the community.

**Collective Knowledge (CK)** — a general framework for organizing research
projects as a database of reusable components and portable workflows behind
common interfaces. CK was used for community
[Artifact Evaluation](https://cTuning.org/ae) at ACM and IEEE conferences and
journals, and for reproducing and re-running published experiments.
Repository: [mlcommons/ck](https://github.com/mlcommons/ck).

**Collective Mind (CM / CM4MLOps) and CMX** — the successor generation, focused
on automating the assembly and execution of complex AI/ML benchmarking and
MLOps pipelines across heterogeneous hardware. CM and the MLPerf automations
were developed and then donated to [MLCommons](https://mlcommons.org).

**cMeta (cX)** — the current framework. It keeps the artifact + uniform
interface model of its predecessors, but with a deliberately small engine:
`cm.access({'category', 'command', ...})` in Python and
`cx <category> <command>` on the CLI, with everything else living in pluggable
content repositories. It also takes a first pass at making the framework itself
extensible **by AI agents** through the same interface humans use — see the
`ctx` dictionary and the shipped skills described in
[using-cmeta.md](using-cmeta.md).

What carried over from one generation to the next: uniform access, artifacts
identified by both a human-readable alias and a stable UID, tag-based
discovery, declared dependencies instead of hard-coded scripts, and
content-addressed caching for repeatable runs.

---

## Related publications and talks

Selected work describing the concepts behind cMeta and its predecessors:

- G. Fursin. *Collective knowledge: organizing research projects as a database
  of reusable components and portable workflows with common interfaces.*
  Philosophical Transactions of the Royal Society A, 379(2197), 2021.
  [doi:10.1098/rsta.2020.0211](https://doi.org/10.1098/rsta.2020.0211)
- G. Fursin. *Enabling more efficient and cost-effective AI/ML systems with
  Collective Mind, virtualized MLOps, MLPerf, Collective Knowledge Playground
  and reproducible optimization tournaments.* arXiv:2406.16791, 2024.
  [arxiv.org/abs/2406.16791](https://arxiv.org/abs/2406.16791)
- G. Fursin, D. Altunay. *Framing AI System Benchmarking as a Learning Task:
  FlexBench and the Open MLPerf Dataset.* arXiv:2509.11413, 2025.
  [arxiv.org/abs/2509.11413](https://arxiv.org/abs/2509.11413)
- G. Fursin. *Collective Mind: toward a common language to facilitate
  reproducible research and technology transfer.* Presentation, Zenodo, 2023.
  [doi:10.5281/zenodo.8105339](https://doi.org/10.5281/zenodo.8105339)
- G. Fursin. *Reproducing 150 Research Papers and Testing Them in the Real
  World.* ACM Tech Talk, 2021.
  [video](https://www.youtube.com/watch?v=7zpeIVwICa4) ·
  [slides](https://learning.acm.org/binaries/content/assets/leaning-center/webinar-slides/2021/grigorifursin_techtalk_slides.pdf)

---

## How to cite

If you use cMeta in your work, cite the software. GitHub's **"Cite this
repository"** button — generated from [`CITATION.cff`](../CITATION.cff) —
produces APA and BibTeX automatically. The BibTeX entry:

```bibtex
@software{fursin_cmeta,
  author  = {Fursin, Grigori},
  title   = {{cMeta (Common Meta Framework)}},
  year    = {2026},
  version = {0.32.2},
  license = {Apache-2.0},
  url     = {https://github.com/cTuningLabs/cmeta},
  note    = {cTuning Labs}
}
```

If your work builds on the ideas rather than on the code, the two most directly
relevant references are the *Collective knowledge* article (Phil. Trans. R.
Soc. A, 2021) and the *Collective Mind* preprint (arXiv:2406.16791, 2024),
both listed above.

### Reusing the code or the concepts

**Code, metadata or scripts.** cMeta is Apache-2.0, so you are free to use,
modify and redistribute it. Section 4 of the licence asks that you retain the
copyright and attribution notices and reproduce the contents of
[`NOTICE`](../NOTICE) in your distribution. This holds whether the code was
copied by a person or produced with the help of an AI agent or an LLM.

**Concepts.** If you build on the ideas rather than the code — the uniform
`access()` interface, alias + UID artifact identity, content-addressed
artifacts and caching, or the plugin/category model — a citation is very
welcome and costs you nothing.

**Collaboration is actively invited.** If you are building something on top of
cMeta, or exploring the same problems in your own framework, the author would
genuinely like to hear about it: [cTuning.ai/@gfursin](https://cTuning.ai/@gfursin).

---

## License note

cMeta is Apache-2.0. It may include minor functionality reused from
[MLCommons CK/CM](https://github.com/mlcommons/ck), developed by the same
author and licensed under the same Apache-2.0 terms.
