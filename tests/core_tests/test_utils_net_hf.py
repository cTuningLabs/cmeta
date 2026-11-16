"""
cmeta.utils.net: repositories of the Hugging Face Hub by its API - the names a repository is given as
(hf_repo), the token of the machine (hf_token), and a folder kept in step with a repository (hf_sync: what
changed is fetched and checked, what the repository dropped is removed, what was added locally stays).
"""

import hashlib
import json
import os

import pytest

from cmeta.utils import net


def test_the_names_of_a_hub_repository():
    assert net.hf_repo('hf://ctuning/cmeta-repo-ctuning-midatasets') == {'type': 'dataset', 'id': 'ctuning/cmeta-repo-ctuning-midatasets', 'revision': 'main'}
    assert net.hf_repo('hf://models/meta-llama/Llama-3.2-1B') == {'type': 'model', 'id': 'meta-llama/Llama-3.2-1B', 'revision': 'main'}
    assert net.hf_repo('hf://ctuning/x@v2') == {'type': 'dataset', 'id': 'ctuning/x', 'revision': 'v2'}
    assert net.hf_repo('https://huggingface.co/datasets/ctuning/x/tree/dev/sub') == {'type': 'dataset', 'id': 'ctuning/x', 'revision': 'dev'}
    assert net.hf_repo('https://huggingface.co/ctuning/some-model') == {'type': 'model', 'id': 'ctuning/some-model', 'revision': 'main'}
    assert net.hf_repo('https://huggingface.co/spaces/ctuning/FlexBoard') == {'type': 'space', 'id': 'ctuning/FlexBoard', 'revision': 'main'}
    for text in ('https://github.com/ctuning/x', 'hf://alone', 'hf://', 'ctuning/x', '', None):
        assert net.hf_repo(text) is None


def test_the_token_of_the_machine(monkeypatch, tmp_path):
    monkeypatch.delenv('HF_TOKEN', raising = False)
    monkeypatch.delenv('HUGGING_FACE_HUB_TOKEN', raising = False)
    monkeypatch.delenv('HF_TOKEN_PATH', raising = False)
    monkeypatch.setenv('HF_HOME', str(tmp_path / 'none'))
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    assert net.hf_token() is None
    (tmp_path / '.cache' / 'huggingface').mkdir(parents = True)
    (tmp_path / '.cache' / 'huggingface' / 'token').write_text('hf_from_file\n')
    assert net.hf_token() == 'hf_from_file'
    (tmp_path / 'home').mkdir()
    (tmp_path / 'home' / 'token').write_text('hf_from_home')
    monkeypatch.setenv('HF_HOME', str(tmp_path / 'home'))
    assert net.hf_token() == 'hf_from_home'
    monkeypatch.setenv('HF_TOKEN', 'hf_from_env')
    assert net.hf_token() == 'hf_from_env'


