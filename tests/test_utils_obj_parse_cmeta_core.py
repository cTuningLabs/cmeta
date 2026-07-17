"""
cMeta core tests

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import pytest

from cmeta import CMeta

def test_cmeta_access_basic():
    cm = CMeta()
    r = cm.access({'category':'category',
                   'command':'find'})
    assert r['return'] == 0

    artifacts = r['artifacts']
    found = False

    for a in artifacts:
        assert 'cmeta_ref_parts' in a
        cmeta_ref_parts = a['cmeta_ref_parts']

        assert 'artifact_alias' in cmeta_ref_parts

        artifact_alias = cmeta_ref_parts['artifact_alias']

        if artifact_alias == 'repo':
            found = True
            break

    assert found

def test_cmeta_access_read():
    cm = CMeta()
    r = cm.access({'category':'category',
                   'command':'read',
                   'arg1':'category'})
    assert r['return'] == 0

def test_cmeta_access_read():
    cm = CMeta()
    r = cm.access({'category':'category',
                   'command':'read',
                   'arg1':'category',
                   'load_files':['test']})
    assert r['return'] == 0

    assert 'artifact' in r
    artifact = r['artifact']

    assert 'loaded_files' in r
    loaded_files = r['loaded_files']

    assert 'test' in loaded_files
    assert 'data' in loaded_files['test']
    assert 'test' in loaded_files['test']['data']
    assert loaded_files['test']['data']['test']

def test_cmeta_access_read2():
    cm = CMeta()
    r = cm.access({'category':'category',
                   'command':'read',
                   'arg1':'category',
                   'load_files':['test.json']})
    assert r['return'] == 0

    assert 'artifact' in r
    artifact = r['artifact']

    assert 'loaded_files' in r
    loaded_files = r['loaded_files']

    assert 'test.json' in loaded_files
    assert 'data' in loaded_files['test.json']
    assert 'test' in loaded_files['test.json']['data']
    assert loaded_files['test.json']['data']['test']

def test_cmeta_access_read3():
    cm = CMeta()
    r = cm.access({'category':'category',
                   'command':'read',
                   'arg1':'category',
                   'load_files':['test.yaml']})
    assert r['return'] == 0

    assert 'artifact' in r
    artifact = r['artifact']

    assert 'loaded_files' in r
    loaded_files = r['loaded_files']

    assert 'test.yaml' in loaded_files
    assert 'data' in loaded_files['test.yaml']
    assert 'test' in loaded_files['test.yaml']['data']
    assert loaded_files['test.yaml']['data']['test']
