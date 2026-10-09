"""
The engine benchmark next to this file (benchmark_engine.py) must keep running on every platform and Python
the suite covers: this runs it on a small home and checks that every section reported its numbers and that
the index it built is consistent. The numbers themselves are not asserted (the speed of a CI runner varies).
The benchmark proper is run by hand before and after an engine change:

    python tests/benchmarks/benchmark_engine.py --home <empty folder> --n 10000 --json before.json
    python tests/benchmarks/benchmark_engine.py --home <empty folder> --n 10000 --json after.json --compare before.json

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, 'benchmark_engine.py')

EXPECTED = (
    'CMeta() warm',
    'repo plug (incremental index of the repo)',
    'full reindex (cx --reindex)',
    'records in the index',
    'find by alias (1 hit)',
    'find by UID (1 hit)',
    'find a missing alias (error 16)',
    'find by alias after a changed index',
    'create (meta file + index write)',
    'update (meta edit in place + index write)',
    'reindex one artifact',
    'delete (index write + folder removal)',
    'os.stat of the index file',
    'engine lock acquire+release',
    'candidate lock, file removed on release',
    'write a 1 KB file atomically',
    'concurrent creates: wall time',
    'concurrent creates: records lost',
    'concurrent creates: folders on disk',
    'index consistency: broken alias links',
)


def test_benchmark_runs_and_reports_every_section(tmp_path):
    out = tmp_path / 'bench.json'
    env = dict(os.environ)
    for v in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR'):
        env.pop(v, None)

    r = subprocess.run([sys.executable, SCRIPT, '--home', str(tmp_path / 'home'), '--n', '50', '--writes', '3',
                        '--procs', '2', '--per', '3', '--json', str(out)],
                       env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    assert r.returncode == 0, r.stdout.decode('utf-8', 'replace')[-4000:]

    data = json.loads(out.read_text(encoding='utf-8'))
    results = data['results']
    for name in EXPECTED:
        assert name in results, name
        assert results[name]['n'] >= 1

    assert results['records in the index']['median'] == 50
    assert results['concurrent creates: folders on disk']['median'] == 6
    assert results['index consistency: broken alias links']['median'] == 0
    assert data['worker_errors'] == []
    assert data['meta']['n'] == 50
