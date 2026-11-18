"""
Integration tests for the sensitivity scope of one call: `clearance`, `allow_repos` and `write_repos` in
CMeta.access, beside `hide_repos`.

A repository declares its label with `sensitivity:` in its _cmr.yaml - public, general, confidential,
highly-confidential (or a synonym: internal, private, conf, conf-high, restricted) -, an artifact may raise its own
with `sensitivity:` in its _cmeta. A call with a clearance does not find, list or read what is labelled above it;
`personal` and any word that is no label are above the four clearances and are read by a named grant (allow_repos)
or by the clearance personal - the server owner's, which reads everything; a repository without a label is public. A call writes (create, update, delete, move, copy, a connection)
only into the repositories its write scope names, never into a hidden one, never lowering a label under a
clearance; a nested call only narrows. Without any of the keys everything works as before.

Each test runs against a fresh <CMETA_HOME> in tmp_path with repositories of its own, one per label.

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import subprocess
import sys
import time

import pytest
import yaml

from cmeta import CMeta
from cmeta.repos import clearance_rank, scope_for, sensitivity_label, sensitivity_rank, SENSITIVITY_LEVELS

URLS = {'url': 'http://127.0.0.1:8004/browse?', 'url_files': 'http://127.0.0.1:8004/browse/',
        'url_server': 'http://127.0.0.1:8004/'}

# the repositories of a test home: alias -> the label written into its _cmr.yaml (None: no label at all)
REPOS = {'pub-repo': 'public', 'gen-repo': 'general', 'conf-repo': 'confidential', 'hc-repo': 'highly-confidential',
         'plain-repo': None, 'syn-repo': 'Restricted', 'odd-repo': 'secret', 'mine-repo': 'personal'}

# the artifacts (of the log category): alias -> (repository, the artifact's own label or None)
NOTES = {'pub-note': ('pub-repo', None), 'gen-note': ('gen-repo', None), 'conf-note': ('conf-repo', None),
         'hc-note': ('hc-repo', None), 'plain-note': ('plain-repo', None), 'syn-note': ('syn-repo', None),
         'odd-note': ('odd-repo', None), 'mine-note': ('mine-repo', None),
         'hc-marked': ('conf-repo', 'highly-confidential'),          # raised above its repository
         'internal-marked': ('pub-repo', 'internal'),                # raised, by a synonym
         'conf-again': ('conf-repo', 'confidential'),                # only repeats its repository's label
         'mine-marked': ('gen-repo', 'personal')}                    # raised above every clearance

ALL = sorted(NOTES)
AT_GENERAL = ['gen-note', 'internal-marked', 'plain-note', 'pub-note']
AT_CONFIDENTIAL = sorted(AT_GENERAL + ['conf-again', 'conf-note'])
AT_HIGHEST = sorted(AT_CONFIDENTIAL + ['hc-marked', 'hc-note', 'syn-note'])


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    cm = CMeta(home=str(tmp_path))

    for alias, label in REPOS.items():
        request = {'category': 'repo', 'command': 'create', 'arg1': alias, 'con': False}
        if label is not None:
            request['meta'] = {'sensitivity': label}
        r = cm.access(request)
        assert r['return'] == 0, r
        cmr = (tmp_path / 'repos' / alias / '_cmr.yaml').read_text(encoding='utf-8')
        assert (('sensitivity: ' + label) in cmr) if label is not None else ('sensitivity' not in cmr), cmr

    for alias, (repo, own) in NOTES.items():
        request = {'category': 'log', 'command': 'create', 'arg1': '%s:%s' % (repo, alias), 'con': False,
                   'meta': {'tags': ['note']}}
        if own is not None:
            request['meta']['sensitivity'] = own
        r = cm.access(request)
        assert r['return'] == 0, r
    return cm


def names(r):
    assert r['return'] in (0, 16), r
    return sorted(a['cmeta_ref_parts']['artifact_alias'] for a in r.get('artifacts', []))


def find(cm, **scope):
    return names(cm.access(dict({'category': 'log', 'command': 'find', 'arg1': '*', 'con': False}, **scope)))


def uid_of(cm, alias, category='log'):
    r = cm.access({'category': category, 'command': 'find', 'arg1': alias, 'con': False})
    assert r['return'] == 0 and len(r['artifacts']) == 1, r
    return r['artifacts'][0]['cmeta_ref_parts']['artifact_uid']


def path_of(cm, alias, category='log'):
    r = cm.access({'category': category, 'command': 'find', 'arg1': alias, 'con': False})
    assert r['return'] == 0 and len(r['artifacts']) == 1, r
    return r['artifacts'][0]['path']


def connections(cm, alias):
    """The connections an artifact's _desc.yaml lists (the aliases of the artifacts named)."""
    f = os.path.join(path_of(cm, alias), '_desc.yaml')
    if not os.path.isfile(f):
        return []
    with open(f, encoding='utf-8') as h:
        desc = yaml.safe_load(h) or {}
    return sorted(str(c).split('::')[1].split(',')[0] for c in desc.get('connections') or [])


def clean_scope(cm):
    repos = cm.repos
    return (repos.clearance is None and repos.hidden_repos == () and repos._write_scopes == ()
            and repos._allow_names == frozenset() and repos._allow_patterns == () and repos._default_rank == 0)


# ---------------------------------------------------------------------------
# The labels
# ---------------------------------------------------------------------------

def test_the_ranks_the_synonyms_and_the_clearances():
    assert [sensitivity_rank(l) for l in SENSITIVITY_LEVELS] == [0, 1, 2, 3]
    assert sensitivity_rank('Internal') == 1 and sensitivity_rank('private') == 1
    assert sensitivity_rank('conf') == 2
    assert sensitivity_rank('conf-high') == 3 and sensitivity_rank('Restricted') == 3
    assert sensitivity_rank('highly confidential') == 3 and sensitivity_rank('highly_confidential') == 3
    assert sensitivity_rank('') is None and sensitivity_rank(None) is None
    # personal, and any word the engine does not know, are above every clearance
    assert sensitivity_rank('personal') == 4 and sensitivity_rank('secret') == 4 and sensitivity_rank('Confidental') == 4
    assert [sensitivity_label(r) for r in range(5)] == list(SENSITIVITY_LEVELS) + ['personal']

    assert [clearance_rank(l) for l in SENSITIVITY_LEVELS] == [0, 1, 2, 3]
    assert clearance_rank('internal') == 1 and clearance_rank('RESTRICTED') == 3
    assert clearance_rank('Personal') == 4                     # the server owner's: everything
    for word in ('secret', 'Confidental', 'all', '*', '', None):
        with pytest.raises(ValueError):
            clearance_rank(word)


