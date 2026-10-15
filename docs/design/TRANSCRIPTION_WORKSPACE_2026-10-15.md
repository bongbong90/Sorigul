# #193/#194 전사 작업 중심 화면 — Source 검증

2026-10-15 사용자 작업지시서의 승인 범위다. 기존 디자인 토큰과 기능을 유지한다.
설치형 Release Acceptance와 구분하며, 새로운 Freeze/MSI/설치를 수행하지 않는다.

## #193 원인 및 수정

원본 Integration `b86cb3b…`의 80행 synthetic DOM에서 화면 높이는 926px이나
문서 scrollHeight는 6063px였다. 하단 엔진 radio의 `.visually-hidden` 절대 위치가
BODY를 containing block으로 사용하며 top 6062px까지 문서 overflow를 확장했다.
`.app-main`에 containing block을 지정하자 문서 높이가 viewport와 같아졌다.
엔진 option/queue wrapper에도 로컬 배치 기준을 지정한다. 스크롤바를 숨기는
CSS 대신 `.app-main` 하나가 콘텐츠의 수직 스크롤을 소유한다.

## #194 승인된 화면 구성

- 전사 작업 버튼은 하나의 HeaderActions portal로 제목 오른쪽에 둔다.
  기존 callback/disabled 조건을 유지하며 다른 화면에는 렌더링하지 않는다.
- 전체 진행률은 본문에 독립적인 작은 행으로 남긴다. 유휴 작업 카드를 줄이고
  검토할 파일명이 없을 때 빈 검토 카드를 표시하지 않는다.
- 전사에는 폴더/분류/엔진/작업별 Drive opt-in/진행/목록/실제 오류를 남긴다.
  opt-in은 앱 시작마다 OFF다. Job의 실제 엔진과 파일별 Drive 상태를 표시한다.
- 설정에 Drive 인증/업로드 기록/실패한 Drive만 재시도, Colab 연결 준비·수동 URL,
  Backend와 Local Runtime 상태를 통합한다. Runtime probe는 기존 검증 캐시를
  재사용해 파일/manifest/앱 빌드를 확인하며 Worker/모델/GPU를 실행하지 않는다.
  연결 가능 상태를 GPU 실행 성공으로 확대 표시하지 않는다.
- 전사 페이지는 화면 이동 중에도 유지해 입력/선택/진행을 보존하고, Colab의
  검증된 연결 URL은 App 상태에서 공유한다. 설정의 작업 상태 불확실 시 엔진
  변경을 막는다. 연결 조작과 Drive retry는 명시적 버튼으로만 실행한다.

## 검증 결과

- 집중 pytest **206 PASS**: preflight/폴더 변경/manual week/엔진 계약/UX/Local,
  읽기 전용 Runtime probe 4가지(정상/불일치/해시 오류/없음) 포함.
- Frontend typecheck/lint **PASS**.
- 실제 source App/pages/CSS + synthetic API의 Chromium DOM **PASS**.
- 별도 Tauri QA host의 Windows WebView2 source UI **PASS**: 1440×926,
  1024×768, 800×650, 1920×1080, 80행 마지막 접근, 한 수직 스크롤,
  헤더 버튼 배치/Tab, 휠/PageDown, 전체 선택, 4화면 이동, 입력/진행 보존,
  시작/중지/취소/실패 재시도, 완료/부분 실패/Runtime 오류,
  자동 업로드 기본 OFF, Drive만 retry, 설정에서 Colab 연결 후 복귀.
- 실제 MP3/Drive OAuth/API/Runtime 전환/설치본 실행 **NOT RUN**.
  최종 병합 Source의 설치형 종료/릴리스 재검증은 별도 계획된 주기에 필요하다.

## 재현 명령

저장소 root에서 `node tests/frontend/transcription_workspace_dom.mjs`.
`--baseline`은 고정된 원본 Integration을 `git show`로 읽어 변경 전 DOM을 렌더링한다.
실제 코드와 CSS를 사용하며 API/native/hooks만 synthetic 구현으로 대체한다.

Windows WebView2 검증은 `frontend/src-tauri`에서 다음 QA example만 컴파일한다.
이는 MSI/Release 빌드가 아니며 product main/plugins/backend를 실행하지 않는다.

```powershell
cargo rustc --locked --offline --example transcription_workspace_qa -- -C link-arg=/MANIFEST:EMBED -C link-arg=/MANIFESTINPUT:examples/transcription_workspace_qa.manifest
node ../../tests/frontend/transcription_workspace_dom.mjs --webview2
```

Node는 workspace tmp의 새로운 profile과 임시 loopback port를 사용한다.
결과 JSON/synthetic screenshots/profile은 Git ignored tmp에 보존한다.
Common Controls v6 manifest 누락과 초기 WebView 탐색 경합은 QA 도구에서 수정했다.
실패 시도는 제품 PASS 증거가 아니며 최종 성공한 시도만 위 결과에 포함한다.
