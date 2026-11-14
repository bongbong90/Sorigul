# [SORIGUL PHASE 17 결과]

- 작업 판정: 구현·Mock E2E·Backend 전체 회귀 PASS. 실제 운영 승인과 실환경 검증은 미실행.
- 전용 Issue: [#250](https://github.com/bongbong90/Sorigul/issues/250)
- 부모 PR: #249
- 부모 HEAD: `0639b37b8c4312db75c42de064702b51dedee3fe` (착수·완료 전 원격 부모 브랜치와 일치 확인)
- Branch: `feature/48-colab-automatic-model-provisioning`
- Draft PR base: `fix/248-colab-runtime-finally-cleanup`
- 완료 Commit·Push·Draft PR 링크: Issue #250 및 #7 완료 댓글에 기록.

## 구현 결과

서버 전용 provisioning authorizer → 소유 Runtime/계정 재검증 → CHECK → 필요한 고정 패키지만 INSTALL → 필요한 고정 모델만 DOWNLOAD → VERIFY(CUDA 모델 실제 로드) → 기존 읽기 전용 prepare() → MP3 전사 → Runner/Writer Bundle → PHASE 16A close_session() 흐름을 구현했다. 같은 커널의 로드된 모델을 재사용한다. 기본 경로는 설치·다운로드 권한을 부여하지 않는다.

패키지 계약은 faster-whisper 1.2.1 / ctranslate2 4.6.0 / huggingface-hub 0.36.0이다. 원격 현재 Python의 고정 pip 명령, wheel 전용 설치, PyPI 고정 index, pip 설정 격리를 사용한다. 설치 후 metadata와 실제 import 버전을 재검증한다.

모델은 Systran/faster-whisper-large-v3 / revision edaa852ec7e145841d8ffdb056a99866b5f0a478로 고정한다. local-only 캐시 조회, revision 디렉터리·필수 파일·incomplete 검사, 고정 Hub endpoint·token=False, 다운로드 후 재검증 및 CUDA 모델 로드를 수행한다. 독립 해시·서명·전이 의존성 전체 고정은 NOT VERIFIED이며 공급망 무결성 전체 PASS를 주장하지 않는다.

GPU는 고정 nvidia-smi 조회와 ctranslate2 CUDA device count로 검사한다. 새 준비 경로는 GPU 상실·CUDA 실패 때 CPU나 유료 자원으로 전환하지 않는다. 구조화된 11개 준비 상태와 고정 한국어 Job 이벤트를 제공하며 가짜 백분율은 없다.

STOP/CANCEL·응답 유실·커널 불확실은 기존 finally 정리에 연결한다. 불확실한 원격 실행은 durable checkpoint에 남겨 재시도와 새로운 실행을 차단한다. Runtime 삭제 실패는 실패 Job·미정리 ownership을 유지한다. 기존 결과 Bundle은 보존한다.

## 검증 결과

| 검증 | 결과 |
| --- | --- |
| 신규 Phase 17 소켓 차단 Mock | 46 PASS |
| 관련 전사·Job·정리 회귀 (중간 검증) | 236 PASS |
| 최종 Backend 전체 (`backend/tests`) | 1500 PASS / 2 SKIP / 0 FAIL / 0 ERROR / warning 1 |
| PowerShell 5.1 설치 테스트 단독 | 11 PASS |
| 추가 문서/릴리스 계약 검사 | 12 PASS / 2 부모 기준선 불일치 (아래) |
| git diff / staged diff whitespace | PASS |
| Frontend lint/typecheck/build | NOT RUN — Frontend 변경 없음 |
| 실제 Google 계정·Runtime·GPU·다운로드 | NOT RUN |

Backend 최종 실행은 Python 3.13.14와 저장소 venv의 기존 site-packages를 사용했다. `sys.path`에 절대 경로로 venv site-packages와 backend를 추가하고 `pytest.main(['backend/tests', '-q', '--tb=short', '--junitxml=tmp/phase17-backend-regression.xml'])`을 실행했다. XML은 ignored tmp 경로에만 남긴다. 최종 pytest 요약 시간 130.04초, XML에는 테스트 suite 시간 124.132초가 기록되어 있다.

최초 전체 실행은 1493 PASS / 2 SKIP / 7 환경 ERROR였다. PowerShell 7에서 상속된 PSModulePath가 PowerShell 5.1 Security 모듈 자동 로드와 충돌했다. 테스트 프로세스의 PSModulePath를 `C:\WINDOWS\system32\WindowsPowerShell\v1.0\Modules;C:\Program Files\WindowsPowerShell\Modules`로 한정한 뒤 해당 테스트 11개와 최종 전체 회귀가 통과했다. 시스템 설정·실행 정책·설치 프로그램 코드는 변경하지 않았다. 최종 두 SKIP은 non-Windows 전용 HOME fallback과 호스트에서 생성할 수 없는 symlink 검사다. warning은 기존 Starlette/httpx deprecation이다.

추가 `tests/test_release_readiness_contracts.py`의 두 실패는 Git 객체로 부모 HEAD에도 존재함을 확인했다.

1. 기존 `docs/project/48_COLAB_DRIVE_VALIDATION_2026-11-11.md`가 문서 원장에 등록되지 않았다. 이번 신규 Phase 17 문서는 원장에 별도 등록했다.
2. 부모 `backend/requirements.txt`의 `python-multipart==0.0.32`와 이를 금지하는 기존 root test 기대값이 불일치한다.

이번 범위에서 이 두 기존 계약을 수정하지 않았으며 Root 전체 PASS를 주장하지 않는다.

## 변경 파일

- backend/src/services/colab_model_provisioner.py
- backend/src/services/colab_jupyter_inference.py
- backend/src/services/colab_inference_worker.py
- backend/src/services/colab_full_file_pipeline.py
- backend/src/services/official_colab_launcher.py
- backend/src/engines/official_colab.py
- backend/tests/test_colab_model_provisioner.py
- backend/tests/test_official_colab_desktop_launch.py (서버 주입 fixture 확장)
- docs/COLAB_PHASE17_MODEL_PROVISIONING.md
- docs/project/CURRENT_SOURCE_OF_TRUTH.md (신규 문서 분류 1행)
- audit/48-colab-model-provisioning-20261114.md

## 보존 및 차단 조건

미추적 monitor.ps1, smoke.ps1, smoke_desktop.ps1, smoke_qa.ps1, tunnel_log 5개를 수정·실행·스테이징하지 않았다. RuntimeOwnership 및 Runner의 close_session() 구현을 변경하지 않고 기존 안전장치를 재사용했다. main/Integration 변경·rebase·force-push·병합은 수행하지 않는다.

COST_GATE=CONDITIONAL / POLICY_GATE=NOT VERIFIED / launch_approval=BLOCKED / 공식 엔진 DEFAULT OFF 유지. Drive token 재사용, 임의 터널, 유료 GPU·CU 자동 전환 없음. 실환경 비용·정책·접근 권한, CUDA·패키지·모델 호환성, 별도 서버 실행 승인 확인은 남아 있다.

GitHub 완료 기록 후 PHASE 17 STOP.
