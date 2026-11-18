"""
Tests for a package whose module is not named as its distribution (python-dotenv is imported as dotenv): the import
name given outright (import_name), or found from the installed distribution's own record - no pip run for what is
installed, the version from the distribution when the module carries none - and nothing changed for a name that
imports as it is.

Each test makes its own throwaway distribution in tmp_path (a module folder and a .dist-info beside it).

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import asyncio
import importlib
import sys

import pytest

from cmeta.packages import Packages


def make_dist(root, dist, version, module, top_level=True, module_version=None):
    """A distribution `dist` that provides `module`, as pip would leave it in a site folder."""
    pkg = root / module
    pkg.mkdir()
    (pkg / '__init__.py').write_text('' if module_version is None else '__version__ = %r\n' % module_version, encoding='utf-8')
    info = root / ('%s-%s.dist-info' % (dist.replace('-', '_'), version))
    info.mkdir()
    (info / 'METADATA').write_text('Metadata-Version: 2.1\nName: %s\nVersion: %s\n' % (dist, version), encoding='utf-8')
    (info / 'RECORD').write_text('%s/__init__.py,,\n%s/METADATA,,\n%s/RECORD,,\n' % (module, info.name, info.name), encoding='utf-8')
    if top_level:
        (info / 'top_level.txt').write_text(module + '\n', encoding='utf-8')


@pytest.fixture()
def site(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    yield tmp_path
    for name in [m for m in sys.modules if m.startswith('cmeta_probe_mod')]:
        del sys.modules[name]
    importlib.invalidate_caches()


@pytest.fixture()
def packages(monkeypatch):
    p = Packages()
    calls = []
    monkeypatch.setattr(p, 'pip_install_sync', lambda *a, **k: calls.append(a[0]))
    p.pip_calls = calls
    return p


def test_a_distribution_installed_under_another_module_name_is_found_without_pip(site, packages):
    make_dist(site, 'cmeta-probe-dist-a', '1.2.3', 'cmeta_probe_mod_a')

    assert packages.import_names('cmeta-probe-dist-a') == ['cmeta_probe_mod_a']
    r = packages.get('cmeta-probe-dist-a')
    assert r['return'] == 0, r
    assert r['package'].module.__name__ == 'cmeta_probe_mod_a'
    assert r['package'].name == 'cmeta-probe-dist-a' and r['package'].version == '1.2.3'       # the distribution's version
    assert r['package'].installed_now is False and packages.pip_calls == []                  # nothing was installed

    # a version asked is checked against the distribution's
    assert packages.get('cmeta-probe-dist-a', version_min='1.0', use_cache=False)['return'] == 0
    r = packages.get('cmeta-probe-dist-a', version_min='2.0', use_cache=False)
    assert r['return'] == 1 and 'does NOT satisfy' in r['error'], r


def test_the_module_is_found_from_the_files_when_the_record_has_no_top_level(site, packages):
    make_dist(site, 'cmeta-probe-dist-b', '0.5', 'cmeta_probe_mod_b', top_level=False)

    assert packages.import_names('cmeta-probe-dist-b') == ['cmeta_probe_mod_b']
    r = packages.get('cmeta-probe-dist-b', allow_install=False)
    assert r['return'] == 0 and r['package'].module.__name__ == 'cmeta_probe_mod_b' and r['package'].version == '0.5', r


def test_import_name_says_the_module_outright(site, packages):
    make_dist(site, 'cmeta-probe-dist-c', '3.0', 'cmeta_probe_mod_c', module_version='3.0.1')

    r = packages.get('cmeta-probe-dist-c', import_name='cmeta_probe_mod_c', allow_install=False)
    assert r['return'] == 0 and r['package'].module.__name__ == 'cmeta_probe_mod_c', r
    assert r['package'].version == '3.0.1'                                                    # the module's own, as before

    # a module name that is not there: never the distribution's other modules instead
    r = packages.get('cmeta-probe-dist-c', import_name='cmeta_probe_mod_missing', allow_install=False)
    assert r['return'] == 1 and 'missing; installation disabled' in r['error'], r

    # the settings of get_all take it too
    r = packages.get_all({'cmeta-probe-dist-c': {'import_name': 'cmeta_probe_mod_c', 'allow_install': False}})
    assert r['return'] == 0 and r['mpkg']['cmeta-probe-dist-c'].__name__ == 'cmeta_probe_mod_c', r


def test_a_name_that_imports_as_it_is_works_as_before(packages):
    r = packages.get('json', allow_install=False)
    assert r['return'] == 0 and r['package'].module.__name__ == 'json' and r['package'].name == 'json', r
    assert packages.import_names('cmeta-probe-no-such-distribution') == []
    assert packages.pip_calls == []


def test_what_is_not_installed_is_installed_by_its_name_and_the_error_says_what_to_do(site, packages):
    # nothing installed, installation off: as before
    r = packages.get('cmeta-probe-dist-d', allow_install=False)
    assert r['return'] == 1 and "Package 'cmeta-probe-dist-d' missing; installation disabled" in r['error'], r

    # installation on: pip is asked for the distribution by its own name; here it "installs" the distribution under
    # another module name, which is then found
    def install(requirement, *args, **kwargs):
        packages.pip_calls.append(requirement)
        make_dist(site, 'cmeta-probe-dist-d', '7.1', 'cmeta_probe_mod_d')
    packages.pip_install_sync = install
    r = packages.get('cmeta-probe-dist-d', allow_install=True)
    assert r['return'] == 0 and r['package'].installed_now is True and r['package'].version == '7.1', r
    assert packages.pip_calls == ['cmeta-probe-dist-d']

    # an installation that brings nothing importable: the error names the way out
    packages.pip_install_sync = lambda *a, **k: None
    r = packages.get('cmeta-probe-dist-e', allow_install=True)
    assert r['return'] == 1 and 'cannot import it (name its module with import_name)' in r['error'], r
    r = packages.get('cmeta-probe-dist-e', import_name='cmeta_probe_mod_e', allow_install=True)
    assert r['return'] == 1 and "cannot import it as 'cmeta_probe_mod_e'" in r['error'], r


def test_the_async_get_does_the_same(site):
    make_dist(site, 'cmeta-probe-dist-f', '2.4', 'cmeta_probe_mod_f')
    p = Packages()

    r = asyncio.run(p.get_async('cmeta-probe-dist-f', allow_install=False))
    assert r['return'] == 0 and r['package'].module.__name__ == 'cmeta_probe_mod_f' and r['package'].version == '2.4', r
    r = asyncio.run(p.get_async('cmeta-probe-dist-f', import_name='cmeta_probe_mod_f', allow_install=False, use_cache=False))
    assert r['return'] == 0, r
    r = asyncio.run(p.get_async('cmeta-probe-dist-f', import_name='cmeta_probe_mod_missing', allow_install=False))
    assert r['return'] == 1 and 'missing; installation disabled' in r['error'], r


def test_a_real_distribution_named_unlike_its_module():
    pytest.importorskip('dotenv')
    r = Packages().get('python-dotenv', allow_install=False)
    assert r['return'] == 0 and r['package'].module.__name__ == 'dotenv' and r['package'].version, r
