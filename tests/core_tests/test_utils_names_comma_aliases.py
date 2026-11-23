"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

An alias may hold commas (the user, 2026-11-23): a name is split at its LAST comma, and the part after it is the UID
only when it is a valid UID - otherwise the whole name is the alias. split_cmeta_name is that rule, parse_cmeta_name
reads through it (the same answers as before, every one compared below), and alias_ends_with_uid finds the one alias
that cannot be named by itself (a UID after its last comma), which is_valid_cmeta_alias refuses.
"""

import itertools

import pytest

from cmeta.utils.names import (alias_ends_with_uid, is_valid_category_alias, is_valid_cmeta_alias, parse_cmeta_name,
                               parse_cmeta_obj, parse_cmeta_ref, split_cmeta_name)

UID = '5ca1ab1e5ca1ab1e'
KIM = 'Kim Doe, joined Example Co, 20260922'


@pytest.mark.parametrize('name, expected', [
    # the forms of before
    ('alias', ('alias', '')),
    ('alias,' + UID, ('alias', UID)),
    (UID, ('', UID)),
    ('my-alias , ' + UID, ('my-alias', UID)),

    # an alias with commas, with and without its UID
    (KIM, (KIM, '')),
    (KIM + ',' + UID, (KIM, UID)),
    (KIM + ' , ' + UID + ' ', (KIM, UID)),
    ('a,b', ('a,b', '')),
    ('a, b, c', ('a, b, c', '')),

    # the UID in capitals: read and lower-cased
    (KIM + ',' + UID.upper(), (KIM, UID)),
    (UID.upper(), ('', UID)),

    # what is not a UID after the last comma stays in the alias
    ('a,' + UID[:15], ('a,' + UID[:15], '')),
    ('a,' + UID + 'f', ('a,' + UID + 'f', '')),
    ('a,g' + UID[1:], ('a,g' + UID[1:], '')),
    ('a,', ('a,', '')),
    ('a, ', ('a,', '')),

    # an alias that ends with a UID-like part, then its own UID: the last comma decides
    ('a,0123456789abcdef,' + UID, ('a,0123456789abcdef', UID)),
    (UID + ',' + UID, (UID, UID)),

    # no alias before the UID, and nothing at all
    (',' + UID, ('', UID)),
    ('', ('', '')),
    ('   ', ('', '')),
    (None, ('', '')),
])
def test_split_cmeta_name(name, expected):
    assert split_cmeta_name(name) == expected


def _old_parse_cmeta_name(name, key=None):
    """parse_cmeta_name as it was before split_cmeta_name (cMeta 0.45.2), to compare every answer with it."""
    from cmeta.utils.names import is_valid_cmeta_uid
    if isinstance(name, dict):
        return {'return': 0, 'name': name}
    if name is None:
        alias, uid = None, None
    else:
        name = name.strip()
        if not name:
            alias, uid = None, None
        elif is_valid_cmeta_uid(name):
            alias, uid = None, name.lower()
        else:
            i = name.rfind(",")
            if i != -1:
                left = name[:i].strip()
                right = name[i + 1:].strip()
                if is_valid_cmeta_uid(right):
                    alias, uid = left or None, right.lower()
                else:
                    alias, uid = name or None, None
            else:
                alias, uid = name or None, None
    result = {}
    if alias is not None and is_valid_cmeta_uid(alias):
        return {'return': 1, 'error': f"alias can't be a UID in {name}"}
    if key is not None:
        if alias is not None:
            result[f"{key}_alias"] = alias
        if uid is not None:
            result[f"{key}_uid"] = uid
    else:
        if alias is not None:
            result["alias"] = alias
        if uid is not None:
            result["uid"] = uid
    return {'return': 0, 'name': result}


def test_parse_cmeta_name_answers_as_before_for_every_combination():
    pieces = ['', ' ', 'a', 'Kim Doe', ',', ', ', ' ,', UID, UID.upper(), UID[:15], 'g' + UID[1:], '*', 'x y']
    names = {''.join(p) for n in range(1, 4) for p in itertools.product(pieces, repeat=n)}
    names.add(None)
    assert len(names) > 1000
    for name in names:
        for key in (None, 'artifact'):
            assert parse_cmeta_name(name, key) == _old_parse_cmeta_name(name, key), repr(name)


def test_parse_cmeta_name_keeps_commas_in_the_alias():
    assert parse_cmeta_name(KIM) == {'return': 0, 'name': {'alias': KIM}}
    assert parse_cmeta_name(KIM + ',' + UID.upper(), 'artifact') == {
        'return': 0, 'name': {'artifact_alias': KIM, 'artifact_uid': UID}}
    assert parse_cmeta_name(UID + ',' + UID)['return'] == 1          # an alias that is a UID: an error, as before


def test_parse_cmeta_ref_and_obj_with_commas_on_both_sides():
    r = parse_cmeta_ref('demo.person,0ddba11c0ddba11c::' + KIM + ',' + UID)
    assert r['ref_parts'] == {'category_alias': 'demo.person', 'category_uid': '0ddba11c0ddba11c',
                              'artifact_alias': KIM, 'artifact_uid': UID}
    r = parse_cmeta_ref('demo.person::demo:' + KIM)
    assert r['ref_parts'] == {'category_alias': 'demo.person', 'artifact_repo_alias': 'demo', 'artifact_alias': KIM}
    r = parse_cmeta_ref('my, category::a, b')
    assert r['ref_parts'] == {'category_alias': 'my, category', 'artifact_alias': 'a, b'}
    r = parse_cmeta_obj('my, repo,0123456789abcdef:' + KIM + ',' + UID, key='artifact')
    assert r['obj_parts'] == {'artifact_repo_alias': 'my, repo', 'artifact_repo_uid': '0123456789abcdef',
                              'artifact_alias': KIM, 'artifact_uid': UID}


@pytest.mark.parametrize('alias, expected', [
    ('a,' + UID, True),
    ('a, ' + UID.upper(), True),
    ('a,b,' + UID + ' ', True),
    (',' + UID, True),
    ('a', False),
    (UID, False),                                  # a bare UID is refused elsewhere (it reads as a UID)
    (KIM, False),
    ('a,' + UID[:15], False),
    ('a,' + UID + 'x', False),
    (UID + ',a', False),
    ('', False),
    (None, False),
])
def test_alias_ends_with_uid(alias, expected):
    assert alias_ends_with_uid(alias) is expected


def test_is_valid_cmeta_alias_takes_commas_but_not_a_uid_after_the_last_one():
    for good in (KIM, 'a,b', 'a, b, c', 'x,' + UID[:15], 'x,' + UID + 'f'):
        assert is_valid_cmeta_alias(good) == {'return': 0}, good
    for bad in ('a,' + UID, 'a, ' + UID.upper()):
        r = is_valid_cmeta_alias(bad)
        assert r['return'] == 1 and 'alias,UID' in r['error'], r

    # the checks of before stay
    assert is_valid_cmeta_alias('a/b')['return'] == 1
    assert is_valid_cmeta_alias(' a')['return'] == 1

    # a category's alias: the same rule, after its own checks
    assert is_valid_category_alias('my.category')['return'] == 0
    assert is_valid_category_alias('x,' + UID)['return'] == 1