# ---------------------------------------------------------------------------
# The clearance of a call
# ---------------------------------------------------------------------------

def test_without_a_scope_everything_is_found(cm):
    assert find(cm) == ALL
    assert clean_scope(cm)


def test_a_clearance_hides_the_repositories_and_the_artifacts_labelled_above_it(cm):
    # public: the public repository and the unlabelled one (no label = public: the labels are an extra) - and not
    # the artifact of the public repository that raised itself to internal (general)
    assert find(cm, clearance='public') == ['plain-note', 'pub-note']
    assert find(cm, clearance='general') == AT_GENERAL
    # confidential: the artifact that only repeats its repository's label, not the one raised above it
    assert find(cm, clearance='confidential') == AT_CONFIDENTIAL
    # highly-confidential: the synonym-labelled repository (Restricted) too - never the personal repository, the one
    # labelled with a word that is no label, nor the artifact raised to personal
    assert find(cm, clearance='highly-confidential') == AT_HIGHEST
    assert sorted(set(ALL) - set(AT_HIGHEST)) == ['mine-marked', 'mine-note', 'odd-note']


def test_the_clearance_takes_a_synonym_and_refuses_a_word_that_is_no_clearance(cm):
    assert find(cm, clearance='internal') == AT_GENERAL
    assert find(cm, clearance='restricted') == AT_HIGHEST
    assert find(cm, clearance='CONF') == AT_CONFIDENTIAL

    for word in ('secret', 'Confidental', 'all'):
        r = cm.access({'category': 'log', 'command': 'find', 'arg1': '*', 'con': False, 'clearance': word})
        assert r['return'] == 1 and 'unknown clearance' in r['error'], r
        # and nothing of the failed scope stays behind
        assert clean_scope(cm) and find(cm) == ALL
    assert 'personal' in r['error']


def test_a_hidden_artifact_is_not_found_by_alias_nor_by_uid_nor_read(cm):
    uid = uid_of(cm, 'conf-note')
    for key in ('conf-note', uid, 'conf-repo:conf-note'):
        r = cm.access({'category': 'log', 'command': 'find', 'arg1': key, 'con': False, 'clearance': 'general'})
        assert r['return'] == 16, r
        r = cm.access({'category': 'log', 'command': 'read', 'arg1': key, 'con': False, 'clearance': 'general'})
        assert r['return'] > 0, r
    # the artifact that raised its own label, by UID too
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': uid_of(cm, 'hc-marked'), 'con': False, 'clearance': 'confidential'})
    assert r['return'] == 16, r


def test_a_category_defined_in_a_repository_above_the_clearance_is_not_found(cm):
    r = cm.access({'category': 'category', 'command': 'create', 'arg1': 'conf-repo:conf.kind', 'con': False})
    assert r['return'] == 0, r
    r = cm.access({'category': 'conf.kind', 'command': 'create', 'arg1': 'pub-repo:thing', 'con': False})
    assert r['return'] == 0, r

    r = cm.access({'category': 'conf.kind', 'command': 'find', 'arg1': '*', 'con': False, 'clearance': 'confidential'})
    assert r['return'] == 0 and len(r['artifacts']) == 1, r
    r = cm.access({'category': 'conf.kind', 'command': 'find', 'arg1': '*', 'con': False, 'clearance': 'general'})
    assert r['return'] > 0 and 'not found' in r.get('error', ''), r


def test_a_category_without_an_index_follows_the_scope_too(cm):
    r = cm.access({'category': 'category', 'command': 'create', 'arg1': 'pub-repo:scan.kind', 'meta': {'no_index': True}, 'con': False})
    assert r['return'] == 0, r
    for repo, alias, own in (('pub-repo', 'a-pub', None), ('conf-repo', 'a-conf', None), ('pub-repo', 'a-raised', 'confidential'),
                             ('mine-repo', 'a-mine', None)):
        meta = {'sensitivity': own} if own else {}
        r = cm.access({'category': 'scan.kind', 'command': 'create', 'arg1': '%s:%s' % (repo, alias), 'meta': meta, 'con': False})
        assert r['return'] == 0, r

    def scan(**scope):
        return names(cm.access(dict({'category': 'scan.kind', 'command': 'find', 'arg1': '*', 'con': False}, **scope)))

    assert scan() == ['a-conf', 'a-mine', 'a-pub', 'a-raised']
    assert scan(clearance='general') == ['a-pub']
    assert scan(clearance='confidential') == ['a-conf', 'a-pub', 'a-raised']
    assert scan(clearance='general', allow_repos='mine-repo') == ['a-mine', 'a-pub']
    assert scan(hide_repos='conf-repo') == ['a-mine', 'a-pub', 'a-raised']
    # the category itself is defined in pub-repo: hidden with it
    assert scan(hide_repos='pub-repo') == []


def test_the_default_label_of_an_unlabelled_repository_can_be_set(cm):
    # public by default: an unlabelled repository is read by any clearance (the labels are an extra)
    assert find(cm, clearance='public') == ['plain-note', 'pub-note']
    # a server of an organisation that wants Microsoft 365's default marking: general
    assert find(cm, clearance='public', default_sensitivity='general') == ['pub-note']
    assert find(cm, clearance='general', default_sensitivity='general') == AT_GENERAL
    assert find(cm, clearance='general', default_sensitivity='confidential') == ['gen-note', 'internal-marked', 'pub-note']
    # a server that shows nothing unlabelled: any word above the clearances
    assert find(cm, clearance='highly-confidential', default_sensitivity='personal') == sorted(set(AT_HIGHEST) - {'plain-note'})
    # the engine's own repositories carry no label and are read by any clearance: the categories are always found
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'pub-note', 'con': False, 'clearance': 'public',
                   'default_sensitivity': 'highly-confidential'})
    assert r['return'] == 0 and len(r['artifacts']) == 1, r
    assert clean_scope(cm)


