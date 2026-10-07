import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, List, Set, Tuple
from pydantic import BaseModel

# Windows-forbidden filename characters and ASCII control characters. Course
# and subject are free-typed by the user (CORE_WORKFLOW_REFINEMENT_PLAN.md
# D12) but still feed directly into the generated filename, so they get the
# same safety net filenames already require (D23B).
FORBIDDEN_CHARS_PATTERN = re.compile(r'[<>:"/\\|?*]')
CONTROL_CHARS_PATTERN = re.compile(r'[\x00-\x1f\x7f]')

# "(p.8)" / "(p. 8 ~ 12)" style page markers left over from Legacy lecture
# titles. Only used to reduce noise before extracting week/lesson -- the
# generated filename is always rebuilt from typed course/subject plus
# detected week/lesson, so leftover title text never survives into output.
PAGE_MARKER_PATTERN = re.compile(r'\(\s*p\.?\s*\d+\s*(?:[~\-]\s*\d*)?\s*\)', re.IGNORECASE)

# Legacy week/lesson detection precedence (#124). A leading "N강" is the
# course-wide lecture counter of the downloaded name (e.g. "13강_[4주차]_..."),
# never the lesson within the week: a lesson only counts when it follows the
# week ("N주차 ... M강") or comes from the "[N-M]" week-lesson bracket.
BRACKET_WEEK_LESSON_PATTERN = re.compile(r'\[(\d+)-(\d+)\]')
WEEK_AND_LESSON_PATTERN = re.compile(r'(\d+)\s*주차[^\d]*(\d+)\s*강')
WEEK_PATTERN = re.compile(r'(\d+)\s*주차')

# Manual-week fallback (#180). A provider such as Eduwill names a lecture only
# by its course-wide counter ("2026_이영방_부동산학개론_기초이론_4강"), with
# no week at all. That counter is never a week and never the lesson within a
# week -- it only proves the file is a numbered lecture, so the user's typed
# week may place it at the week's first/next free lesson. The token must stand
# alone ("_4강", " 4강", "4강" at the end), and exactly one such token must
# exist; "특강", "3강의", "3강 4강 합본" never qualify.
GLOBAL_LECTURE_PATTERN = re.compile(r'(?:^|(?<=[\s_\[\(\-]))(\d+)\s*강(?=$|[\s_\]\)\-.,])')

STANDARD_PATTERN = re.compile(
    r'^(?P<course>[^_]+)_(?P<subject>[^_]+)_(?P<week>\d+)주차_(?P<lesson>\d+)강$'
)

RESULT_EXTENSIONS = (".mp3", ".txt", ".json", ".srt")

MAX_LESSON_SEARCH_ATTEMPTS = 1000


class DetectionMode(str, Enum):
    BRACKET = "BRACKET"                  # "[N-M]": week N, preferred lesson M
    WEEK_AND_LESSON = "WEEK_AND_LESSON"  # "N주차 ... M강": week N, preferred lesson M
    WEEK_ONLY = "WEEK_ONLY"              # "N주차" alone: week N, first free lesson
    UNKNOWN = "UNKNOWN"                  # no week: INVALID_TARGET


@dataclass(frozen=True)
class WeekLessonDetection:
    week: Optional[int]
    preferred_lesson: Optional[int]
    mode: DetectionMode


def detect_week_lesson(text: str) -> WeekLessonDetection:
    """Detect week/lesson with the Legacy precedence: bracket, then
    week-followed-by-lesson, then week only. Course/subject are never
    detected here (D12)."""
    bracket = BRACKET_WEEK_LESSON_PATTERN.search(text)
    if bracket:
        return WeekLessonDetection(int(bracket.group(1)), int(bracket.group(2)), DetectionMode.BRACKET)
    week_and_lesson = WEEK_AND_LESSON_PATTERN.search(text)
    if week_and_lesson:
        return WeekLessonDetection(
            int(week_and_lesson.group(1)), int(week_and_lesson.group(2)), DetectionMode.WEEK_AND_LESSON
        )
    week = WEEK_PATTERN.search(text)
    if week:
        return WeekLessonDetection(int(week.group(1)), None, DetectionMode.WEEK_ONLY)
    return WeekLessonDetection(None, None, DetectionMode.UNKNOWN)


