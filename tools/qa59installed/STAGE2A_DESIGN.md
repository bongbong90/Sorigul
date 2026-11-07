# #59 Stage 2A — 로컬 Runtime 경계

기준: #220 HEAD `64063193704ebb262a4f56db73531d9e03924e26`.
변경 범위는 `tools/qa59installed/`뿐이다. 제품 실행, 설치, Backend 종료,
Private Runner 및 Actions 실행 권한을 추가하지 않는다.

## 1. 계약과 신뢰 경계

- 배포용 `Qa59Contracts.dll`은 `QA59_CONTRACT_TESTS` 없이 빌드한다.
  test seam과 `InternalsVisibleTo`가 없고 `GateDecision` 생성 자체가 DENY다.
- 테스트 빌드는 별도 `test-only` 폴더에 생성한다. assembly 이름은 위조할 수
  있으므로 테스트 DLL과 테스트 ALLOW 결정은 실행 권한이 아니다.
- 공개 `ContextGate.Evaluate`는 승인 소비·예산 역할별 빈 허용 목록을 사용한다.
  승인 문자열이나 JSON의 모든 주장을 채워도 실행, 다운로드, 설치는 DENY다.
- `AcceptanceDecision`과 `ResultValidation`은 readonly 값과 동결된 사유를
  반환한다. 공개 schema 배열과 evidence 배열은 복사본이다.
- Result schema 3은 S08 `foreground_confirmed`와 `hit_target_confirmed`를
  분리한다. 어느 하나라도 미측정이면 PASS가 아니다. schema 2는 거부한다.
- null/invalid result QA SHA는 `RESULT_QA_COMMIT_MISSING`으로 별도 기록한다.
- lint는 문자열·문자를 먼저 제거하고 escaped/verbatim identifier를 정규화한다.
  lint는 실수 방지 장치이며 sandbox가 아니다.

## 2. Filesystem containment

`runtime/Containment.cs`는 Windows 전용 내부 모듈이다.

1. 지정된 QA 부모는 `qa59-scratch-<32 lowercase hex>` 형식이다. 상대 경로,
   UNC, device namespace, ADS, 8.3 별칭, dot/trailing alias를 거부한다.
2. 기존 순수 `SyntheticFixtures.ValidateRoot`를 생성 전에 재사용한다.
   Desktop, Documents, OneDrive 및 제품 이름 세그먼트 보호를 완화하지 않는다.
3. 보호 경로 목록이 비어 있거나 정규 형태가 아니거나 QA 부모와 조상·자손
   관계이면 거부한다. AppData/Settings/Jobs/Runtime/Windows/Program Files
   세그먼트도 거부한다. 보호 경로는 비교만 하고 실제 파일을 열지 않는다.
4. 모든 QA 경로 조상을 `OPEN_REPARSE_POINT | BACKUP_SEMANTICS`로 열고
   handle attributes와 `GetFinalPathNameByHandle`을 확인한다. READ만 공유하여
   rename/delete 및 경쟁 write handle을 거부한다. 하나라도 실패하면 DENY다.
5. 부모 handle 기준 `NtCreateFile(FILE_CREATE | FILE_DIRECTORY_FILE)`로
   GUID 루트 생성과 handle 획득을 원자화한다. 기존 디렉터리는 채택하지 않는다.
6. fixture는 생성한 루트의 고정된 A/B JSON만 허용한다. 기존 계약 검증 후
   `CREATE_NEW`로 열고 최종 handle 경로·non-reparse·link count 1을 확인한다.
   파일 handle을 배타적으로 유지하고 실제 bytes는 그 handle에만 쓴다.
7. cleanup은 보유한 파일/루트 handle에 `FileDispositionInfo`를 설정한다.
   pin 해제 후 경로를 다시 따라가 삭제하는 fallback은 없다. 실패하면 QA
   artifact를 남기며 cleanup 성공을 주장하지 않는다.

이 모듈은 이미 설치된 Settings/Jobs를 바꾸는 기능이 없다. Backend 상태
문자열도 쓰기 권한으로 사용하지 않는다. QA fixture 쓰기와 실제 설치 데이터
교체는 별개이며, 후자는 이번 범위에서 계속 금지한다.

