"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Tests for the size of the cserver's pool of worker processes (src/app.py, 2026-11-04): CSERVER_WORKERS - set by
`cx app run cserver --param.workers=N` - decides it; without it, or with a value that is no number of workers,
0.8 of the logical processors as before.

The app module is loaded in-process against a fresh <CMETA_HOME> in tmp_path, as test_cserver_home.py does.
Skipped without the server extra (fastapi).
"""

import importlib.util
import os

import pytest

pytest.importorskip('fastapi')

import cmeta  # noqa: E402

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo', 'app', 'cserver')


@pytest.fixture()
def load_app(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'CSERVER_SESSION_SECRET', 'CSERVER_WORKERS'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    monkeypatch.setenv('CSERVER_SESSION_SECRET', 'random')
    monkeypatch.chdir(APP_DIR)
    loaded = []

    def load(workers=None):
        if workers is not None:
            monkeypatch.setenv('CSERVER_WORKERS', workers)
        spec = importlib.util.spec_from_file_location('cserver_app_workers_%d' % len(loaded),
                                                      os.path.join(APP_DIR, 'src', 'app.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded.append(module)
        return module

    yield load
    for module in loaded:
        module.cm.shutdown()


def test_the_default_is_eight_tenths_of_the_processors(load_app):
    module = load_app()
    assert module.max_workers == int(os.cpu_count() * 0.8 + 0.5)
    assert module.cm._executor._max_workers == module.max_workers


def test_cserver_workers_sets_the_pool_size(load_app):
    module = load_app('3')
    assert module.max_workers == 3 and module.cm._executor._max_workers == 3


@pytest.mark.parametrize('value', ['', '0', '-2', 'many'])
def test_a_value_that_is_no_number_of_workers_keeps_the_default(load_app, value):
    module = load_app(value)
    assert module.max_workers == int(os.cpu_count() * 0.8 + 0.5)
