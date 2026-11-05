"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

What `info` prints and copies (2026-11-05): the reference {{{<category>::<alias>,<UID>}}} - how notes, memories and
docs name an artifact - and with --cref the full cRef=<category>,<UID>::<alias>,<UID> it printed up to 0.38.9;
--name and --url as before. Each test runs in a fresh CMETA_HOME; the clipboard is replaced by a list.
"""

import pytest

from cmeta import CMeta
import cmeta.utils.common


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    """A fresh CMeta bound to a temp CMETA_HOME, and what info copies collected instead of the clipboard."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    copied = []
    monkeypatch.setattr(cmeta.utils.common, 'copy_text_to_clipboard',
                        lambda text, **kwargs: copied.append(text) or {'return': 0})
    c = CMeta(home=str(tmp_path))
    c.copied = copied
    return c


def info(cm, capsys, **params):
    r = cm.access({'category': 'config', 'command': 'info', 'arg1': 'local:my-notes', 'con': True, **params})
    assert r['return'] == 0, r
    return capsys.readouterr().out


def test_info_prints_and_copies_the_braces_reference_and_cref_the_old_form(cm, capsys):
    r = cm.access({'category': 'config', 'command': 'add', 'arg1': 'local:my-notes', 'con': False})
    assert r['return'] == 0, r
    uid = r['meta']['artifact']
    cat_uid = r['meta']['category'].split(',')[-1]
    capsys.readouterr()

    # the default: {{{<category alias>::<alias>,<UID>}}}, printed on its own line and copied
    out = info(cm, capsys)
    braces = '{{{config::my-notes,' + uid + '}}}'
    assert braces in out.splitlines() and 'cRef=' not in out, out
    assert cm.copied[-1] == braces

    # --cref: the full cRef of before, printed and copied
    out = info(cm, capsys, cref=True)
    old = 'cRef=config,' + cat_uid + '::my-notes,' + uid
    assert old in out.splitlines() and '{{{' not in out, out
    assert cm.copied[-1] == old

    # --name copies the name, --clip- copies nothing; the parts are printed as before
    info(cm, capsys, name=True)
    assert cm.copied[-1] == 'my-notes,' + uid
    n = len(cm.copied)
    out = info(cm, capsys, clip=False)
    assert len(cm.copied) == n and braces in out.splitlines()
    assert 'artifact_uid: ' + uid in out.splitlines()
