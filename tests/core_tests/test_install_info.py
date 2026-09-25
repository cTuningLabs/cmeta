"""
Tests for cmeta.utils.sys.describe_cmeta_install: how cMeta was installed, and the command
that updates it - for every install route the docs describe.

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

from cmeta.utils.sys import describe_cmeta_install, cmeta_install_info

EXE = r'C:\py\python.exe'
GIT_DEV = {'url': 'https://github.com/cTuningLabs/cmeta',
           'vcs_info': {'vcs': 'git', 'commit_id': 'abc', 'requested_revision': 'dev'}}
RECEIPT = ('[tool]\nrequirements = [{ name = "cmeta", extras = ["server"] }]\n'
           'entrypoints = [{ name = "cx", install-path = "/home/u/.local/bin/cx", from = "cmeta" }]\n')
RECEIPT_GIT = ('[tool]\nrequirements = [{ name = "cmeta", extras = ["server", "dev"], '
               'git = "https://github.com/cTuningLabs/cmeta?rev=dev" }]\n')


def test_uv_tool_from_pypi_upgrades_and_keeps_extras():
    i = describe_cmeta_install(installer='uv', receipt=RECEIPT, executable=EXE)
    assert i['method'] == 'uv tool' and i['source'] == 'pypi'
    assert i['update'] == ['uv tool upgrade cmeta']


def test_uv_tool_from_git_reinstalls_the_same_revision_with_its_extras():
    i = describe_cmeta_install(installer='uv', direct_url=GIT_DEV, receipt=RECEIPT_GIT, executable=EXE)
    assert i['label'] == 'uv tool, from git (dev)'
    assert i['update'] == ['uv tool install --force "cmeta[server,dev] @ git+https://github.com/cTuningLabs/cmeta@dev"']
    assert 'dev' in i['note']


def test_uv_tool_receipt_without_extras():
    receipt = '[tool]\nrequirements = [{ name = "cmeta" }]\n'
    i = describe_cmeta_install(installer='uv', direct_url=GIT_DEV, receipt=receipt)
    assert i['update'] == ['uv tool install --force "cmeta @ git+https://github.com/cTuningLabs/cmeta@dev"']


def test_uv_in_an_environment():
    i = describe_cmeta_install(installer='uv\n', executable=EXE)
    assert i['method'] == 'uv'
    assert i['update'] == ['uv pip install -U --python "%s" cmeta' % EXE]
    g = describe_cmeta_install(installer='uv', direct_url=GIT_DEV, executable=EXE)
    assert g['update'] == ['uv pip install --force-reinstall --python "%s" '
                           '"cmeta @ git+https://github.com/cTuningLabs/cmeta@dev"' % EXE]


def test_pip_from_pypi_and_from_git():
    i = describe_cmeta_install(installer='pip', executable=EXE)
    assert i['label'] == 'pip, from PyPI'
    assert i['update'] == ['"%s" -m pip install -U cmeta' % EXE]
    g = describe_cmeta_install(installer='pip', direct_url=GIT_DEV, executable=EXE)
    assert g['update'] == ['"%s" -m pip install --force-reinstall '
                           '"cmeta @ git+https://github.com/cTuningLabs/cmeta@dev"' % EXE]


def test_unknown_installer_is_treated_as_pip():
    assert describe_cmeta_install(installer='', executable=EXE)['method'] == 'pip'


def test_git_without_a_requested_revision():
    du = {'url': 'https://github.com/cTuningLabs/cmeta', 'vcs_info': {'vcs': 'git', 'commit_id': 'abc'}}
    i = describe_cmeta_install(installer='pip', direct_url=du, executable=EXE)
    assert i['update'] == ['"%s" -m pip install --force-reinstall "cmeta @ git+https://github.com/cTuningLabs/cmeta"' % EXE]
    assert i['note'] == ''


def test_editable_install_updates_the_checkout():
    du = {'url': 'file:///C:/work/cmeta', 'dir_info': {'editable': True}}
    i = describe_cmeta_install(installer='uv', direct_url=du, executable=EXE)
    assert i['method'] == 'editable'
    assert i['update'] == ['git -C "C:/work/cmeta" pull']


def test_non_editable_local_directory():
    du = {'url': 'file:///home/u/src/cmeta', 'dir_info': {}}
    i = describe_cmeta_install(installer='uv', direct_url=du, receipt=RECEIPT)
    assert i['source'] == 'local'
    assert i['update'] == ['uv tool install --force "cmeta[server] @ /home/u/src/cmeta"']
    assert 'directory' in i['note']


def test_running_from_a_checkout_and_frozen():
    s = describe_cmeta_install(source_dir='/home/u/cmeta')
    assert s['method'] == 'source' and s['update'] == ['git -C "/home/u/cmeta" pull']
    f = describe_cmeta_install(frozen=True)
    assert f['method'] == 'frozen' and f['update'] == []


def test_the_running_install_is_described():
    i = cmeta_install_info()
    assert i['return'] == 0 and i['label'] and isinstance(i['update'], list)