def test_a_repository_of_secrets_without_a_label_is_above_every_clearance(cm, tmp_path):
    r = cm.access({'category': 'repo', 'command': 'create', 'arg1': 'vault-repo', 'meta': {'secrets': True}, 'con': False})
    assert r['return'] == 0, r
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'vault-repo:vault-note', 'con': False})
    assert r['return'] == 0, r

    assert 'vault-note' not in find(cm, clearance='highly-confidential')
    assert 'vault-note' in find(cm, clearance='public', allow_repos='vault-repo')
    assert 'vault-note' in find(cm)
    # a label of its own is read as written
    cmr = tmp_path / 'repos' / 'vault-repo' / '_cmr.yaml'
    cmr.write_text(cmr.read_text(encoding='utf-8') + 'sensitivity: general\n', encoding='utf-8')
    assert 'vault-note' in find(cm, clearance='general')


def test_a_label_edited_in_cmr_yaml_counts_at_once_without_a_reindex(cm, tmp_path):
    cmr = tmp_path / 'repos' / 'gen-repo' / '_cmr.yaml'
    assert 'gen-note' in find(cm, clearance='general')

    # raised by hand: hidden from the next call, the index untouched
    text = cmr.read_text(encoding='utf-8')
    time.sleep(0.05)
    cmr.write_text(text.replace('sensitivity: general', 'sensitivity: highly-confidential'), encoding='utf-8')
    assert 'gen-note' not in find(cm, clearance='confidential')
    assert 'gen-note' in find(cm, clearance='highly-confidential')

    # the label taken away: public again
    time.sleep(0.05)
    cmr.write_text(text.replace('sensitivity: general\n', ''), encoding='utf-8')
    assert 'gen-note' in find(cm, clearance='public')

    # and a label given to an unlabelled repository
    cmr = tmp_path / 'repos' / 'plain-repo' / '_cmr.yaml'
    cmr.write_text(cmr.read_text(encoding='utf-8') + 'sensitivity: personal\n', encoding='utf-8')
    assert 'plain-note' not in find(cm, clearance='highly-confidential')


def test_a_named_grant_lifts_a_repository_above_the_clearance_but_not_an_artifact_that_raised_itself(cm):
    # the artifact that only repeats the repository's label comes with the repository; the raised one does not
    assert find(cm, clearance='general', allow_repos='conf-repo') == sorted(AT_GENERAL + ['conf-again', 'conf-note'])
    # by UID and by pattern
    r = cm.access({'category': 'repo', 'command': 'find', 'arg1': 'hc-repo', 'con': False})
    uid = r['artifacts'][0]['cmeta_ref_parts']['artifact_uid']
    assert 'hc-note' in find(cm, clearance='public', allow_repos=uid)
    assert find(cm, clearance='public', allow_repos=['conf-*', 'hc-*']) == ['conf-again', 'conf-note', 'hc-note', 'plain-note', 'pub-note']
    assert 'hc-marked' not in find(cm, clearance='general', allow_repos='conf-repo')
    assert 'hc-marked' in find(cm, clearance='highly-confidential')


def test_personal_is_read_by_a_named_grant_only(cm):
    for clearance in SENSITIVITY_LEVELS:
        found = find(cm, clearance=clearance)
        assert 'mine-note' not in found and 'mine-marked' not in found and 'odd-note' not in found
    # the owner's record: a grant by name, whatever the clearance
    assert 'mine-note' in find(cm, clearance='public', allow_repos='mine-repo')
    assert find(cm, **scope_for({'clearance': 'general', 'repos': {'mine-repo': 'read'}})) == sorted(AT_GENERAL + ['mine-note'])
    # a repository labelled with a word that is no label opens the same way
    assert 'odd-note' in find(cm, clearance='general', allow_repos='odd-repo')
    # an artifact raised to personal inside a shared repository is read through no grant of that repository - by
    # the owner's clearance or a call without a clearance
    assert 'mine-marked' not in find(cm, clearance='highly-confidential', allow_repos='gen-repo')
    assert 'mine-marked' in find(cm) and 'mine-marked' in find(cm, hide_repos='pub-repo')


def test_the_clearance_personal_is_the_owners_and_reads_everything(cm, tmp_path):
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'local:machine-log', 'con': False})
    assert r['return'] == 0, r

    # everything: the personal repository, the artifact raised to personal, the word that is no label, the machine's
    # own repository - whatever the site's default label
    assert find(cm, clearance='personal') == sorted(ALL + ['machine-log'])
    assert find(cm, clearance='personal', default_sensitivity='personal') == sorted(ALL + ['machine-log'])
    assert find(cm, **scope_for({'clearance': 'personal'}, default_sensitivity='general')) == sorted(ALL + ['machine-log'])
    # still a scope: a denial by name holds, a nested call narrows it, writes follow the write scope
    assert 'conf-note' not in find(cm, clearance='personal', hide_repos='conf-repo')
    saved = cm.repos.push_scope(clearance='personal', write_repos='mine-repo')
    try:
        assert find(cm, clearance='general') == AT_GENERAL
        assert cm.repos.write_refused('mine-repo') is None and cm.repos.write_refused('gen-repo') is not None
        # a nested call that asks to write into more writes into no more
        r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'gen-repo:widened', 'con': False, 'write_repos': 'mine-repo,gen-repo'})
        assert r['return'] == 1 and 'may not write' in r['error'], r
    finally:
        cm.repos.pop_scope(saved)
    assert clean_scope(cm)

    # a link between labels is written on the higher side only, for the owner too: the name of the personal artifact
    # never lands in a general one through a door
    r = cm.access({'category': 'log', 'command': 'update', 'arg1': 'mine-note', 'connect': 'log::gen-note', 'con': False,
                   'clearance': 'personal', 'write_repos': 'mine-repo,gen-repo'})
    assert r['return'] == 1 and 'higher side only' in r['error'], r
    r = cm.access({'category': 'log', 'command': 'update', 'arg1': 'mine-note', 'connect_to': 'log::gen-note', 'con': False,
                   'clearance': 'personal', 'write_repos': 'mine-repo'})
    assert r['return'] == 0, r

    # the table of the owner: every repository read
    t = {row['alias']: row for row in cm.repos.scope_table({'clearance': 'personal'})}
    assert all(row['read'] for row in t.values()) and t['mine-repo']['why'] == 'clearance' and t['local']['why'] == 'clearance'


