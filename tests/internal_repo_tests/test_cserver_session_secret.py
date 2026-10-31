"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Tests for the key that signs the cserver's session cookie (_session_secret of src/app.py): kept beside the
cserver config by default, pinned by CSERVER_SESSION_SECRET, new at every start and kept nowhere with "random"
(`cx app run cserver --param.session_secret=random`).

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
    """Load src/app.py once per call on a fresh home; returns the module (its session_secret is set at import)."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'CSERVER_SESSION_SECRET'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    monkeypatch.chdir(APP_DIR)
    loaded = []

    def load():
        spec = importlib.util.spec_from_file_location('cserver_app_secret_%d' % len(loaded),
                                                      os.path.join(APP_DIR, 'src', 'app.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded.append(module)
        return module

    yield load
    for module in loaded:
        module.cm.shutdown()


def _kept_files(home):
    return [os.path.join(root, name) for root, _, files in os.walk(home) for name in files if name == 'session-secret']


def test_the_default_key_is_made_once_and_kept(load_app, tmp_path):
    first = load_app().session_secret
    kept = _kept_files(str(tmp_path))
    assert len(kept) == 1 and len(first) >= 32
    assert load_app().session_secret == first                  # a restart keeps every browser signed in


def test_a_pinned_key_is_used_as_given(load_app, monkeypatch, tmp_path):
    monkeypatch.setenv('CSERVER_SESSION_SECRET', 'my-own-key-for-several-servers-0123456789')
    assert load_app().session_secret == 'my-own-key-for-several-servers-0123456789'
    assert _kept_files(str(tmp_path)) == []


@pytest.mark.parametrize('value', ['random', 'RANDOM', ' random '])
def test_random_is_a_new_key_at_each_start_kept_nowhere(load_app, monkeypatch, tmp_path, value):
    monkeypatch.setenv('CSERVER_SESSION_SECRET', value)
    first, second = load_app().session_secret, load_app().session_secret
    assert first != second
    assert value.strip().lower() not in (first.lower(), second.lower()) and len(first) >= 32
    assert _kept_files(str(tmp_path)) == []
