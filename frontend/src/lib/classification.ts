// Mirrors backend/src/services/classification.py and the validation rules
// in backend/src/services/normalizer.py (validate_classification_text).
// Backend re-validates independently on every request -- this module exists
// only to give the user immediate inline feedback (D23B), never as the
// source of truth.

export type Stage = '1차' | '2차'

// CORE_WORKFLOW_REFINEMENT_PLAN.md D16 -- exact, trimmed subject strings only.
export const KNOWN_SUBJECT_STAGE: Record<string, Stage> = {
  부동산학개론: '1차',
  민법: '1차',
  공인중개사법: '2차',
  부동산공법: '2차',
  부동산공시법: '2차',
  부동산세법: '2차',
}

const FORBIDDEN_CHARS_PATTERN = /[<>:"/\\|?*]/
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS_PATTERN = /[\x00-\x1f\x7f]/

export interface ClassificationValidation {
  value: string
  error?: string
}

export function validateClassificationText(raw: string, fieldLabel: string): ClassificationValidation {
  const trimmed = raw.trim()
  if (!trimmed) return { value: trimmed, error: `${fieldLabel}을(를) 입력해 주세요.` }
  if (CONTROL_CHARS_PATTERN.test(trimmed)) {
    return { value: trimmed, error: `${fieldLabel}에 사용할 수 없는 제어 문자가 포함되어 있습니다.` }
  }
  if (FORBIDDEN_CHARS_PATTERN.test(trimmed)) {
    return { value: trimmed, error: `${fieldLabel}에는 다음 문자를 사용할 수 없습니다: < > : " / \\ | ? *` }
  }
  if (trimmed.endsWith('.')) {
    return { value: trimmed, error: `${fieldLabel}은(는) 마침표(.)로 끝날 수 없습니다.` }
  }
  return { value: trimmed }
}

export function knownStageFor(subject: string): Stage | undefined {
  return KNOWN_SUBJECT_STAGE[subject.trim()]
}

export function overrideStageFor(subject: string, overrides: Record<string, Stage>): Stage | undefined {
  return overrides[subject.trim()]
}

// Resolves what the Transcription screen should show/send for stage: the
// known mapping first, then a saved override, otherwise undefined (meaning
// the UI must ask the user, mirroring backend resolve_stage()).
export function resolveStageHint(subject: string, overrides: Record<string, Stage>): Stage | undefined {
  const trimmed = subject.trim()
  if (!trimmed) return undefined
  return knownStageFor(trimmed) ?? overrideStageFor(trimmed, overrides)
}
