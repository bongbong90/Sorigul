export type CurrentTaskStatus =
  | 'IDLE'
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
  | 'RETRYING'
  | 'CANCEL_REQUESTED'

export const currentTaskStatusPresentation = {
  IDLE: { label: '준비', tone: 'waiting' as const, detail: '전사 대기' },
  WAITING: { label: '대기', tone: 'waiting' as const, detail: '작업 시작 대기' },
  PREPARING: { label: '준비 중', tone: 'preparing' as const, detail: '엔진 준비 중' },
  TRANSCRIBING: {
    label: '전사 중',
    tone: 'transcribing' as const,
    detail: '전사 진행 중',
  },
  VERIFYING: { label: '검증 중', tone: 'verifying' as const, detail: '결과 파일 확인 중' },
  SAVING: { label: '저장 중', tone: 'preparing' as const, detail: '결과 파일 저장 중' },
  DONE: { label: '완료', tone: 'done' as const, detail: '선택한 파일 완료' },
  FAILED: { label: '실패', tone: 'failed' as const, detail: '오류 원인을 확인해 주세요' },
  STOPPED: { label: '중지됨', tone: 'stopped' as const, detail: '다시 시도하면 처음부터 처리' },
  CANCELLED: { label: '취소됨', tone: 'cancelled' as const, detail: '미완료 파일은 다시 시도 가능' },
  CRASHED: { label: '복구 필요', tone: 'crashed' as const, detail: '완료된 파일은 유지됩니다' },
  RETRYING: { label: '재시도 중', tone: 'retrying' as const, detail: '현재 파일을 처음부터 처리 중' },
  CANCEL_REQUESTED: {
    label: '취소 요청 중',
    tone: 'cancelled' as const,
    detail: '안전하게 작업을 마치는 중',
  },
}
