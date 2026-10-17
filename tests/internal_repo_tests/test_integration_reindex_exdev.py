"""
Integration test of the full reindex where the index folder cannot be renamed (EXDEV): on overlayfs - a later step
of a Containerfile, or a container's entrypoint - a folder made in a lower layer of the image cannot be renamed, so
the swap of the new index for the old one (rename the old folder away, the new one in its place) failed with
"Invalid cross-device link" (seen 2026-10-16 building an app image on cmeta/ubuntu). The new index then replaces
the old one file by file: the reindex succeeds, the index holds exactly the files of the new one, nothing is left
behind, and a find answers from it.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import errno
import os

import pytest

from cmeta import CMeta
from cmeta.utils import files


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def test_a_full_reindex_on_overlayfs_replaces_the_index_file_by_file(cm, tmp_path, monkeypatch):
    # a repository with an artifact, plugged and indexed: the index folder exists ("a lower layer")
    repo = tmp_path / 'extra' / 'r1'
    (repo / 'log' / 'note-a').mkdir(parents=True)
    (repo / '_cmr.yaml').write_text('artifact: r1,a1b2c3d4e5f60718\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')
    (repo / 'log' / 'note-a' / '_cmeta.yaml').write_text('artifact: note-a,b1b2c3d4e5f60718\ncategory: log,f1b42d8e3e1a4b50\n',
                                                          encoding='utf-8')
    assert access(cm, category='repo', command='plug', arg1=str(repo))['return'] == 0

    index = tmp_path / 'index'
    assert index.is_dir()
    (index / 'stale-leftover.pkl').write_bytes(b'not a category any more')

    # a second artifact, so that the new index differs from the old one
    (repo / 'log' / 'note-b').mkdir(parents=True)
    (repo / 'log' / 'note-b' / '_cmeta.yaml').write_text('artifact: note-b,c1b2c3d4e5f60718\ncategory: log,f1b42d8e3e1a4b50\n',
                                                          encoding='utf-8')

    # overlayfs: renaming the index folder itself is refused, as for a folder of a lower image layer
    real_replace = files._replace_file
    refused = []

    def replace(src, dst, logger=None, timeout=None):
        if os.path.normcase(os.path.normpath(str(src))) == os.path.normcase(os.path.normpath(str(index))):
            refused.append(dst)
            raise OSError(errno.EXDEV, 'Invalid cross-device link', str(src))
        return real_replace(src, dst, logger, timeout)

    monkeypatch.setattr(files, '_replace_file', replace)

    r = access(cm, reindex=True)
    assert r['return'] == 0, r.get('error')
    assert refused, 'the reindex did not try to swap the index folder'

    # the index is the new one: no stale file, no temporary or old sibling left, and the new artifact is found
    assert not (index / 'stale-leftover.pkl').exists()
    assert not [n for n in os.listdir(tmp_path) if n.startswith('index.tmp-') or n.startswith('index.old-')]
    r = access(cm, category='log', command='find', arg1='r1:note-b')
    assert r['return'] == 0 and len(r['artifacts']) == 1, r
    r = access(cm, category='log', command='find', arg1='r1:note-a')
    assert r['return'] == 0 and len(r['artifacts']) == 1, r