보호 경로 설정은 검토된 호스트 구성이어야 하며 입력 JSON에서 신뢰하지 않는다.
경로 문자열만으로 보호 디렉터리의 알려지지 않은 별칭을 검증했다고 주장하지
않는다. reparse/최종 경로/공유 잠금 확인 실패 시 접근을 계속하지 않는다.
같은 프로세스의 악성 코드, 관리자, kernel/filter driver에 대한 sandbox는 아니다.

## 3. Process ownership observer

`runtime/ProcessOwnership.cs`는 새 합성 worker만 소유한다. 프로세스 이름 검색,
임의 PID 종료, Sorigul Backend 종료, breakaway fallback은 없다.

- `QaAccountBoundary`의 provisioned SID 목록은 현재 비어 있다. 현재 사용자
  이름이나 호출자 bool로 QA 계정 분리를 인정하지 않는다. 모든 launch는 거부된다.
- 실행 파일은 새 QA 루트의 고정 `Qa59SyntheticWorker.exe` 하나뿐이다.
  hash는 검토된 build 출력과 비교하고 파일 handle을 잠근다.
- PID, creation time, 최종 확인된 image path, SHA256을 함께 기록한다.
  root의 부모 PID는 현재 supervisor와 일치해야 한다.
- 이름 없는 자체 Job에 `KILL_ON_JOB_CLOSE`를 설정하고,
  `PROC_THREAD_ATTRIBUTE_JOB_LIST`로 생성 시점에 Job을 원자적으로 연결한다.
  worker는 suspended 생성 후 관측·소유권 확인을 마쳐야 resume한다.
- supervisor가 기존 Job 안에 있으면 중첩 Job을 추측하지 않고 거부한다.
  구형 OS나 Job-list API 실패도 거부한다. 관련 native 동작은 미검증이다.
- 자손은 자체 Job snapshot과 부모·자손 관계, creation time, 동일 합성 binary
  hash를 확인한다. 중간 부모를 놓치거나 자손이 관측 전에 종료하면 NOT_VERIFIED다.
- PID 재사용을 막기 위해 관측 handle을 유지하며 수를 4096개로 제한한다.
  같은 PID에 다른 identity가 나타나면 FAIL이다. 임의 프로세스 파일을 읽지 않는다.
- TCP/UDP IPv4/IPv6 조회는 소유자가 조회 전후 확인한 PID 집합만 사용한다.
  raw PID 목록을 받지 않는다. 한 table이라도 실패하거나 집합이 달라지면
  counts는 null이고 NOT_VERIFIED다. 주소·포트·타 PID는 출력하지 않는다.
- 정상 종료는 root exit 0과 Job의 active process 0을 함께 요구한다.
  강제 종료·Job-close kill은 정상 종료로 바꾸지 않는다.

`runtime/worker/SyntheticWorker.cs`는 exit/hang/crash/child 모델이다. 로컬
검증에서는 컴파일만 한다. 별도 QA 계정과 보호 경계 검증 전에는 실행하지 않는다.

## 4. Bounded supervisor와 Evidence bridge

- UIAutomation/native provider 호출은 별도 process worker에만 배치한다.
  supervisor는 해당 provider를 호출하지 않고 kernel process wait를 짧게 반복한다.
- worker deadline은 1~60000ms의 monotonic 시간이다. 결과 commit 직전에도
  deadline을 확인하고 기존 `VerdictLatch`를 동결한다. 늦은 PASS는 폐기한다.
- `Record`는 계약의 고정 ID/schema와 정확한 evidence shape만 허용한다.
  이 진입점은 내부 trusted observer용이며 JSON 입력 처리기가 아니다.
- deadline/worker 실패 때 결과를 먼저 동결하고 cleanup을 background에 요청한다.
  cleanup의 native 대기가 결과 반환 deadline을 연장하지 않는다. cleanup 성공은
  별도 확인 전까지 NOT_VERIFIED다. 강제 cleanup 필요 표시는 보수적으로 유지한다.
