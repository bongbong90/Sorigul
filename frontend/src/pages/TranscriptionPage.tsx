import { useCallback, useEffect, useMemo, useState, useRef } from 'react'
import { AlertTriangle, CheckCircle2, Cloud, FilePenLine, RefreshCw, WifiOff } from 'lucide-react'
import {
  api,
  getSavedFolder,
  getUserMessage,
  saveFolder,
  type JobModel,
  type NormalizationPreview,
  type RuntimeSettings,
  type ScannedFile,
} from '../api/client'
import { pickFolder } from '../lib/native'
import { knownStageFor, overrideStageFor, validateClassificationText, type Stage } from '../lib/classification'
import {
  classifyPreview,
  needsDriveConfirmation,
  remapId,
  remapResolutionKey,
  toFileResolutionsPayload,
  type FileResolution,
} from '../lib/preflight'
import { ClassificationSection } from '../components/transcription/ClassificationSection'
import { CurrentTaskSection, type CurrentTaskStatus } from '../components/transcription/CurrentTaskSection'
import { FolderSection } from '../components/transcription/FolderSection'
import { QueueTable, type QueueRow, type QueueStatus } from '../components/transcription/QueueTable'
import { TranscriptionActions } from '../components/transcription/TranscriptionActions'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

type DialogKind = 'start-all' | 'empty-target' | 'retranscribe' | null
type BackendStatus = 'OFFLINE' | 'STARTING' | 'CONNECTED'
interface PreflightAttempt {
  ids: string[]
  filenames: Record<string, string>
  force: boolean
  scope: 'selected' | 'all_incomplete'
}
interface AdoptedClassification {
  course: string
  subject: string
  fromFileId: string
}
const ACTIVE_STATES = new Set(['WAITING', 'PREPARING', 'TRANSCRIBING', 'SAVING', 'VERIFYING', 'CANCEL_REQUESTED'])
const drivePresentation: Record<string, { label: string; tone: BadgeTone }> = {
  DISABLED: { label: 'Drive 사용 안 함', tone: 'waiting' }, AUTH_REQUIRED: { label: '인증 필요', tone: 'cancelled' },
  CLASSIFICATION_FAILED: { label: 'Drive 분류 실패', tone: 'failed' }, PENDING: { label: 'Drive 대기', tone: 'waiting' },
  UPLOADING: { label: 'Drive 업로드 중', tone: 'preparing' }, DONE: { label: 'Drive 완료', tone: 'done' },
  FAILED: { label: 'Drive 실패', tone: 'failed' },
}

function queueStatus(value: string): QueueStatus {
  return value as QueueStatus
}

function rowsFrom(files: ScannedFile[], job?: JobModel): QueueRow[] {
  return files.map((file) => {
    const local = job?.files[file.id] ?? (file.completion_status === 'DONE' ? 'DONE' : 'WAITING')
    const drive = job?.drive[file.id]
    const localDetail = file.completion_status === 'INVALID_RESULT' ? '기존 결과 bundle 검증 실패' : file.completion_status === 'DONE' ? '정상 TXT/JSON/SRT bundle' : undefined
    const driveDetail = drive && drive.status !== 'DISABLED' ? `${drivePresentation[drive.status]?.label ?? drive.status}${drive.error ? ` · ${drive.error}` : ''}` : undefined
    return { id: file.id, filename: file.filename, duration: '—', status: queueStatus(local), detail: [localDetail, driveDetail].filter(Boolean).join(' · ') || undefined }
  })
}

