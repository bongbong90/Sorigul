"""#195: settings changes are opt-in for existing profiles, never migration."""
import json

import pytest

from src.services.settings import CloseBehavior, RuntimeSettings, SettingsManager, SettingsPatch


def test_new_profile_defaults_to_idle_exit_without_writing(tmp_path):
    path = tmp_path / "settings.json"
    assert RuntimeSettings().close_behavior == CloseBehavior.EXIT
    assert SettingsManager(path).get().close_behavior == CloseBehavior.EXIT
    assert not path.exists()


@pytest.mark.parametrize("stored", ["tray", "exit"])
def test_existing_saved_policy_is_preserved_byte_for_byte(tmp_path, stored):
    path = tmp_path / "settings.json"
    original = json.dumps({"close_behavior": stored, "last_subject": "synthetic"}, indent=3).encode()
    path.write_bytes(original)
    manager = SettingsManager(path)
    assert manager.get().close_behavior.value == stored
    assert path.read_bytes() == original
    manager.update(SettingsPatch(last_course="synthetic"))
    assert SettingsManager(path).get().close_behavior.value == stored
    assert not list(tmp_path.glob("settings.corrupt.*"))


def test_profile_without_stored_policy_gets_new_default_without_rewrite(tmp_path):
    path = tmp_path / "settings.json"
    original = b'{"notifications":{"file_complete":false,"job_complete":true}}'
    path.write_bytes(original)
    manager = SettingsManager(path)
    assert manager.get().close_behavior == CloseBehavior.EXIT
    assert not manager.get().notifications.file_complete
    assert path.read_bytes() == original


def test_explicit_tray_remains_an_available_choice_for_new_profile(tmp_path):
    path = tmp_path / "settings.json"
    SettingsManager(path).update(SettingsPatch(close_behavior="tray"))
    assert SettingsManager(path).get().close_behavior == CloseBehavior.TRAY