def has_global_lecture_counter(text: str) -> bool:
    """True when `text` carries exactly one standalone course-wide "N강"
    counter. Only meaningful once detect_week_lesson() found no week; the
    number itself is discarded (#180)."""
    return len(GLOBAL_LECTURE_PATTERN.findall(text)) == 1


class ManualWeekValidationError(ValueError):
    """Raised by validate_manual_week on a missing or non-positive week."""


def validate_manual_week(value: Optional[int]) -> int:
    """Validate the user-entered week (#180). The request models already
    reject non-integers; this is the independent server-side check that a
    week was actually given and is a positive integer."""
    if value is None:
        raise ManualWeekValidationError("주차를 입력해 주세요.")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ManualWeekValidationError("주차는 1 이상의 정수로 입력해 주세요.")
    return value


class ClassificationValidationError(ValueError):
    """Raised by validate_classification_text on an invalid course/subject."""


def validate_classification_text(value: str, field_label: str) -> str:
    """Validate a user-typed course/subject value (D23B).

    Trims surrounding whitespace, then rejects: empty (post-trim), control
    characters, Windows-forbidden filename characters, and a trailing dot
    (invalid at the end of a Windows filename component). Never silently
    strips or substitutes an invalid character -- callers must surface the
    raised message and let the user correct it.
    """
    trimmed = value.strip()
    if not trimmed:
        raise ClassificationValidationError(f"{field_label}을(를) 입력해 주세요.")
    if CONTROL_CHARS_PATTERN.search(trimmed):
        raise ClassificationValidationError(f"{field_label}에 사용할 수 없는 제어 문자가 포함되어 있습니다.")
    if FORBIDDEN_CHARS_PATTERN.search(trimmed):
        raise ClassificationValidationError(f'{field_label}에는 다음 문자를 사용할 수 없습니다: < > : " / \\ | ? *')
    # Underscore is reserved as the structural delimiter in the generated
    # standard filename ({course}_{subject}_{week}주차_{lesson}강,
    # STANDARD_PATTERN below) -- allowing it inside course/subject would make
    # the course/subject boundary unrecoverable when the name is re-parsed.
    if '_' in trimmed:
        raise ClassificationValidationError(f"{field_label}에는 밑줄(_)을 사용할 수 없습니다.")
    if trimmed.endswith('.'):
        raise ClassificationValidationError(f"{field_label}은(는) 마침표(.)로 끝날 수 없습니다.")
    return trimmed


def collect_existing_stems(folder: Path, exclude_stem: Optional[str] = None) -> Set[str]:
    """Collect the stems of MP3/TXT/JSON/SRT siblings actually on disk in
    `folder` (CORE_WORKFLOW_REFINEMENT_PLAN.md Section 18) -- collision truth
    is the filesystem, not a client-supplied filename list.
    """
    stems: Set[str] = set()
    if not folder.exists() or not folder.is_dir():
        return stems
    for entry in folder.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in RESULT_EXTENSIONS:
            continue
        stem = entry.stem
        if exclude_stem is not None and stem == exclude_stem:
            continue
        stems.add(stem)
    return stems


