"""
Tests for the pure helpers on cmeta.packages.Packages (no network / install).

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import pytest

from cmeta.packages import Packages, PackageResult


@pytest.fixture()
def pkgs():
    # allow_install=False so nothing can ever actually pip-install during tests.
    return Packages(allow_install=False)


# ---------------------------------------------------------------------------
# poetry_to_pep440
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec,expected", [
    ("^1.2.0", ">=1.2.0,<2.0"),
    ("^0.4.1", ">=0.4.1,<1.0"),
    ("~2",     ">=2,<3.0"),
    ("~2.3",   ">=2.3,<2.4"),
    ("1.*",    ">=1,<2"),
    ("1.2.*",  ">=1.2,<1.3"),
    (">=1.0",  ">=1.0"),                # already PEP440, returned as-is
    (">=3.14 <3.15", ">=3.14,<3.15"),   # space-separated multi-op → comma-joined
])
def test_poetry_to_pep440(pkgs, spec, expected):
    assert pkgs.poetry_to_pep440(spec) == expected


# ---------------------------------------------------------------------------
# build_spec
# ---------------------------------------------------------------------------

def test_build_spec_with_exact(pkgs):
    assert pkgs.build_spec("1.2.3", None, None, None) == "==1.2.3"


def test_build_spec_with_min_and_max(pkgs):
    assert pkgs.build_spec(None, "1.0", "2.0", None) == ">=1.0,<=2.0"


def test_build_spec_with_specifier_normalises_poetry(pkgs):
    assert pkgs.build_spec(None, None, None, "^1.2.0") == ">=1.2.0,<2.0"


def test_build_spec_combined(pkgs):
    assert pkgs.build_spec(None, "1.0", None, "^1.2.0") == ">=1.0,>=1.2.0,<2.0"


def test_build_spec_none_returns_none(pkgs):
    assert pkgs.build_spec(None, None, None, None) is None


# ---------------------------------------------------------------------------
# build_pip_requirement
# ---------------------------------------------------------------------------

def test_build_pip_requirement_bare_name(pkgs):
    assert pkgs.build_pip_requirement("numpy", None, None, None, None) == "numpy"


def test_build_pip_requirement_with_min_and_max(pkgs):
    assert pkgs.build_pip_requirement("numpy", None, "1.20", "2.0", None) == "numpy>=1.20,<=2.0"


def test_build_pip_requirement_with_specifier(pkgs):
    assert pkgs.build_pip_requirement("pydantic", None, None, None, "^2.0") == "pydantic>=2.0,<3.0"


# ---------------------------------------------------------------------------
# build_cache_key
# ---------------------------------------------------------------------------

def test_build_cache_key_is_deterministic(pkgs):
    k1 = pkgs.build_cache_key("numpy", None, "1.20", None, None, False)
    k2 = pkgs.build_cache_key("numpy", None, "1.20", None, None, False)
    assert k1 == k2
    assert "async=False" in k1


def test_build_cache_key_distinguishes_sync_and_async(pkgs):
    ks = pkgs.build_cache_key("numpy", None, "1.20", None, None, False)
    ka = pkgs.build_cache_key("numpy", None, "1.20", None, None, True)
    assert ks != ka


# ---------------------------------------------------------------------------
# try_import
# ---------------------------------------------------------------------------

def test_try_import_returns_module(pkgs):
    import json
    m = pkgs.try_import("json")
    assert m is json


def test_try_import_missing_returns_none(pkgs):
    assert pkgs.try_import("definitely-not-a-real-module-xyz") is None


# ---------------------------------------------------------------------------
# get() on an already-installed stdlib-ish package (packaging is a runtime dep)
# ---------------------------------------------------------------------------

def test_get_returns_package_result_for_installed_package(pkgs):
    r = pkgs.get("packaging")
    assert r['return'] == 0
    pr = r['package']
    assert isinstance(pr, PackageResult)
    assert pr.name == "packaging"
    assert pr.installed_now is False
    assert pr.satisfies is True


def test_get_uses_cache_on_second_call(pkgs):
    r1 = pkgs.get("packaging")
    r2 = pkgs.get("packaging")
    assert r1['package'] is r2['package']    # same cached object


def test_get_missing_package_returns_error_when_install_disabled(pkgs):
    r = pkgs.get("definitely-not-a-real-pkg-xyz")
    assert r['return'] == 1
    assert 'pip install failed' in r['error']
