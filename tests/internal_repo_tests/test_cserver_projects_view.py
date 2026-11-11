"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

The customized view of cserver.projects (2026-11-10): sections of buttons with names of one's own, each button an
artifact of cserver.projects whose _desc.yaml holds title, page or url, section, order and note. Made once from
the pages of this machine (a section per repository, a button per page) in the repository chosen; changed through
the page's actions - a button added or changed, moved, a section moved or renamed (into another one: joined),
orders set back (Undo), a button deleted and put back -; a page the view names that this machine does not have is
marked, the pages it does not name are listed; only a browser on this machine or past the password, from a page
of this server, may change it. Each test runs in a fresh CMETA_HOME.
"""

import os

import pytest
import yaml

from cmeta import CMeta

URLS = {'url': 'http://127.0.0.1:8004/projects?', 'url_files': 'http://127.0.0.1:8004/projects/',
        'url_server': 'http://127.0.0.1:8004/'}
LOCAL = {'client_local': True, 'same_origin': True}

PAGE_API = '''from cmeta.category import InitCategory


class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    def web_(self, ctx, urls, query={}, misc={}):
        return {'return': 0, 'html_meta': {'html': '<p>hello</p>'}}
'''


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    """A fresh CMeta bound to a temp CMETA_HOME, with a second repository "mine" holding a page cserver.hello."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    cm = CMeta(home=str(tmp_path))
    r = cm.access({'category': 'repo', 'command': 'create', 'arg1': 'mine', 'con': False})
    assert r['return'] == 0, r
    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'mine:cserver.hello', 'con': False,
                   'meta': {'name': 'Hello - a page of my own'}})
    assert r['return'] == 0, r
    with open(os.path.join(r['path'], 'api', 'v1.py'), 'w', encoding='utf-8') as f:
        f.write(PAGE_API)
    return cm


def act(cm, na, misc=None, **query):
    r = cm.access({'category': 'cserver.projects', 'command': 'web', 'con': False, 'urls': dict(URLS),
                   'misc': dict(LOCAL if misc is None else misc), 'query': dict(query, native_action=na)})
    assert r['return'] == 0, r
    return r['json']


def ok(out):
    assert 'error' not in out, out
    return out


def view(cm):
    return ok(act(cm, 'view'))


def by_title(v):
    return {b['title']: b for b in v['buttons']}


def made(cm, repo='mine'):
    ok(act(cm, 'view_make', repo=repo))
    return view(cm)


def test_no_view_yet_lists_the_pages_and_where_one_may_be_kept(cm):
    v = view(cm)
    assert v['buttons'] == [] and v['sections'] == [] and v['home'] == ''
    assert [p['page'] for p in v['loose']] == ['browse', 'cmeta.configs', 'settings', 'hello']   # not the page itself, not cref
    assert v['repos'] == ['local', 'mine'] and v['default_repo'] == 'local' and v['edit'] is True
    # every page of this machine with its card's heading (the form offers them)
    assert v['pages'] == [{'page': 'browse', 'title': 'cMeta browse'}, {'page': 'cmeta.configs', 'title': 'cMeta configs'},
                          {'page': 'settings', 'title': 'Settings'}, {'page': 'hello', 'title': 'Hello'}]


def test_the_view_is_made_from_this_machines_pages(cm):
    v = made(cm)
    assert [(b['section'], b['title'], b['page'], b['order'], b['repo']) for b in v['buttons']] == [
        ('internal', 'cMeta browse', 'browse', 10, 'mine'),
        ('internal', 'cMeta configs', 'cmeta.configs', 20, 'mine'),
        ('internal', 'Settings', 'settings', 30, 'mine'),
        ('mine', 'Hello', 'hello', 40, 'mine')]
    assert v['sections'] == ['internal', 'mine'] and v['home'] == 'mine' and v['loose'] == []
    assert all(b['href'] == URLS['url_server'] + b['page'] and b['missing'] is False for b in v['buttons'])
    # one artifact per button, its _desc.yaml in the order of its keys, a generator record
    arts = cm.access({'category': 'cserver.projects', 'command': 'find', 'arg1': 'Hello', 'con': False})['artifacts']
    with open(os.path.join(arts[0]['path'], '_desc.yaml'), encoding='utf-8') as f:
        text = f.read()
    assert list(yaml.safe_load(text)) == ['title', 'page', 'section', 'order']
    assert arts[0]['cmeta']['generator']['via'].startswith('cserver.projects')
    # made once: a second time is refused
    assert 'already' in act(cm, 'view_make', repo='mine')['error']


