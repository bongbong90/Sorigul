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
  // Drive auto-upload is intentionally NOT part of this shape -- it is a
  // per-run CreateJobRequest field, never a persisted setting (D23A).
  subject_stage_overrides: Record<string, '1차' | '2차'>
}

export interface ShutdownState {
  phase: 'inactive' | 'counting_down' | 'cancelled' | 'ready_to_shutdown'
  job_id: string | null
  deadline: string | null
  remaining_seconds: number | null
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

const configuredBase = (import.meta.env.VITE_BACKEND_URL as string | undefined)?.trim()
export const API_BASE_URL = (configuredBase || 'http://127.0.0.1:8000/api').replace(/\/$/, '')

function errorMessage(payload: unknown): string | undefined {
  if (!payload || typeof payload !== 'object') return undefined
  const detail = (payload as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return '입력값을 확인해 주세요.'
  return undefined
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError({
      code: 'BACKEND_OFFLINE',
      userMessage: 'Backend에 연결할 수 없습니다.',
      retryable: true,
    })
  }
  if (!response.ok) {
    let payload: unknown
    try {
      payload = await response.json()
    } catch {
      payload = undefined
    }
    throw new ApiError({
      code: `HTTP_${response.status}`,
      userMessage: errorMessage(payload) ?? '요청을 처리하지 못했습니다.',
      retryable: response.status >= 500 || response.status === 408 || response.status === 429,
      status: response.status,
    })
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: 'ok' }>('/health'),
  scan: (folder: string) => request<ScannedFile[]>('/scan', {
    method: 'POST', body: JSON.stringify({ folder }),
  }),
  normalize: (folder: string, filename: string, course: string, subject: string) =>
    request<NormalizationPreview>('/normalize/preview', {
      method: 'POST', body: JSON.stringify({ folder, filename, course, subject }),
    }),
  normalizeBatch: (folder: string, filenames: string[], course: string, subject: string) =>
    request<NormalizationPreview[]>('/normalize/batch', {
      method: 'POST', body: JSON.stringify({ folder, filenames, course, subject }),
    }),
  rename: (folder: string, oldStem: string, newStem: string) =>
    request<{ status: string; old_file_id: string; new_file_id: string }>('/rename', {
      method: 'POST', body: JSON.stringify({ folder, old_stem: oldStem, new_stem: newStem }),
    }),
  jobs: () => request<JobModel[]>('/jobs'),
  job: (jobId: string) => request<JobModel>(`/jobs/${encodeURIComponent(jobId)}`),
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
  }) => request<JobModel>('/jobs', { method: 'POST', body: JSON.stringify(payload) }),
  startJob: (jobId: string) => request<JobModel>(`/jobs/${encodeURIComponent(jobId)}/start`, { method: 'POST' }),
  actionJob: (jobId: string, action: 'stop' | 'cancel' | 'retry') =>
    request<JobModel>(`/jobs/${encodeURIComponent(jobId)}/action`, {
      method: 'POST', body: JSON.stringify({ action }),
    }),
  uploadDrive: (jobId: string, fileId: string, retry = false) =>
    request<DriveFileState>(
      `/jobs/${encodeURIComponent(jobId)}/files/${encodeURIComponent(fileId)}/drive${retry ? '/retry' : ''}`,
      { method: 'POST' },
    ),
  driveStatus: () => request<{ auth_state: DriveAuthState; scope: string }>('/drive/status'),
  startDriveAuth: () => request<{ state: string; authorization_url: string; scope: string }>('/drive/auth/start', {
    method: 'POST',
  }),
  completeDriveAuth: (code: string) => request<{ auth_state: DriveAuthState }>('/drive/auth/complete', {
    method: 'POST', body: JSON.stringify({ code }),
  }),
  folders: (folder: string, filter: FolderFilter) => request<FolderScanResult>('/folders/scan', {
    method: 'POST', body: JSON.stringify({ folder, filter }),
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
  events: () => request<StructuredEvent[]>('/events'),
  settings: () => request<RuntimeSettings>('/settings'),
  saveSettings: (settings: RuntimeSettings) => request<RuntimeSettings>('/settings', {
    method: 'PUT', body: JSON.stringify(settings),
  }),
  shutdown: () => request<ShutdownState>('/desktop/shutdown'),
  cancelShutdown: () => request<ShutdownState>('/desktop/shutdown/cancel', { method: 'POST' }),
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
