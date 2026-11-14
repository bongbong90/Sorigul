# [SORIGUL] PHASE 18 — 별도 승인 후 LIVE 검증 계획

이 문서는 실행 승인이 아니다. PHASE 18에서는 실제 OAuth 동의·Google 계정 접근·Runtime/GPU 실행을 하지 않았다. 정책 문의는 진행 중이며 결제정보 미연결·과거 성공·FREE 응답만으로 정책/비용 gate를 해제하지 않는다. #252 #48 #60 #233 #114 #7 추적을 유지한다.

## 사전 준비

- 소스·Commit·Draft PR 및 설치본/Backend identity를 확인한다. 테스트 계정·전용 Google Cloud 프로젝트/Desktop client를 사용하고 Drive 설정과 분리한다.
- 공식 Colab 엔진 DEFAULT OFF, COST_GATE CONDITIONAL, POLICY_GATE NOT VERIFIED를 유지한다. GUI/Job/API 요청으로 실행 승인을 우회하지 않는다.
- 미정리 ownership·이전 불확실 실행·진행 중 공식 Job이 없어야 한다. 기존 사용자 설정·결과물·Drive token·기존 Runtime을 보존한다.
- 실제 강의 MP3 대신 검증용 짧은 합성 음성을 준비한다. 실제 계정/token/email/프로필은 로그·Job·보고서에 기록하지 않는다.

## 1단계 — 사용자 승인 후 인증·읽기 전용 검증

**필요 승인:** 특정 Google 테스트 계정으로 OAuth 동의 및 최소 Scope 발급, token/인증서/UserInfo 확인, subscription 및 runtimespecs의 읽기 전용 GET. Runtime 생성·삭제·Jupyter·패키지·모델·Drive 변경은 승인 범위에 포함하지 않는다.

1. Google에서 발급된 별도 Desktop client JSON을 제품 전용 경로에 배치한다. client ID/project가 Drive와 다르고 endpoint가 고정 Google 주소인지 확인한다. JSON·Secret·token 원문을 증빙에 붙이지 않는다.
2. 설치형 제품에서 Google Colab 연결을 눌러 기본 브라우저 consent → PKCE loopback → signed OIDC nonce/계정 대조 → DPAPI 저장을 확인한다.
3. 실제 Token 응답의 정확한 Scope 집합과 연결 상태를 확인한다. scope_evidence와 Runtime 생성 권한 NOT_VERIFIED를 구분한다. 권한 누락·다른 계정·오래된 응답·취소는 실패로 처리한다.
4. 명시적 연결 상태 확인으로 기존 read-only preflight를 실행한다. subscription tier와 T4 eligible 여부, 오류/접근 제한을 기록한다. Runtime POST/DELETE는 0회여야 한다.
5. refresh·재인증·취소·연결 해제/철회는 합의된 테스트 계정에서만 확인한다. 미정리 ownership이 생기면 계정 변경/철회를 중지하고 기존 회복 절차를 따른다.

**확인 가능한 정보:** Token 발급·부여 Scope·계정 일치, 읽기 API 접근, 응답 시점의 공식 구독 tier 및 runtime spec/eligibility.

**확인 불가능하거나 별도 근거가 필요한 정보:** Runtime 생성 권한의 실증, 향후 GPU 확보, 자동화 정책 적합성, paid CU가 절대 소비되지 않는다는 보장, 완전한 사용량/과금 원장. 지원되는 공개 API에 근거가 없는 항목은 NOT VERIFIED/NO_SUPPORTED_API로 남긴다. 결제수단 미연결은 참고 조건에만 기록한다.

**완료 판정:** 인증·읽기 전용 결과만 PASS/FAIL. 전사/비용/정책/실사용 준비 PASS로 확대하지 않는다. 1단계 결과 보고 후 STOP하고 2단계 승인을 기다린다.

## 2단계 — 별도 승인 후 제한적 Runtime/GPU 검증

**필요 승인:** 정확한 계정·소스·기간·Runtime 1개에 대한 생성/조회/삭제, GPU 확인, Jupyter/Contents 접근, 고정 패키지 설치, 고정 large-v3 다운로드, 합성 MP3 전송·전사·결과 회수. 비용 노출·중단 조건과 정리 권한을 별도로 합의한다. 승인만으로 현재 제품의 비용/정책 gate가 충족되는 것은 아니다. 근거와 서버 권한을 함께 검토하기 전 실행하지 않는다.

1. 승인된 서버 경로의 launch/provisioning 권한과 시간/자원 한도를 명시한다. DEFAULT OFF를 영구 설정값이나 클라이언트 요청으로 바꾸지 않는다. 자동 paid GPU/CU 전환·구매·임의 외부 터널은 금지한다.
2. 정확히 한 번의 임시 Runtime 생성 시도와 소유권 checkpoint를 기록한다. 생성 응답 유실·계정 불일치·정리 불확실이면 자동 재시도/새 Runtime 없이 중단한다.
3. 실제 장치와 CUDA, 고정 패키지 faster-whisper 1.2.1 / ctranslate2 4.6.0 / huggingface-hub 0.36.0을 확인한다. 다른 버전/CPU로 전환하지 않는다.
4. Systran/faster-whisper-large-v3 revision edaa852ec7e145841d8ffdb056a99866b5f0a478만 준비한다. 캐시·필수 파일·실제 CUDA 로드 → 기존 prepare() 재검증을 수행한다. 공급망 전체 무결성은 독립 해시/서명 검증 없이 PASS로 보고하지 않는다.
5. #233: 실제 Contents PUT/GET의 format·size·hash·acknowledgement·DELETE 호환성을 시험용 파일로 확인한다. 미확인 응답을 소유권 증명으로 취급하거나 사용자 기존 파일을 정리하지 않는다.
6. 짧은 합성 MP3를 전사하고 TXT/JSON/SRT Bundle·시간축·내용·저장·회수·정상 결과 보존을 검증한다.
7. PHASE 16A close_session()으로 해당 소유 Runtime만 정리한다. 삭제 실패·응답 유실은 CLEANUP_REQUIRED/STATE_UNCERTAIN으로 남기고 정리 성공을 추정하지 않는다.
8. 승인된 공식 화면/지원 API 범위에서 실행 전후 구독·비용·사용량 관찰을 기록한다. 관찰할 수 없는 paid CU 항목은 NOT VERIFIED로 유지한다.

**중단 조건:** 유료/불명확 구독·GPU 없음·예상 밖 계정·Scope·추가 비용 요구·정책 제한·예상 밖 endpoint·불완전 모델·불확실 커널·정리 실패. 실제로 시작한 작업의 안전한 정리는 합의한 소유권 범위에서 수행하며 사용자 기존 Runtime이나 정상 Bundle은 보존한다.

## 이후 확장

2단계 결과를 검토한 뒤 긴 MP3, 실제 STOP/CANCEL·네트워크 단절·프로세스 손실·재시작/복구를 별도 범위로 승인한다. 실제 강의 파일 사용과 Drive 자동 업로드는 별도 승인하며 Drive 인증·권한·파일 변화를 독립적으로 검증한다. #114 STUDY USE READY와 MAIN MERGE는 설치형 전체 흐름의 근거와 명시적 승인 전까지 NO/HOLD다.
