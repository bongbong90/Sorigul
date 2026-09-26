export type FileStatus =
  | 'WAITING'
  | 'PREPARING'
  | 'TRANSCRIBING'
  | 'SAVING'
  | 'VERIFYING'
  | 'DONE'
  | 'FAILED'
  | 'STOPPED'
  | 'CANCELLED'
  | 'CRASHED'
  | 'CANCEL_REQUESTED'

export type DriveStatus =
  | 'DISABLED'
  | 'AUTH_REQUIRED'
  | 'CLASSIFICATION_FAILED'
  | 'PENDING'
  | 'UPLOADING'
  | 'DONE'
  | 'FAILED'

export type DriveAuthState =
  | 'UNAUTHENTICATED'
  | 'AUTHORIZING'
  | 'CONNECTED'
  | 'REFRESH_FAILED'
  | 'REAUTH_REQUIRED'

export interface DriveFileState {
  status: DriveStatus
  error: string | null
  remote_file_ids: Record<string, string>
  updated_at: string
}

export interface ScannedFile {
  id: string
  filename: string
  source_path: string
  size: number
  modified_at: string
  completion_status: 'DONE' | 'INCOMPLETE' | 'INVALID_RESULT'
  duration_seconds: number | null
  needs_rename: boolean | null
}

export interface NormalizationPreview {
  original_name: string
  suggested_name: string | null
  detected_course: string | null
  detected_subject: string | null
  detected_week: string | null
  detected_lesson: string | null
  warnings: string[]
  conflicts: string[]
  can_apply: boolean
  // NORMALIZED | UNCHANGED | MISMATCH | INVALID_TARGET | CONFLICT
  result_type: string
}

export interface FileMetadata {
  week: string | null
  lesson: string | null
  normalized_name: string | null
}

export interface JobEvent {
  timestamp: string
  level: string
  category: string
  message: string
  file_id?: string | null
  filename?: string | null
}

export interface JobModel {
  job_id: string
  created_at: string
  updated_at: string
  status: FileStatus
  folder: string
  engine: string
  force_retranscribe: boolean
  upload_to_drive: boolean
  total_files: number
  done_files: number
  failed_files: number
  current_file: string | null
  current_progress: number | null
  eta_seconds: number | null
  files: Record<string, FileStatus>
  events: JobEvent[]
  drive: Record<string, DriveFileState>
  error: string | null
  course: string | null
  subject: string | null
  stage: '1차' | '2차' | null
  file_metadata: Record<string, FileMetadata>
}

export type FolderFilter = 'all' | 'complete' | 'incomplete' | 'results'

export interface FolderItem {
  id: string
  filename: string
  kind: 'MP3' | 'TXT' | 'JSON' | 'SRT'
  status: 'COMPLETE' | 'INCOMPLETE' | 'RESULT'
  size: number
  modified_at: string
  has_source: boolean
}

export interface FolderScanResult {
  scan_id: string
  folder: string
  filter: FolderFilter
  items: FolderItem[]
  counts: Record<FolderFilter, number>
}

export interface TextContent {
  filename: string
  text: string
  truncated: boolean
}

export interface StructuredEvent extends JobEvent {
  source: 'job' | 'application'
  job_id?: string | null
  desktop_intent?: string | null
}

export interface RuntimeSettings {
  notifications: {
    file_complete: boolean
    job_complete: boolean
  }
  close_behavior: 'tray' | 'exit'
  shutdown: 'disabled' | 'immediate' | '15_seconds' | '30_seconds'
  transcription_folder: string | null
  last_course: string | null
  last_subject: string | null
  last_engine: 'local_whisper' | 'direct_colab'
  // Drive auto-upload is intentionally NOT part of this shape -- it is a
  // per-run CreateJobRequest field, never a persisted setting (D23A).
  subject_stage_overrides: Record<string, '1차' | '2차'>
  drive_exam_root: string
}

export interface ShutdownState {
  phase: 'inactive' | 'counting_down' | 'cancelled' | 'ready_to_shutdown'
  job_id: string | null
  deadline: string | null
  remaining_seconds: number | null
}