def blob_sha1(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def fake_hub(monkeypatch, contents, sha = 'c0ffee00'):
    """A Hub with these files: {path: (bytes, 'git' | 'lfs')}; downloads write the bytes."""
    def hf_files(repo_id, repo_type = 'dataset', revision = 'main', token = None):
        files = []
        for path, (data, kind) in contents.items():
            if kind == 'lfs':
                files.append({'path': path, 'size': len(data), 'oid': 'x' * 40, 'lfs': {'oid': hashlib.sha256(data).hexdigest(), 'size': len(data)}})
            else:
                files.append({'path': path, 'size': len(data), 'oid': blob_sha1(data), 'lfs': None})
        return {'return': 0, 'files': files, 'sha': sha}

    fetched = []

    def hf_fetch(repo_id, repo_type, revision, path, dest, token = None, expected = None):
        fetched.append(path)
        data = contents[path][0]
        if expected:
            lfs = expected.get('lfs')
            if lfs and lfs['oid'] != hashlib.sha256(data).hexdigest():
                return {'return': 1, 'error': f'{path}: digest'}
        os.makedirs(os.path.dirname(dest) or '.', exist_ok = True)
        with open(dest, 'wb') as f:
            f.write(data)
        return {'return': 0, 'size': len(data)}

    monkeypatch.setattr(net, 'hf_files', hf_files)
    monkeypatch.setattr(net, 'hf_fetch', hf_fetch)
    return fetched


def test_a_folder_is_made_from_a_repository_then_kept_in_step_with_it(monkeypatch, tmp_path):
    contents = {'_cmr.yaml': (b'artifact: x\n', 'git'), 'dataset/a/files/in/data.bin': (b'\x00' * 100, 'lfs'), 'README.md': (b'# x\n', 'git')}
    fetched = fake_hub(monkeypatch, contents)
    folder = tmp_path / 'repo'
    r = net.hf_sync('ctuning/x', 'dataset', 'main', str(folder), workers = 2)
    assert r['return'] == 0 and r['downloaded'] == 3 and r['removed'] == 0 and r['files'] == 3 and r['commit'] == 'c0ffee00'
    assert (folder / 'dataset' / 'a' / 'files' / 'in' / 'data.bin').read_bytes() == b'\x00' * 100
    record = json.loads((folder / net.HF_RECORD).read_text())
    assert record['repo'] == 'ctuning/x' and record['type'] == 'dataset' and record['commit'] == 'c0ffee00'
    assert set(record['files']) == set(contents) and record['files']['dataset/a/files/in/data.bin'] == hashlib.sha256(b'\x00' * 100).hexdigest()

    # The same repository again: nothing fetched; a file deleted locally comes back
    fetched.clear()
    assert net.hf_sync('ctuning/x', 'dataset', 'main', str(folder))['downloaded'] == 0 and fetched == []
    (folder / 'README.md').unlink()
    assert net.hf_sync('ctuning/x', 'dataset', 'main', str(folder))['downloaded'] == 1 and fetched == ['README.md']

    # The repository changed: one file new, one changed, one gone; a file added locally stays
    (folder / 'program.output' / 'mine').mkdir(parents = True)
    (folder / 'program.output' / 'mine' / 'case.json').write_text('{}')
    contents.clear()
    contents.update({'_cmr.yaml': (b'artifact: x\nnote: changed\n', 'git'), 'dataset/b/files/in/data.bin': (b'\x01' * 10, 'lfs'), 'README.md': (b'# x\n', 'git')})
    fetched.clear()
    r = net.hf_sync('ctuning/x', 'dataset', 'main', str(folder))
    assert r['downloaded'] == 2 and r['removed'] == 1 and sorted(fetched) == ['_cmr.yaml', 'dataset/b/files/in/data.bin']
    assert not (folder / 'dataset' / 'a').exists()                       # the empty folders went with the file
    assert (folder / 'dataset' / 'b' / 'files' / 'in' / 'data.bin').exists()
    assert (folder / 'program.output' / 'mine' / 'case.json').exists()  # added locally: kept
    assert (folder / '_cmr.yaml').read_bytes() == b'artifact: x\nnote: changed\n'


def test_a_wrong_digest_and_a_path_that_leaves_the_folder_are_refused(monkeypatch, tmp_path):
    contents = {'ok.txt': (b'ok', 'git'), 'big.bin': (b'\x02' * 5, 'lfs')}
    fetched = fake_hub(monkeypatch, contents)
    # The repository says another digest than the bytes it gives
    def hf_files_bad(repo_id, repo_type = 'dataset', revision = 'main', token = None):
        return {'return': 0, 'files': [{'path': 'big.bin', 'size': 5, 'oid': 'x', 'lfs': {'oid': 'f' * 64, 'size': 5}}], 'sha': 's'}
    monkeypatch.setattr(net, 'hf_files', hf_files_bad)
    r = net.hf_sync('ctuning/x', 'dataset', 'main', str(tmp_path / 'r1'))
    assert r['return'] > 0 and 'digest' in r['error']

    def hf_files_evil(repo_id, repo_type = 'dataset', revision = 'main', token = None):
        return {'return': 0, 'files': [{'path': '../outside.txt', 'size': 2, 'oid': blob_sha1(b'ok'), 'lfs': None}], 'sha': 's'}
    monkeypatch.setattr(net, 'hf_files', hf_files_evil)
    r = net.hf_sync('ctuning/x', 'dataset', 'main', str(tmp_path / 'r2'))
    assert r['return'] > 0 and 'leaves the folder' in r['error'] and not (tmp_path / 'outside.txt').exists()


def test_a_download_is_checked_against_the_digest_the_hub_names(monkeypatch, tmp_path):
    data = b'hello hub'
    def hf_get(url, token = None, timeout = 120, to_file = None):
        with open(to_file, 'wb') as f:
            f.write(data)
        return {'return': 0, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'sha1_blob': blob_sha1(data), 'headers': {}}
    monkeypatch.setattr(net, 'hf_get', hf_get)
    dest = tmp_path / 'f.txt'
    assert net.hf_fetch('ctuning/x', 'dataset', 'main', 'f.txt', str(dest), expected = {'oid': blob_sha1(data), 'lfs': None})['return'] == 0
    assert dest.read_bytes() == data
    assert net.hf_fetch('ctuning/x', 'dataset', 'main', 'f.txt', str(tmp_path / 'g.txt'), expected = {'oid': 'nope', 'lfs': None})['return'] > 0
    assert not (tmp_path / 'g.txt').exists() and not (tmp_path / 'g.txt.cmeta-part').exists()
    assert net.hf_fetch('ctuning/x', 'dataset', 'main', 'f.txt', str(tmp_path / 'h.txt'), expected = {'oid': 'x', 'lfs': {'oid': hashlib.sha256(data).hexdigest()}})['return'] == 0
