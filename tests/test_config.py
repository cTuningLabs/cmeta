"""
Tests for cmeta.config helpers.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import pytest

from cmeta import config


# ---------------------------------------------------------------------------
# is_on truth-table
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ['1', 'on', 'true', 'yes',
                                   'ON', 'True', 'YES',
                                   '  yes  '])
def test_is_on_truthy(value):
    assert config.is_on(value) is True


@pytest.mark.parametrize("value", ['0', 'off', 'false', 'no', '', 'random'])
def test_is_on_falsy(value):
    assert config.is_on(value) is False


def test_is_on_bool_true():
    assert config.is_on(True) is True


def test_is_on_none():
    assert config.is_on(None) is False


def test_is_on_non_string_non_bool_is_false():
    assert config.is_on(123) is False


# ---------------------------------------------------------------------------
# check_init_vars_from_env — CMETA_HOME resolution order
# ---------------------------------------------------------------------------

# Env vars we sniff in the resolution order — test each override precedence.

def _clear(monkeypatch, *names):
    for n in names:
        monkeypatch.delenv(n, raising=False)


def test_home_uses_explicit_env_var(monkeypatch, tmp_path):
    _clear(monkeypatch, 'CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX')
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    r = config.check_init_vars_from_env()
    assert r['return'] == 0
    assert r['init']['home'] == str(tmp_path)


def test_home_falls_back_to_virtual_env(monkeypatch, tmp_path):
    _clear(monkeypatch, 'CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX')
    monkeypatch.setenv('VIRTUAL_ENV', str(tmp_path))
    r = config.check_init_vars_from_env()
    assert r['init']['home'] == os.path.join(str(tmp_path), config.cfg['capitalized_name'])


def test_home_falls_back_to_conda_prefix(monkeypatch, tmp_path):
    _clear(monkeypatch, 'CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX')
    monkeypatch.setenv('CONDA_PREFIX', str(tmp_path))
    r = config.check_init_vars_from_env()
    assert r['init']['home'] == os.path.join(str(tmp_path), config.cfg['capitalized_name'])


def test_home_falls_back_to_cmeta_home2(monkeypatch, tmp_path):
    _clear(monkeypatch, 'CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX')
    monkeypatch.setenv('CMETA_HOME2', str(tmp_path))
    r = config.check_init_vars_from_env()
    assert r['init']['home'] == str(tmp_path)


def test_home_defaults_to_user_home_when_nothing_set(monkeypatch):
    _clear(monkeypatch, 'CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX')
    r = config.check_init_vars_from_env()
    # It ends with the capitalized project name under user's home.
    assert r['init']['home'].endswith(config.cfg['capitalized_name'])


def test_precedence_cmeta_home_beats_virtual_env(monkeypatch, tmp_path):
    _clear(monkeypatch, 'CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX')
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'primary'))
    monkeypatch.setenv('VIRTUAL_ENV', str(tmp_path / 'venv'))
    r = config.check_init_vars_from_env()
    assert r['init']['home'] == str(tmp_path / 'primary')


def test_fail_on_error_env(monkeypatch):
    _clear(monkeypatch, 'CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                       'CMETA_DEBUG')
    monkeypatch.setenv(config.cfg['env_var_cmeta_fail_on_error'], 'yes')
    r = config.check_init_vars_from_env()
    assert r['init'].get('fail_on_error') is True


def test_debug_env_also_enables_fail_on_error(monkeypatch):
    _clear(monkeypatch, 'CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                       config.cfg['env_var_cmeta_fail_on_error'])
    monkeypatch.setenv(config.cfg['env_var_cmeta_debug'], '1')
    r = config.check_init_vars_from_env()
    assert r['init'].get('debug') is True
    assert r['init'].get('fail_on_error') is True


def test_log_level_and_file_env(monkeypatch, tmp_path):
    log_file = tmp_path / 'x.log'
    monkeypatch.setenv(config.cfg['env_cmeta_log'], 'INFO')
    monkeypatch.setenv(config.cfg['env_cmeta_log_file'], str(log_file))
    r = config.check_init_vars_from_env()
    assert r['init']['log_level'] == 'INFO'
    assert r['init']['log_file'] == str(log_file)


# ---------------------------------------------------------------------------
# Global cfg has the expected constants (guardrails against accidental renames)
# ---------------------------------------------------------------------------

def test_cfg_has_required_keys():
    for k in ['name', 'capitalized_name', 'repos_dir', 'repos_config_filename',
              'meta_filename_base', 'repo_meta_desc', 'category_repo_uid',
              'command_aliases', 'base_category_last_api_version']:
        assert k in config.cfg, f'missing config key: {k}'


def test_command_aliases_include_common_shortcuts():
    aliases = config.cfg['command_aliases']
    for short, long in [('add', 'create'), ('rm', 'delete'), ('ls', 'list'),
                        ('mv', 'move'), ('cp', 'copy'), ('search', 'find'),
                        ('rename', 'move'), ('load', 'read')]:
        assert aliases.get(short) == long


def test_category_repo_uid_is_valid_uid():
    from cmeta.utils.names import is_valid_cmeta_uid
    assert is_valid_cmeta_uid(config.cfg['category_repo_uid'])