def test_the_machines_own_repository_is_read_under_a_clearance_by_a_named_grant_only(cm, tmp_path):
    # local holds the machine's logs, caches and config artifacts: no public data, though it carries no label
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'local:machine-log', 'con': False})
    assert r['return'] == 0, r
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'no-repo-named', 'con': False})      # goes to local
    assert r['return'] == 0, r
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'no-repo-named', 'con': False})
    assert r['return'] == 0 and r['artifacts'][0]['cmeta_ref_parts']['repo_alias'] == 'local', r

    assert 'machine-log' in find(cm) and 'machine-log' in find(cm, hide_repos='pub-repo')
    for clearance in SENSITIVITY_LEVELS:
        found = find(cm, clearance=clearance)
        assert 'machine-log' not in found and 'no-repo-named' not in found
        assert 'machine-log' not in find(cm, clearance=clearance, default_sensitivity='public')
    assert 'machine-log' in find(cm, clearance='public', allow_repos='local')

    # nothing is written into it under a clearance either - a new artifact without a repository would land there
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'lands-in-local', 'con': False, 'clearance': 'highly-confidential'})
    assert r['return'] == 1 and 'out of the scope' in r['error'], r
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'lands-in-local', 'con': False, 'clearance': 'general',
                   'allow_repos': 'local', 'write_repos': 'local'})
    assert r['return'] == 0, r

    # the engine's internal repository is public: the categories are found by any clearance, whatever the default
    r = cm.access({'category': 'category', 'command': 'find', 'arg1': 'log', 'con': False, 'clearance': 'public',
                   'default_sensitivity': 'personal'})
    assert r['return'] == 0 and len(r['artifacts']) == 1, r

    # a label of its own in local's _cmr.yaml is read as written (an organisation's choice)
    cmr = tmp_path / 'repos' / 'local' / '_cmr.yaml'
    assert cmr.is_file()
    cmr.write_text(cmr.read_text(encoding='utf-8').rstrip() + '\nsensitivity: general\n', encoding='utf-8')
    assert 'machine-log' in find(cm, clearance='general') and 'machine-log' not in find(cm, clearance='public')


def test_the_machines_settings_are_read_by_the_code_that_serves_a_call_whatever_its_scope(cm):
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'machine-settings', 'meta': {'colour': 'blue'}, 'con': False})
    assert r['return'] == 0, r

    def get(name, **scope):
        return cm.access(dict({'category': 'config,cc6bfe174be847ed', 'command': 'get', 'arg1': name, 'con': False}, **scope))

    assert get('machine-settings')['config_cmeta'].get('colour') == 'blue'

    # a person's own request for the settings (the request a door forwards carries the scope): within the scope -
    # the config artifacts are in local, above every clearance; nothing is made in their place
    for scope in ({'clearance': 'highly-confidential'}, {'clearance': 'general', 'write_repos': 'none'}):
        r = get('machine-settings', **scope)
        assert r['return'] > 0 or not (r.get('config_cmeta') or {}).get('colour'), r
        r = cm.access(dict({'category': 'config', 'command': 'find', 'arg1': '*', 'con': False}, **scope))
        assert names(r) == [], r
    assert names(cm.access({'category': 'config', 'command': 'find', 'arg1': 'machine-settings', 'con': False,
                            'clearance': 'public', 'allow_repos': 'local'})) == ['machine-settings']

    # the code of a category or of a page, inside a call with a scope: the settings read as from a shell, a missing
    # config artifact made as ever - and nothing else of the scope lifted
    for scope in ({'clearance': 'public'}, {'write_repos': 'none'}, {'clearance': 'general', 'hide_repos': 'local', 'write_repos': 'none'}):
        saved = cm.repos.push_scope(**scope)
        try:
            assert get('machine-settings')['config_cmeta'].get('colour') == 'blue', scope
            r = get('made-on-demand-%d' % len(scope))
            assert r['return'] == 0 and r['config_cmeta'] == {}, r
            assert 'conf-note' not in find(cm) or 'clearance' not in scope
            r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'local:not-a-setting', 'con': False})
            assert r['return'] == 1, r
            assert cm.repos.scoped or cm.repos.write_scoped
        finally:
            cm.repos.pop_scope(saved)
    assert clean_scope(cm)

    # hide_repos alone, as the servers used it before the labels: a call into config stays within it
    saved = cm.repos.push_scope(hide_repos='local')
    try:
        r = cm.access({'category': 'config', 'command': 'find', 'arg1': 'machine-settings', 'con': False})
        assert names(r) == [], r
    finally:
        cm.repos.pop_scope(saved)


def test_the_table_of_a_scope_says_what_the_engine_enforces(cm):
    def table(scope=None):
        return {row['alias']: row for row in cm.repos.scope_table(scope)}

    # without a scope: the labels, everything read and written
    t = table()
    assert set(REPOS) | {'local', 'internal'} == set(t)
    assert all(row['read'] and row['write'] and row['why'] == 'open' for row in t.values())
    assert (t['conf-repo']['sensitivity'], t['conf-repo']['label'], t['conf-repo']['from']) == ('confidential', 'confidential', 'label')
    assert (t['syn-repo']['sensitivity'], t['syn-repo']['label']) == ('highly-confidential', 'Restricted')
    assert (t['odd-repo']['sensitivity'], t['odd-repo']['label'], t['odd-repo']['rank']) == ('personal', 'secret', 4)
    assert (t['plain-repo']['sensitivity'], t['plain-repo']['label'], t['plain-repo']['from']) == ('public', None, 'default')
    assert (t['local']['sensitivity'], t['local']['from']) == ('personal', 'local')
    assert (t['internal']['sensitivity'], t['internal']['from']) == ('public', 'engine')

    # a person's record
    record = {'clearance': 'general', 'repos': {'conf-repo': 'read', 'hc-repo': 'write', 'pub-repo': 'none'}}
    t = table(scope_for(record))
    assert {a: (row['read'], row['write'], row['why']) for a, row in t.items()} == {
        'pub-repo': (False, False, 'denied'), 'gen-repo': (True, False, 'clearance'), 'plain-repo': (True, False, 'clearance'),
        'conf-repo': (True, False, 'granted'), 'hc-repo': (True, True, 'granted'), 'syn-repo': (False, False, 'label'),
        'odd-repo': (False, False, 'label'), 'mine-repo': (False, False, 'label'), 'local': (False, False, 'label'),
        'internal': (True, False, 'clearance')}
    # ... and it is what the calls of that scope get
    found = find(cm, **scope_for(record))
    for alias, (repo, own) in NOTES.items():
        if own is None:
            assert (alias in found) == t[repo]['read'], alias

    # an administrator's page reports on another person's record whatever its own scope - which comes back after
    saved = cm.repos.push_scope(clearance='public', hide_repos='hc-repo', write_repos='none')
    try:
        assert table(scope_for(record)) == t
        mine = table()
        assert (mine['hc-repo']['read'], mine['hc-repo']['why']) == (False, 'denied') and not mine['gen-repo']['read']
        assert not any(row['write'] for row in mine.values())
        with pytest.raises(ValueError):
            cm.repos.scope_table({'clearance': 'secret'})
        assert cm.repos.clearance == 0 and cm.repos.hidden_repos
    finally:
        cm.repos.pop_scope(saved)
    assert clean_scope(cm)

    # the command: cx repo scope
    r = cm.access(dict({'category': 'repo', 'command': 'scope', 'con': False}, **scope_for(record)))
    assert r['return'] == 0 and {row['alias']: row for row in r['repos']} == t, r