export function TranscriptionPage() {
  const [folder, setFolder] = useState(getSavedFolder)
  const [files, setFiles] = useState<ScannedFile[]>([])
  const [job, setJob] = useState<JobModel>()
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('STARTING')
  const [driveAuth, setDriveAuth] = useState('UNAUTHENTICATED')
  const [dialog, setDialog] = useState<DialogKind>(null)
  const [pendingIds, setPendingIds] = useState<string[]>([])
  const [message, setMessage] = useState('Backend 연결 상태를 확인하고 있습니다.')
  const [normalization, setNormalization] = useState<NormalizationPreview>()
  const [filenameValue, setFilenameValue] = useState('')
  const [filenameMode, setFilenameMode] = useState<'review' | 'editing'>('review')
  // Pre-Job preflight state (CORE_WORKFLOW_REFINEMENT_PLAN.md Sections 2-13):
  // fileResolutions/attempt/resolvingId/adoptedClassification together track
  // one in-progress Start attempt across pauses for MISMATCH/INVALID_TARGET/
  // CONFLICT resolution. Plain local state, not a persisted architecture --
  // cleared whenever an attempt finishes (success or abort) or the folder
  // changes.
  const [fileResolutions, setFileResolutions] = useState<Map<string, FileResolution>>(new Map())
  const [resolvingId, setResolvingId] = useState<string | null>(null)
  const [attempt, setAttempt] = useState<PreflightAttempt | null>(null)
  const [adoptedClassification, setAdoptedClassification] = useState<AdoptedClassification | null>(null)
  // D23A: Drive auto-upload is a per-run choice only -- always unchecked on
  // launch, never restored from a prior Job or persisted to RuntimeSettings.
  const [uploadToDrive, setUploadToDrive] = useState(false)
  const [settings, setSettings] = useState<RuntimeSettings>()
  const [course, setCourse] = useState('')
  const [subject, setSubject] = useState('')
  const [courseError, setCourseError] = useState<string>()
  const [subjectError, setSubjectError] = useState<string>()
  const [editingOverride, setEditingOverride] = useState(false)
  const activeJobId = job?.job_id
  const activeJobStatus = job?.status
  const preflightLockRef = useRef(false)
  const [preflightActive, setPreflightActive] = useState(false)
  const isPreflighting = preflightActive

  const knownStage = knownStageFor(subject)
  const overrideStage = overrideStageFor(subject, settings?.subject_stage_overrides ?? {})
  const needsStagePrompt = Boolean(subject.trim()) && !knownStage && (!overrideStage || editingOverride)

  // Loaded once at startup: the backend transcription_folder setting is the
  // source of truth going forward, but a pre-existing localStorage folder
  // from before this upgrade is non-destructively adopted rather than
  // dropped (D22). last_course/last_subject prefill the classification
  // inputs.
  const loadSettings = useCallback(async () => {
    try {
      const loaded = await api.settings()
      let effectiveFolder = loaded.transcription_folder
      if (!effectiveFolder) {
        const legacy = getSavedFolder()
        if (legacy) {
          effectiveFolder = legacy
          try {
            const adopted = await api.saveSettings({ ...loaded, transcription_folder: legacy })
            setSettings(adopted)
          } catch {
            setSettings(loaded)
          }
        } else {
          setSettings(loaded)
        }
      } else {
        setSettings(loaded)
      }
      if (effectiveFolder && effectiveFolder !== folder) setFolder(effectiveFolder)
      setCourse((current) => current || loaded.last_course || '')
      setSubject((current) => current || loaded.last_subject || '')
    } catch {
      // Backend offline at startup: fall back to whatever localStorage has;
      // the health/reconnect flow will retry settings once connected.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadFolder = useCallback(async () => {
    if (!folder) { setFiles([]); setMessage('전사 폴더를 선택해 주세요.'); return }
    try {
      const [scanned, jobs, drive] = await Promise.all([api.scan(folder), api.jobs(), api.driveStatus()])
      const matching = jobs.filter((item) => item.folder === folder).sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))[0]
      setFiles(scanned); setJob(matching); setDriveAuth(drive.auth_state); setBackendStatus('CONNECTED'); setMessage(`실제 디스크에서 ${scanned.length}개 MP3를 확인했습니다.`)
    } catch (cause) { setBackendStatus('OFFLINE'); setMessage(getUserMessage(cause)) }
  }, [folder])

  // A packaged Tauri cold start can have the frontend polling before the
  // backend sidecar is up, so settings/folder adoption must happen again
  // once the backend actually answers -- not just once at mount (Section
  // 14). loadSettings is idempotent (guards its own writes), so calling it
  // again here on every successful reconnect is safe.
  const reconnect = useCallback(async () => {
    setBackendStatus('STARTING')
    try { await api.health(); await loadSettings(); await loadFolder() }
    catch (cause) { setBackendStatus('OFFLINE'); setMessage(getUserMessage(cause)) }
  }, [loadSettings, loadFolder])

  useEffect(() => { void reconnect() }, [reconnect])
  useEffect(() => {
    const healthTimer = window.setInterval(async () => {
      try {
        await api.health()
        setBackendStatus((current) => {
          // Only the OFFLINE/STARTING -> CONNECTED edge triggers a real
          // resync; once already CONNECTED, every 4s tick just confirms
          // liveness without re-fetching (no request loop).
          if (current !== 'CONNECTED') void reconnect()
          return 'CONNECTED'
        })
      } catch { setBackendStatus('OFFLINE') }
    }, 4000)
    return () => window.clearInterval(healthTimer)
  }, [reconnect])
  useEffect(() => {
    if (!activeJobId || !activeJobStatus || !ACTIVE_STATES.has(activeJobStatus)) return
    let active = true
    const timer = window.setInterval(async () => {
      try {
        const updated = await api.job(activeJobId)
        if (active) setJob(updated)
        if (!ACTIVE_STATES.has(updated.status)) { window.clearInterval(timer); if (active) void loadFolder() }
      } catch (cause) { if (active) { setBackendStatus('OFFLINE'); setMessage(getUserMessage(cause)) } }
    }, 1500)
    return () => { active = false; window.clearInterval(timer) }
  }, [activeJobId, activeJobStatus, loadFolder])

  const rows = useMemo(() => rowsFrom(files, job), [files, job])
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const currentRow = rows.find((row) => row.filename === job?.current_file)
  const completedCount = rows.filter((row) => row.status === 'DONE').length
  const failedRows = rows.filter((row) => row.status === 'FAILED')
  const isProcessing = Boolean(job && ACTIVE_STATES.has(job.status))
  const canControl = Boolean(job && ['PREPARING', 'TRANSCRIBING', 'SAVING', 'VERIFYING'].includes(job.status))
  const runState: CurrentTaskStatus = job ? (job.status as CurrentTaskStatus) : 'IDLE'

  async function changeFolder() {
    const value = await pickFolder(folder)
    if (!value) return
    saveFolder(value); setFolder(value); setSelectedIds([]); setJob(undefined)
    resetPreflight()
    if (settings) {
      try { setSettings(await api.saveSettings({ ...settings, transcription_folder: value })) }
      catch { /* best-effort; localStorage still has the current selection */ }
    }
  }

  function onCourseChange(value: string) {
    setCourse(value)
    setCourseError(value.trim() ? validateClassificationText(value, '과정명').error : undefined)
  }

  function onSubjectChange(value: string) {
    setSubject(value)
    setSubjectError(value.trim() ? validateClassificationText(value, '과목명').error : undefined)
    setEditingOverride(false)
  }

  async function onPickStage(stage: Stage) {
    if (!settings) return
    const trimmedSubject = subject.trim()
    if (!trimmedSubject) return
    const nextOverrides = { ...settings.subject_stage_overrides, [trimmedSubject]: stage }
    try {
      setSettings(await api.saveSettings({ ...settings, subject_stage_overrides: nextOverrides }))
      setEditingOverride(false)
    } catch (cause) { setMessage(getUserMessage(cause)) }
  }

  function toggle(id: string) {
    if (isProcessing) return
    setSelectedIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])
  }

  function releasePreflight() {
    preflightLockRef.current = false
    setPreflightActive(false)
  }

  function resetPreflight() {
    releasePreflight()
    setFileResolutions(new Map())
    setResolvingId(null)
    setAttempt(null)
    setAdoptedClassification(null)
    setNormalization(undefined)
    setFilenameMode('review')
  }

  function filenamesFor(ids: string[]): Record<string, string> {
    const map: Record<string, string> = {}
    for (const id of ids) {
      const file = files.find((item) => item.id === id)
      if (file) map[id] = file.filename
    }
    return map
  }

  function resolveStageFor(subjectValue: string): Stage | undefined {
    return knownStageFor(subjectValue) ?? overrideStageFor(subjectValue, settings?.subject_stage_overrides ?? {})
  }

  function handleStart() {
    if (!folder || isProcessing) return
    const courseCheck = validateClassificationText(course, '과정명')
    const subjectCheck = validateClassificationText(subject, '과목명')
    setCourseError(courseCheck.error); setSubjectError(subjectCheck.error)
    if (courseCheck.error || subjectCheck.error) { setMessage('과정명/과목명을 확인해 주세요.'); return }
    if (needsStagePrompt) { setMessage('과목의 1차/2차 분류를 먼저 선택해 주세요.'); return }
    if (selectedIds.length === 0) {
      const targets = rows.filter((row) => row.status !== 'DONE').map((row) => row.id)
      setPendingIds(targets); setDialog(targets.length ? 'start-all' : 'empty-target'); return
    }
    const targets = rows.filter((row) => selectedSet.has(row.id) && row.status !== 'DONE').map((row) => row.id)
    if (!targets.length) { setDialog('empty-target'); return }
    void startAttempt(targets, false, 'selected')
  }

  function startAttempt(ids: string[], force: boolean, scope: 'selected' | 'all_incomplete') {
    if (preflightLockRef.current) return
    preflightLockRef.current = true
    setPreflightActive(true)

    return runPreflight(
      { ids, filenames: filenamesFor(ids), force, scope },
      new Map(),
      null,
      course,
      subject,
    )
  }

  // Walk every target in the current attempt in order (Section 9 -- never
  // just the last-toggled file): safe renames apply automatically, already-
  // correct names are no-ops, and the first unresolved MISMATCH/
  // INVALID_TARGET/CONFLICT pauses the whole attempt for an explicit user
  // choice (D24). Every rename remaps the id into the in-flight local
  // `ids`/`filenames`/`resolutions`, selectedIds, and the saved resume state
  // together -- never relying on possibly-stale React state read later
  // (Section 11). Resumes (from a resolution handler) re-enter with the
  // same target list and the resolutions accumulated so far.
  async function runPreflight(
    seed: PreflightAttempt,
    resolutionsIn: Map<string, FileResolution>,
    adoptedIn: AdoptedClassification | null,
    courseValue: string,
    subjectValue: string,
  ) {
    if (!folder) { resetPreflight(); return }
    const courseCheck = validateClassificationText(courseValue, '과정명')
    const subjectCheck = validateClassificationText(subjectValue, '과목명')
    if (courseCheck.error || subjectCheck.error) { setDialog(null); setMessage('과정명/과목명을 확인해 주세요.'); resetPreflight(); return }

    let ids = [...seed.ids]
    const filenames: Record<string, string> = { ...seed.filenames }
    let resolutions = new Map(resolutionsIn)

    const orderedFilenames = ids.map((id) => filenames[id])
    if (orderedFilenames.some((name) => !name)) {
      setMessage('선택한 파일 목록이 변경되었습니다. 다시 시도해 주세요.')
      resetPreflight()
      return
    }

    let previews: NormalizationPreview[]
    try {
      previews = await api.normalizeBatch(folder, orderedFilenames as string[], courseCheck.value, subjectCheck.value)
    } catch (cause) { setMessage(getUserMessage(cause)); resetPreflight(); return }

    let renamedAny = false

    for (let index = 0; index < ids.length; index += 1) {
      const id = ids[index]
      if (resolutions.has(id)) continue
      const preview = previews[index]
      const disposition = classifyPreview(preview)

      if (disposition === 'NO_OP') { resolutions.set(id, 'UNCHANGED'); continue }

      if (disposition === 'AUTO_RENAME' && preview.suggested_name) {
        try {
          const oldStem = preview.original_name.replace(/\.mp3$/i, '')
          const newStem = preview.suggested_name.replace(/\.mp3$/i, '')
          const response = await api.rename(folder, oldStem, newStem)
          renamedAny = true
          ids = remapId(ids, response.old_file_id, response.new_file_id)
          delete filenames[response.old_file_id]
          filenames[response.new_file_id] = preview.suggested_name
          resolutions = remapResolutionKey(resolutions, response.old_file_id, response.new_file_id)
          resolutions.set(response.new_file_id, 'AUTO_RENAME')
          setSelectedIds((current) => remapId(current, response.old_file_id, response.new_file_id))
        } catch (cause) { setMessage(getUserMessage(cause)); resetPreflight(); return }
        continue
      }

      // NEEDS_RESOLUTION, first time seen this attempt -> pause and wait for
      // an explicit user choice via FilenameReview.
      setNormalization(preview)
      setFilenameValue(preview.suggested_name ?? preview.original_name)
      setFilenameMode('review')
      setResolvingId(id)
      setFileResolutions(resolutions)
      setAdoptedClassification(adoptedIn)
      setAttempt({ ids, filenames, force: seed.force, scope: seed.scope })
      return
    }

    // Every target in this attempt now has a resolution.
    setFileResolutions(resolutions)
    setResolvingId(null)
    setNormalization(undefined)

    if (renamedAny) {
      try { await loadFolder() } catch (cause) { setMessage(getUserMessage(cause)); resetPreflight(); return }
    }

    // The current Drive classifier is still filename-based (Phase 2 not
    // done); a CONTINUE_ORIGINAL target's classification was never actually
    // confirmed, so this run's upload is forced off entirely -- never a
    // partial/opt-in upload, never an "upload anyway" override (Section 8,
    // per explicit correction).
    const forceDriveOff = needsDriveConfirmation(ids, resolutions)
    if (forceDriveOff && uploadToDrive) {
      setMessage('일부 파일의 이름/분류가 원본 그대로 유지되어, 이번 작업은 Google Drive 자동 업로드 없이 진행됩니다.')
    }

    setAttempt(null)
    setAdoptedClassification(null)
    await finalizeJob(ids, seed.force, 'selected', resolutions, forceDriveOff ? false : uploadToDrive, courseCheck.value, subjectCheck.value)
  }

  async function finalizeJob(
    ids: string[],
    force: boolean,
    scope: 'selected' | 'all_incomplete',
    resolutions: Map<string, FileResolution>,
    uploadToDriveForRun: boolean,
    courseValue: string,
    subjectValue: string,
  ) {
    if (!folder) { releasePreflight(); return }
    try {
      const created = await api.createJob({
        folder, file_ids: ids, scope, force_retranscribe: force, upload_to_drive: uploadToDriveForRun,
        course: courseValue, subject: subjectValue, stage: resolveStageFor(subjectValue),
        file_resolutions: toFileResolutionsPayload(resolutions),
      })
      setJob(created); setDialog(null); setPendingIds([]); setFileResolutions(new Map())
      setMessage('Job을 생성했습니다. 전사를 시작합니다.')
      setJob(await api.startJob(created.job_id))
      // Only remember a course/subject that actually produced a valid Job.
      if (settings) {
        try { setSettings(await api.saveSettings({ ...settings, last_course: courseValue, last_subject: subjectValue })) }
        catch { /* best-effort */ }
      }
      releasePreflight()
    } catch (cause) { setMessage(getUserMessage(cause)); setDialog(null); releasePreflight() }
  }

  async function action(actionName: 'stop' | 'cancel' | 'retry') {
    if (!job) return
    try {
      const updated = await api.actionJob(job.job_id, actionName)
      setJob(updated)
      if (actionName === 'retry' && updated.status === 'WAITING') setJob(await api.startJob(job.job_id))
    } catch (cause) { setMessage(getUserMessage(cause)) }
  }

  async function uploadDrive(retry = false) {
    if (!job) return
    const targets = Object.entries(job.files).filter(([id, state]) => state === 'DONE' && (!selectedIds.length || selectedSet.has(id))).map(([id]) => id)
    if (!targets.length) { setMessage('Drive에 업로드할 로컬 완료 파일이 없습니다.'); return }
    for (const id of targets) {
      try { await api.uploadDrive(job.job_id, id, retry || job.drive[id]?.status === 'FAILED') }
      catch (cause) { setMessage(getUserMessage(cause)) }
    }
    setJob(await api.job(job.job_id))
  }

  // The four ways a paused MISMATCH/INVALID_TARGET/CONFLICT resolution can
  // be picked, each recording a FileResolution and resuming the same
  // attempt (runPreflight) from where it left off. Every rename here remaps
  // the id into the resumed attempt's ids/filenames/resolutions together,
  // same as the automatic-rename path inside runPreflight.

  // D24 option C: continue with the file's original (unresolved) name --
  // no filesystem change; this is the only resolution that still leaves
  // classification unresolved, so it's the one that forces Drive upload off
  // for this run (Section 8) and is the only value ever sent to the backend
  // via file_resolutions (Section 12's server-side backstop).
  async function onContinueOriginalForCurrent() {
    if (!resolvingId || !attempt) return
    const next = new Map(fileResolutions)
    next.set(resolvingId, 'CONTINUE_ORIGINAL')
    await runPreflight(attempt, next, adoptedClassification, course, subject)
  }

  // Manual rename via the editable filename field -- covers INVALID_TARGET/
  // CONFLICT resolution (no course/subject mismatch, just an unrecognized
  // or colliding name) as well as a manual override for a MISMATCH file.
  async function onApplyEditedName() {
    if (!resolvingId || !attempt || !normalization || !folder) return
    if (!filenameValue.toLowerCase().endsWith('.mp3')) return
    try {
      const oldStem = normalization.original_name.replace(/\.mp3$/i, '')
      const newStem = filenameValue.replace(/\.mp3$/i, '')
      const response = await api.rename(folder, oldStem, newStem)
      const nextIds = remapId(attempt.ids, response.old_file_id, response.new_file_id)
      const nextFilenames = { ...attempt.filenames }
      delete nextFilenames[response.old_file_id]
      nextFilenames[response.new_file_id] = filenameValue
      const nextResolutions = remapResolutionKey(new Map(fileResolutions), response.old_file_id, response.new_file_id)
      nextResolutions.set(response.new_file_id, 'RENAME_TO_TYPED')
      setSelectedIds((current) => remapId(current, response.old_file_id, response.new_file_id))
      await runPreflight({ ...attempt, ids: nextIds, filenames: nextFilenames }, nextResolutions, adoptedClassification, course, subject)
    } catch (cause) { setMessage(getUserMessage(cause)); resetPreflight() }
  }

  // D24 mismatch option B: keep the typed course/subject and rename this one
  // file to match -- built from the typed values plus the week/lesson
  // already embedded in its current standard name. Never overwrites: the
  // rename endpoint rejects the call outright if the target already exists.
  async function onRenameToTypedForCurrent() {
    if (!resolvingId || !attempt || !normalization || !folder || !normalization.detected_week || !normalization.detected_lesson) return
    const courseCheck = validateClassificationText(course, '과정명')
    const subjectCheck = validateClassificationText(subject, '과목명')
    if (courseCheck.error || subjectCheck.error) return
    const targetStem = `${courseCheck.value}_${subjectCheck.value}_${normalization.detected_week}주차_${normalization.detected_lesson}강`
    try {
      const oldStem = normalization.original_name.replace(/\.mp3$/i, '')
      const response = await api.rename(folder, oldStem, targetStem)
      const nextIds = remapId(attempt.ids, response.old_file_id, response.new_file_id)
      const nextFilenames = { ...attempt.filenames }
      delete nextFilenames[response.old_file_id]
      nextFilenames[response.new_file_id] = `${targetStem}.mp3`
      const nextResolutions = remapResolutionKey(new Map(fileResolutions), response.old_file_id, response.new_file_id)
      nextResolutions.set(response.new_file_id, 'RENAME_TO_TYPED')
      setSelectedIds((current) => remapId(current, response.old_file_id, response.new_file_id))
      await runPreflight({ ...attempt, ids: nextIds, filenames: nextFilenames }, nextResolutions, adoptedClassification, courseCheck.value, subjectCheck.value)
    } catch (cause) { setMessage(getUserMessage(cause)); resetPreflight() }
  }

  // D24 mismatch option A: adopt the file's own embedded classification as
  // the job-level typed course/subject instead of renaming the file. This
  // changes the classification every *other* target in the attempt was just
  // checked against, so the whole attempt restarts from its full target
  // list under the new course/subject -- no partial carry-forward of the
  // other targets' now-stale resolutions (only this file's own resolution
  // survives the restart). If a second, different embedded classification
  // would be adopted later in the same attempt, that means the selection
  // genuinely spans more than one course/subject, which a single Job cannot
  // represent -- abort the whole attempt and ask the user to run those
  // files separately, rather than keep silently re-typing course/subject.
  async function onUseFileClassificationForCurrent() {
    if (!resolvingId || !attempt || !normalization) return
    const newCourse = normalization.detected_course
    const newSubject = normalization.detected_subject
    if (!newCourse || !newSubject) return

    if (adoptedClassification && (adoptedClassification.course !== newCourse || adoptedClassification.subject !== newSubject)) {
      setMessage('선택한 파일에 서로 다른 과정/과목 분류가 섞여 있습니다. 각 분류별로 나누어 전사해 주세요.')
      resetPreflight()
      return
    }

    onCourseChange(newCourse)
    onSubjectChange(newSubject)

    const nextKnownStage = knownStageFor(newSubject)
    const nextOverrideStage = overrideStageFor(newSubject, settings?.subject_stage_overrides ?? {})
    if (!nextKnownStage && !nextOverrideStage) {
      setMessage('이 과목의 1차/2차를 선택한 뒤 다시 전사를 시작해 주세요.')
      setEditingOverride(true)
      resetPreflight()
      return
    }

    const nextAdopted: AdoptedClassification = { course: newCourse, subject: newSubject, fromFileId: resolvingId }
    const nextResolutions = new Map<string, FileResolution>([[resolvingId, 'USE_FILE_CLASSIFICATION']])

    await runPreflight(attempt, nextResolutions, nextAdopted, newCourse, newSubject)
  }

  const crashed = rows.some((row) => row.status === 'CRASHED')
  const driveEntries = job ? Object.entries(job.drive).filter(([, state]) => state.status !== 'DISABLED') : []
  return (
    <div className="transcription-page">
      <RuntimeBanner status={backendStatus} message={message} onReconnect={() => void reconnect()} />
      <FolderSection folderPath={folder || '선택된 폴더 없음'} onChangeFolder={() => { if (!isPreflighting) void changeFolder() }} />
      <ClassificationSection
        course={course}
        subject={subject}
        courseError={courseError}
        subjectError={subjectError}
        onCourseChange={(v) => { if (!isPreflighting) onCourseChange(v) }}
        onSubjectChange={(v) => { if (!isPreflighting) onSubjectChange(v) }}
        knownStage={knownStage}
        overrideStage={overrideStage}
        needsStagePrompt={needsStagePrompt}
        onPickStage={(stage) => { if (!isPreflighting) void onPickStage(stage) }}
        onEditOverride={() => { if (!isPreflighting) setEditingOverride(true) }}
        disabled={isProcessing || isPreflighting}
      />
      {crashed ? <div className="status-banner status-banner-warning" role="status"><AlertTriangle aria-hidden="true" /><div><strong>이전 작업이 비정상적으로 종료되었습니다.</strong><span>완료 파일은 유지되며 자동 재개하지 않습니다.</span></div><Button variant="secondary" onClick={() => { if (!isPreflighting) void action('retry') }}>다시 시도</Button></div> : null}
      <TranscriptionActions completedCount={completedCount} selectedCount={selectedIds.length} totalCount={rows.length} canStart={backendStatus === 'CONNECTED' && Boolean(folder) && !isProcessing && !isPreflighting} canStop={canControl} canCancel={canControl} retryCount={failedRows.length} onStart={handleStart} onStop={() => void action('stop')} onCancel={() => void action('cancel')} onRetryFailed={() => { if (!isPreflighting) void action('retry') }} />
      {job && job.failed_files > 0 ? <div className="result-summary" aria-live="polite"><div><strong>{job.done_files}개 완료</strong><span>{job.failed_files}개 실패 · 성공한 결과는 유지됩니다.</span></div><Badge tone="failed">부분 실패</Badge></div> : null}
      <CurrentTaskSection filename={currentRow?.filename ?? job?.current_file ?? undefined} progress={job?.current_progress ?? null} status={runState} />
      <QueueTable rows={rows} selectedIds={selectedIds} currentId={currentRow?.id} onToggle={(id) => { if (!isPreflighting) toggle(id) }} onToggleAll={() => { if (!isPreflighting) setSelectedIds(selectedIds.length === rows.length ? [] : rows.map((row) => row.id)) }} onRetry={() => { if (!isPreflighting) void action('retry') }} onRetranscribe={(id) => { if (!isPreflighting) { setPendingIds([id]); setDialog('retranscribe') } }} />
      <FilenameReview preview={normalization} mode={filenameMode} value={filenameValue} onValueChange={setFilenameValue} onContinueOriginal={() => void onContinueOriginalForCurrent()} onEdit={() => setFilenameMode('editing')} onApply={() => void onApplyEditedName()} onUseFileClassification={() => void onUseFileClassificationForCurrent()} onRenameToTyped={() => void onRenameToTypedForCurrent()} />
      <section className="service-section" aria-labelledby="service-heading"><div className="section-heading-row"><div><h2 className="text-section-heading" id="service-heading">연결 및 저장 상태</h2><p>전사 결과와 외부 서비스 상태를 분리해 표시합니다.</p></div></div><div className="service-grid">
        <Card className="service-card"><div className="service-card-heading"><Cloud aria-hidden="true" /><strong>Direct Colab</strong><Badge tone={job?.engine === 'direct_colab' ? 'done' : 'waiting'}>{job?.engine === 'direct_colab' ? '현재 Job 엔진' : '사용 안 함'}</Badge></div><p>실제 Job에 저장된 engine 선택을 표시합니다.</p></Card>
        <Card className="service-card service-card-wide"><div className="service-card-heading"><Cloud aria-hidden="true" /><strong>Google Drive</strong><Badge tone={driveAuth === 'CONNECTED' ? 'done' : 'cancelled'}>{driveAuth === 'CONNECTED' ? '연결됨' : '인증 필요'}</Badge></div><p>로컬 완료 상태와 독립적으로 업로드하고 실패한 Drive만 재시도합니다.</p>
          <label className="setting-row"><span><strong>전사 완료 후 자동 업로드</strong><small>TXT/JSON/SRT 3개</small></span><input type="checkbox" checked={uploadToDrive} disabled={isPreflighting} onChange={(event) => setUploadToDrive(event.target.checked)} /></label>
          {uploadToDrive ? <DrivePathPreview course={course} subject={subject} settings={settings} /> : null}
          <div className="drive-status-list">{driveEntries.map(([id, state]) => { const view = drivePresentation[state.status]; return <div className="drive-status-item" key={id}><span>{id}</span><Badge tone={view?.tone ?? 'waiting'}>{view?.label ?? state.status}</Badge></div> })}{driveEntries.length === 0 ? <span>아직 Drive 업로드 기록이 없습니다.</span> : null}</div><div className="inline-actions"><Button variant="secondary" disabled={!driveEntries.some(([, state]) => state.status === 'FAILED') || isPreflighting} onClick={() => void uploadDrive(true)}>Drive 실패 다시 시도</Button></div></Card>
      </div></section>
      {dialog ? <div className="dialog-backdrop" role="presentation"><div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        {dialog === 'start-all' ? <><h2 className="text-card-title" id="dialog-title">전체 파일을 전사할까요?</h2><p className="dialog-summary">전체 <strong>{rows.length}개</strong> 중 완료 <strong>{completedCount}개</strong>를 제외한 <strong>{pendingIds.length}개</strong> 파일을 전사합니다.</p><div className="dialog-actions"><Button variant="secondary" onClick={() => setDialog(null)}>취소</Button><Button onClick={() => void startAttempt(pendingIds, false, 'all_incomplete')}>실행</Button></div></> : null}
        {dialog === 'empty-target' ? <><h2 className="text-card-title" id="dialog-title">처리할 파일이 없습니다</h2><p>선택한 파일이 모두 완료되었거나 실제 전사 대상이 0개입니다.</p><div className="dialog-actions"><Button onClick={() => setDialog(null)}>확인</Button></div></> : null}
        {dialog === 'retranscribe' ? <><h2 className="text-card-title" id="dialog-title">다시 전사</h2><ul className="contract-list"><li>기존 정상 결과를 보존합니다.</li><li>새 결과 검증 성공 후에만 교체합니다.</li></ul><div className="dialog-actions"><Button variant="secondary" onClick={() => setDialog(null)}>취소</Button><Button onClick={() => void startAttempt(pendingIds, true, 'selected')}>다시 전사 시작</Button></div></> : null}
      </div></div> : null}
    </div>
  )
}

