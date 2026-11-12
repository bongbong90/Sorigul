import type { ChangeEvent } from 'react'
import type { Stage } from '../../lib/classification'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Input } from '../ui/Input'

interface ClassificationSectionProps {
  course: string
  subject: string
  courseError?: string
  subjectError?: string
  onCourseChange: (value: string) => void
  onSubjectChange: (value: string) => void
  knownStage?: Stage
  overrideStage?: Stage
  needsStagePrompt: boolean
  onPickStage: (stage: Stage) => void
  onEditOverride: () => void
  disabled?: boolean
}

export function ClassificationSection({
  course,
  subject,
  courseError,
  subjectError,
  onCourseChange,
  onSubjectChange,
  knownStage,
  overrideStage,
  needsStagePrompt,
  onPickStage,
  onEditOverride,
  disabled,
}: ClassificationSectionProps) {
  const resolvedStage = knownStage ?? overrideStage

  return (
    <Card className="classification-section">
      <div className="section-heading-row">
        <div>
          <span className="eyebrow">전사 파일 분류</span>
          <h2 className="text-section-heading">과정명과 과목명을 입력해 주세요</h2>
        </div>
      </div>
      <div className="classification-grid">
        <Input
          label="과정명"
          placeholder="예: 개념완성"
          value={course}
          disabled={disabled}
          error={Boolean(courseError)}
          helperText={courseError}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onCourseChange(event.target.value)}
        />
        <Input
          label="과목명"
          placeholder="예: 부동산학개론"
          value={subject}
          disabled={disabled}
          error={Boolean(subjectError)}
          helperText={subjectError}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onSubjectChange(event.target.value)}
        />
      </div>
      {resolvedStage && !needsStagePrompt ? (
        <div className="setting-note">
          <Badge tone="waiting">{resolvedStage}</Badge>
          {knownStage ? (
            <span>알려진 과목으로 자동 분류되었습니다.</span>
          ) : (
            <>
              <span>이전에 저장한 분류입니다.</span>
              <Button variant="secondary" onClick={onEditOverride} disabled={disabled}>
                1차/2차 변경
              </Button>
            </>
          )}
        </div>
      ) : null}
      {needsStagePrompt ? (
        <div className="setting-note" role="alert">
          <span>알 수 없는 과목입니다. 1차 또는 2차를 선택해 주세요.</span>
          <div className="inline-actions">
            <Button variant="secondary" onClick={() => onPickStage('1차')} disabled={disabled}>
              1차
            </Button>
            <Button variant="secondary" onClick={() => onPickStage('2차')} disabled={disabled}>
              2차
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  )
}