class NormalizationPreview(BaseModel):
    original_name: str
    suggested_name: Optional[str] = None
    detected_course: Optional[str] = None
    detected_subject: Optional[str] = None
    detected_week: Optional[str] = None
    detected_lesson: Optional[str] = None
    warnings: List[str] = []
    conflicts: List[str] = []
    can_apply: bool = False
    # NORMALIZED: a safe rename is proposed (suggested_name != original_name).
    # UNCHANGED: already the correct standard name, nothing to do.
    # MISMATCH: already a standard name, but its course/subject differ from
    #   what was typed for this job -- never auto-resolved (D24).
    # WEEK_MISMATCH: the filename carries an explicit week that differs from
    #   the manually entered week -- never auto-resolved either way (#180).
    # INVALID_TARGET: week/lesson could not be found in the filename (and no
    #   manual-week fallback applies).
    # CONFLICT: no free lesson number could be found within the search bound.
    result_type: str = "UNCHANGED"
    # The manually entered week this preview was computed against (#180).
    manual_week: Optional[str] = None
    # MISMATCH/WEEK_MISMATCH only: the target an explicit "rename to the typed
    # classification" choice would use -- typed course + typed subject +
    # manual week, the source lesson as the preferred lesson (else the first
    # free one), stepped past occupied stems. None when no free lesson exists.
    typed_target_name: Optional[str] = None


def _first_free_stem(
    course: str, subject: str, week: int, lesson: int, existing_stems: Set[str]
) -> Tuple[str, int]:
    """The preferred (or first) lesson's stem, stepped forward past any
    MP3/TXT/JSON/SRT stem already on disk or reserved earlier in the batch.
    Returns the last candidate tried; the caller checks it is actually free."""
    suggested_stem = f"{course}_{subject}_{week}주차_{lesson}강"
    attempts = 0
    while suggested_stem in existing_stems and attempts < MAX_LESSON_SEARCH_ATTEMPTS:
        lesson += 1
        suggested_stem = f"{course}_{subject}_{week}주차_{lesson}강"
        attempts += 1
    return suggested_stem, lesson