- worker 비정상 종료나 wait 실패는 fail-closed다. supervisor 사망 시 비상속 Job
  handle이 닫혀 worker를 종료하도록 설계했다. 실제 상호 장애는 QA 계정에서
  검증하지 않았으므로 NOT_VERIFIED다.
- `EvidenceBridge`는 기존 `ResultContract.Validate`를 통과하는 schema만 만든다.
  고정 코드·bool·bounded count·검증된 SHA 외 자유 텍스트, 원시 예외, path,
  인증정보를 결과로 내보내지 않는다.
- 합성 worker 결과는 설치 제품 증거가 아니다. 설치 12단계/7음성 사례 및
  제품 정상 종료·실제 cleanup은 null을 유지한다. 제품 실행 증거가 없으므로
  완벽한 입력 JSON이나 합성 테스트 PASS도 installed acceptance를 올리지 못한다.

## 5. 단일 실행 외부 승인 — DESIGN ONLY

현재 `SingleUseApproval`은 순수 상태 전이 제안일 뿐이다. stale ISSUED snapshot에
Consume을 두 번 호출하면 제안도 둘 나온다. 외부 저장소의 **state + version에 대한
원자적 compare-and-swap** 없이는 단일 소비를 보장하지 못한다. 로컬 CAS 모델
검사는 이 차이를 보이며 실제 외부 제어기 구현을 대신하지 않는다.

다음 절차는 설계이며 API 호출이나 workflow를 추가하지 않는다.

1. 외부 제어기가 repository ID/name, QA SHA, ref, workflow identity, 권한,
   승인 범위·유효 기간, 사전 비용 자료를 확인한다. 무료 잔여량과 유료 초과
   차단이 검증되지 않으면 승인권을 선점하거나 dispatch하지 않는다.
2. durable CAS로 `ISSUED(version)` → `RESERVED(request identity, expiry, version+1)`을
   선점한다. 이어서 `DISPATCHING`을 CAS로 기록한 단일 소유자만 공식 API를
   **한 번** 호출한다. HTTP client/proxy의 자동 retry도 끈다.
3. 공식 `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches`에
   `return_run_details=true`를 사용한다. 200 응답의 `workflow_run_id`를 받아
   같은 reservation/version에 `BOUND(run_id)`를 CAS로 결합한다. 최신 run 목록,
   시간 근접성, 실행 이름으로 Run ID를 추측하지 않는다.
4. Runner 시작 시 외부 제어기에서 BOUND 상태, exact Run ID/repository/QA SHA/ref,
   event, attempt=1, 유효 기간을 확인하고 `STARTED`를 CAS로 소비한다. 아직
   BOUND가 아니면 즉시 DENY하며 나중 결합되어도 해당 시작을 승격하지 않는다.
5. 응답 손실·204·timeout·충돌·중복 dispatch 의심은 reservation을 격리/폐기한다.
   dispatch를 retry하지 않고 자동으로 ISSUED로 돌리지 않는다. 늦은 bind는
   거부한다. 취소는 terminal revoke이며 재실행은 attempt와 STARTED 상태로
   차단한다. 새 실행에는 새 검토와 새 승인이 필요하다.

승인 저장소와 GitHub dispatch 사이에는 분산 트랜잭션이 없다. 따라서 위 설계의
보장은 승인권당 at-most-one 요청 시도이며, 응답 손실 때 성공을 추측하지 않는다.
Runner의 사후 비용 검사는 사전 비용 통제가 아니다. Runner 시작 이전에 과금이
발생할 수 있으므로 외부의 비용·초과 차단이 실제 구현·검증되기 전에는 **전부 DENY**다.
Private 비용과 잔여 무료 사용량은 **NOT VERIFIED**로 유지한다.

공식 근거:
[GitHub REST workflows — dispatch response](https://docs.github.com/en/rest/actions/workflows?apiVersion=2022-11-28#create-a-workflow-dispatch-event),
[GitHub dispatch Run ID 변경 공지](https://github.blog/changelog/2026-02-19-workflow-dispatch-api-now-returns-run-ids/).

Native 경계 참고:
[NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile),
[CreateFile 공유 모드](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew),
[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[UpdateProcThreadAttribute](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute).
