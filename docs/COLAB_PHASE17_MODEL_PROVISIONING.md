# [SORIGUL] PHASE 17 — 공식 Colab Runtime 자동 준비

관련 Issue: #250, #48, #60, #233, #248, #114, #7. 부모 PR #249 / HEAD `0639b37b8c4312db75c42de064702b51dedee3fe`.

## 실행 구조

`OfficialColabLauncher(provisioning_authorizer=...)`의 별도 서버 권한을 `ColabFullFilePipeline`에 주입한다. 이 권한은 launch authorizer와 별개이며 API 요청, Job, Settings에서 받지 않는다. 권한이 없는 기본 경로는 기존 읽기 전용 `prepare()`를 유지한다. `FailClosedProvisioningAuthorizer`는 항상 거절한다. 이번 단계의 허용 authorizer는 테스트 전용이다.

소유권·계정·Runtime binding 확인 → GPU/환경 CHECK → 필요한 패키지 INSTALL → 필요한 모델 DOWNLOAD → VERIFY 및 CUDA 모델 로드 → 기존 읽기 전용 `prepare()` → MP3 업로드 → 전사 → 기존 Runner/Writer의 TXT/JSON/SRT 저장 → PHASE 16A `close_session()` 정리 순서다. 준비와 전사는 같은 소유 커널을 사용한다. 로컬 제품 코드는 ML 모듈을 import하거나 pip·모델 다운로드를 실행하지 않는다.

`ColabModelProvisioner`는 NOT_STARTED, CHECKING, INSTALL_REQUIRED, INSTALLING, MODEL_DOWNLOAD_REQUIRED, DOWNLOADING, VERIFYING, READY, FAILED, CANCELLED, STATE_UNCERTAIN 상태를 제공한다. 구조화 이벤트는 `{kind: "colab_provisioning", state, message}`이며 원격 텍스트, 인증정보, 경로, 백분율을 포함하지 않는다. 기존 Job 이벤트에는 검증된 `ColabProvisioning:<상태>`와 고정 한국어 문구만 전달한다. Frontend 변경은 없다.

## 고정 패키지와 설치

기존 `PACKAGES` 계약을 공유한다.

| 패키지 | 버전 |
| --- | --- |
| faster-whisper | 1.2.1 |
| ctranslate2 | 4.6.0 |
| huggingface-hub | 0.36.0 |

현재 Python이 3.10 이상인지 확인하고, 고정 `nvidia-smi` 명령으로 GPU를 확인한다. metadata 기준 미설치·버전 불일치 항목만 설치 계획에 넣는다. 실행 명령은 원격 현재 Python의 `-m pip --isolated --disable-pip-version-check --no-input install --only-binary=:all: --index-url https://pypi.org/simple <고정된 패키지==버전>`이다. PIP 환경 설정을 제거하고 `PIP_CONFIG_FILE=os.devnull`로 전역·환경별 설정도 비활성화한다. 사용자 명령·URL·외부 스크립트를 입력받지 않는다. pip 출력은 버리고 설치는 1,200초로 제한한다.

설치 후 metadata, 실제 import 및 모듈 `__version__`을 확인한다. 기존 커널에 오래된 native module이 로드되어 있으면 준비 실패로 처리한다. 패키지 재설치·커널 재시작을 자동 반복하지 않는다. import 후 `ctranslate2.get_cuda_device_count()`를 재검증한다.

## 모델 캐시와 준비 증명

- Repository: `Systran/faster-whisper-large-v3`
- Revision: `edaa852ec7e145841d8ffdb056a99866b5f0a478`
- 필수 파일: model.bin, config.json, tokenizer.json, preprocessor_config.json

기존 상수를 공유한다. 먼저 `snapshot_download(..., local_files_only=True)`로 캐시를 조회한다. 고정 revision 디렉터리명, 필수 파일 존재·비어 있지 않음, snapshot 내 `.incomplete` 부재를 확인한다. 조회는 설치·다운로드를 하지 않는다. 패키지 설치 후 캐시가 이미 유효하면 모델을 다시 받지 않는다.

캐시가 없거나 부분 캐시이면 승인 경로에서만 같은 revision과 고정 allow_patterns로 다운로드한다. endpoint는 `https://huggingface.co`, token은 `False`로 고정하며 Drive/OAuth token을 전달하지 않는다. 불완전 캐시를 복구하는 다운로드는 `force_download=True`를 사용한다. 다른 revision 캐시는 오류로 처리한다. 다운로드 완료 후 같은 검사를 다시 수행하고, VERIFY에서 `WhisperModel(..., device="cuda", compute_type="float16")`을 실제 로드한다. 로드된 모델은 기존 worker의 커널 캐시에 넣는다. 준비 증명에는 execution ID, 단계, revision, missing package 목록, model_cached, device, error_code만 있다. 클라이언트는 receipt 스키마와 실행 ID·단계·revision을 확인하고 reply와 idle 모두 수신해야 완료로 인정한다.

