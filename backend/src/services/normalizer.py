import re
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
from pydantic import BaseModel

class NormalizationPreview(BaseModel):
    original_name: str
    suggested_name: str
    detected_course: Optional[str] = None
    detected_subject: Optional[str] = None
    detected_week: Optional[str] = None
    detected_lesson: Optional[str] = None
    warnings: List[str] = []
    conflicts: List[str] = []
    can_apply: bool = False
    result_type: str = "UNCHANGED" # NORMALIZED, UNCHANGED, CONFLICT, INVALID_TARGET

class FilenameNormalizer:
    FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*]')

    def normalize(self, original_name: str, existing_basenames: set[str] = set()) -> NormalizationPreview:
        # Local copy to avoid modifying the caller's set, and ignore the file's own original name
        # unless it conflicts with another file that we already processed (handled in batch).
        # Actually in batch, if another file took our original name, it's a conflict!
        # So we should only remove original_name if it was already in the directory, NOT if it was reserved by batch.
        # It's simpler: if `suggested` is in `existing_basenames`, it's a conflict. period.
        # The caller must pass `existing_basenames` excluding the file itself, UNLESS another file took it.
        # Let's just remove the `suggested != original_name` constraint.
        name_no_ext = Path(original_name).stem
        ext = Path(original_name).suffix

        # 1. Clean forbidden chars
        cleaned = self.FORBIDDEN_CHARS.sub('', name_no_ext)
        # 2. Plus to space
        cleaned = cleaned.replace('+', ' ')
        # 3. Collapse spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Extract components. A simplified heuristic for testing:
        # We look for "주차" and "강"
        week_match = re.search(r'(\d+)주차', cleaned)
        lesson_match = re.search(r'(\d+)강', cleaned)

        # We will attempt a standard pattern match if it's already standard
        # Standard: {과정}_{과목}_{N}주차_{M}강.ext
        standard_match = re.match(r'^([^_]+)_([^_]+)_(\d+)주차_(\d+)강$', cleaned)

        course, subject, week, lesson = None, None, None, None
        warnings = []

        if standard_match:
            # It's already in the standard format
            course = standard_match.group(1)
            subject = standard_match.group(2)
            week = standard_match.group(3)
            lesson = standard_match.group(4)
            suggested = f"{course}_{subject}_{week}주차_{lesson}강{ext}"
        elif week_match and lesson_match:
            week = week_match.group(1)
            lesson = lesson_match.group(1)

            # Simple heuristic for course and subject
            parts = [p for p in re.split(r'[_\[\]\s]', cleaned) if p and '주차' not in p and '강' not in p]

            # Try to filter out date patterns or page markers like 26_04_22, 교재2
            filtered_parts = [
                p for p in parts
                if not re.match(r'^\d{2}$', p) and '교재' not in p
            ]

            if len(filtered_parts) >= 2:
                course = filtered_parts[0]
                subject = filtered_parts[1]
            elif len(filtered_parts) == 1:
                course = "과정미상"
                subject = filtered_parts[0]
            else:
                course = "과정미상"
                subject = "과목미상"

            suggested = f"{course}_{subject}_{week}주차_{lesson}강{ext}"
        else:
            suggested = cleaned.replace(' ', '_') + ext
            warnings.append("과정/과목/주차/강 패턴을 완벽히 인식하지 못했습니다.")

            # Conflict resolution for non-standard names
            base_suggested = Path(suggested).stem
            counter = 2
            while suggested in existing_basenames:
                suggested = f"{base_suggested}_{counter}{ext}"
                counter += 1

        # Attempt to find a free lesson number if there is a conflict (for standard or parsed names)
        if lesson is not None:
            base_lesson = int(lesson)
            while suggested in existing_basenames:
                base_lesson += 1
                suggested = f"{course}_{subject}_{week}주차_{base_lesson}강{ext}"
                lesson = str(base_lesson)

        conflicts = []
        can_apply = True
        result_type = "NORMALIZED"

        if suggested == original_name:
            can_apply = False
            result_type = "UNCHANGED"
        elif suggested in existing_basenames:
            conflicts.append(f"이름 충돌: {suggested}")
            can_apply = False
            result_type = "CONFLICT"

        return NormalizationPreview(
            original_name=original_name,
            suggested_name=suggested,
            detected_course=course,
            detected_subject=subject,
            detected_week=week,
            detected_lesson=lesson,
            warnings=warnings,
            conflicts=conflicts,
            can_apply=can_apply,
            result_type=result_type
        )

    def normalize_batch(self, original_names: List[str], existing_basenames: set[str]) -> List[NormalizationPreview]:
        results = []
        reserved_basenames = set(existing_basenames)

        for name in original_names:
            preview = self.normalize(name, reserved_basenames)
            reserved_basenames.add(preview.suggested_name)
            results.append(preview)

        return results
