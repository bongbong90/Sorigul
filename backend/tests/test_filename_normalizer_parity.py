"""Legacy week/lesson detection and lesson allocation parity (#124).

Legacy baseline: jeonsa_doumi@fbc86313 filename_normalizer.py
(detect_week_lesson / resolve_next_available_lesson / build_unique_normalize_plan).
Only the week/lesson contract is restored; course/subject stay user free-text (D12).
"""

from pathlib import Path

import pytest

from src.services.job_manager import JobManager
from src.services.normalizer import (
    DetectionMode,
    FilenameNormalizer,
    collect_existing_stems,
    detect_week_lesson,
)
from src.services.settings import SettingsManager


COURSE = "개념완성"
SUBJECT = "민법"


def _stem(week: int, lesson: int, course: str = COURSE, subject: str = SUBJECT) -> str:
    return f"{course}_{subject}_{week}주차_{lesson}강"


def _suggest(name: str, existing=frozenset()):
    return FilenameNormalizer().normalize(name, COURSE, SUBJECT, set(existing))


# ---------------------------------------------------------------------------
# Detection precedence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, week, lesson, mode",
    [
        ("13강_[4-1] 시장론 4", 4, 1, DetectionMode.BRACKET),
        ("4주차 3강 민법", 4, 3, DetectionMode.WEEK_AND_LESSON),
        ("개념완성_민법_4주차_3강", 4, 3, DetectionMode.WEEK_AND_LESSON),
        ("13강_[4주차]_민법 물권", 4, None, DetectionMode.WEEK_ONLY),
        ("[4주차] 민법 특강", 4, None, DetectionMode.WEEK_ONLY),
        ("13강 민법", None, None, DetectionMode.UNKNOWN),
        ("민법 특강", None, None, DetectionMode.UNKNOWN),
    ],
)
def test_detect_week_lesson_follows_legacy_precedence(text, week, lesson, mode):
    detection = detect_week_lesson(text)
    assert (detection.week, detection.preferred_lesson, detection.mode) == (week, lesson, mode)


def test_bracket_wins_over_week_and_lesson_text():
    detection = detect_week_lesson("[4-2] 5주차 3강")
    assert (detection.week, detection.preferred_lesson) == (4, 2)
    assert detection.mode is DetectionMode.BRACKET


# ---------------------------------------------------------------------------
# The five 5F audit reproduction cases (each alone in an empty week)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "original, expected",
    [
        ("1강_[1주차]_26 민법 총칙.mp3", "개념완성_민법_1주차_1강.mp3"),
        ("13강_[4주차]_민법 물권.mp3", "개념완성_민법_4주차_1강.mp3"),
        ("13강_[4-1] 시장론 4.mp3", "개념완성_민법_4주차_1강.mp3"),
        ("[4주차] 민법 특강.mp3", "개념완성_민법_4주차_1강.mp3"),
        ("4주차 3강 민법(p.12~34).mp3", "개념완성_민법_4주차_3강.mp3"),
    ],
)
def test_audit_reproduction_cases_match_legacy(original, expected):
    preview = _suggest(original)
    assert preview.result_type == "NORMALIZED"
    assert preview.suggested_name == expected


def test_leading_global_lecture_counter_is_never_the_lesson():
    preview = _suggest("13강_[4주차]_민법 물권.mp3")
    assert preview.suggested_name != "개념완성_민법_4주차_13강.mp3"
    assert (preview.detected_week, preview.detected_lesson) == ("4", "1")


# ---------------------------------------------------------------------------
# Week-only first-free allocation (first gap, not max + 1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "occupied, expected_lesson",
    [
        ([], 1),
        ([1], 2),
        ([1, 2], 3),
        ([1, 2, 4], 3),
        ([2, 3], 1),
    ],
)
def test_week_only_takes_first_free_lesson(occupied, expected_lesson):
    preview = _suggest("[4주차] 새 강의.mp3", {_stem(4, n) for n in occupied})
    assert preview.suggested_name == f"{_stem(4, expected_lesson)}.mp3"


def test_week_only_ignores_other_weeks_courses_and_subjects():
    existing = {
        _stem(3, 1),
        _stem(4, 1, course="기본이론"),
        _stem(4, 1, subject="부동산학개론"),
    }
    preview = _suggest("13강_[4주차]_민법.mp3", existing)
    assert preview.suggested_name == f"{_stem(4, 1)}.mp3"


# ---------------------------------------------------------------------------
# Explicit preferred lesson: preferred, else the next free number
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "original, occupied, expected_lesson",
    [
        ("13강_[4-1] 시장론 4.mp3", [], 1),
        ("13강_[4-1] 시장론 4.mp3", [1], 2),
        ("13강_[4-1] 시장론 4.mp3", [1, 2], 3),
        ("4주차 3강 민법.mp3", [3], 4),
        ("4주차 3강 민법.mp3", [1, 2], 3),
    ],
)
def test_explicit_lesson_is_preferred_then_next_free(original, occupied, expected_lesson):
    preview = _suggest(original, {_stem(4, n) for n in occupied})
    assert preview.suggested_name == f"{_stem(4, expected_lesson)}.mp3"