export interface RendezvousState {
  state: 'WAITING' | 'FOUND' | 'CONNECTED' | 'FAILED' | 'EXPIRED' | 'AUTH_REQUIRED' | 'PAIRING_REQUIRED'
  base_url?: string | null
  request_id?: string | null
}

export interface ApiErrorShape {
  code: string
  userMessage: string
  retryable: boolean
  status?: number
}

export class ApiError extends Error implements ApiErrorShape {
  code: string
  userMessage: string
  retryable: boolean
  status?: number

  constructor(value: ApiErrorShape) {
    super(value.userMessage)
    this.name = 'ApiError'
    this.code = value.code
    this.userMessage = value.userMessage
    this.retryable = value.retryable
    this.status = value.status
  }
}

export const REQUEST_TIMEOUT_MS = {
  FAST_LOCAL: 5_000,
  STANDARD_LOCAL: 30_000,
  // Backend Drive I/O is bounded at 60s and Colab readiness at 12s.
  LONG_EXTERNAL_BRIDGE: 90_000,
} as const

interface RequestOptions extends RequestInit {
  timeoutMs?: number
}

const configuredBase = (import.meta.env.VITE_BACKEND_URL as string | undefined)?.trim()
export const API_BASE_URL = (configuredBase || 'http://127.0.0.1:8000/api').replace(/\/$/, '')

function errorMessage(payload: unknown): string | undefined {
  if (!payload || typeof payload !== 'object') return undefined
  const detail = (payload as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return '입력값을 확인해 주세요.'
  return undefined
}

async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const { timeoutMs = REQUEST_TIMEOUT_MS.STANDARD_LOCAL, signal: callerSignal, ...fetchInit } = init
  const controller = new AbortController()
  let timedOut = false
  const abortFromCaller = () => controller.abort(callerSignal?.reason)
  if (callerSignal?.aborted) abortFromCaller()
  else callerSignal?.addEventListener('abort', abortFromCaller, { once: true })
  const timer = window.setTimeout(() => {
    timedOut = true
    controller.abort('request-timeout')
  }, timeoutMs)

  let responseReceived = false
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...fetchInit,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...fetchInit.headers },
    })
    responseReceived = true
    if (!response.ok) {
      let payload: unknown
      try {
        payload = await response.json()
      } catch (error) {
        if (controller.signal.aborted) throw error
        payload = undefined
      }
      throw new ApiError({
        code: `HTTP_${response.status}`,
        userMessage: errorMessage(payload) ?? '요청을 처리하지 못했습니다.',
        retryable: response.status >= 500 || response.status === 408 || response.status === 429,
        status: response.status,
      })
    }
    return await response.json() as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (timedOut) {
      const mutation = Boolean(fetchInit.method && !['GET', 'HEAD'].includes(fetchInit.method.toUpperCase()))
      throw new ApiError({
        code: 'REQUEST_TIMEOUT',
        userMessage: mutation
          ? '요청 시간이 초과되어 결과를 확인할 수 없습니다. 상태를 다시 확인해 주세요.'
          : '요청 시간이 초과되었습니다. 상태를 다시 확인해 주세요.',
        retryable: true,
      })
    }
    if (controller.signal.aborted) {
      throw new ApiError({
        code: 'REQUEST_ABORTED',
        userMessage: '요청이 취소되었습니다.',
        retryable: false,
      })
    }
    if (responseReceived) {
      throw new ApiError({
        code: 'INVALID_RESPONSE',
        userMessage: 'Backend 응답을 읽지 못했습니다.',
        retryable: true,
      })
    }
    throw new ApiError({
      code: 'BACKEND_OFFLINE',
      userMessage: 'Backend에 연결할 수 없습니다.',
      retryable: true,
    })
  } finally {
    window.clearTimeout(timer)
    callerSignal?.removeEventListener('abort', abortFromCaller)
  }
}

