[![PyPI version](https://badge.fury.io/py/cmeta.svg)](https://pepy.tech/project/cmeta)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://github.com/ctuninglabs/cmeta)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE.md)

# cMeta (Common Meta Framework)

cMeta (aka cX) is a common meta-framework for unifying, interconnecting and reusing code, data, 
models, agents, and knowledge across projects and domains.

## License

Apache 2.0

## Copyright

Copyright (C) 2025-2026 [Grigori Fursin](https://cTuning.ai/@gfursin) and [cTuning Labs](https://cTuning.ai).

This project may include minor functionality reused from [MLCommons CK](https://github.com/mlcommons/ck), 
developed by the same author and licensed under the same Apache 2.0 terms.

## Installation

### Simple PIP

```bash
pip install cmeta
cmeta --version
```

### UV + PIP


```bash
uv venv
uv pip install cmeta
uv run cmeta --version
```

### UV + GIT


```bash
uv venv
uv pip install --force-reinstall git+ssh://git@github.com/ctuninglabs/cmeta.git@main#egg=cmeta
uv run cmeta --version
```

## Command line

```bash
cmeta --help
cmeta --version
```
or
```bash
cx --help
cx --version
```

## Python interface

```python
from cmeta import CMeta
cm = CMeta()
r = cm.access({'category':'repo', 'command':'list'})
print (r)
```


## Status

*Under active development.*
