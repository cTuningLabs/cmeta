"""
Tests for writing over a YAML file that was written by hand: `safe_write_file(..., preserve=True)` edits
only the top-level keys that changed (`edit_yaml_text`), reads the result back and compares it with the
intended data before the file is replaced, and falls back to a full dump that keeps the order of the keys
and never rewraps a long string. `cx <category> update` and `cx <category> index` use it.

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os

import pytest
import yaml

from cmeta import CMeta
from cmeta.utils import files
from cmeta.utils.files import (YAML_META_KEY_ORDER, edit_yaml_text, order_meta_keys, safe_write_file,
                               write_file, yaml_dump_keep)

UID = '0123456789abcdef'

LONG_NOTE = 'a very long note that PyYAML would fold at eighty columns whenever it dumped the whole file again and again'

TEXT = ('# the header of a hand-written meta\n'
        f'artifact: {UID}\n'
        'authors: Grigori Fursin\n'
        '\n'
        '# what it is for\n'
        'tags:\n'
        '  - a   # the first tag\n'
        '  - b\n'
        f'note: {LONG_NOTE}\n'
        'folded: >\n'
        '  folded text\n'
        '  continues here\n'
        'literal: |\n'
        '  line 1\n'
        '  # not a comment, part of the text\n'
        '\n'
        'quoted: "has: colon # and hash"\n'
        "unicode: 'caf\u00e9 \u2014 \u00fc'\n"
        'flow_tags: [x, y]\n'
        'category: task,c36be4b9314a45e0  # a trailing comment\n')


def loaded(text):
    return yaml.safe_load(text)


def edit(text, data):
    out = edit_yaml_text(text, data)
    assert out is not None
    assert loaded(out) == data, out
    return out


# --- edit_yaml_text: what changes and what stays ---------------------------------------------------

def test_a_new_key_is_appended_and_nothing_else_moves():
    data = dict(loaded(TEXT), last_update_timestamp='2026-10-04T18:00:00+00:00')
    out = edit(TEXT, data)
    assert out == TEXT + "last_update_timestamp: '2026-10-04T18:00:00+00:00'\n"


def test_a_changed_scalar_replaces_only_its_line():
    data = dict(loaded(TEXT), authors='Someone Else')
    out = edit(TEXT, data)
    assert out == TEXT.replace('authors: Grigori Fursin\n', 'authors: Someone Else\n')


def test_a_changed_list_keeps_the_comments_around_it_and_the_indentation_style():
    data = dict(loaded(TEXT), tags=['a', 'b', 'c'])
    out = edit(TEXT, data)
    assert '# what it is for\ntags:\n  - a\n  - b\n  - c\nnote: ' in out
    assert '# the header' in out and '# a trailing comment' in out
    assert 'folded: >\n' in out and 'literal: |\n' in out and 'flow_tags: [x, y]' in out


def test_lists_at_the_key_column_stay_at_the_key_column():
    text = 'tags:\n- a\nx: 1\n'
    assert edit(text, {'tags': ['a', 'b'], 'x': 1}) == 'tags:\n- a\n- b\nx: 1\n'


def test_a_removed_key_disappears_with_its_lines_only():
    data = loaded(TEXT)
    del data['authors']
    out = edit(TEXT, data)
    assert out == TEXT.replace('authors: Grigori Fursin\n', '')


def test_a_changed_nested_mapping_is_rewritten_in_place_and_the_rest_stays():
    text = TEXT + 'nested:\n  a: 1\n  b:\n    - 1\n    - 2\n'
    data = dict(loaded(text), nested={'a': 2, 'b': [1, 2, 3]})
    out = edit(text, data)
    assert out.startswith(TEXT)
    assert out[len(TEXT):] == 'nested:\n  a: 2\n  b:\n    - 1\n    - 2\n    - 3\n'


def test_a_multi_line_string_becomes_a_literal_block():
    data = dict(loaded(TEXT), note='line one\nline two\n')
    out = edit(TEXT, data)
    assert 'note: |\n  line one\n  line two\n' in out


def test_the_long_plain_note_is_never_folded():
    data = dict(loaded(TEXT), note=LONG_NOTE + ' and even longer than before')
    out = edit(TEXT, data)
    assert ('note: ' + LONG_NOTE + ' and even longer than before\n') in out


def test_quoted_and_unicode_values_round_trip():
    data = dict(loaded(TEXT), quoted='now: with # more', unicode='na\u00efve \u2192 \u00e9')
    out = edit(TEXT, data)
    assert 'na\u00efve \u2192 \u00e9' in out          # allow_unicode: written as is, not escaped
    assert "unicode: 'caf\u00e9" not in out


def test_crlf_files_keep_crlf_everywhere():
    crlf = TEXT.replace('\n', '\r\n')
    data = dict(loaded(crlf), tags=['z'], extra='v')
    out = edit(crlf, data)
    assert out.count('\n') == out.count('\r\n')
    assert out.startswith('# the header of a hand-written meta\r\nartifact: ')
    assert out.endswith('extra: v\r\n')


def test_a_byte_order_mark_is_kept_even_when_the_first_key_changes():
    bom = '\ufeff' + TEXT
    data = dict(loaded(bom), artifact='fedcba9876543210')
    out = edit(bom, data)
    assert out.startswith('\ufeff# the header')
    assert 'artifact: fedcba9876543210\n' in out
    assert out.count('\ufeff') == 1


def test_a_file_without_a_final_newline_gets_one_before_the_appended_key():
    data = dict(loaded(TEXT), extra=1)
    assert edit(TEXT.rstrip('\n'), data).endswith('# a trailing comment\nextra: 1\n')


def test_an_empty_value_and_a_timestamp_only_change():
    assert edit('a:\nb: 2\n', {'a': None, 'b': 3}) == 'a:\nb: 3\n'
    text = f'artifact: {UID}\ncreation_timestamp: 2026-10-04T10:00:00+00:00\n'
    data = loaded(text)                                     # the unquoted timestamp loads as a datetime
    data['last_update_timestamp'] = '2026-10-04T18:00:00+00:00'
    out = edit(text, data)
    assert out.startswith(text)


@pytest.mark.parametrize('text', ['{a: 1, b: 2}\n',               # a flow mapping at the top level
                                  'a: &x 1\nb: *x\n',               # anchors and aliases
                                  'a: 1\na: 2\n',                   # duplicate keys
                                  'a: 1\n---\nb: 2\n',              # several documents
                                  '1: x\n',                         # a key that is not a string
                                  '# only a comment\n',             # no mapping at all
                                  'a: [\n'])                        # a parse error
def test_texts_that_cannot_be_edited_safely_give_none(text):
    assert edit_yaml_text(text, {'a': 3}) is None


def test_data_with_non_string_keys_gives_none():
    assert edit_yaml_text('a: 1\n', {1: 2}) is None


def test_yaml_dump_keep_keeps_order_and_long_lines():
    out = yaml_dump_keep({'z': 'x' * 200, 'a': 'line\nline', 'tags': ['t']})
    assert out.splitlines()[0] == 'z: ' + 'x' * 200
    assert out.index('z:') < out.index('a:') < out.index('tags:')
    assert 'a: |-\n  line\n  line\n' in out
    assert yaml_dump_keep({'tags': ['t']}, indent_lists=True) == 'tags:\n  - t\n'


# --- safe_write_file(preserve=True): validation, fallback, atomicity ---------------------------------

def read_text(path):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def write_text(path, text):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def test_preserve_edits_the_file_and_leaves_no_temporary_file(tmp_path):
    path = str(tmp_path / '_cmeta.yaml')
    write_text(path, TEXT)
    data = dict(loaded(TEXT), tags=['a', 'b', 'c'], uses_categories=['tool,c393ba5c6fa14f66'])
    r = safe_write_file(path, data, preserve=True)
    assert r['return'] == 0 and r['method'] == 'edit' and r['validated'] is True
    text = read_text(path)
    assert loaded(text) == data
    assert text.startswith('# the header of a hand-written meta\n')
    assert text.endswith("category: task,c36be4b9314a45e0  # a trailing comment\nuses_categories:\n  - tool,c393ba5c6fa14f66\n")
    assert os.listdir(str(tmp_path)) == ['_cmeta.yaml']


def test_preserve_falls_back_to_a_full_dump_in_the_keep_style_when_the_text_cannot_be_edited(tmp_path):
    path = str(tmp_path / '_cmeta.yaml')
    write_text(path, 'zeta: &x 1\nalpha: *x\nnote: ' + LONG_NOTE + '\n')
    data = {'zeta': 1, 'alpha': 2, 'note': LONG_NOTE}
    r = safe_write_file(path, data, preserve=True)
    assert r['return'] == 0 and r['method'] == 'dump' and r['validated'] is True
    text = read_text(path)
    assert text == 'zeta: 1\nalpha: 2\nnote: ' + LONG_NOTE + '\n'      # order kept, nothing folded


def test_an_edit_that_does_not_load_as_intended_is_dropped_for_the_dump(tmp_path, monkeypatch):
    path = str(tmp_path / '_cmeta.yaml')
    write_text(path, TEXT)
    data = dict(loaded(TEXT), authors='X')

    monkeypatch.setattr(files, 'edit_yaml_text', lambda text, d: 'authors: [\n')           # broken YAML
    r = safe_write_file(path, data, preserve=True)
    assert r['return'] == 0 and r['method'] == 'dump' and r['validated'] is True
    assert loaded(read_text(path)) == data

    write_text(path, TEXT)
    monkeypatch.setattr(files, 'edit_yaml_text', lambda text, d: TEXT.replace('Grigori Fursin', 'Y'))   # valid, wrong
    r = safe_write_file(path, data, preserve=True)
    assert r['return'] == 0 and r['method'] == 'dump' and r['validated'] is True
    assert loaded(read_text(path)) == data
    assert os.listdir(str(tmp_path)) == ['_cmeta.yaml']


def test_a_dump_that_loads_differently_is_still_written_as_before(tmp_path):
    path = str(tmp_path / '_cmeta.yaml')
    write_text(path, 'a: 1\n')
    r = safe_write_file(path, {'a': 1, 'pair': (1, 2)}, preserve=True)      # a tuple loads back as a list
    assert r['return'] == 0 and r['method'] == 'dump' and r['validated'] is False
    assert loaded(read_text(path)) == {'a': 1, 'pair': [1, 2]}


def test_crlf_and_bom_survive_the_fallback_dump(tmp_path):
    path = str(tmp_path / '_cmeta.yaml')
    write_text(path, '\ufeffa: &x 1\r\nb: *x\r\n')
    r = safe_write_file(path, {'a': 1, 'b': 2}, preserve=True)
    assert r['return'] == 0 and r['method'] == 'dump'
    assert read_text(path) == '\ufeffa: 1\r\nb: 2\r\n'


def test_without_preserve_the_old_dump_is_written(tmp_path):
    path = str(tmp_path / '_cmeta.yaml')
    write_text(path, TEXT)
    data = loaded(TEXT)
    r = safe_write_file(path, data)
    assert r['return'] == 0 and 'method' not in r
    assert read_text(path) == yaml.safe_dump(data, sort_keys=True)          # the old style: sorted, folded


def test_preserve_on_a_file_that_does_not_exist_writes_the_keep_style(tmp_path):
    data = loaded(TEXT)
    new_path = str(tmp_path / 'new.yaml')
    r = safe_write_file(new_path, data, preserve=True)
    assert r['return'] == 0 and 'method' not in r
    assert read_text(new_path) == yaml_dump_keep(order_meta_keys(data), indent_lists=True)
    assert loaded(read_text(new_path)) == data


# --- new files: the keep style with the key order of a new meta -------------------------------------

def test_order_meta_keys_puts_the_known_keys_first_and_the_rest_as_given():
    data = {'zeta': 1, 'note': 'n', 'creation_timestamp': 't', 'category': 'c', 'alpha': 2, 'tags': ['t'],
            'artifact': UID, 'authors': 'a', 'uses_categories': {'tool': 'tool,1'}, 'last_generator': {'agent': 'x'}}
    out = order_meta_keys(data)
    assert list(out) == ['artifact', 'category', 'tags', 'note', 'authors', 'creation_timestamp', 'last_generator',
                         'uses_categories', 'zeta', 'alpha']
    assert out == data and out is not data                                  # a copy, same content
    assert order_meta_keys(['not', 'a', 'dict']) == ['not', 'a', 'dict']
    assert YAML_META_KEY_ORDER[:3] == ('artifact', 'alias', 'category')
    assert len(set(YAML_META_KEY_ORDER)) == len(YAML_META_KEY_ORDER)          # no key twice


def test_write_file_keep_writes_a_new_meta_in_the_keep_style(tmp_path):
    path = str(tmp_path / '_cmeta.yaml')
    data = {'note': LONG_NOTE, 'tags': ['b', 'a'], 'artifact': UID, 'text': 'line 1\nline 2', 'desc': 'café — ü',
            'zeta': {'k': 'v', 'list': [1, 2]}, 'category': 'task,c36be4b9314a45e0', 'authors': 'Grigori Fursin'}
    r = write_file(path, data, keep=True)
    assert r['return'] == 0, r.get('error')
    text = read_text(path)
    assert text == ('artifact: ' + UID + '\n'
                    'category: task,c36be4b9314a45e0\n'
                    'tags:\n  - b\n  - a\n'
                    'desc: café — ü\n'
                    'note: ' + LONG_NOTE + '\n'
                    'authors: Grigori Fursin\n'
                    'text: |-\n  line 1\n  line 2\n'
                    'zeta:\n  k: v\n  list:\n    - 1\n    - 2\n')
    assert loaded(text) == data
    # without keep: the old sorted, folded dump
    r = write_file(path, data)
    assert r['return'] == 0 and read_text(path) == yaml.safe_dump(data, sort_keys=True)


def test_keep_leaves_json_sorted_as_before(tmp_path):
    path = str(tmp_path / '_cmeta.json')
    data = {'zeta': 1, 'artifact': UID}
    r = safe_write_file(path, data, keep=True)
    assert r['return'] == 0 and 'method' not in r
    assert read_text(path) == json.dumps(data, indent=2, sort_keys=True) + '\n'


def test_json_files_are_written_as_before(tmp_path):
    path = str(tmp_path / '_cmeta.json')
    write_text(path, '{"b": 1, "a": 2}')
    r = safe_write_file(path, {'b': 1, 'a': 3}, preserve=True)
    assert r['return'] == 0 and 'method' not in r
    assert read_text(path) == json.dumps({'a': 3, 'b': 1}, indent=2, sort_keys=True) + '\n'


# --- end to end: cx <category> index / update on a scratch CMETA_HOME --------------------------------

@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_GENERATOR', 'CMETA_AUTHORS', 'CMETA_COPYRIGHT'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def hand_made(cm, tmp_path, name, text):
    # The index exists first (the first access builds it), then the folder is made by hand
    cm.access({'category': 'log', 'command': 'find', 'arg1': 'nothing-yet', 'con': False})
    folder = tmp_path / 'repos' / 'local' / 'log' / name
    folder.mkdir(parents=True)
    path = str(folder / '_cmeta.yaml')
    write_text(path, text)
    return path


def category_of_log(cm, tmp_path):
    path = hand_made(cm, tmp_path, 'probe', f'artifact: fedcba9876543210\n')
    r = cm.access({'category': 'log', 'command': 'index', 'arg1': 'local:probe', 'con': False})
    assert r['return'] == 0, r.get('error')
    return r['meta']['category']


def test_index_leaves_a_complete_hand_made_meta_byte_identical(cm, tmp_path):
    category = category_of_log(cm, tmp_path)
    text = TEXT.replace('category: task,c36be4b9314a45e0', f'category: {category}')
    path = hand_made(cm, tmp_path, 'complete', text)
    r = cm.access({'category': 'log', 'command': 'index', 'arg1': 'local:complete', 'con': False})
    assert r['return'] == 0, r.get('error')
    assert read_text(path) == text                      # no timestamp, no generator, nothing rewrapped
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': f'complete,{UID}', 'con': False})
    assert r['return'] == 0 and len(r['artifacts']) == 1


def test_index_adds_only_what_the_meta_lacks(cm, tmp_path):
    category = category_of_log(cm, tmp_path)
    text = f'# made by hand\nartifact: {UID}\ntags:\n  - hand-made   # keep me\n'
    path = hand_made(cm, tmp_path, 'partial', text)
    r = cm.access({'category': 'log', 'command': 'index', 'arg1': 'local:partial', 'tags': 'indexed', 'con': False})
    assert r['return'] == 0, r.get('error')
    new = read_text(path)
    assert new.startswith('# made by hand\n' + f'artifact: {UID}\n')
    assert loaded(new) == {'artifact': UID, 'tags': ['hand-made', 'indexed'], 'category': category}
    assert new.endswith(f'category: {category}\n')


def test_update_edits_a_hand_made_yaml_in_place(cm, tmp_path):
    category = category_of_log(cm, tmp_path)
    text = TEXT.replace('category: task,c36be4b9314a45e0', f'category: {category}')
    path = hand_made(cm, tmp_path, 'edited', text)
    r = cm.access({'category': 'log', 'command': 'index', 'arg1': 'local:edited', 'con': False})
    assert r['return'] == 0, r.get('error')

    r = cm.access({'category': 'log', 'command': 'update', 'arg1': 'local:edited',
                   'meta': {'uses_categories': ['tool,c393ba5c6fa14f66'], 'authors': 'Someone Else'},
                   'new_tags': 'c', 'con': False})
    assert r['return'] == 0, r.get('error')

    new = read_text(path)
    # the header, the comments, the folded and literal scalars, the quoting and the long line are untouched
    for kept in ('# the header of a hand-written meta\n', '# what it is for\n', 'folded: >\n  folded text\n',
                 'literal: |\n  line 1\n  # not a comment', 'quoted: "has: colon # and hash"\n',
                 "unicode: 'caf\u00e9 \u2014 \u00fc'\n", 'flow_tags: [x, y]\n', f'note: {LONG_NOTE}\n',
                 '# a trailing comment\n'):
        assert kept in new, kept
    assert 'authors: Someone Else\n' in new and 'Grigori Fursin' not in new
    assert 'tags:\n  - a\n  - b\n  - c\n' in new                      # the list changed: rewritten, indented as before
    assert 'uses_categories:\n  - tool,c393ba5c6fa14f66\n' in new    # appended at the end
    meta = loaded(new)
    assert meta['tags'] == ['a', 'b', 'c'] and 'creation_timestamp' in meta
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': f'edited,{UID}', 'con': False})
    assert r['return'] == 0 and r['artifacts'][0]['cmeta'] == meta        # the index holds what the file holds


def test_add_writes_a_new_yaml_meta_in_the_keep_style(cm, tmp_path):
    r = cm.access({'category': 'log', 'command': 'add', 'arg1': 'local:fresh', 'yaml': True, 'tags': 'x,y',
                   'meta': {'zeta': {'k': 'v'}, 'note': LONG_NOTE, 'desc': 'café — ü'}, 'con': False})
    assert r['return'] == 0, r.get('error')
    path = os.path.join(r['path'], '_cmeta.yaml')
    text = read_text(path)
    meta = loaded(text)
    assert meta == r['meta'] and meta['tags'] == ['x', 'y'] and 'creation_timestamp' in meta
    keys = list(meta)                                                  # the order of the file
    assert keys[:2] == ['artifact', 'category'] and keys.index('tags') < keys.index('desc') < keys.index('note')
    assert keys.index('note') < keys.index('creation_timestamp') < keys.index('zeta')   # bookkeeping, then the rest
    assert 'tags:\n  - x\n  - y\n' in text                              # lists indented under their key
    assert f'note: {LONG_NOTE}\n' in text                               # a long line is not folded
    assert 'desc: café — ü\n' in text                    # unicode as it is
    assert text == yaml_dump_keep(order_meta_keys(meta), indent_lists=True)
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'local:fresh', 'con': False})
    assert r['return'] == 0 and r['artifacts'][0]['cmeta'] == meta        # the index holds what the file holds


def test_add_of_a_json_meta_is_sorted_as_before(cm, tmp_path):
    r = cm.access({'category': 'log', 'command': 'add', 'arg1': 'local:fresh-json', 'meta': {'zeta': 1, 'alpha': 2}, 'con': False})
    assert r['return'] == 0, r.get('error')
    path = os.path.join(r['path'], '_cmeta.json')
    assert read_text(path) == json.dumps(r['meta'], indent=2, sort_keys=True) + '\n'


def test_update_of_a_json_meta_stays_json(cm, tmp_path):
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'local:as-json', 'meta': {'x': 1}, 'con': False})
    assert r['return'] == 0, r.get('error')
    path = os.path.join(r['path'], '_cmeta.json')
    r = cm.access({'category': 'log', 'command': 'update', 'arg1': 'local:as-json', 'meta': {'x': 2}, 'con': False})
    assert r['return'] == 0, r.get('error')
    assert os.path.isfile(path) and not os.path.isfile(os.path.join(os.path.dirname(path), '_cmeta.yaml'))
    with open(path, encoding='utf-8') as f:
        assert json.load(f)['x'] == 2
