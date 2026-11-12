import re
from pathlib import Path
from typing import Optional, List, Set
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

WEEK_PATTERN = re.compile(r'(\d+)\s*주차')
LESSON_PATTERN = re.compile(r'(\d+)\s*강')

STANDARD_PATTERN = re.compile(
    r'^(?P<course>[^_]+)_(?P<subject>[^_]+)_(?P<week>\d+)주차_(?P<lesson>\d+)강$'
)

RESULT_EXTENSIONS = (".mp3", ".txt", ".json", ".srt")

MAX_LESSON_SEARCH_ATTEMPTS = 1000


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
    # INVALID_TARGET: week/lesson could not be found in the filename.
    # CONFLICT: no free lesson number could be found within the search bound.
    result_type: str = "UNCHANGED"


class FilenameNormalizer:
    def normalize(
        self,
        original_name: str,
        course: str,
        subject: str,
        existing_stems: Set[str] = frozenset(),
    ) -> NormalizationPreview:
        stem = Path(original_name).stem
        ext = Path(original_name).suffix or ".mp3"

        standard_match = STANDARD_PATTERN.fullmatch(stem)
        if standard_match:
            embedded_course = standard_match.group("course")
            embedded_subject = standard_match.group("subject")
            week = standard_match.group("week")
            lesson = int(standard_match.group("lesson"))
            if embedded_course != course or embedded_subject != subject:
                return NormalizationPreview(
                    original_name=original_name,
                    suggested_name=original_name,
                    detected_course=embedded_course,
                    detected_subject=embedded_subject,
                    detected_week=week,
                    detected_lesson=str(lesson),
                    warnings=[
                        f"현재 파일의 분류({embedded_course}/{embedded_subject})가 "
                        f"입력한 과정/과목({course}/{subject})과 다릅니다."
                    ],
                    conflicts=[],
                    can_apply=False,
                    result_type="MISMATCH",
                )
        else:
            cleaned = FORBIDDEN_CHARS_PATTERN.sub('', stem)
            cleaned = cleaned.replace('+', ' ')
            cleaned = PAGE_MARKER_PATTERN.sub(' ', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()

            week_match = WEEK_PATTERN.search(cleaned)
            lesson_match = LESSON_PATTERN.search(cleaned)

            if not week_match or not lesson_match:
                return NormalizationPreview(
                    original_name=original_name,
                    suggested_name=None,
                    detected_course=course,
                    detected_subject=subject,
                    detected_week=week_match.group(1) if week_match else None,
                    detected_lesson=lesson_match.group(1) if lesson_match else None,
                    warnings=["파일명에서 주차/강을 확인하지 못했습니다."],
                    conflicts=[],
                    can_apply=False,
                    result_type="INVALID_TARGET",
                )

            week = week_match.group(1)
            lesson = int(lesson_match.group(1))

        # Resolve the target stem, stepping the lesson number forward past
        # any collision on disk/in-batch -- this applies even when the file
        # is already standard-named, so a batch of files that would collide
        # on the same lesson number still gets a stable, conflict-free
        # assignment (Section 19).
        suggested_stem = f"{course}_{subject}_{week}주차_{lesson}강"
        attempts = 0
        while suggested_stem in existing_stems and attempts < MAX_LESSON_SEARCH_ATTEMPTS:
            lesson += 1
            suggested_stem = f"{course}_{subject}_{week}주차_{lesson}강"
            attempts += 1

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
        )

    def normalize_batch(
        self,
        original_names: List[str],
        course: str,
        subject: str,
        existing_stems: Set[str] = frozenset(),
    ) -> List[NormalizationPreview]:
        results = []
        reserved = set(existing_stems)

        for name in original_names:
            preview = self.normalize(name, course, subject, reserved)
            if preview.suggested_name:
                reserved.add(Path(preview.suggested_name).stem)
            results.append(preview)

        return results