# ---------------------------------------------------------------------------
# Batch reservation across detection modes
# ---------------------------------------------------------------------------

def _batch(names, existing=frozenset()):
    results = FilenameNormalizer().normalize_batch(names, COURSE, SUBJECT, set(existing))
    return [Path(result.suggested_name).stem for result in results]


def test_batch_week_only_files_are_allocated_in_order():
    names = ["13강_[4주차]_A.mp3", "14강_[4주차]_B.mp3", "15강_[4주차]_C.mp3"]
    assert _batch(names) == [_stem(4, 1), _stem(4, 2), _stem(4, 3)]


def test_batch_week_only_skips_existing_lesson():
    names = ["13강_[4주차]_A.mp3", "14강_[4주차]_B.mp3", "15강_[4주차]_C.mp3"]
    assert _batch(names, {_stem(4, 1)}) == [_stem(4, 2), _stem(4, 3), _stem(4, 4)]


def test_batch_mixed_detection_modes_never_duplicate_targets():
    names = ["13강_[4-2] A.mp3", "14강_[4주차]_B.mp3", "15강_[4-1] C.mp3", "4주차 2강 D.mp3"]
    stems = _batch(names)
    assert stems == [_stem(4, 2), _stem(4, 1), _stem(4, 3), _stem(4, 4)]
    assert len(set(stems)) == len(stems)


def test_batch_allocation_is_stable_for_the_same_order():
    names = ["13강_[4주차]_A.mp3", "[4-1] B.mp3", "4주차 1강 C.mp3"]
    assert _batch(names) == _batch(names)


# ---------------------------------------------------------------------------
# Cross-extension collision truth (filesystem stems)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("extension", [".mp3", ".txt", ".json", ".srt"])
def test_any_bundle_extension_occupies_the_lesson(tmp_path, extension):
    (tmp_path / f"{_stem(4, 1)}{extension}").write_text("x", encoding="utf-8")
    preview = _suggest("[4주차] 새 강의.mp3", collect_existing_stems(tmp_path))
    assert preview.suggested_name == f"{_stem(4, 2)}.mp3"


# ---------------------------------------------------------------------------
# Preserved contracts: standard names, MISMATCH, INVALID_TARGET
# ---------------------------------------------------------------------------

def test_matching_standard_name_keeps_its_week_and_lesson():
    preview = _suggest("개념완성_민법_4주차_3강.mp3")
    assert preview.result_type == "UNCHANGED"
    assert preview.suggested_name == "개념완성_민법_4주차_3강.mp3"


def test_standard_name_with_other_course_is_still_mismatch():
    preview = FilenameNormalizer().normalize("개념완성_민법_4주차_3강.mp3", "파이널", "민법", set())
    assert preview.result_type == "MISMATCH"
    assert preview.suggested_name == "개념완성_민법_4주차_3강.mp3"
    assert preview.can_apply is False


@pytest.mark.parametrize("original", ["민법 특강.mp3", "13강 민법.mp3"])
def test_names_without_a_week_stay_invalid_target(original):
    preview = _suggest(original)
    assert preview.result_type == "INVALID_TARGET"
    assert preview.suggested_name is None
    assert preview.detected_week is None
    assert preview.detected_lesson is None


# ---------------------------------------------------------------------------
# API: batch preview on disk truth, then rename + Job metadata
# ---------------------------------------------------------------------------

def test_batch_endpoint_and_job_metadata_use_restored_allocation(tmp_path):
    from src.api.routes import (
        CreateJobRequest,
        NormalizeBatchRequest,
        RenameRequest,
        apply_rename,
        create_job,
        preview_normalization_batch,
    )
    import src.api.routes

    folder = tmp_path / "전사자료"
    folder.mkdir()
    (folder / f"{_stem(4, 1)}.txt").write_text("legacy archive", encoding="utf-8")
    originals = ["13강_[4주차]_민법 물권", "14강_[4-1] 민법 채권"]
    for stem in originals:
        (folder / f"{stem}.mp3").write_bytes(b"mp3")

    src.api.routes.job_manager = JobManager(str(tmp_path / "jobs.json"))
    src.api.routes.settings_manager = SettingsManager(tmp_path / "settings.json")

    previews = preview_normalization_batch(
        NormalizeBatchRequest(
            folder=str(folder),
            filenames=[f"{stem}.mp3" for stem in originals],
            course=COURSE,
            subject=SUBJECT,
        )
    )
    targets = [Path(preview.suggested_name).stem for preview in previews]
    assert targets == [_stem(4, 2), _stem(4, 3)]

    for old_stem, new_stem in zip(originals, targets):
        apply_rename(RenameRequest(folder=str(folder), old_stem=old_stem, new_stem=new_stem))

    job = create_job(
        CreateJobRequest(folder=str(folder), file_ids=[], scope="all_incomplete", course=COURSE, subject=SUBJECT)
    )
    for lesson, stem in ((2, targets[0]), (3, targets[1])):
        metadata = job.file_metadata[stem]
        assert (metadata.week, metadata.lesson, metadata.normalized_name) == ("4", str(lesson), stem)