class FilenameNormalizer:
    def normalize(
        self,
        original_name: str,
        course: str,
        subject: str,
        existing_stems: Set[str] = frozenset(),
        manual_week: Optional[int] = None,
    ) -> NormalizationPreview:
        """Preview the standard name for one file.

        `manual_week` is the user-entered week (#180). The Legacy detector
        (detect_week_lesson) runs first and is never altered by it: an
        explicit source week equal to the manual week behaves exactly as
        before, a different one is a WEEK_MISMATCH. Only when the source has
        no week at all does the manual week apply, and then only to a name
        carrying a standalone course-wide "N강" counter.
        """
        stem = Path(original_name).stem
        ext = Path(original_name).suffix or ".mp3"
        manual_week_text = str(manual_week) if manual_week is not None else None

        def typed_target(source_week: int, source_lesson: Optional[int]) -> Optional[str]:
            target_week = manual_week if manual_week is not None else source_week
            target_stem, _ = _first_free_stem(
                course, subject, target_week,
                source_lesson if source_lesson is not None else 1, existing_stems,
            )
            return None if target_stem in existing_stems else f"{target_stem}{ext}"

        standard_match = STANDARD_PATTERN.fullmatch(stem)
        if standard_match:
            embedded_course = standard_match.group("course")
            embedded_subject = standard_match.group("subject")
            week = int(standard_match.group("week"))
            lesson = int(standard_match.group("lesson"))
            if embedded_course != course or embedded_subject != subject:
                warnings = [
                    f"현재 파일의 분류({embedded_course}/{embedded_subject})가 "
                    f"입력한 과정/과목({course}/{subject})과 다릅니다."
                ]
                if manual_week is not None and week != manual_week:
                    warnings.append(f"파일명은 {week}주차, 입력한 주차는 {manual_week}주차입니다.")
                return NormalizationPreview(
                    original_name=original_name,
                    suggested_name=original_name,
                    detected_course=embedded_course,
                    detected_subject=embedded_subject,
                    detected_week=str(week),
                    detected_lesson=str(lesson),
                    warnings=warnings,
                    conflicts=[],
                    can_apply=False,
                    result_type="MISMATCH",
                    manual_week=manual_week_text,
                    typed_target_name=typed_target(week, lesson),
                )
            explicit_week, explicit_lesson = week, lesson
        else:
            cleaned = FORBIDDEN_CHARS_PATTERN.sub('', stem)
            cleaned = cleaned.replace('+', ' ')
            cleaned = PAGE_MARKER_PATTERN.sub(' ', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()

            detection = detect_week_lesson(cleaned)
            if detection.week is None:
                if manual_week is None or not has_global_lecture_counter(cleaned):
                    return NormalizationPreview(
                        original_name=original_name,
                        suggested_name=None,
                        detected_course=course,
                        detected_subject=subject,
                        detected_week=None,
                        detected_lesson=None,
                        warnings=["파일명에서 주차/강을 확인하지 못했습니다."],
                        conflicts=[],
                        can_apply=False,
                        result_type="INVALID_TARGET",
                        manual_week=manual_week_text,
                    )
                # No-week global lecture counter: the typed week, first free
                # lesson. The counter itself is discarded, never reused.
                explicit_week, explicit_lesson = None, None
                week, lesson = manual_week, 1
            else:
                explicit_week, explicit_lesson = detection.week, detection.preferred_lesson
                week = detection.week
                # Week-only names take the first free lesson of that week.
                lesson = detection.preferred_lesson if detection.preferred_lesson is not None else 1

        if explicit_week is not None and manual_week is not None and explicit_week != manual_week:
            target = typed_target(explicit_week, explicit_lesson)
            warnings = [f"파일명은 {explicit_week}주차, 입력한 주차는 {manual_week}주차입니다."]
            if target is None:
                warnings.append(f"입력한 {manual_week}주차에서 사용 가능한 강 번호를 찾지 못했습니다.")
            return NormalizationPreview(
                original_name=original_name,
                suggested_name=original_name,
                detected_course=course,
                detected_subject=subject,
                detected_week=str(explicit_week),
                detected_lesson=str(explicit_lesson) if explicit_lesson is not None else None,
                warnings=warnings,
                conflicts=[],
                can_apply=False,
                result_type="WEEK_MISMATCH",
                manual_week=manual_week_text,
                typed_target_name=target,
            )

        # Resolve the target stem -- this applies even when the file is
        # already standard-named, so a batch of files that would collide on
        # the same lesson number still gets a stable, conflict-free
        # assignment (Section 19).
        suggested_stem, lesson = _first_free_stem(course, subject, week, lesson, existing_stems)
        week = str(week)

        if suggested_stem in existing_stems:
            return NormalizationPreview(
                original_name=original_name,
                suggested_name=None,
                detected_course=course,
                detected_subject=subject,
                detected_week=week,
                detected_lesson=str(lesson),
                warnings=["사용 가능한 강 번호를 찾지 못했습니다."],
                conflicts=[f"이름 충돌: {suggested_stem}{ext}"],
                can_apply=False,
                result_type="CONFLICT",
                manual_week=manual_week_text,
            )

        if suggested_stem == stem:
            return NormalizationPreview(
                original_name=original_name,
                suggested_name=original_name,
                detected_course=course,
                detected_subject=subject,
                detected_week=week,
                detected_lesson=str(lesson),
                warnings=[],
                conflicts=[],
                can_apply=False,
                result_type="UNCHANGED",
                manual_week=manual_week_text,
            )

        return NormalizationPreview(
            original_name=original_name,
            suggested_name=f"{suggested_stem}{ext}",
            detected_course=course,
            detected_subject=subject,
            detected_week=week,
            detected_lesson=str(lesson),
            warnings=[],
            conflicts=[],
            can_apply=True,
            result_type="NORMALIZED",
            manual_week=manual_week_text,
        )

    def normalize_batch(
        self,
        original_names: List[str],
        course: str,
        subject: str,
        existing_stems: Set[str] = frozenset(),
        manual_week: Optional[int] = None,
    ) -> List[NormalizationPreview]:
        # Request order is the allocation order and the response is 1:1 with
        # the input -- a global "N강" counter never re-sorts the batch (#180).
        results = []
        reserved = set(existing_stems)

        for name in original_names:
            preview = self.normalize(name, course, subject, reserved, manual_week)
            if preview.suggested_name:
                reserved.add(Path(preview.suggested_name).stem)
            results.append(preview)

        return results
