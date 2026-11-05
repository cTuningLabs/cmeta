"""
Dated aliases (2026-11-05): the date in front of an alias is asked for with -dt, never added behind one's back.
`add`, `get` and `set` of every category take `dt` (True: today's date in front, 20261105.<alias>; a text: that
date; the date alone names an artifact given no alias) and add nothing to an alias that starts with a date. A
category whose meta says `dated_aliases: true` (the engine's work, note, journal, experiment, research) warns about
a new alias without a date and keeps the alias as given. `<category>_create_repo` of the default config names the
repository a category's new artifacts go to when the request names none - for add, get and set alike. The create
the dated categories called until 0.38.8, `utils create_artifact_with_date`, still serves a category of an older
repository whose `create` calls it. Each test runs in a fresh CMETA_HOME.
"""

import os
from datetime import datetime

import pytest
import yaml

from cmeta import CMeta


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    """A fresh CMeta bound to a temp CMETA_HOME."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def today():
    return datetime.now().strftime('%Y%m%d')


def call(cm, category, command, arg1=None, **params):
    r = cm.access({'category': category, 'command': command, 'arg1': arg1, 'con': False, **params})
    assert r['return'] == 0, r
    return r


def path_of(r):
    """The folder an add (path) or a get / set (artifact) answered with."""
    return r.get('path') or r['artifact']['path']


def name_of(r):
    return os.path.basename(path_of(r).rstrip('\\/'))


def repo_of(cm, r):
    """The alias of the repository the artifact was made in."""
    path = os.path.normcase(os.path.abspath(path_of(r)))
    for a in call(cm, 'repo', 'find', '*')['artifacts']:
        root = os.path.normcase(os.path.abspath(a['path']))
        if path.startswith(root + os.sep):
            return a['cmeta_ref_parts']['artifact_alias']
    raise AssertionError(path)


def desc_of(path):
    with open(os.path.join(path, '_desc.yaml'), encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# the warning of a dated category, -dt in any category
# ---------------------------------------------------------------------------

def test_a_dated_category_keeps_the_alias_and_warns(cm):
    r = call(cm, 'work', 'add', 'a note')
    assert name_of(r) == 'a note'
    assert len(r['warnings']) == 1 and r['warnings'][0].startswith('cMeta warning: a work alias starts with its date')
    assert '"a note" has none' in r['warnings'][0] and '-dt' in r['warnings'][0]
    r = call(cm, 'work', 'add')                                     # no alias: named by its UID, the warning says so
    assert name_of(r) == r['meta']['artifact'] and 'none was given' in r['warnings'][0]
    r = call(cm, 'config', 'add', 'a config')                       # not a dated category: no warning
    assert name_of(r) == 'a config' and r['warnings'] == []


def test_dt_puts_todays_date_in_front_in_any_category(cm):
    assert name_of(call(cm, 'work', 'add', 'a note', dt=True)) == today() + '.a note'
    assert name_of(call(cm, 'config', 'add', 'a config', dt=True)) == today() + '.a config'
    r = call(cm, 'work', 'add', dt=True)                            # no alias: the date alone
    assert name_of(r) == today() and r['warnings'] == []
    assert name_of(call(cm, 'work', 'add', 'local:in a repo', dt=True)) == today() + '.in a repo'


@pytest.mark.parametrize('alias', ['20261001.x', '2026-10-01.x', '202610.x', '2026.x', '202604xx.x', '2026xxxx.x',
                                   '198xxxxx.x', '2020-2022.x', '20261001-1430.x', '20261001'])
def test_nothing_is_added_to_an_alias_that_starts_with_a_date(cm, alias):
    r = call(cm, 'work', 'add', alias, dt=True)
    assert name_of(r) == alias and r['warnings'] == []
    r = call(cm, 'note', 'add', alias)                              # and a dated category does not warn about it
    assert name_of(r) == alias and r['warnings'] == []


def test_a_given_date_in_front(cm):
    assert name_of(call(cm, 'work', 'add', 'x', dt='20261001')) == '20261001.x'
    assert name_of(call(cm, 'work', 'add', 'y', dt='202610')) == '202610.y'
    assert name_of(call(cm, 'work', 'add', 'z', dt='2026-10-01')) == '2026-10-01.z'
    assert name_of(call(cm, 'work', 'add', dt='20261001')) == '20261001'
    for bad in ('yesterday', '20261001 x', '20261301', '2026-10'):
        r = cm.access({'category': 'work', 'command': 'add', 'arg1': 'w', 'con': False, 'dt': bad})
        assert r['return'] == 1 and 'is not a date' in r['error'], bad
    assert cm.access({'category': 'work', 'command': 'find', 'arg1': 'w', 'con': False})['return'] == 16   # nothing made


def test_a_warning_is_printed_but_not_under_quiet(cm, capsys):
    cm.access({'category': 'work', 'command': 'add', 'arg1': 'loud', 'con': True})
    out = capsys.readouterr().out
    assert 'rtifact was created in' in out and 'cMeta warning: a work alias starts with its date' in out
    cm.access({'category': 'work', 'command': 'add', 'arg1': 'quiet', 'con': True, 'quiet': True})
    assert 'cMeta warning' not in capsys.readouterr().out
    r = call(cm, 'work', 'add', 'silent')                           # con False: in the answer only
    assert len(r['warnings']) == 1 and 'cMeta warning' not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# get and set: one name whether it exists or not
# ---------------------------------------------------------------------------

def test_get_reads_or_makes_the_same_dated_alias(cm):
    r = call(cm, 'work', 'get', 'a note', dt=True)
    assert r['created'] is True and name_of(r) == today() + '.a note' and r['warnings'] == []
    path = path_of(r)
    r = call(cm, 'work', 'get', 'a note', dt=True)                  # again: read, not made
    assert r['created'] is False and path_of(r) == path and r['warnings'] == []
    r = call(cm, 'work', 'get', today() + '.a note')                # by its full name
    assert r['created'] is False and path_of(r) == path
    r = call(cm, 'work', 'get', 'a plain note')                     # no -dt: made as given, with the warning
    assert r['created'] is True and name_of(r) == 'a plain note' and len(r['warnings']) == 1
    r = call(cm, 'work', 'get', 'a plain note')                     # it exists: no warning
    assert r['created'] is False and r['warnings'] == []
    r = call(cm, 'work', 'get', dt=True)                            # no alias: today's date names it
    assert name_of(r) == today() and call(cm, 'work', 'get', dt=True)['created'] is False


def test_set_takes_dt_too(cm):
    r = call(cm, 'work', 'set', 'b', dt=True, meta={'x': 1})
    assert r['created'] is True and name_of(r) == today() + '.b' and r['cmeta']['x'] == 1 and r['warnings'] == []
    r = call(cm, 'work', 'set', 'b', dt=True, meta={'y': 2})
    assert r['created'] is False and r['cmeta']['x'] == 1 and r['cmeta']['y'] == 2 and r['warnings'] == []
    r = call(cm, 'work', 'set', 'c', meta={'x': 1})
    assert r['created'] is True and name_of(r) == 'c' and len(r['warnings']) == 1


# ---------------------------------------------------------------------------
# the repository of the default config
# ---------------------------------------------------------------------------

def test_the_default_config_names_the_repository_of_new_artifacts(cm):
    call(cm, 'repo', 'create', 'private')
    call(cm, 'config', 'set', 'default', meta={'work_create_repo': 'private', 'my_cat_create_repo': 'private'})
    call(cm, 'category', 'add', 'local:my.cat')

    assert repo_of(cm, call(cm, 'work', 'add', 'c', dt=True)) == 'private'
    assert repo_of(cm, call(cm, 'work', 'get', 'd', dt=True)) == 'private'       # add, get and set: one repository
    assert repo_of(cm, call(cm, 'work', 'set', 'e', dt=True)) == 'private'
    assert repo_of(cm, call(cm, 'work', 'add', 'local:f', dt=True)) == 'local'  # the request's repository wins
    assert repo_of(cm, call(cm, 'note', 'add', 'g', dt=True)) == 'local'        # no note_create_repo: local
    assert repo_of(cm, call(cm, 'my.cat', 'add', 'h')) == 'private'             # the dots of an alias as "_"
    r = call(cm, 'work', 'get', 'd', dt=True)                                   # found where it is
    assert r['created'] is False and repo_of(cm, r) == 'private'

    # a repository the config names and that is not plugged: the error says so, nothing is made elsewhere
    call(cm, 'config', 'set', 'default', meta={'work_create_repo': 'nowhere'})
    r = cm.access({'category': 'work', 'command': 'add', 'arg1': 'i', 'con': False, 'dt': True})
    assert r['return'] > 0 and 'nowhere' in r['error']
    assert cm.access({'category': 'work', 'command': 'find', 'arg1': '*.i', 'con': False})['return'] == 16


# ---------------------------------------------------------------------------
# the options of _desc.yaml, an older category, the shipped categories
# ---------------------------------------------------------------------------

def test_the_options_of_desc_go_with_dt(cm):
    call(cm, 'config', 'add', 'ctx', meta={'template': {'ai_uses': {'alias': 'ctx', 'title': 'C'}}})
    other = call(cm, 'config', 'add', 'other')
    r = call(cm, 'work', 'add', 'w', dt=True, ai='ctx', connect='other')
    desc = desc_of(r['path'])
    assert len(desc['ai_uses']) == 1 and [c.split(',')[-1] for c in desc['connections']] == [other['meta']['artifact']]
    assert r['desc_changes']
    r = call(cm, 'work', 'get', 'v', dt=True, ai='ctx')
    assert r['created'] is True and len(desc_of(path_of(r))['ai_uses']) == 1


OLD_CREATE = '''from cmeta.category import InitCategory

class Category(InitCategory):
    """A category written for cMeta 0.38.8 and before: its own create calls utils create_artifact_with_date."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)

    def create(self, params):
        p = self._prepare_input_from_params(params, base = False)
        p['from_category'] = p['category']
        p['category'] = 'utils,234ce5e3262e4d52'
        p['command'] = 'create_artifact_with_date'
        return self.cm.access(p)