def test_hide_repos_and_the_clearance_work_together_and_the_scope_ends_with_the_call(cm):
    assert find(cm, clearance='highly-confidential', hide_repos='pub-repo') == sorted(set(AT_HIGHEST) - {'pub-note', 'internal-marked'})
    assert find(cm, clearance='general', hide_repos='gen-*') == ['internal-marked', 'plain-note', 'pub-note']
    # a denial by name wins over a grant by name
    assert find(cm, clearance='general', hide_repos='conf-repo', allow_repos='conf-repo') == AT_GENERAL

    assert clean_scope(cm)
    assert find(cm) == ALL


def test_a_nested_call_never_widens_the_scope(cm):
    # a move looks the artifact up through a nested find: the clearance of the outer call holds inside it
    r = cm.access({'category': 'log', 'command': 'move', 'arg1': 'conf-note', 'arg2': 'conf-note-2', 'con': False,
                   'clearance': 'general'})
    assert r['return'] == 16, r
    assert 'conf-note' in find(cm)

    saved = cm.repos.push_scope(clearance='general', default_sensitivity='general')
    try:
        assert find(cm) == AT_GENERAL
        # a nested call asks for more: a wider clearance, a grant, a lower default - none of them counts
        assert find(cm, clearance='highly-confidential') == AT_GENERAL
        assert find(cm, allow_repos='conf-repo,mine-repo') == AT_GENERAL
        assert find(cm, clearance='highly-confidential', allow_repos='*') == AT_GENERAL
        assert 'plain-note' in find(cm, default_sensitivity='public')            # general stays the default: still read
        assert find(cm, clearance='public', default_sensitivity='public') == ['pub-note']
        # it may narrow: a lower clearance, more hidden repositories, a higher default
        assert find(cm, clearance='public') == ['pub-note']
        assert find(cm, hide_repos='gen-repo') == ['internal-marked', 'plain-note', 'pub-note']
        assert find(cm, default_sensitivity='confidential') == ['gen-note', 'internal-marked', 'pub-note']
        assert cm.repos.clearance == 1
    finally:
        cm.repos.pop_scope(saved)
    assert clean_scope(cm)

    # a grant given with the first clearance holds for the calls inside it
    saved = cm.repos.push_scope(clearance='general', allow_repos='conf-repo')
    try:
        assert 'conf-note' in find(cm) and 'conf-note' in find(cm, clearance='general')
        assert 'conf-note' not in find(cm, hide_repos='conf-repo')
    finally:
        cm.repos.pop_scope(saved)
    assert clean_scope(cm)


def test_a_server_sets_the_scope_aside_for_its_own_bookkeeping(cm):
    saved = cm.repos.push_scope(clearance='public', hide_repos='pub-repo', write_repos='none')
    try:
        assert find(cm) == ['plain-note']
        inner = cm.repos.suspend_scope()
        try:
            assert not cm.repos.scoped and not cm.repos.write_scoped
            assert find(cm) == ALL
            r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'local:bookkeeping', 'con': False})
            assert r['return'] == 0, r
        finally:
            cm.repos.pop_scope(inner)
        assert find(cm) == ['plain-note']
        assert cm.repos.write_refused('local') is not None
    finally:
        cm.repos.pop_scope(saved)
    assert clean_scope(cm)


# ---------------------------------------------------------------------------
# The write scope of a call
# ---------------------------------------------------------------------------

def test_writes_go_through_as_before_without_a_scope(cm):
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'conf-repo:new-note', 'con': False})
    assert r['return'] == 0, r
    r = cm.access({'category': 'log', 'command': 'update', 'arg1': 'new-note', 'meta': {'tags': ['x']}, 'con': False})
    assert r['return'] == 0, r
    # a connection both ways between labels, a move to a lower label: a shell decides
    r = cm.access({'category': 'log', 'command': 'update', 'arg1': 'new-note', 'connect': 'log::pub-note', 'con': False})
    assert r['return'] == 0, r
    assert connections(cm, 'new-note') == ['pub-note'] and connections(cm, 'pub-note') == ['new-note']
    r = cm.access({'category': 'log', 'command': 'move', 'arg1': 'new-note', 'arg2': 'pub-repo:new-note', 'con': False})
    assert r['return'] == 0, r
    r = cm.access({'category': 'log', 'command': 'delete', 'arg1': 'new-note', 'con': False, 'force': True})
    assert r['return'] == 0, r
    r = cm.access({'category': 'repo', 'command': 'create', 'arg1': 'another-repo', 'con': False})
    assert r['return'] == 0, r


def test_write_repos_names_the_only_repositories_a_call_may_write_into(cm):
    # a create into another repository is refused, into the named one it goes
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'gen-repo:x', 'con': False, 'write_repos': 'pub-repo'})
    assert r['return'] == 1 and 'may not write into the repository "gen-repo"' in r['error'], r
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'pub-repo:x', 'con': False, 'write_repos': 'pub-repo'})
    assert r['return'] == 0, r
    assert 'x' in find(cm)

    # update, delete and move of an artifact outside the write scope - refused before anything is touched
    r = cm.access({'category': 'log', 'command': 'update', 'arg1': 'gen-note', 'meta': {'tags': ['y']}, 'con': False, 'write_repos': 'pub-repo'})
    assert r['return'] == 1 and 'updating an artifact refused' in r['error'], r
    r = cm.access({'category': 'log', 'command': 'delete', 'arg1': 'gen-note', 'con': False, 'force': True, 'write_repos': 'pub-repo'})
    assert r['return'] == 1 and 'deleting an artifact refused' in r['error'], r
    assert 'gen-note' in find(cm)
    r = cm.access({'category': 'log', 'command': 'move', 'arg1': 'gen-note', 'arg2': 'gen-note-2', 'con': False, 'write_repos': 'pub-repo'})
    assert r['return'] == 1 and 'refused' in r['error'], r
    assert 'gen-note' in find(cm) and 'gen-note-2' not in find(cm)

    # a move into a repository outside the write scope - refused by the target
    r = cm.access({'category': 'log', 'command': 'move', 'arg1': 'x', 'arg2': 'gen-repo:x', 'con': False, 'write_repos': 'pub-repo'})
    assert r['return'] == 1 and 'into a repository refused' in r['error'], r
    # a copy reads its source and writes its target: the target decides
    r = cm.access({'category': 'log', 'command': 'copy', 'arg1': 'gen-note', 'arg2': 'pub-repo:gen-copy', 'con': False, 'write_repos': 'pub-repo'})
    assert r['return'] == 0, r
    assert 'gen-copy' in find(cm)

    # the write scope takes several names and patterns, and 'none' refuses every write
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'conf-repo:y', 'con': False, 'write_repos': ['pub-repo', 'conf-*']})
    assert r['return'] == 0, r
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'pub-repo:z', 'con': False, 'write_repos': 'none'})
    assert r['return'] == 1 and 'no repository' in r['error'], r
    assert 'z' not in find(cm)
    assert clean_scope(cm)


