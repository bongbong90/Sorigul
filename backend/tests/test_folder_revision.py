"""Issue #111: selected transcription-folder live-change revision.

The revision is a metadata-only, top-level, read-only probe. Only changes to
MP3/TXT/JSON/SRT regular files in the selected folder itself may change it.
"""

import os

import pytest
from fastapi.testclient import TestClient

from src.services.folder_revision import folder_revision

ROUTE = "/api/folders/revision"


def rev(folder):
    return folder_revision(str(folder)).revision


def bump_mtime(path, delta_ns=5_000_000_000):
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + delta_ns))


def test_empty_folder_revision_is_stable(tmp_path):
    first = folder_revision(str(tmp_path))
    assert first.file_count == 0
    assert first.revision == rev(tmp_path)


def test_same_state_repeated_gives_same_revision(tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"audio")
    (tmp_path / "a.txt").write_text("text", encoding="utf-8")
    assert rev(tmp_path) == rev(tmp_path) == rev(tmp_path)


def test_mp3_add_remove_and_modify_change_revision(tmp_path):
    empty = rev(tmp_path)
    mp3 = tmp_path / "lecture.mp3"
    mp3.write_bytes(b"audio")
    added = rev(tmp_path)
    assert added != empty

    mp3.write_bytes(b"audio-longer")
    resized = rev(tmp_path)
    assert resized != added

    bump_mtime(mp3)
    touched = rev(tmp_path)
    assert touched != resized

    mp3.unlink()
    assert rev(tmp_path) == empty


@pytest.mark.parametrize("extension", [".txt", ".json", ".srt", ".TXT", ".Json"])
def test_result_file_add_modify_remove_change_revision(tmp_path, extension):
    (tmp_path / "lecture.mp3").write_bytes(b"audio")
    before = rev(tmp_path)
    result = tmp_path / f"lecture{extension}"

    result.write_text("one", encoding="utf-8")
    added = rev(tmp_path)
    assert added != before

    result.write_text("one-two", encoding="utf-8")
    modified = rev(tmp_path)
    assert modified != added

    result.unlink()
    assert rev(tmp_path) == before


@pytest.mark.parametrize("name", ["notes.pdf", ".lecture.abc.txt.tmp", "run.log", "cover.png"])
def test_irrelevant_extensions_are_ignored(tmp_path, name):
    (tmp_path / "lecture.mp3").write_bytes(b"audio")
    before = folder_revision(str(tmp_path))
    other = tmp_path / name
    other.write_bytes(b"x")
    assert rev(tmp_path) == before.revision
    other.write_bytes(b"xyz")
    bump_mtime(other)
    assert rev(tmp_path) == before.revision
    other.unlink()
    assert folder_revision(str(tmp_path)).file_count == before.file_count == 1


def test_nested_subfolder_changes_are_not_scanned(tmp_path):
    (tmp_path / "lecture.mp3").write_bytes(b"audio")
    nested = tmp_path / "archive"
    nested.mkdir()
    before = rev(tmp_path)

    (nested / "old.mp3").write_bytes(b"audio")
    (nested / "old.txt").write_text("text", encoding="utf-8")
    deeper = nested / "deeper"
    deeper.mkdir()
    (deeper / "x.json").write_text("{}", encoding="utf-8")
    assert rev(tmp_path) == before


def test_directory_named_like_result_is_ignored(tmp_path):
    before = folder_revision(str(tmp_path))
    (tmp_path / "looks-like.mp3").mkdir()
    (tmp_path / "folder.txt").mkdir()
    after = folder_revision(str(tmp_path))
    assert after == before
    assert after.file_count == 0


def test_symlinked_entries_are_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "secret.mp3"
    target.write_bytes(b"audio")
    selected = tmp_path / "selected"
    selected.mkdir()
    before = rev(selected)
    try:
        os.symlink(target, selected / "link.mp3")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not permitted on this host")
    assert rev(selected) == before
    target.write_bytes(b"audio-changed")
    assert rev(selected) == before


def test_unicode_korean_and_spaced_filenames_are_stable(tmp_path):
    folder = tmp_path / "전사 자료" / "개념완성 민법"
    folder.mkdir(parents=True)
    long_stem = "민법 총칙 제1강 " + "가" * 120
    (folder / f"{long_stem}.mp3").write_bytes(b"audio")
    (folder / "민법 1주차 1강.txt").write_text("본문", encoding="utf-8")
    first = folder_revision(str(folder))
    assert first.file_count == 2
    assert first.revision == rev(folder)

    (folder / "민법 1주차 1강.srt").write_text("", encoding="utf-8")
    assert rev(folder) != first.revision


def test_missing_and_non_directory_raise(tmp_path):
    with pytest.raises(FileNotFoundError):
        folder_revision(str(tmp_path / "missing"))
    plain = tmp_path / "plain.mp3"
    plain.write_bytes(b"audio")
    with pytest.raises(NotADirectoryError):
        folder_revision(str(plain))


def test_revision_does_not_read_file_contents(tmp_path, monkeypatch):
    (tmp_path / "a.mp3").write_bytes(b"audio")
    (tmp_path / "a.json").write_text("{not json", encoding="utf-8")

    def forbidden_open(*args, **kwargs):
        raise AssertionError("revision must not open files")

    import builtins
    monkeypatch.setattr(builtins, "open", forbidden_open)
    monkeypatch.setattr(os, "open", forbidden_open)
    assert folder_revision(str(tmp_path)).file_count == 2


def _client(tmp_path, monkeypatch):
    import src.api.routes as routes
    from src.main import app
    from src.services.job_manager import JobManager

    manager = JobManager(str(tmp_path / "jobs.json"))
    monkeypatch.setattr(routes, "job_manager", manager)
    return TestClient(app, base_url="http://127.0.0.1:8000"), manager


def test_revision_api_returns_revision_without_side_effects(tmp_path, monkeypatch):
    client, manager = _client(tmp_path, monkeypatch)
    folder = tmp_path / "전사자료"
    folder.mkdir()
    (folder / "새 강의.mp3").write_bytes(b"audio")
    listing_before = sorted(path.name for path in folder.iterdir())

    first = client.post(ROUTE, json={"folder": str(folder)})
    second = client.post(ROUTE, json={"folder": str(folder)})

    assert first.status_code == 200
    body = first.json()
    assert set(body) == {"revision", "file_count"}
    assert body["file_count"] == 1
    assert second.json() == body
    assert manager.list_jobs() == []
    assert sorted(path.name for path in folder.iterdir()) == listing_before


def test_revision_api_missing_and_not_directory_are_safe_400(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    plain = tmp_path / "plain.txt"
    plain.write_text("x", encoding="utf-8")

    for target in (tmp_path / "missing", plain):
        response = client.post(ROUTE, json={"folder": str(target)})
        assert response.status_code == 400
        assert response.json() == {"detail": "전사 폴더를 읽을 수 없습니다."}
