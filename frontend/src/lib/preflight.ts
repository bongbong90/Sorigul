// Pure, dependency-free helpers for the pre-Job normalization preflight
// (CORE_WORKFLOW_REFINEMENT_PLAN.md Sections 2-13). Kept side-effect free so
// they stay easy to reason about without a UI test harness -- the
// orchestration that calls these (frontend/src/pages/TranscriptionPage.tsx)
// owns all API calls and React state.
import type { NormalizationPreview } from '../api/client'

export type FileResolution =
  | 'AUTO_RENAME'
  | 'UNCHANGED'
  | 'USE_FILE_CLASSIFICATION'
  | 'RENAME_TO_TYPED'
  | 'CONTINUE_ORIGINAL'

export type PreviewDisposition = 'AUTO_RENAME' | 'NO_OP' | 'NEEDS_RESOLUTION'

// Decide what a single target file's freshly-fetched normalization preview
// means for the Start preflight: a safe rename to apply automatically, an
// already-correct name needing nothing, or a MISMATCH/INVALID_TARGET/
// CONFLICT that must block Start until the user makes an explicit choice
// (D24 -- never silently rename/reclassify, never silently proceed).
export function classifyPreview(preview: NormalizationPreview): PreviewDisposition {
  if (preview.result_type === 'UNCHANGED') return 'NO_OP'
  if (preview.result_type === 'NORMALIZED' && preview.can_apply && preview.conflicts.length === 0) {
    return 'AUTO_RENAME'
  }
  return 'NEEDS_RESOLUTION'
}

// Remap a rename's old id to its new id inside an ordered id list, used for
// selectedIds/target-id lists so the same logical file stays tracked across
// a rename that happens mid-preflight (Section 11 -- never rely on stale
// pre-rename ids for the eventual createJob call).
export function remapId(ids: string[], oldId: string, newId: string): string[] {
  if (oldId === newId) return ids
  return ids.map((id) => (id === oldId ? newId : id))
}

// Same remap, but for a Map keyed by file id (e.g. per-file resolution
// state) -- moves the value from the old key to the new key.
export function remapResolutionKey<T>(map: Map<string, T>, oldId: string, newId: string): Map<string, T> {
  if (oldId === newId || !map.has(oldId)) return map
  const next = new Map(map)
  const value = next.get(oldId) as T
  next.delete(oldId)
  next.set(newId, value)
  return next
}

// A preflight attempt may only proceed to createJob once every target in
// this attempt has a recorded resolution -- partial preflight state must
// never produce a Job (Section 9/12).
export function allTargetsResolved(targetIds: string[], resolutions: Map<string, FileResolution>): boolean {
  return targetIds.every((id) => resolutions.has(id))
}

// Drive upload must never silently fire against a file whose classification
// was never actually confirmed against the typed course/subject: the
// current Drive classifier is still filename-based (Phase 2 not done yet),
// so any CONTINUE_ORIGINAL target means this run's upload must be forced
// off entirely -- no partial/opt-in upload for the unresolved file only,
// and no "upload anyway" override (Section 8).
export function needsDriveConfirmation(targetIds: string[], resolutions: Map<string, FileResolution>): boolean {
  return targetIds.some((id) => resolutions.get(id) === 'CONTINUE_ORIGINAL')
}

// Build the file_resolutions payload for createJob: only CONTINUE_ORIGINAL
// entries are meaningful to the backend gate (every other resolution either
// renamed the file to a standard name or changed the typed course/subject
// to match it, so the backend's own re-normalize already resolves to
// UNCHANGED without needing an explicit flag).
export function toFileResolutionsPayload(resolutions: Map<string, FileResolution>): Record<string, 'CONTINUE_ORIGINAL'> {
  const payload: Record<string, 'CONTINUE_ORIGINAL'> = {}
  for (const [id, resolution] of resolutions) {
    if (resolution === 'CONTINUE_ORIGINAL') payload[id] = 'CONTINUE_ORIGINAL'
  }
  return payload
}