def test_a_repository_hidden_from_the_call_is_never_written_into(cm):
    # by its label above the clearance
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'conf-repo:x', 'con': False, 'clearance': 'general'})
    assert r['return'] == 1 and 'out of the scope' in r['error'], r
    # by name
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'pub-repo:x', 'con': False, 'hide_repos': 'pub-repo'})
    assert r['return'] == 1 and 'out of the scope' in r['error'], r
    # a personal repository: whatever the clearance
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'mine-repo:x', 'con': False, 'clearance': 'highly-confidential'})
    assert r['return'] == 1 and 'out of the scope' in r['error'], r
    # a grant by name makes it writable again when the write scope names it
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'conf-repo:x', 'con': False, 'clearance': 'general',
                   'allow_repos': 'conf-repo', 'write_repos': 'conf-repo'})
    assert r['return'] == 0, r
    # reads with the same scope see it
    assert 'x' in find(cm, clearance='general', allow_repos='conf-repo')


def test_a_nested_write_scope_only_narrows(cm):
    saved = cm.repos.push_scope(write_repos='pub-repo,gen-repo')
    try:
        inner = cm.repos.push_scope(write_repos='gen-repo,conf-repo')
        try:
            assert cm.repos.write_refused('gen-repo') is None
            assert cm.repos.write_refused('pub-repo') is not None        # the inner scope does not name it
            assert cm.repos.write_refused('conf-repo') is not None       # the outer scope does not name it
        finally:
            cm.repos.pop_scope(inner)
        assert cm.repos.write_refused('pub-repo') is None
    finally:
        cm.repos.pop_scope(saved)
    assert cm.repos.write_refused('conf-repo') is None


def test_a_move_or_a_copy_under_a_clearance_never_lowers_a_label(cm):
    scope = {'clearance': 'highly-confidential', 'con': False}

    # from confidential into general: refused, for a move and for a copy
    for command in ('move', 'copy'):
        r = cm.access(dict({'category': 'log', 'command': command, 'arg1': 'conf-note', 'arg2': 'gen-repo:conf-moved'}, **scope))
        assert r['return'] == 1 and 'would lower its sensitivity label from confidential to general' in r['error'], r
    assert 'conf-moved' not in find(cm) and 'conf-note' in find(cm)

    # an artifact that carries its own label keeps it wherever it goes: no lowering, the move goes through
    r = cm.access(dict({'category': 'log', 'command': 'copy', 'arg1': 'hc-marked', 'arg2': 'hc-repo:hc-copy'}, **scope))
    assert r['return'] == 0, r
    r = cm.access(dict({'category': 'log', 'command': 'copy', 'arg1': 'conf-again', 'arg2': 'gen-repo:conf-again-2'}, **scope))
    assert r['return'] == 0, r
    assert 'conf-again-2' not in find(cm, clearance='general') and 'conf-again-2' in find(cm, clearance='confidential')
    # ... but out of a repository labelled above its own label it would be lowered
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'hc-repo:low-marked', 'meta': {'sensitivity': 'general'}, 'con': False})
    assert r['return'] == 0, r
    r = cm.access(dict({'category': 'log', 'command': 'copy', 'arg1': 'low-marked', 'arg2': 'conf-repo:low-marked-2'}, **scope))
    assert r['return'] == 1 and 'from highly-confidential to confidential' in r['error'], r

    # up, or to the same label: fine
    r = cm.access(dict({'category': 'log', 'command': 'copy', 'arg1': 'gen-note', 'arg2': 'conf-repo:gen-up'}, **scope))
    assert r['return'] == 0, r
    r = cm.access(dict({'category': 'log', 'command': 'move', 'arg1': 'gen-up', 'arg2': 'gen-up-renamed'}, **scope))
    assert r['return'] == 0, r
    assert 'gen-up-renamed' in find(cm)

    # without a clearance a move is the way to reclassify
    r = cm.access({'category': 'log', 'command': 'move', 'arg1': 'conf-note', 'arg2': 'gen-repo:conf-note', 'con': False,
                   'write_repos': 'conf-repo,gen-repo'})
    assert r['return'] == 0, r
    assert 'conf-note' in find(cm, clearance='general')


