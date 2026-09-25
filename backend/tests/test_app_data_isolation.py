"""Regression: backend tests never resolve app data to the real user's
%LOCALAPPDATA%\\Sorigul (Windows) or ~/.config/Sorigul (elsewhere), and the
temporary redirect is in place before any test module is collected.

Proven by comparing environment-derived path strings only -- real user
directories are never probed, listed, read or written.
"""

import importlib
import os
import sys
from pathlib import Path

import pytest

import conftest as isolation  # the instance pytest loaded before collection

ROUTES = "src.api.routes"

# Evaluated while this module is being collected.
LOCALAPPDATA_WHILE_THIS_MODULE_WAS_COLLECTED = os.environ.get("LOCALAPPDATA")
HOME_WHILE_THIS_MODULE_WAS_COLLECTED = os.environ.get("HOME")


def _norm(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _is_under(path, root) -> bool:
    path, root = _norm(path), _norm(root)
    return path == root or path.startswith(root.rstrip("\\/") + os.sep)


def _real_app_data_roots():
    """String-derived real locations (never touched on disk)."""
    roots = []
    if isolation.ORIGINAL_LOCALAPPDATA is not None:
        roots.append(Path(isolation.ORIGINAL_LOCALAPPDATA) / "Sorigul")
    if isolation.ORIGINAL_HOME is not None:
        roots.append(Path(isolation.ORIGINAL_HOME) / ".config" / "Sorigul")
    return roots


def _assert_not_real(path):
    for real in _real_app_data_roots():
        assert not _is_under(path, real), "resolved to the real user app data"


def _assert_routes_singletons_under(routes, sorigul: Path):
    assert _norm(routes.app_data_dir) == _norm(sorigul)
    assert _norm(routes.job_manager.storage_path) == _norm(sorigul / "jobs.json")
    paths = (
        routes.job_manager.storage_path,
        routes.settings_manager.storage_path,
        routes.drive_auth.token_path,
        routes.drive_auth.credential_path,
        routes.engine_resolver._cache_root,
    )
    for path in paths:
        assert _is_under(path, sorigul)
        _assert_not_real(path)


def test_redirect_was_established_before_any_module_collection(isolated_app_data_root):
    root = isolated_app_data_root
    assert _norm(LOCALAPPDATA_WHILE_THIS_MODULE_WAS_COLLECTED) == _norm(root)
    assert _norm(HOME_WHILE_THIS_MODULE_WAS_COLLECTED) == _norm(root)
    recorded = isolation.ENVIRONMENT_AT_MODULE_COLLECTION
    assert any(path.endswith("test_app_data_isolation.py") for path in recorded)
    for module_path, environment in recorded.items():
        for name, value in environment.items():
            assert value is not None and _norm(value) == _norm(root), (
                f"{module_path} was collected with {name} not redirected"
            )


def test_test_root_is_owned_temp_and_differs_from_originals(isolated_app_data_root):
    root = isolated_app_data_root
    assert Path(root).name.startswith("sorigul-test-appdata-")
    assert _norm(os.environ["LOCALAPPDATA"]) == _norm(root)
    assert _norm(os.environ["HOME"]) == _norm(root)
    for original in (isolation.ORIGINAL_LOCALAPPDATA, isolation.ORIGINAL_HOME):
        if original is not None:
            assert _norm(root) != _norm(original)
            assert not _is_under(root, original)


def test_routes_import_used_by_tests_is_isolated(isolated_app_data_root):
    import src.api.routes as routes

    _assert_routes_singletons_under(routes, Path(isolated_app_data_root) / "Sorigul")


def test_fresh_routes_import_resolves_under_temporary_localappdata(tmp_path, monkeypatch):
    import src.api as api_package

    temp_localappdata = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(temp_localappdata))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    # Fresh import; monkeypatch restores the previously imported module
    # (used by the other route tests) at teardown.
    monkeypatch.delitem(sys.modules, ROUTES, raising=False)
    monkeypatch.delattr(api_package, "routes", raising=False)

    routes = importlib.import_module(ROUTES)

    expected = (
        temp_localappdata / "Sorigul" if os.name == "nt" else tmp_path / "home" / ".config" / "Sorigul"
    )
    _assert_routes_singletons_under(routes, expected)
    assert _is_under(routes.job_manager.storage_path, tmp_path)


def test_get_app_data_dir_resolves_under_test_root(isolated_app_data_root):
    from src.utils.paths import get_app_data_dir

    resolved = get_app_data_dir()
    assert _is_under(resolved, isolated_app_data_root)
    _assert_not_real(resolved)


@pytest.mark.skipif(os.name == "nt", reason="exercises the non-Windows Path.home() fallback")
def test_non_windows_fallback_uses_redirected_home(isolated_app_data_root):
    from src.utils.paths import get_app_data_dir

    assert _norm(get_app_data_dir()) == _norm(Path(isolated_app_data_root) / ".config" / "Sorigul")
