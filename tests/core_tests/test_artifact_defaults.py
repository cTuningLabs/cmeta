"""
Tests for the provenance stamped on new and updated artifacts: authors, copyright and generator,
from the meta itself, the environment and the artifact_defaults of the repository (_cmr.yaml).

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json

from cmeta.category_api_v1 import apply_artifact_defaults, _parse_generator

REPO = {'artifact_defaults': {'authors': 'Repo Owner',
                              'copyright': 'Copyright (C) 2026 Repo Owner. All rights reserved.',
                              'generator': {'method': 'manual'}}}


def test_nothing_set_adds_nothing():
    assert apply_artifact_defaults({}, repo_meta={}, env={}) == {}


def test_environment_only_is_backward_compatible():
    m = apply_artifact_defaults({}, repo_meta={}, env={'CMETA_AUTHORS': 'A', 'CMETA_COPYRIGHT': 'C'})
    assert m == {'authors': 'A', 'copyright': 'C'}


def test_repository_defaults_fill_missing_keys():
    m = apply_artifact_defaults({}, repo_meta=REPO, env={})
    assert m['authors'] == 'Repo Owner'
    assert m['copyright'] == 'Copyright (C) 2026 Repo Owner. All rights reserved.'
    assert m['generator'] == {'method': 'manual', 'by': 'Repo Owner'}


def test_copyright_follows_the_repository_authors_follow_the_person():
    env = {'CMETA_AUTHORS': 'Someone Else', 'CMETA_COPYRIGHT': 'Copyright (C) Someone Else'}
    m = apply_artifact_defaults({}, repo_meta=REPO, env=env)
    assert m['authors'] == 'Someone Else'
    assert m['copyright'] == 'Copyright (C) 2026 Repo Owner. All rights reserved.'
    assert m['generator']['by'] == 'Someone Else'


def test_explicit_meta_wins():
    meta = {'authors': 'X', 'copyright': 'Y', 'generator': {'method': 'script', 'script': 'build.py'}}
    m = apply_artifact_defaults(dict(meta), repo_meta=REPO, env={'CMETA_GENERATOR': '{"method": "task"}'})
    assert m == meta


def test_generator_from_the_environment_beats_the_repository_default():
    g = {'method': 'task', 'task': 'import-x,0123456789abcdef', 'model': 'm', 'effort': 'max'}
    m = apply_artifact_defaults({}, repo_meta=REPO, env={'CMETA_GENERATOR': json.dumps(g)})
    assert m['generator'] == dict(g, by='Repo Owner')


def test_repository_defaults_are_not_mutated():
    before = json.dumps(REPO, sort_keys=True)
    apply_artifact_defaults({}, repo_meta=REPO, env={})
    assert json.dumps(REPO, sort_keys=True) == before


def test_update_records_last_generator_only_when_set():
    m = {'authors': 'A', 'generator': {'method': 'manual', 'by': 'A'}}
    assert apply_artifact_defaults(dict(m), env={}, creating=False) == m
    u = apply_artifact_defaults(dict(m), env={'CMETA_GENERATOR': '{"method": "task", "task": "t"}'},
                                creating=False, today='2026-09-25')
    assert u['generator'] == {'method': 'manual', 'by': 'A'}
    assert u['last_generator'] == {'method': 'task', 'task': 't', 'by': 'A', 'date': '2026-09-25'}


def test_update_does_not_touch_authors_or_copyright():
    u = apply_artifact_defaults({}, repo_meta=REPO, env={'CMETA_AUTHORS': 'A'}, creating=False)
    assert u == {}


def test_parse_generator_forms():
    assert _parse_generator('') is None
    assert _parse_generator('  ') is None
    assert _parse_generator('manual') == {'method': 'manual'}
    assert _parse_generator('{"method": "agent", "model": "m"}') == {'method': 'agent', 'model': 'm'}
    assert _parse_generator('cMeta task x; model y') == {'note': 'cMeta task x; model y'}
    assert _parse_generator('[1, 2]') == {'note': '[1, 2]'}


def test_custom_variable_names_from_config():
    cfg = {'env_var_cmeta_authors': 'MY_AUTHORS', 'env_var_cmeta_copyright': 'MY_COPYRIGHT',
           'env_var_cmeta_generator': 'MY_GENERATOR'}
    m = apply_artifact_defaults({}, env={'MY_AUTHORS': 'A', 'MY_COPYRIGHT': 'C', 'MY_GENERATOR': 'manual'}, cfg=cfg)
    assert m == {'authors': 'A', 'copyright': 'C', 'generator': {'method': 'manual', 'by': 'A'}}