function DrivePathPreview({ course, subject, settings }: { course: string; subject: string; settings?: RuntimeSettings }) {
  if (!settings) return null
  const driveRoot = settings.drive_exam_root || '2026 제37회 공인중개사 자격시험'

  const trimmedCourse = course.trim()
  const trimmedSubject = subject.trim()

  if (!trimmedCourse || !trimmedSubject) {
    return (
      <div className="setting-note">
        <span>파일명 확인 후 주차 폴더가 확정됩니다.</span>
      </div>
    )
  }

  const stage = knownStageFor(trimmedSubject) ?? overrideStageFor(trimmedSubject, settings.subject_stage_overrides) ?? '?'

  return (
    <div className="setting-note">
      <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.4 }}>
        {driveRoot}
{'\n/ '}전사자료
{'\n/ '}{trimmedCourse}
{'\n/ '}[{stage}] {trimmedSubject}
{'\n/ '}파일명 확인 후 주차 폴더가 확정됩니다.
      </div>
    </div>
  )
}

function RuntimeBanner({ status, message, onReconnect }: { status: BackendStatus; message: string; onReconnect: () => void }) {
  const connected = status === 'CONNECTED'
  return <div className={connected ? 'runtime-banner runtime-banner-connected' : 'runtime-banner'} role="status">{connected ? <CheckCircle2 aria-hidden="true" /> : <WifiOff aria-hidden="true" />}<div><strong>{status === 'OFFLINE' ? 'Backend 오프라인' : status === 'STARTING' ? 'Backend 시작 중' : 'Backend 연결됨'}</strong><span>{message}</span></div>{!connected ? <Button variant="secondary" disabled={status === 'STARTING'} onClick={onReconnect}><RefreshCw aria-hidden="true" />{status === 'STARTING' ? '연결 중' : '다시 연결'}</Button> : null}</div>
}

