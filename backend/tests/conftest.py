"""Backend test user-data isolation, established before test collection.

`src.api.routes` builds its JobManager / SettingsManager / OAuth / Colab
cache singletons from `get_app_data_dir()` the moment it is first imported:
%LOCALAPPDATA%\\Sorigul on Windows, ~/.config/Sorigul elsewhere. Backend
tests must never read, write or quarantine the real user's app data, so the
redirect happens in `pytest_configure`:

* This conftest is always imported before any test module in this directory
  is collected, and `pytest_configure` is a historic hook -- it runs for an
  initial conftest before the session starts, and for a conftest discovered
  later immediately upon registration. Either way it precedes the import of
  every sibling test module, so even a collection-time `src.api.routes`
  import can only ever see the temporary root.
* `LOCALAPPDATA` (Windows) and `HOME` (the non-Windows `Path.home()`
  fallback) both point at one test-run-owned `tempfile.mkdtemp` root.
  Product source and Windows release behaviour are unchanged.
* `pytest_unconfigure` restores the original environment strings and removes
  exactly that owned root -- nothing else.

The collection guard below is defense-in-depth only: it flags a
module-level routes import as a test-architecture violation, even though
such an import would already resolve under the temporary root.

Only environment strings are recorded; real user directories are never probed.
"""

import os
import shutil
import sys
import tempfile

import pytest

ROUTES_MODULE = "src.api.routes"
REDIRECTED_VARIABLES = ("LOCALAPPDATA", "HOME")

# Original environment strings, captured before the redirect (comparison only).
ORIGINAL_ENVIRONMENT = {name: os.environ.get(name) for name in REDIRECTED_VARIABLES}
ORIGINAL_LOCALAPPDATA = ORIGINAL_ENVIRONMENT["LOCALAPPDATA"]
ORIGINAL_HOME = ORIGINAL_ENVIRONMENT["HOME"]

# The exact root this test run created; set in pytest_configure.
TEST_APP_DATA_ROOT = None

# LOCALAPPDATA / HOME as seen when each test module was collected.
ENVIRONMENT_AT_MODULE_COLLECTION = {}


def pytest_configure(config):
    global TEST_APP_DATA_ROOT
    if TEST_APP_DATA_ROOT is not None:
        return
    TEST_APP_DATA_ROOT = tempfile.mkdtemp(prefix="sorigul-test-appdata-")
    for name in REDIRECTED_VARIABLES:
        os.environ[name] = TEST_APP_DATA_ROOT


def pytest_unconfigure(config):
    global TEST_APP_DATA_ROOT
    root = TEST_APP_DATA_ROOT
    if root is None:
        return
    for name, value in ORIGINAL_ENVIRONMENT.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    # Only the exact directory mkdtemp created for this run.
    shutil.rmtree(root, ignore_errors=True)
    TEST_APP_DATA_ROOT = None


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(module_path, parent):
    ENVIRONMENT_AT_MODULE_COLLECTION[str(module_path)] = {
        name: os.environ.get(name) for name in REDIRECTED_VARIABLES
    }


def pytest_collection_finish(session):
    # Defense-in-depth: data is already safe (see module docstring); this only
    # reports a module-level routes import as an architecture violation.
    if ROUTES_MODULE in sys.modules:
        raise pytest.UsageError(
            f"{ROUTES_MODULE} was imported during test collection; import it "
            "inside a test or fixture instead."
        )


@pytest.fixture(scope="session")
def isolated_app_data_root():
    assert TEST_APP_DATA_ROOT is not None, "app-data isolation was not established"
    return TEST_APP_DATA_ROOT