VERIFY 후에도 기존 `ColabJupyterInference.prepare()` 검증을 다시 수행한다. 새 준비 경로에서 GPU가 사라지거나 CUDA 모델 로드·전사가 실패하면 CPU로 전환하지 않는다. 기존 Local·DirectColab 경로는 유지한다.

## 공급망 검증 범위

고정한 최상위 버전, TLS PyPI index, wheel 전용 설치, 실제 import 버전, 고정 Hub revision, 캐시 파일 상태 및 모델 로드는 검증한다. **패키지·모델 바이너리의 독립 SHA-256 허용 목록, 서명, provenance, 전이 의존성 전체 버전 고정은 검증하지 않았다. 공급망 무결성 전체 PASS를 선언하지 않는다.** 캐시 이름과 모델 로드 성공은 암호학적 무결성 증명이 아니다. wheel이 없는 환경은 source build로 전환하지 않고 실패한다.

참고: [pip isolated 옵션](https://pip.pypa.io/en/stable/cli/pip/), [pip 설정 파일 비활성화](https://pip.pypa.io/en/stable/topics/configuration/#pip-config-file), [huggingface-hub 0.36.0 다운로드 API](https://huggingface.co/docs/huggingface_hub/v0.36.0/package_reference/file_download). 이 문서는 실환경 패키지 호환성 또는 무료 자원 보장을 의미하지 않는다.

## 실패·중지·복구

각 단계는 한 번만 시도한다. 설치·다운로드 직전 서버 권한과 소유 binding을 다시 확인한다. 설치 실패, 실제 버전 불일치, import 실패, 다운로드 실패, 부분 캐시, revision 불일치, 모델 로드 실패, GPU 없음은 고정 오류 코드로 반환한다. 원격 exception·stdout·stderr·URL·token은 기록하지 않는다.

응답 유실, 커널 생성 응답 불확실, reply/idle 미확인 상태에서 STOP/CANCEL은 STATE_UNCERTAIN으로 취급한다. 자동 재시도나 새 Runtime 생성은 없다. pipeline은 durable checkpoint에 REMOTE_STATE_UNCERTAIN/CLEANUP_REQUIRED를 남기고 다음 실행을 차단한다. 중지 요청 전부터 남아 있던 미정리 ownership도 기존 launcher가 차단한다. 결과가 확실한 단계 사이의 중지는 CANCELLED이며, 전송된 원격 작업 결과가 불명확하면 불확실 상태가 우선한다.

기존 pipeline finally가 소유 kernel·upload·splitter를 정리하며 Runner finally는 PHASE 16A의 `close_session()`으로 소유 Runtime을 정리한다. Runtime 삭제 실패는 ownership 기록을 유지하고 Job을 정상 완료로 보고하지 않는다. 기존 사용자 파일과 저장 완료한 결과 Bundle은 보존한다.

## 검증 및 운영 게이트

`backend/tests/test_colab_model_provisioner.py`는 소켓·HTTPTransport를 차단하고 Google REST, Jupyter, pip, Hub, ML을 가짜 계층으로 대체한다. 실제 고정 원격 소스를 Mock 커널에서 실행한다. 캐시 4가지 조합, 정확한 설치 계획·버전, 실패·취소·응답 변조·유실, 계정 불일치, 권한 철회, 중복 실행, GPU 상실, 정리 실패, 다중 파일, Runner/Writer Bundle 및 민감정보 비노출을 검증한다.

전체 회귀 결과와 Git/GitHub 산출물은 Issue #250 및 최종 결과 보고에 기록한다. 테스트는 저장소 venv의 기존 site-packages를 사용하며 사용자 앱 데이터는 기존 conftest에 의해 임시 경로로 격리된다. 제품 PC에 Whisper 패키지나 모델을 설치하지 않는다.

`COST_GATE=CONDITIONAL`, `POLICY_GATE=NOT VERIFIED`, `launch_approval=BLOCKED`, 공식 엔진 DEFAULT OFF 유지. 별도 provisioning 권한을 주입해도 launch gate는 해제되지 않는다. 실제 Google 계정·Runtime·GPU·다운로드 테스트는 수행하지 않았다. 실환경 비용·정책·접근 권한·CUDA/모델 호환성 및 별도 서버 승인 확인 전 운영 실행은 차단된다.

PHASE 17 완료 후 STOP.