interface FilenameReviewProps {
  preview?: NormalizationPreview
  mode: 'review' | 'editing'
  value: string
  onValueChange: (value: string) => void
  onContinueOriginal: () => void
  onEdit: () => void
  onApply: () => void
  onUseFileClassification: () => void
  onRenameToTyped: () => void
}

function FilenameReview({
  preview, mode, value, onValueChange, onContinueOriginal, onEdit, onApply,
  onUseFileClassification, onRenameToTyped,
}: FilenameReviewProps) {
  const invalid = /[<>:"/\\|?*]/.test(value.replace(/\.mp3$/i, '')) || !value.toLowerCase().endsWith('.mp3')
  const mismatch = preview?.result_type === 'MISMATCH'

  return (
    <Card className="filename-review">
      <div className="section-heading-row">
        <div><span className="eyebrow">파일명 확인</span><h2 className="text-section-heading">정규화 결과를 확인해 주세요</h2></div>
        <FilePenLine aria-hidden="true" />
      </div>
      {!preview ? (
        <p>전사를 시작하면 이름/분류 확인이 필요한 파일이 있을 때 여기에 표시됩니다.</p>
      ) : mismatch ? (
        // D24: never silently rename/reclassify -- always require an
        // explicit choice among the file's own classification, renaming to
        // the typed classification, or continuing under the original name.
        <div role="alert">
          <dl className="filename-comparison">
            <div><dt>현재 파일</dt><dd>{preview.original_name} ({preview.detected_course}/{preview.detected_subject})</dd></div>
          </dl>
          {preview.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          <div className="inline-actions">
            <Button variant="secondary" onClick={onUseFileClassification}>현재 파일의 분류 사용</Button>
            <Button variant="secondary" onClick={onRenameToTyped}>입력한 분류로 파일명 변경</Button>
            <Button variant="secondary" onClick={onContinueOriginal}>원래 이름으로 Local 전사 계속</Button>
          </div>
        </div>
      ) : (
        <>
          <dl className="filename-comparison">
            <div><dt>원본</dt><dd>{preview.original_name}</dd></div>
            <div><dt>추천</dt><dd>{preview.suggested_name ?? preview.original_name}</dd></div>
          </dl>
          {preview.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          {mode === 'editing' ? (
            <div className="filename-editor">
              <label htmlFor="normalized-filename">수정할 이름</label>
              <input className={invalid ? 'input input-error' : 'input'} id="normalized-filename" value={value} onChange={(event) => onValueChange(event.target.value)} />
            </div>
          ) : null}
          <div className="inline-actions">
            <Button variant="secondary" onClick={onContinueOriginal}>원래 이름으로 계속</Button>
            {mode === 'editing' ? <Button disabled={invalid} onClick={onApply}>이름 적용</Button> : <Button onClick={onEdit}>이름 수정</Button>}
          </div>
        </>
      )}
    </Card>
  )
}
