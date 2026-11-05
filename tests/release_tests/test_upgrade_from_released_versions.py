"""
The upgrade in place from the released versions, for real: a throwaway environment gets an older cMeta from PyPI
and indexes a home with it; the engine under test is then installed over it the way users upgrade (`pip install -U`
into a venv, `uv tool install --force` into a tool environment), and its first command in that home must find what
the new engine brings - a probe artifact planted in its internal repository - at once, with no `cx --reindex` and no
`cx repo reindex internal`.

Why this test exists: 0.38.7 shipped a new built-in page, and every upgraded installation answered `category
"cserver.cmeta.configs" not found` until a reindex by hand, because the home's index of the engine's own repository
stayed at the release before (2026-11-04). The engine's unit tests could not see it: they ran the new engine in a
fresh home. A release is checked against the installations people really have: this test is a step of
docs/releasing.md.

It needs the network (PyPI), `uv` on PATH and a few minutes, so it runs only when asked:

    CMETA_RELEASE_TESTS=1 python -m pytest tests/release_tests -q -rs
    CMETA_RELEASE_FROM=0.38.4,0.38.7      the versions upgraded from (default: FROM below)
    CMETA_RELEASE_WHEEL=<wheel>           the engine under test (default: this tree, built by uv/pip)
    CMETA_RELEASE_MODES=pip,tool          the ways of upgrading (default: both)

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import secrets
import shutil
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'cmeta'))
from version import __version__ as NEW  # noqa: E402  (cmeta/version.py: the version of the tree under test)

# The releases people upgrade from: the one with the previous fix of the internal repository (0.37.3), the first
# 0.38, a middle one, the one before the gap was found and the one that showed it
FROM = ['0.37.3', '0.38.0', '0.38.4', '0.38.6', '0.38.7']
WINDOWS = os.name == 'nt'

pytestmark = pytest.mark.skipif(not os.environ.get('CMETA_RELEASE_TESTS'),
                                reason='the upgrade from released versions runs only with CMETA_RELEASE_TESTS=1 (network, uv, minutes)')


def versions():
    return [v.strip() for v in os.environ.get('CMETA_RELEASE_FROM', ','.join(FROM)).split(',') if v.strip()]


def modes():
    return [m.strip() for m in os.environ.get('CMETA_RELEASE_MODES', 'pip,tool').split(',') if m.strip()]


def run(cmd, env, timeout=900, cwd=None):
    t0 = time.monotonic()
    p = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, env=env, timeout=timeout, cwd=cwd)
    return p.returncode, (p.stdout + p.stderr).decode('utf-8', 'replace'), time.monotonic() - t0


@pytest.fixture(scope='module')
def uv():
    exe = shutil.which('uv')
    if not exe:
        pytest.skip('uv is not on PATH')
    return exe


@pytest.fixture(scope='module')
def wheel(tmp_path_factory, uv):
    """The engine under test: CMETA_RELEASE_WHEEL, or a wheel of this tree built once for the module."""
    given = os.environ.get('CMETA_RELEASE_WHEEL')
    if given:
        assert os.path.isfile(given), given
        return given
    out_dir = str(tmp_path_factory.mktemp('wheel'))
    code, out, _ = run([uv, 'build', '--wheel', '--out-dir', out_dir, ROOT], dict(os.environ), cwd=ROOT)
    assert code == 0, out
    built = [f for f in os.listdir(out_dir) if f.endswith('.whl')]
    assert len(built) == 1, built
    return os.path.join(out_dir, built[0])


class Install:
    """One throwaway installation: a venv (pip) or a uv tool environment (tool), its cx and its python."""

    def __init__(self, mode, work, uv, python_version):
        self.mode, self.work, self.uv = mode, work, uv
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('CMETA_', 'UV_TOOL_')) and k not in ('VIRTUAL_ENV', 'CONDA_PREFIX')}
        self.env['CMETA_HOME'] = os.path.join(work, 'home')
        self.env['PYTHONIOENCODING'] = 'utf-8'
        self.python_version = python_version
        if mode == 'pip':
            self.venv = os.path.join(work, 'venv')
            bindir = os.path.join(self.venv, 'Scripts' if WINDOWS else 'bin')
        else:
            self.env['UV_TOOL_DIR'] = os.path.join(work, 'tools')
            self.env['UV_TOOL_BIN_DIR'] = os.path.join(work, 'bin')
            self.venv = os.path.join(work, 'tools', 'cmeta')
            bindir = os.path.join(work, 'bin')
        self.python = os.path.join(self.venv, 'Scripts' if WINDOWS else 'bin', 'python.exe' if WINDOWS else 'python')
        self.cx = os.path.join(bindir, 'cx.exe' if WINDOWS else 'cx')

    def install(self, what):
        """cMeta `what` (a `cmeta==X.Y.Z` of PyPI, or the path of a wheel) the way users install or upgrade."""
        if self.mode == 'pip':
            if not os.path.isdir(self.venv):
                code, out, _ = run([self.uv, 'venv', '--python', self.python_version, self.venv], self.env, cwd=self.work)
                assert code == 0, out
            cmd = [self.uv, 'pip', 'install', '--python', self.python, '--reinstall-package', 'cmeta', what]
        else:
            cmd = [self.uv, 'tool', 'install', '--force', '--reinstall', '--python', self.python_version, what]
        code, out, sec = run(cmd, self.env, cwd=self.work)
        assert code == 0, out
        return sec

    def internal_repo(self):
        """The internal repository of the installed engine. Python runs isolated (-I) and in the work folder: pytest's
        current directory is the engine's own tree, whose `cmeta/` folder would be imported instead of the installed
        package (the probe then landed in the tree under test, 2026-11-05)."""
        code, out, _ = run([self.python, '-I', '-c', 'import cmeta, os; print(os.path.dirname(os.path.abspath(cmeta.__file__)))'],
                           self.env, cwd=self.work)
        assert code == 0, out
        repo = os.path.join(out.strip().splitlines()[-1], 'internal-repo')
        assert os.path.normcase(os.path.abspath(repo)).startswith(os.path.normcase(os.path.abspath(self.work))), repo
        return repo

    def command(self, *words):
        code, out, sec = run([self.cx] + list(words), self.env, timeout=600, cwd=self.work)
        return code, out, sec


@pytest.mark.parametrize('old', versions())
@pytest.mark.parametrize('mode', modes())
def test_the_first_command_after_the_upgrade_finds_what_the_new_engine_brings(tmp_path, uv, wheel, old, mode):
    if old == NEW:
        # the engine tells an upgrade by the version of its internal repository: the same version over itself (a git
        # pull of a development tree, a rebuilt wheel of the same version) is not an upgrade to it - "cx repo reindex
        # internal" there. The case of the release before is the one that matters: run this after the version bump
        pytest.skip('the tree is %s itself: run the release tests after the version bump' % NEW)
    python_version = '%d.%d' % sys.version_info[:2]
    inst = Install(mode, str(tmp_path), uv, python_version)

    # the older release from PyPI makes and indexes the home
    inst.install('cmeta==' + old)
    code, out, _ = inst.command('--version')
    assert code == 0 and 'cMeta version ' + old in out, out

    # the engine under test over it, in the same folder, as pip -U / uv tool install --force do
    inst.install(wheel)
    repo = inst.internal_repo()
    assert os.path.isfile(os.path.join(repo, '_cmr.yaml')), repo

    # what the new engine brings: an app of its internal repository that the older release never had
    probe = 'upgrade-probe-' + old.replace('.', '-')
    os.makedirs(os.path.join(repo, 'app', probe))
    with open(os.path.join(repo, 'app', probe, '_cmeta.yaml'), 'w', encoding='utf-8') as f:
        f.write('artifact: %s\ncategory: app,554a9a2199104713\n' % secrets.token_hex(8))

    # the first command: the probe is found at once, the engine says that it read its repository again
    code, out, sec = inst.command('app', 'find', probe)
    assert code == 0, out
    assert probe in out and 'indexing it again' in out, out
    assert 'cMeta notice' not in out, out
    # ... once: the next command is at rest, and it is the new engine
    code, out, _ = inst.command('--version')
    assert code == 0 and 'cMeta version ' + NEW in out and 'indexing it again' not in out, out
    # the pages the releases after `old` brought are there too (0.38.7: the configs page)
    code, out, _ = inst.command('category', 'find', 'cserver.cmeta.configs')
    assert code == 0, out
    print('%s %s -> %s: the first command %.1f s' % (mode, old, NEW, sec))