def test_a_connection_is_a_write_on_both_sides_and_never_points_down_under_a_clearance(cm):
    def update(alias, **more):
        return cm.access(dict({'category': 'log', 'command': 'update', 'arg1': alias, 'con': False}, **more))

    # the write scope: the other side of --connect is written too
    r = update('pub-note', connect='log::gen-note', write_repos='pub-repo')
    assert r['return'] == 1 and 'connecting both ways refused' in r['error'] and '--ct' in r['error'], r
    assert connections(cm, 'pub-note') == [] and connections(cm, 'gen-note') == []
    r = update('pub-note', connect_to='log::plain-note', write_repos='pub-repo')
    assert r['return'] == 0, r
    assert connections(cm, 'pub-note') == ['plain-note'] and connections(cm, 'plain-note') == []
    r = update('pub-note', connect='log::gen-note', write_repos='pub-repo,gen-repo')
    assert r['return'] == 0, r
    assert connections(cm, 'gen-note') == ['pub-note']

    # under a clearance a link between labels is written on the higher side only
    scope = {'clearance': 'highly-confidential'}
    r = update('gen-note', connect_to='log::conf-note', **scope)          # the confidential alias into a general artifact
    assert r['return'] == 1 and 'higher side only' in r['error'] and 'conf-note' in r['error'], r
    r = update('conf-note', connect='log::gen-note', **scope)             # both ways: its alias into the general one
    assert r['return'] == 1 and 'higher side only' in r['error'], r
    assert 'conf-note' not in connections(cm, 'gen-note') and connections(cm, 'conf-note') == []
    r = update('conf-note', connect_to='log::gen-note', **scope)          # from the higher side, this side only
    assert r['return'] == 0, r
    assert connections(cm, 'conf-note') == ['gen-note'] and 'conf-note' not in connections(cm, 'gen-note')
    # an artifact's own label counts: the raised artifact of the public repository points down, never the reverse
    r = update('pub-note', connect_to='log::internal-marked', **scope)
    assert r['return'] == 1 and 'higher side only' in r['error'], r
    r = update('internal-marked', connect_to='log::pub-note', **scope)
    assert r['return'] == 0, r
    # the same label: both ways, as ever
    r = update('conf-note', connect='log::conf-again', **scope)
    assert r['return'] == 0, r
    assert 'conf-note' in connections(cm, 'conf-again') and 'conf-again' in connections(cm, 'conf-note')
    # a disconnection takes information away: both sides, under any clearance
    r = update('conf-note', connect='-log::conf-again', **scope)
    assert r['return'] == 0, r
    assert 'conf-note' not in connections(cm, 'conf-again') and 'conf-again' not in connections(cm, 'conf-note')

    # a new artifact with its connections: refused before it is made
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'gen-repo:fresh', 'connect_to': 'log::conf-note', 'con': False,
                   'clearance': 'highly-confidential'})
    assert r['return'] == 1 and 'higher side only' in r['error'], r
    assert 'fresh' not in find(cm)
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'conf-repo:fresh', 'connect_to': 'log::gen-note', 'con': False,
                   'clearance': 'highly-confidential'})
    assert r['return'] == 0, r
    assert connections(cm, 'fresh') == ['gen-note']
    assert clean_scope(cm)


def test_a_call_with_a_write_scope_manages_no_repository(cm, tmp_path):
    for request in ({'command': 'create', 'arg1': 'new-repo'},
                    {'command': 'delete', 'arg1': 'pub-repo', 'force': True},
                    {'command': 'delete', 'arg1': 'pub-repo', 'unplug': True},
                    {'command': 'pull', 'arg1': 'pub-repo'}):
        r = cm.access(dict({'category': 'repo', 'con': False, 'write_repos': 'pub-repo'}, **request))
        assert r['return'] == 1 and 'manages none' in r['error'], (request, r)
    assert not (tmp_path / 'repos' / 'new-repo').exists() and (tmp_path / 'repos' / 'pub-repo').is_dir()
    # reading the repositories stays open
    r = cm.access({'category': 'repo', 'command': 'find', 'arg1': 'pub-repo', 'con': False, 'write_repos': 'none'})
    assert r['return'] == 0 and len(r['artifacts']) == 1, r
    # and a clearance alone is no write scope: the repositories are managed as before
    r = cm.access({'category': 'repo', 'command': 'create', 'arg1': 'new-repo', 'con': False, 'clearance': 'general'})
    assert r['return'] == 0, r


# ---------------------------------------------------------------------------
# A person's record, the pages, the command line
# ---------------------------------------------------------------------------

def test_scope_for_turns_a_record_into_the_keys_of_a_call(cm):
    record = {'clearance': 'general', 'repos': {'conf-repo': 'read', 'hc-repo': 'write', 'pub-repo': 'none'}}
    scope = scope_for(record)
    assert scope == {'clearance': 'general', 'hide_repos': ['pub-repo'], 'allow_repos': ['conf-repo', 'hc-repo'],
                     'write_repos': ['hc-repo']}

    assert find(cm, **scope) == ['conf-again', 'conf-note', 'gen-note', 'hc-note', 'plain-note']
    r = cm.access(dict({'category': 'log', 'command': 'create', 'arg1': 'hc-repo:mine', 'con': False}, **scope))
    assert r['return'] == 0, r
    r = cm.access(dict({'category': 'log', 'command': 'create', 'arg1': 'conf-repo:mine', 'con': False}, **scope))
    assert r['return'] == 1 and 'may not write' in r['error'], r

    # a record without a clearance reads general; one with no write at all writes nowhere
    assert scope_for({})['clearance'] == 'general' and scope_for({})['write_repos'] == 'none'
    assert scope_for({'clearance': 'public'}) == {'clearance': 'public', 'write_repos': 'none'}
    r = cm.access(dict({'category': 'log', 'command': 'create', 'arg1': 'pub-repo:mine', 'con': False}, **scope_for({'clearance': 'public'})))
    assert r['return'] == 1 and 'no repository' in r['error'], r
    # a record whose clearance is no clearance is refused by the call, never read as "everything"
    r = cm.access(dict({'category': 'log', 'command': 'find', 'arg1': '*', 'con': False}, **scope_for({'clearance': 'secret'})))
    assert r['return'] == 1 and 'unknown clearance' in r['error'], r

    # the site's default label of the repositories that declare none (general on a site of an organisation)
    scope = scope_for({'clearance': 'public'}, default_sensitivity='general')
    assert scope == {'clearance': 'public', 'write_repos': 'none', 'default_sensitivity': 'general'}
    assert find(cm, **scope) == ['pub-note']
    assert 'plain-note' in find(cm, **scope_for({}, default_sensitivity='general'))
    assert 'default_sensitivity' not in scope_for({}, default_sensitivity='') and 'default_sensitivity' not in scope_for({})


def test_the_browse_page_follows_the_clearance_of_its_request(cm):
    def page(action, scope=None, **query):
        r = cm.access(dict({'category': 'cserver.browse', 'command': 'web', 'con': False, 'urls': dict(URLS),
                            'query': dict(query, native_action=action), 'misc': {}}, **(scope or {})))
        assert r['return'] == 0, r
        return r['json']

    def search(scope=None):
        out = page('search', scope, cats='log')
        assert 'error' not in out, out
        return sorted(x['alias'] for x in out['rows'])

    assert search() == ALL
    assert search({'clearance': 'general'}) == AT_GENERAL
    assert search({'clearance': 'confidential'}) == AT_CONFIDENTIAL
    assert search({'clearance': 'general', 'allow_repos': 'mine-repo'}) == sorted(AT_GENERAL + ['mine-note'])
    assert search({'clearance': 'public', 'default_sensitivity': 'general'}) == ['pub-note']

    # an artifact above the clearance asked for by its UID or its cRef: not shown, not resolved - the one raised
    # by its own label too
    for alias in ('conf-note', 'hc-marked', 'mine-note'):
        out = page('artifact', {'clearance': 'general'}, uid=uid_of(cm, alias))
        assert 'error' in out, out
        out = page('resolve', {'clearance': 'general'}, cref='log::' + alias)
        assert out['uid'] == '' and out['notice'], out
    out = page('artifact', {'clearance': 'confidential'}, uid=uid_of(cm, 'conf-note'))
    assert 'error' not in out, out

    # its repository is no target of a new artifact or of a move
    out = page('create', {'clearance': 'general'}, repo='conf-repo', cat='log', alias='made-here')
    assert 'error' in out and 'made-here' not in find(cm), out
    # and the catalog kept per process was not narrowed by the scoped requests before
    assert search() == ALL