def test_the_engine_repository_keeps_no_view(cm):
    assert 'engine' in act(cm, 'view_make', repo='internal')['error']
    assert view(cm)['buttons'] == []


def test_buttons_added_changed_and_where_they_go(cm):
    v = made(cm)
    browse = by_title(v)['cMeta browse']
    # an address of another machine, a new section at the end; with no title: the site's name
    gh = ok(act(cm, 'view_save', url='https://github.com/cTuningLabs/cmeta', section='Links'))
    assert gh['created'] and gh['button']['title'] == 'Github' and gh['button']['repo'] == 'mine'   # where the view is
    # a page with a query, before a button (into its section); its title: the heading of its card
    mon = ok(act(cm, 'view_save', page='/hello?x=1', before=browse['uid']))['button']
    assert (mon['title'], mon['section'], mon['page']) == ('Hello', 'internal', 'hello?x=1')
    v = view(cm)
    assert [b['title'] for b in v['buttons'] if b['section'] == 'internal'] == ['Hello', 'cMeta browse', 'cMeta configs', 'Settings']
    # what is never kept
    assert 'never kept' in act(cm, 'view_save', url='javascript:alert(1)', section='x')['error']
    assert 'not the name of a page' in act(cm, 'view_save', page='http://x', section='x')['error']
    assert 'section' in act(cm, 'view_save', page='browse')['error']
    # a change: only what is given; a new section puts it at that section's end
    ch = ok(act(cm, 'view_save', uid=gh['button']['uid'], title='cMeta on GitHub', note='the engine'))
    assert ch['changed'] and ch['old']['title'] == 'Github'
    mv = ok(act(cm, 'view_save', uid=browse['uid'], section='mine'))
    assert mv['button']['section'] == 'mine'
    assert [b['title'] for b in view(cm)['buttons'] if b['section'] == 'mine'] == ['Hello', 'cMeta browse']
    # Important: a filled button, kept in its _desc.yaml as star: true (Undo gives the old value back)
    st = ok(act(cm, 'view_save', uid=browse['uid'], star='yes'))
    assert st['changed'] and st['old']['star'] is False and by_title(view(cm))['cMeta browse']['star'] is True
    arts = cm.access({'category': 'cserver.projects', 'command': 'find', 'arg1': browse['uid'], 'con': False})['artifacts']
    with open(os.path.join(arts[0]['path'], '_desc.yaml'), encoding='utf-8') as f:
        assert yaml.safe_load(f)['star'] is True
    ok(act(cm, 'view_save', uid=browse['uid'], star='no'))
    with open(os.path.join(arts[0]['path'], '_desc.yaml'), encoding='utf-8') as f:
        assert 'star' not in yaml.safe_load(f)                     # an empty key leaves the file
    # an address instead of a page, and back (Undo gives page or url back)
    ok(act(cm, 'view_save', uid=browse['uid'], url='http://other-machine:8004/browse'))
    b = by_title(view(cm))['cMeta browse']
    assert (b['page'], b['url'], b['href']) == ('', 'http://other-machine:8004/browse', 'http://other-machine:8004/browse')
    ok(act(cm, 'view_save', uid=browse['uid'], page='browse'))
    assert by_title(view(cm))['cMeta browse']['url'] == ''


