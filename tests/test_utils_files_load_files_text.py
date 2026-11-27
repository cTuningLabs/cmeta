"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

utils.files.load_files takes the names of the files to load as a list, as the Python API gives them, or as text from
a command line: "cx model find <name> --load_files=_desc" was read letter by letter ('_', 'd', 'e', 's', 'c') and
loaded nothing (found 2026-11-26). Text is one file name, whole: nothing is split at a comma or a ";", which a file
name may hold. Several files are a list - on a command line "--load_files+=_desc --load_files+=README".
"""

import json

from cmeta import CMeta, utils


def test_text_is_one_file_name_and_a_list_stays_a_list(tmp_path):
    (tmp_path / '_desc.json').write_text(json.dumps({'model': {'hf': 'org/name'}}), encoding = 'utf-8')
    (tmp_path / 'other.json').write_text(json.dumps({'x': 1}), encoding = 'utf-8')
    (tmp_path / 'a,b.json').write_text(json.dumps({'comma': True}), encoding = 'utf-8')

    as_list = utils.files.load_files(str(tmp_path), ['_desc'])
    as_text = utils.files.load_files(str(tmp_path), '_desc')
    assert as_list['return'] == 0 and as_text['return'] == 0
    assert list(as_text['loaded_files']) == ['_desc']
    assert as_text['loaded_files']['_desc']['data'] == as_list['loaded_files']['_desc']['data'] == {'model': {'hf': 'org/name'}}

    # a name with a comma is one file, never two
    one = utils.files.load_files(str(tmp_path), 'a,b')
    assert list(one['loaded_files']) == ['a,b'] and one['loaded_files']['a,b']['data'] == {'comma': True}

    two = utils.files.load_files(str(tmp_path), ['_desc', 'other'])
    assert sorted(two['loaded_files']) == ['_desc', 'other'] and two['loaded_files']['other']['data'] == {'x': 1}
    assert utils.files.load_files(str(tmp_path), '')['loaded_files'] == {}


def test_several_files_on_a_command_line_are_given_one_by_one():
    # --load_files=<name>: text; --load_files+=<name> for each of several: a list, each value whole
    r = utils.cli.parse_cmd(['model', 'find', 'x', '--load_files=_desc'])
    assert r['return'] == 0 and r['params']['load_files'] == '_desc'

    r = utils.cli.parse_cmd(['model', 'find', 'x', '--load_files+=_desc', '--load_files+=a,b'])
    assert r['return'] == 0 and r['params']['load_files'] == ['_desc', 'a,b']


def test_find_loads_a_file_named_as_text(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising = False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    cm = CMeta(home = str(tmp_path))

    r = cm.access({'category': 'config', 'command': 'add', 'arg1': 'local:my-notes', 'con': False})
    assert r['return'] == 0, r
    with open(r['path'] + '/_desc.json', 'w', encoding = 'utf-8') as f:
        json.dump({'note': 'kept'}, f)

    for names in ('_desc', ['_desc']):
        r = cm.access({'category': 'config', 'command': 'find', 'arg1': 'local:my-notes', 'load_files': names, 'con': False})
        assert r['return'] == 0, r
        assert r['artifacts'][0]['loaded_files']['_desc']['data'] == {'note': 'kept'}, names
