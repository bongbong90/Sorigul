"""#180 manual week input + Eduwill no-week filename normalization.

The canonical name stays {과정명}_{과목명}_{N}주차_{M}강. The Legacy detector
(detect_week_lesson) is unchanged; the manually entered week is a separate
fallback layer that only applies to a name with no explicit week and exactly
one standalone course-wide "N강" counter. That counter is never a week and
never the lesson within a week.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.domain.models import FileMetadata
from src.services.drive import DriveClassifier
from src.services.job_manager import JobManager
from src.services.normalizer import (
    DetectionMode,
    FilenameNormalizer,
    ManualWeekValidationError,
    collect_existing_stems,
    detect_week_lesson,
    has_global_lecture_counter,
    validate_manual_week,
)
from src.services.renamer import BundleRenamer, RenameStatus
from src.services.settings import SettingsManager

COURSE = "기초이론"
SUBJECT = "부동산학개론"
EDUWILL = [
    "2026_이영방_부동산학개론_기초이론_2강.mp3",
    "2026_이영방_부동산학개론_기초이론_3강.mp3",
    "2026_이영방_부동산학개론_기초이론_4강.mp3",
]
BUNDLE_EXTENSIONS = (".mp3", ".txt", ".json", ".srt")


def _stem(week, lesson, course=COURSE, subject=SUBJECT):
    return f"{course}_{subject}_{week}주차_{lesson}강"


def _normalize(name, week, existing=frozenset(), course=COURSE, subject=SUBJECT):
    return FilenameNormalizer().normalize(name, course, subject, set(existing), week)


def _batch(names, week, existing=frozenset()):
    return FilenameNormalizer().normalize_batch(names, COURSE, SUBJECT, set(existing), week)


# ---------------------------------------------------------------------------
# Legacy detector is untouched; the fallback is a separate layer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["13강 민법", *[Path(n).stem for n in EDUWILL]])
def test_legacy_detector_still_finds_no_week_in_global_counter_names(text):
    detection = detect_week_lesson(text)
    assert (detection.week, detection.preferred_lesson, detection.mode) == (None, None, DetectionMode.UNKNOWN)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2026_이영방_부동산학개론_기초이론_4강", True),
        ("13강 민법", True),
        ("[13강] 민법", True),
        ("민법 0강 오리엔테이션", True),
        ("민법 특강", False),
        ("민법 강의", False),
        ("3강의 요약", False),
        ("3강 4강 합본", False),
        ("2026_이영방_부동산학개론", False),
    ],
)
def test_global_lecture_counter_must_be_a_single_standalone_token(text, expected):
    assert has_global_lecture_counter(text) is expected


@pytest.mark.parametrize(
    "original",
    ["민법 특강.mp3", "아무개_강의_녹음본.mp3", "3강 4강 합본.mp3", "2026_이영방_부동산학개론.mp3"],
)
def test_names_without_any_lecture_number_stay_invalid_even_with_manual_week(original):
    preview = _normalize(original, 1)
    assert preview.result_type == "INVALID_TARGET"
    assert preview.suggested_name is None
    assert (preview.detected_week, preview.detected_lesson) == (None, None)
    assert preview.manual_week == "1"


def test_global_counter_only_name_is_invalid_without_manual_week():
    for name in ["13강 민법.mp3", *EDUWILL]:
        assert _normalize(name, None).result_type == "INVALID_TARGET"


def test_global_counter_only_name_uses_manual_week_first_free_lesson():
    preview = _normalize("13강 민법.mp3", 5, course="개념완성", subject="민법")
    assert preview.result_type == "NORMALIZED"
    assert preview.suggested_name == "개념완성_민법_5주차_1강.mp3"


# ---------------------------------------------------------------------------
# Exact Eduwill fixture: allocation, never week, never local lesson
# ---------------------------------------------------------------------------

def test_single_eduwill_file_takes_first_free_lesson_of_manual_week():
    preview = _normalize(EDUWILL[2], 1)
    assert preview.result_type == "NORMALIZED"
    assert preview.can_apply is True
    assert preview.suggested_name == f"{_stem(1, 1)}.mp3"
    assert (preview.detected_week, preview.detected_lesson) == ("1", "1")
    # "4강" is neither the week nor the lesson within the week.
    assert preview.suggested_name not in {f"{_stem(4, 1)}.mp3", f"{_stem(1, 4)}.mp3"}


def test_eduwill_batch_in_empty_week_takes_lessons_one_to_three():
    previews = _batch(EDUWILL, 1)
    assert [p.result_type for p in previews] == ["NORMALIZED"] * 3
    assert [p.suggested_name for p in previews] == [f"{_stem(1, n)}.mp3" for n in (1, 2, 3)]
    assert [p.original_name for p in previews] == EDUWILL


def test_eduwill_batch_is_stable_for_the_same_order():
    assert [p.suggested_name for p in _batch(EDUWILL, 1)] == [p.suggested_name for p in _batch(EDUWILL, 1)]


def test_eduwill_batch_keeps_request_order_and_never_resorts_by_counter():
    reordered = [EDUWILL[2], EDUWILL[0], EDUWILL[1]]
    previews = _batch(reordered, 1)
    assert [p.original_name for p in previews] == reordered
    assert [p.suggested_name for p in previews] == [f"{_stem(1, n)}.mp3" for n in (1, 2, 3)]


def test_eduwill_batch_skips_an_occupied_first_lesson():
    previews = _batch(EDUWILL, 1, {_stem(1, 1)})
    assert [p.suggested_name for p in previews] == [f"{_stem(1, n)}.mp3" for n in (2, 3, 4)]


def test_eduwill_batch_fills_gaps_before_appending():
    previews = _batch(EDUWILL, 1, {_stem(1, 1), _stem(1, 3)})
    assert [p.suggested_name for p in previews] == [f"{_stem(1, n)}.mp3" for n in (2, 4, 5)]


def test_eduwill_allocation_ignores_other_weeks_courses_and_subjects():
    existing = {_stem(2, 1), _stem(1, 1, course="개념완성"), _stem(1, 1, subject="민법")}
    assert _normalize(EDUWILL[0], 1, existing).suggested_name == f"{_stem(1, 1)}.mp3"


@pytest.mark.parametrize("extension", BUNDLE_EXTENSIONS)
def test_any_bundle_extension_occupies_the_eduwill_target(tmp_path, extension):
    (tmp_path / f"{_stem(1, 1)}{extension}").write_text("x", encoding="utf-8")
    preview = _normalize(EDUWILL[0], 1, collect_existing_stems(tmp_path))
    assert preview.suggested_name == f"{_stem(1, 2)}.mp3"


# ---------------------------------------------------------------------------
# Explicit source week == manual week: Legacy behavior unchanged
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "original, occupied",
    [
        ("[4-1] 시장론.mp3", []),
        ("[4-1] 시장론.mp3", [1]),
        ("4주차 3강 민법.mp3", []),
        ("4주차 3강 민법.mp3", [3]),
        ("[4주차] 민법 특강.mp3", [1, 2]),
        ("13강_[4주차]_민법 물권.mp3", []),
        ("13강_[4-2] 민법.mp3", [2]),
        (f"{_stem(4, 3)}.mp3", []),
    ],
)
def test_matching_explicit_week_behaves_exactly_like_legacy(original, occupied):
    existing = {_stem(4, n) for n in occupied}
    legacy = _normalize(original, None, existing)
    manual = _normalize(original, 4, existing)
    assert (manual.result_type, manual.suggested_name, manual.detected_week, manual.detected_lesson) == (
        legacy.result_type, legacy.suggested_name, legacy.detected_week, legacy.detected_lesson
    )


def test_leading_global_counter_with_explicit_week_is_never_the_lesson():
    preview = _normalize("13강_[4주차]_민법 물권.mp3", 4)
    assert preview.suggested_name == f"{_stem(4, 1)}.mp3"
    assert preview.suggested_name != f"{_stem(4, 13)}.mp3"


def test_matching_standard_name_stays_protected():
    preview = _normalize(f"{_stem(4, 3)}.mp3", 4)
    assert preview.result_type == "UNCHANGED"
    assert preview.can_apply is False
    assert preview.suggested_name == f"{_stem(4, 3)}.mp3"


# ---------------------------------------------------------------------------
# Explicit source week != manual week: WEEK_MISMATCH, never silent
# ---------------------------------------------------------------------------

def test_week_and_lesson_source_with_other_manual_week_is_week_mismatch():
    preview = _normalize("4주차 3강 민법.mp3", 5)
    assert preview.result_type == "WEEK_MISMATCH"
    assert preview.can_apply is False
    assert preview.suggested_name == "4주차 3강 민법.mp3"  # never renamed implicitly
    assert (preview.detected_week, preview.detected_lesson, preview.manual_week) == ("4", "3", "5")
    assert preview.typed_target_name == f"{_stem(5, 3)}.mp3"
    assert any("4주차" in w and "5주차" in w for w in preview.warnings)


def test_week_mismatch_target_keeps_source_lesson_then_next_free():
    preview = _normalize("4주차 3강 민법.mp3", 5, {_stem(5, 3), _stem(5, 4)})
    assert preview.typed_target_name == f"{_stem(5, 5)}.mp3"


def test_week_only_source_mismatch_targets_first_free_manual_lesson():
    preview = _normalize("13강_[4주차]_민법 물권.mp3", 5, {_stem(5, 1)})
    assert preview.result_type == "WEEK_MISMATCH"
    assert (preview.detected_week, preview.detected_lesson) == ("4", None)
    assert preview.typed_target_name == f"{_stem(5, 2)}.mp3"


def test_bracket_source_mismatch_is_week_mismatch():
    preview = _normalize("[4-2] 시장론.mp3", 1)
    assert preview.result_type == "WEEK_MISMATCH"
    assert (preview.detected_week, preview.detected_lesson) == ("4", "2")
    assert preview.typed_target_name == f"{_stem(1, 2)}.mp3"


def test_standard_name_with_other_week_is_week_mismatch_not_unchanged():
    preview = _normalize(f"{_stem(4, 3)}.mp3", 5)
    assert preview.result_type == "WEEK_MISMATCH"
    assert preview.suggested_name == f"{_stem(4, 3)}.mp3"
    assert preview.typed_target_name == f"{_stem(5, 3)}.mp3"


def test_course_subject_mismatch_stays_mismatch_and_states_week_difference():
    preview = _normalize("개념완성_민법_4주차_3강.mp3", 5)
    assert preview.result_type == "MISMATCH"
    assert (preview.detected_course, preview.detected_subject) == ("개념완성", "민법")
    assert preview.suggested_name == "개념완성_민법_4주차_3강.mp3"
    assert preview.typed_target_name == f"{_stem(5, 3)}.mp3"
    assert any("4주차" in w and "5주차" in w for w in preview.warnings)


def test_week_mismatch_does_not_reserve_its_proposed_target_in_a_batch():
    previews = _batch(["4주차 1강 민법.mp3", EDUWILL[0]], 5)
    assert previews[0].result_type == "WEEK_MISMATCH"
    assert previews[1].suggested_name == f"{_stem(5, 1)}.mp3"


# ---------------------------------------------------------------------------
# Manual week validation (backend never trusts the frontend)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [None, 0, -1, True])
def test_validate_manual_week_rejects_missing_or_non_positive(value):
    with pytest.raises(ManualWeekValidationError):
        validate_manual_week(value)


def test_validate_manual_week_accepts_positive_integers():
    assert validate_manual_week(1) == 1
    assert validate_manual_week(52) == 52


@pytest.mark.parametrize("value", ["4", "1주차", 4.0, 1.5, True])
@pytest.mark.parametrize("model_name", ["NormalizeRequest", "NormalizeBatchRequest", "CreateJobRequest"])
def test_request_models_require_a_strict_integer_week(model_name, value):
    import src.api.routes as routes

    base = {"folder": "x", "course": COURSE, "subject": SUBJECT, "week": value}
    if model_name == "NormalizeRequest":
        base["filename"] = EDUWILL[0]
    if model_name == "NormalizeBatchRequest":
        base["filenames"] = EDUWILL
    with pytest.raises(ValidationError):
        getattr(routes, model_name)(**base)


@pytest.fixture
def client(tmp_path, monkeypatch):
    import src.api.routes as routes
    from src.main import app

    monkeypatch.setattr(routes, "job_manager", JobManager(str(tmp_path / "jobs.json")))
    monkeypatch.setattr(routes, "settings_manager", SettingsManager(tmp_path / "settings.json"))
    return TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.mark.parametrize("path", ["/api/normalize/preview", "/api/normalize/batch", "/api/jobs"])
@pytest.mark.parametrize("week, status", [(None, 400), (0, 400), (-3, 400), ("2", 422), (2.5, 422), ("2주차", 422)])
def test_api_rejects_invalid_week_on_every_normalizing_endpoint(client, tmp_path, path, week, status):
    folder = tmp_path / "에듀윌"
    folder.mkdir()
    (folder / EDUWILL[0]).write_bytes(b"mp3")
    body = {"folder": str(folder), "course": COURSE, "subject": SUBJECT, "filename": EDUWILL[0],
            "filenames": [EDUWILL[0]], "scope": "all_incomplete"}
    if week is not None:
        body["week"] = week
    response = client.post(path, json=body)
    assert response.status_code == status
    assert not any(folder.glob(f"{COURSE}_*"))


def test_api_batch_preview_returns_manual_week_allocation(client, tmp_path):
    folder = tmp_path / "에듀윌"
    folder.mkdir()
    for name in EDUWILL:
        (folder / name).write_bytes(b"mp3")
    response = client.post("/api/normalize/batch", json={
        "folder": str(folder), "filenames": EDUWILL, "course": COURSE, "subject": SUBJECT, "week": 1,
    })
    assert response.status_code == 200
    assert [r["suggested_name"] for r in response.json()] == [f"{_stem(1, n)}.mp3" for n in (1, 2, 3)]
    assert {r["manual_week"] for r in response.json()} == {"1"}


# ---------------------------------------------------------------------------
# Rename bundle, Job metadata and Drive classification
# ---------------------------------------------------------------------------

def _routes(tmp_path, monkeypatch):
    import src.api.routes as routes

    monkeypatch.setattr(routes, "job_manager", JobManager(str(tmp_path / "jobs.json")))
    monkeypatch.setattr(routes, "settings_manager", SettingsManager(tmp_path / "settings.json"))
    return routes


def _eduwill_folder(tmp_path, occupied=()):
    folder = tmp_path / "공인중개사 강의" / "에듀윌 기초이론"
    folder.mkdir(parents=True)
    for name in EDUWILL:
        (folder / name).write_bytes(b"mp3")
    for lesson in occupied:
        for extension in BUNDLE_EXTENSIONS:
            (folder / f"{_stem(1, lesson)}{extension}").write_text("done", encoding="utf-8")
    return folder


def _preflight_and_rename(routes, folder, week):
    previews = routes.preview_normalization_batch(routes.NormalizeBatchRequest(
        folder=str(folder), filenames=EDUWILL, course=COURSE, subject=SUBJECT, week=week,
    ))
    targets = []
    for preview in previews:
        assert preview.result_type == "NORMALIZED"
        new_stem = Path(preview.suggested_name).stem
        routes.apply_rename(routes.RenameRequest(
            folder=str(folder), old_stem=Path(preview.original_name).stem, new_stem=new_stem,
        ))
        targets.append(new_stem)
    return targets


def test_eduwill_end_to_end_job_metadata_and_drive_classification(tmp_path, monkeypatch):
    routes = _routes(tmp_path, monkeypatch)
    folder = _eduwill_folder(tmp_path)

    targets = _preflight_and_rename(routes, folder, 1)
    assert targets == [_stem(1, n) for n in (1, 2, 3)]
    assert not any((folder / name).exists() for name in EDUWILL)

    # Raw name no longer exists: the fresh server-side normalize is UNCHANGED.
    job = routes.create_job(routes.CreateJobRequest(
        folder=str(folder), scope="all_incomplete", course=COURSE, subject=SUBJECT, week=1,
    ))
    assert set(job.files) == set(targets)
    assert job.stage == "1차"
    for lesson, stem in enumerate(targets, start=1):
        assert job.file_metadata[stem] == FileMetadata(week="1", lesson=str(lesson), normalized_name=stem)
    assert not hasattr(job, "week")

    classification = DriveClassifier().classify(job, targets[1], "2026 시험")
    assert (classification.week, classification.lesson) == (1, 2)
    assert classification.folders == (
        "2026 시험", "전사자료", COURSE, f"[1차] {SUBJECT}", f"{COURSE}_{SUBJECT}_1주차",
    )


def test_eduwill_end_to_end_with_occupied_first_lesson(tmp_path, monkeypatch):
    routes = _routes(tmp_path, monkeypatch)
    folder = _eduwill_folder(tmp_path, occupied=(1,))
    assert _preflight_and_rename(routes, folder, 1) == [_stem(1, n) for n in (2, 3, 4)]
    assert (folder / f"{_stem(1, 1)}.txt").read_text(encoding="utf-8") == "done"


def test_create_job_rejects_raw_eduwill_name_before_rename(tmp_path, monkeypatch):
    routes = _routes(tmp_path, monkeypatch)
    folder = _eduwill_folder(tmp_path)
    with pytest.raises(HTTPException, match="파일명 정규화를 먼저 적용해 주세요"):
        routes.create_job(routes.CreateJobRequest(
            folder=str(folder), scope="all_incomplete", course=COURSE, subject=SUBJECT, week=1,
        ))


def test_create_job_rejects_unresolved_week_mismatch(tmp_path, monkeypatch):
    routes = _routes(tmp_path, monkeypatch)
    folder = tmp_path / "전사"
    folder.mkdir()
    (folder / f"{_stem(4, 3)}.mp3").write_bytes(b"mp3")
    with pytest.raises(HTTPException) as excinfo:
        routes.create_job(routes.CreateJobRequest(
            folder=str(folder), scope="all_incomplete", course=COURSE, subject=SUBJECT, week=5,
        ))
    assert excinfo.value.status_code == 400


def test_create_job_never_trusts_a_stale_week_preview(tmp_path, monkeypatch):
    routes = _routes(tmp_path, monkeypatch)
    folder = _eduwill_folder(tmp_path)
    _preflight_and_rename(routes, folder, 1)
    # Preflight ran for week 1 but the Job request says week 2: the fresh
    # normalize sees explicit 1주차 names and refuses them.
    with pytest.raises(HTTPException, match="해결되지 않았습니다"):
        routes.create_job(routes.CreateJobRequest(
            folder=str(folder), scope="all_incomplete", course=COURSE, subject=SUBJECT, week=2,
        ))


def test_continue_original_week_mismatch_records_no_week(tmp_path, monkeypatch):
    routes = _routes(tmp_path, monkeypatch)
    folder = tmp_path / "전사"
    folder.mkdir()
    (folder / "4주차 3강 민법.mp3").write_bytes(b"mp3")
    job = routes.create_job(routes.CreateJobRequest(
        folder=str(folder), scope="all_incomplete", course=COURSE, subject=SUBJECT, week=5,
        file_resolutions={"4주차 3강 민법": "CONTINUE_ORIGINAL"},
    ))
    assert job.file_metadata["4주차 3강 민법"] == FileMetadata(week=None, lesson=None, normalized_name=None)
    assert (folder / "4주차 3강 민법.mp3").exists()


def test_explicit_rename_to_typed_week_then_job_uses_manual_week(tmp_path, monkeypatch):
    routes = _routes(tmp_path, monkeypatch)
    folder = tmp_path / "전사"
    folder.mkdir()
    (folder / "4주차 3강 민법.mp3").write_bytes(b"mp3")
    (folder / "4주차 3강 민법.srt").write_text("srt", encoding="utf-8")
    preview = routes.preview_normalization(routes.NormalizeRequest(
        folder=str(folder), filename="4주차 3강 민법.mp3", course=COURSE, subject=SUBJECT, week=5,
    ))
    assert preview.result_type == "WEEK_MISMATCH"
    target = Path(preview.typed_target_name).stem
    routes.apply_rename(routes.RenameRequest(folder=str(folder), old_stem="4주차 3강 민법", new_stem=target))
    assert (folder / f"{target}.srt").read_text(encoding="utf-8") == "srt"
    job = routes.create_job(routes.CreateJobRequest(
        folder=str(folder), scope="all_incomplete", course=COURSE, subject=SUBJECT, week=5,
    ))
    assert job.file_metadata[target] == FileMetadata(week="5", lesson="3", normalized_name=target)


def test_eduwill_bundle_rename_moves_all_extensions_and_rolls_back(tmp_path):
    old = Path(EDUWILL[0]).stem
    for extension in BUNDLE_EXTENSIONS:
        (tmp_path / f"{old}{extension}").write_text(extension, encoding="utf-8")

    calls = 0

    def fail_third(source: Path, target: Path):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected apply failure")
        source.rename(target)

    failed = BundleRenamer(fail_third).apply_rename(str(tmp_path), old, _stem(1, 1))
    assert failed.status == RenameStatus.RENAME_APPLY_FAILED_ROLLED_BACK
    assert all((tmp_path / f"{old}{ext}").exists() for ext in BUNDLE_EXTENSIONS)
    assert not any((tmp_path / f"{_stem(1, 1)}{ext}").exists() for ext in BUNDLE_EXTENSIONS)

    done = BundleRenamer().apply_rename(str(tmp_path), old, _stem(1, 1))
    assert done.status == RenameStatus.SUCCESS
    assert all((tmp_path / f"{_stem(1, 1)}{ext}").read_text(encoding="utf-8") == ext for ext in BUNDLE_EXTENSIONS)


@pytest.mark.parametrize("extension", BUNDLE_EXTENSIONS)
def test_eduwill_bundle_rename_never_overwrites_any_extension(tmp_path, extension):
    # Cross-extension avoidance happens at preview time (collect_existing_stems,
    # tested above); the renamer itself refuses to overwrite any bundle member.
    old = Path(EDUWILL[0]).stem
    for ext in BUNDLE_EXTENSIONS:
        (tmp_path / f"{old}{ext}").write_text(ext, encoding="utf-8")
    (tmp_path / f"{_stem(1, 1)}{extension}").write_text("owned", encoding="utf-8")
    result = BundleRenamer().apply_rename(str(tmp_path), old, _stem(1, 1))
    assert result.status == RenameStatus.RENAME_CONFLICT
    assert all((tmp_path / f"{old}{ext}").exists() for ext in BUNDLE_EXTENSIONS)
    assert (tmp_path / f"{_stem(1, 1)}{extension}").read_text(encoding="utf-8") == "owned"
