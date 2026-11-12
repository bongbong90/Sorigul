import { Badge } from './components/ui/Badge'
import { Button } from './components/ui/Button'
import { Card } from './components/ui/Card'
import { Input } from './components/ui/Input'
import { Progress } from './components/ui/Progress'

function App() {
  return (
    <main className="foundation-preview">
      <div className="foundation-preview-header">
        <h1 className="text-page-title">소리글</h1>
        <p className="text-body">Design System Foundation Preview</p>
      </div>

      <section className="foundation-preview-section">
        <h2 className="text-section-heading">Typography</h2>
        <p className="text-page-title">페이지 타이틀 24 / Bold</p>
        <p className="text-card-title">카드 타이틀 20 / SemiBold</p>
        <p className="text-section-heading">섹션 헤딩 16 / SemiBold</p>
        <p className="text-body">기본 본문 14 / Regular</p>
        <p className="text-label">라벨 14 / Medium</p>
        <p className="text-caption">캡션 13 / Regular</p>
        <p className="text-timestamp">타임스탬프 12 / Regular</p>
      </section>

      <section className="foundation-preview-section">
        <h2 className="text-section-heading">Button</h2>
        <div className="foundation-preview-row">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="primary" disabled>
            Disabled
          </Button>
        </div>
      </section>

      <section className="foundation-preview-section">
        <h2 className="text-section-heading">Input</h2>
        <div className="foundation-preview-column foundation-preview-example">
          <Input label="샘플 라벨" placeholder="Sample Input" />
          <Input label="에러 상태" defaultValue="잘못된 값" error helperText="에러 메시지 예시" />
          <Input label="비활성 상태" defaultValue="수정할 수 없는 값" disabled />
        </div>
      </section>

      <section className="foundation-preview-section">
        <h2 className="text-section-heading">Badge</h2>
        <div className="foundation-preview-row">
          <Badge tone="waiting">대기</Badge>
          <Badge tone="preparing">준비 중</Badge>
          <Badge tone="transcribing">전사 중</Badge>
          <Badge tone="saving">저장 중</Badge>
          <Badge tone="done">완료</Badge>
          <Badge tone="failed">실패</Badge>
          <Badge tone="cancelled">중지됨</Badge>
        </div>
      </section>

      <section className="foundation-preview-section">
        <h2 className="text-section-heading">Progress</h2>
        <div className="foundation-preview-example">
          <Progress value={50} label="샘플 진행률" />
        </div>
      </section>

      <section className="foundation-preview-section">
        <h2 className="text-section-heading">Card</h2>
        <div className="foundation-preview-example">
          <Card>
            <p className="text-body">Surface Example</p>
          </Card>
        </div>
      </section>
    </main>
  )
}

export default App