def test_moves_renames_and_undo(cm):
    v = made(cm)
    t = by_title(v)
    a = ok(act(cm, 'view_arrange', uid=t['Hello']['uid'], before=t['cMeta browse']['uid']))
    assert [b['title'] for b in view(cm)['buttons']] == ['Hello', 'cMeta browse', 'cMeta configs', 'Settings']
    assert view(cm)['sections'] == ['internal']                       # "mine" was its only button
    ok(act(cm, 'view_arrange', orders=a['undo']))
    assert [b['title'] for b in view(cm)['buttons']] == ['cMeta browse', 'cMeta configs', 'Settings', 'Hello']
    # a section moved before another, renamed, renamed into another one (joined: its buttons at that one's end)
    ok(act(cm, 'view_arrange', move_section='mine', before_section='internal'))
    assert view(cm)['sections'] == ['mine', 'internal']
    r = ok(act(cm, 'view_arrange', section='internal', rename='cMeta'))
    assert view(cm)['sections'] == ['mine', 'cMeta'] and len(r['changed']) == 3
    ok(act(cm, 'view_arrange', section='mine', rename='cmeta'))           # a case apart: the existing name
    v = view(cm)
    assert v['sections'] == ['cMeta'] and [b['title'] for b in v['buttons']] == ['cMeta browse', 'cMeta configs', 'Settings', 'Hello']
    # a button to the end of a section by its name alone
    ok(act(cm, 'view_arrange', uid=t['cMeta browse']['uid'], section='Later'))
    assert view(cm)['sections'] == ['cMeta', 'Later']
    assert 'what to arrange' in act(cm, 'view_arrange')['error']


def test_a_button_deleted_and_put_back(cm):
    v = made(cm)
    hello = by_title(v)['Hello']
    ok(act(cm, 'view_save', uid=hello['uid'], star=True))
    d = ok(act(cm, 'view_discard', uid=hello['uid']))
    v = view(cm)
    assert 'Hello' not in by_title(v) and [p['page'] for p in v['loose']] == ['hello']   # listed as not in the view
    back = ok(act(cm, 'view_restore', removed=d['removed']))['button']
    assert (back['uid'], back['alias'], back['section'], back['order'], back['repo'], back['star']) == \
        (hello['uid'], hello['alias'], 'mine', 40, 'mine', True)
    assert 'already' in act(cm, 'view_restore', removed=d['removed'])['error']


def test_pages_this_machine_does_not_have_and_hidden_repositories(cm):
    made(cm)
    ok(act(cm, 'view_save', page='monitor?watch=x', section='Elsewhere'))
    b = by_title(view(cm))['monitor']
    assert b['missing'] is True and b['href'] == URLS['url_server'] + 'monitor?watch=x'
    # a page of this machine the view does not name is listed - unless its repository is hidden from the cards
    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'mine:cserver.extra', 'con': False})
    with open(os.path.join(r['path'], 'api', 'v1.py'), 'w', encoding='utf-8') as f:
        f.write(PAGE_API)
    assert [p['page'] for p in view(cm)['loose']] == ['extra']
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'meta': {'hide_repos': 'mine'}, 'con': False})
    assert r['return'] == 0, r
    assert view(cm)['loose'] == []


def test_who_may_change_the_view(cm):
    assert 'own machine' in act(cm, 'view_make', misc={}, repo='mine')['error']                    # neither local nor gated
    assert 'page of this server' in act(cm, 'view_make', misc={'client_local': True}, repo='mine')['error']
    assert 'cMeta server' in act(cm, 'view_make', misc={'ctuning_server': True, 'client_local': True, 'same_origin': True},
                                 repo='mine')['error']
    gated = {'password_gate': True, 'same_origin': True}
    assert ok(act(cm, 'view_make', misc=gated, repo='mine'))['made'] == 4                          # past the password
    assert act(cm, 'view', misc={})['edit'] is False                                               # read: anyone
    page = cm.access({'category': 'cserver.projects', 'command': 'web', 'con': False, 'urls': dict(URLS),
                      'misc': {}, 'query': {}})['html_meta']['html']
    assert 'id="cpj-custom"' in page and '"edit": false' in page


def test_the_terminal_lists_the_view(cm, capsys):
    made(cm)
    r = cm.access({'category': 'cserver.projects', 'command': 'view', 'con': True})
    assert r['return'] == 0 and len(r['buttons']) == 4
    out = capsys.readouterr().out
    assert 'internal' in out and '/hello' in out and '4 buttons in 2 sections, kept in mine' in out