'''


def test_an_older_category_whose_create_calls_utils_create_artifact_with_date(cm):
    r = call(cm, 'category', 'add', 'local:old.dated')
    with open(os.path.join(path_of(r), 'api', 'v1.py'), 'w', encoding='utf-8') as f:
        f.write(OLD_CREATE)

    r = call(cm, 'old.dated', 'add', 'x')                           # dated as before, the answer of get as before
    assert name_of(r) == today() + '.x' and r['created'] is True and r['warnings'] == []
    assert r['artifact']['cmeta']['category'].startswith('old.dated')
    r = call(cm, 'old.dated', 'add', 'x')                           # as before: the one that exists
    assert name_of(r) == today() + '.x' and r['created'] is False
    assert name_of(call(cm, 'old.dated', 'add', '20200101.y')) == '20200101.y'
    assert name_of(call(cm, 'old.dated', 'add', '202604xx.z')) == '202604xx.z'
    assert name_of(call(cm, 'old.dated', 'add')) == today()


def test_the_shipped_dated_categories_declare_it(cm):
    for alias in ('work', 'note', 'journal', 'experiment', 'research'):
        meta = call(cm, 'category', 'find', alias)['artifacts'][0]['cmeta']
        assert meta.get('dated_aliases') is True and 'uses_categories' not in meta, alias
    for alias in ('log', 'config', 'script'):
        assert not call(cm, 'category', 'find', alias)['artifacts'][0]['cmeta'].get('dated_aliases'), alias