export const api = {
  health: (signal?: AbortSignal) => request<{ status: 'ok' }>('/health', { signal, timeoutMs: REQUEST_TIMEOUT_MS.FAST_LOCAL }),
  scan: (folder: string, signal?: AbortSignal) => request<ScannedFile[]>('/scan', {
    method: 'POST', body: JSON.stringify({ folder }), signal, timeoutMs: REQUEST_TIMEOUT_MS.STANDARD_LOCAL,
  }),
  normalize: (folder: string, filename: string, course: string, subject: string) =>
    request<NormalizationPreview>('/normalize/preview', {
      method: 'POST', body: JSON.stringify({ folder, filename, course, subject }), timeoutMs: REQUEST_TIMEOUT_MS.STANDARD_LOCAL,
    }),
  normalizeBatch: (folder: string, filenames: string[], course: string, subject: string) =>
    request<NormalizationPreview[]>('/normalize/batch', {
      method: 'POST', body: JSON.stringify({ folder, filenames, course, subject }), timeoutMs: REQUEST_TIMEOUT_MS.STANDARD_LOCAL,
    }),
  rename: (folder: string, oldStem: string, newStem: string) =>
    request<{ status: string; old_file_id: string; new_file_id: string }>('/rename', {
      method: 'POST', body: JSON.stringify({ folder, old_stem: oldStem, new_stem: newStem }), timeoutMs: REQUEST_TIMEOUT_MS.STANDARD_LOCAL,
    }),
  jobs: (signal?: AbortSignal) => request<JobModel[]>('/jobs', { signal, timeoutMs: REQUEST_TIMEOUT_MS.FAST_LOCAL }),
  job: (jobId: string, signal?: AbortSignal) => request<JobModel>(`/jobs/${encodeURIComponent(jobId)}`, { signal, timeoutMs: REQUEST_TIMEOUT_MS.FAST_LOCAL }),
  createJob: (payload: {
    folder: string
    file_ids: string[]
    scope: 'selected' | 'all_incomplete'
    force_retranscribe?: boolean
    engine?: 'local_whisper' | 'direct_colab'
    colab_url?: string
    upload_to_drive?: boolean
    course: string
    subject: string
    stage?: '1차' | '2차'
    file_resolutions?: Record<string, 'CONTINUE_ORIGINAL'>
  }) => request<JobModel>('/jobs', { method: 'POST', body: JSON.stringify(payload), timeoutMs: REQUEST_TIMEOUT_MS.STANDARD_LOCAL }),
  startJob: (jobId: string) => request<JobModel>(`/jobs/${encodeURIComponent(jobId)}/start`, { method: 'POST', timeoutMs: REQUEST_TIMEOUT_MS.STANDARD_LOCAL }),
  actionJob: (jobId: string, action: 'stop' | 'cancel' | 'retry') =>
    request<JobModel>(`/jobs/${encodeURIComponent(jobId)}/action`, {
      method: 'POST', body: JSON.stringify({ action }), timeoutMs: REQUEST_TIMEOUT_MS.STANDARD_LOCAL,
    }),
  uploadDrive: (jobId: string, fileId: string, retry = false) =>
    request<DriveFileState>(
      `/jobs/${encodeURIComponent(jobId)}/files/${encodeURIComponent(fileId)}/drive${retry ? '/retry' : ''}`,
      { method: 'POST', timeoutMs: REQUEST_TIMEOUT_MS.LONG_EXTERNAL_BRIDGE },
    ),
  driveStatus: (signal?: AbortSignal) => request<{ auth_state: DriveAuthState; scope: string }>('/drive/status', { signal, timeoutMs: REQUEST_TIMEOUT_MS.LONG_EXTERNAL_BRIDGE }),
  startDriveAuth: () => request<{ state: string; authorization_url: string; scope: string }>('/drive/auth/start', {
    method: 'POST', timeoutMs: REQUEST_TIMEOUT_MS.LONG_EXTERNAL_BRIDGE,
  }),
  completeDriveAuth: (code: string) => request<{ auth_state: DriveAuthState }>('/drive/auth/complete', {
    method: 'POST', body: JSON.stringify({ code }), timeoutMs: REQUEST_TIMEOUT_MS.LONG_EXTERNAL_BRIDGE,
  }),
  folders: (folder: string, filter: FolderFilter) => request<FolderScanResult>('/folders/scan', {
    method: 'POST', body: JSON.stringify({ folder, filter }), timeoutMs: REQUEST_TIMEOUT_MS.STANDARD_LOCAL,
  }),
  textPreview: (scanId: string, itemId: string) =>
    request<TextContent>(`/folders/${encodeURIComponent(scanId)}/items/${encodeURIComponent(itemId)}/preview`),
  fullText: (scanId: string, itemId: string) =>
    request<TextContent>(`/folders/${encodeURIComponent(scanId)}/items/${encodeURIComponent(itemId)}/text`),
  openFolderIntent: (scanId: string, itemId?: string) => {
    const query = itemId ? `?item_id=${encodeURIComponent(itemId)}` : ''
    return request<{ action: 'OPEN_FOLDER'; folder: string; item_filename?: string }>(
      `/folders/${encodeURIComponent(scanId)}/open-intent${query}`,
      { method: 'POST' },
    )
  },
  events: (signal?: AbortSignal) => request<StructuredEvent[]>('/events', { signal, timeoutMs: REQUEST_TIMEOUT_MS.FAST_LOCAL }),
  settings: (signal?: AbortSignal) => request<RuntimeSettings>('/settings', { signal, timeoutMs: REQUEST_TIMEOUT_MS.FAST_LOCAL }),
  saveSettings: (settings: RuntimeSettings, signal?: AbortSignal) => request<RuntimeSettings>('/settings', {
    method: 'PUT', body: JSON.stringify(settings), signal, timeoutMs: REQUEST_TIMEOUT_MS.STANDARD_LOCAL,
  }),
  startColabRendezvous: (signal?: AbortSignal) => request<RendezvousState>('/colab/rendezvous/start', { method: 'POST', signal, timeoutMs: REQUEST_TIMEOUT_MS.LONG_EXTERNAL_BRIDGE }),
  pollColabRendezvous: (requestId: string, signal?: AbortSignal) => request<RendezvousState>('/colab/rendezvous/' + encodeURIComponent(requestId), { signal, timeoutMs: REQUEST_TIMEOUT_MS.LONG_EXTERNAL_BRIDGE }),
  verifyColabUrl: (url: string, requestId: string, signal?: AbortSignal) => request<RendezvousState>('/colab/verify', {
    method: 'POST', body: JSON.stringify({ url, request_id: requestId }), signal, timeoutMs: REQUEST_TIMEOUT_MS.LONG_EXTERNAL_BRIDGE,
  }),
  shutdown: (signal?: AbortSignal) => request<ShutdownState>('/desktop/shutdown', { signal, timeoutMs: REQUEST_TIMEOUT_MS.FAST_LOCAL }),
  cancelShutdown: () => request<ShutdownState>('/desktop/shutdown/cancel', { method: 'POST', timeoutMs: REQUEST_TIMEOUT_MS.STANDARD_LOCAL }),
}

export function isRequestAbort(error: unknown): boolean {
  return error instanceof ApiError && error.code === 'REQUEST_ABORTED'
}

export function isRequestTimeout(error: unknown): boolean {
  return error instanceof ApiError && error.code === 'REQUEST_TIMEOUT'
}

export function getUserMessage(error: unknown): string {
  return error instanceof ApiError ? error.userMessage : '알 수 없는 오류가 발생했습니다.'
}

const FOLDER_STORAGE_KEY = 'sorigul.transcriptionFolder'

export function getSavedFolder(): string {
  return window.localStorage.getItem(FOLDER_STORAGE_KEY)
    ?? (import.meta.env.VITE_TRANSCRIPTION_FOLDER as string | undefined)
    ?? ''
}

export function saveFolder(folder: string): void {
  if (folder) window.localStorage.setItem(FOLDER_STORAGE_KEY, folder)
  else window.localStorage.removeItem(FOLDER_STORAGE_KEY)
}