def test_the_browse_page_writes_within_the_scope_of_its_request(cm):
    # a signed-in reader the host lets write everywhere (browse_edit) - the engine's scope of the request narrows it
    def act(scope, action, **query):
        r = cm.access(dict({'category': 'cserver.browse', 'command': 'web', 'con': False, 'urls': dict(URLS),
                            'query': dict(query, native_action=action), 'misc': {'same_origin': True, 'browse_edit': True}}, **scope))
        assert r['return'] == 0, r
        return r['json']

    scope = {'clearance': 'general', 'write_repos': 'gen-repo'}

    # a new artifact: only into the write scope
    out = act(scope, 'create', cat='log', repo='pub-repo', alias='page-made')
    assert 'may not write to the repository pub-repo' in out.get('error', ''), out
    out = act(scope, 'create', cat='log', repo='gen-repo', alias='page-made')
    assert out.get('created') == 'page-made', out

    # a file saved, an artifact deleted: refused outside the write scope
    out = act(scope, 'delete_artifact', uid=uid_of(cm, 'pub-note'))
    assert 'may not write to the repository pub-repo' in out.get('error', ''), out
    assert 'pub-note' in find(cm)

    # inside it: the folder into the trash of the machine's local repository - the page's own bookkeeping, done with
    # the scope of the request set aside (local is above every clearance) - and Undo
    uid = uid_of(cm, 'page-made')
    out = act(scope, 'delete_artifact', uid=uid)
    assert out.get('deleted') == 'page-made', out
    assert 'page-made' not in find(cm)
    back = act(scope, 'undelete_artifact', trash=out['trash'])
    assert 'error' not in back, back
    assert 'page-made' in find(cm, clearance='general')

    # a move to a repository outside the write scope
    out = act({'clearance': 'general', 'write_repos': 'gen-repo,plain-repo'}, 'move', uid=uid, repo='pub-repo')
    assert 'may not write to the repository pub-repo' in out.get('error', ''), out
    assert clean_scope(cm)


def test_the_configs_page_follows_the_clearance_of_its_request(cm, tmp_path):
    # a category that declares a config key, defined in the confidential repository
    r = cm.access({'category': 'category', 'command': 'create', 'arg1': 'conf-repo:conf.kind', 'con': False})
    assert r['return'] == 0, r
    with open(os.path.join(r['path'], '_desc.yaml'), 'w', encoding='utf-8') as f:
        f.write('configs:\n  conf-kind-settings:\n    desc: The settings of the confidential kind.\n'
                '    keys:\n      colour:\n        desc: Its colour.\n        default: blue\n')

    def configs(**scope):
        r = cm.access(dict({'category': 'cserver.cmeta.configs', 'command': 'web', 'con': False, 'urls': dict(URLS),
                            'query': {'native_action': 'configs', 'refresh': '1'}, 'misc': {'client_local': True}}, **scope))
        assert r['return'] == 0, r
        assert 'error' not in r['json'], r['json']
        return str(r['json'])

    assert 'conf-kind-settings' in configs()
    # the model is built for every viewer whatever the scope of the request that builds it (its cache is written
    # into the local repository: the write scope set aside too) - and shown by the scope
    assert 'conf-kind-settings' not in configs(clearance='general', write_repos='none')
    assert 'conf-kind-settings' in configs(clearance='confidential')
    assert 'conf-kind-settings' not in configs(hide_repos='conf-repo')
    assert 'conf-kind-settings' in configs()
    assert clean_scope(cm)


def test_the_command_line_flags(cm, tmp_path):
    env = dict(os.environ, CMETA_HOME=str(tmp_path))
    for var in ('CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
        env.pop(var, None)

    def cx(*args):
        p = subprocess.run([sys.executable, '-m', 'cmeta', *args], env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        return p.returncode, p.stdout.decode('utf-8', 'replace')

    code, out = cx('log', 'ls', '--clearance=general')
    assert code == 0, out
    assert 'gen-note' in out and 'conf-note' not in out and 'hc-note' not in out and 'mine-note' not in out

    code, out = cx('log', 'ls', '--clearance=general', '--allow_repos=conf-repo,mine-repo')
    assert code == 0 and 'conf-note' in out and 'mine-note' in out and 'hc-marked' not in out, out

    code, out = cx('log', 'ls', '--clearance=secret')
    assert code != 0 and 'unknown clearance' in out, out

    code, out = cx('log', 'ls', '--clearance=personal')
    assert code == 0 and 'mine-note' in out and 'mine-marked' in out and 'odd-note' in out and 'hc-note' in out, out

    code, out = cx('repo', 'scope', '--clearance=general', '--allow_repos=conf-repo', '--write_repos=gen-repo')
    assert code == 0, out
    rows = {line.split()[0]: ' '.join(line.split()[1:]) for line in out.splitlines() if line.strip()}
    assert rows['gen-repo'] == 'general yes yes within the clearance', out
    assert rows['conf-repo'] == 'confidential yes - above the clearance, granted by name', out
    assert rows['hc-repo'] == 'highly-confidential - - above the clearance', out
    assert rows['plain-repo'] == 'public (no label) yes - within the clearance', out
    assert rows['local'] == 'personal (this machine) - - above the clearance', out
    code, out = cx('repo', 'scope')
    assert code == 0 and 'No scope' in out, out

    code, out = cx('log', 'add', 'gen-repo:cli-note', '--write_repos=none')
    assert code != 0 and 'no repository' in out, out
    code, out = cx('log', 'add', 'gen-repo:cli-note', '--write-repos=gen-repo')
    assert code == 0, out
    assert 'cli-note' in find(cm)
