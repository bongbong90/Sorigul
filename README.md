# Sorigul

소리글(Sorigul)은 Windows용 음성 전사 및 전사 결과 관리 데스크톱 애플리케이션이다.

현재 제품 행동을 판단할 때는 [`docs/project/CURRENT_PRODUCT_CONTRACT.md`](docs/project/CURRENT_PRODUCT_CONTRACT.md)에서 시작한다. 현재 구현이나 과거 문서만으로 의도된 제품 계약을 추정하지 않는다.

Sorigul은 greenfield architecture를 사용하되 Legacy ACTIVE 사용자 기능을 기본 보존하고, 명시적으로 승인된 Intentional Change만 예외로 인정한다. 기존 전사도우미 소스는 dependency로 copy/import하지 않는다.

현재 단계:

**Personal Study Use Completion — Full Legacy Parity Remediation / Installed Validation**

관련 공식 문서:

- [Current Product Contract](docs/project/CURRENT_PRODUCT_CONTRACT.md)
- [Completion Plan](docs/project/SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md)
- [Development Rules](docs/project/DEVELOPMENT_RULES.md)
- [Roadmap](docs/project/ROADMAP.md)
- [Documentation index](docs/README.md)

## #113 canonical preflight

#113 artifact session 전에 개발자나 에이전트가 개별 pytest working directory, PYTHONPATH 또는 child command를 기억해서 재구성하지 않는다. repository root에서 아래 **한 명령만** 실행한다.

```powershell
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ".\scripts\run_113_preflight.ps1"
```

이 `Bypass`는 해당 preflight PowerShell process에만 적용한다. `Set-ExecutionPolicy`, registry 또는 Group Policy를 변경하지 않는다. 스크립트가 canonical root/backend working directory, trusted Windows executables, #161/#159 targeted regression과 전체 source regression을 소유한다. **child command를 직접 재구성하지 않는다.**

Preflight는 Local Runtime/Core/MSI를 만들거나 Sorigul을 설치·제거하지 않는다. 최종 PASS 전에 canonical Single Writer의 probe-only lifecycle도 실행한다. Probe는 임시 lock, PS5 guard, 여러 heartbeat, competing acquisition DENIED, source observation, controlled stop, lock release와 orphan 0을 검증하며 실제 artifact session을 만들지 않는다.

## #113 canonical session bootstrap (#164)

Frozen HEAD의 preflight PASS 후 별도로 승인된 artifact 작업에서만 아래 Start를 사용한다. 에이전트는 inline/ad-hoc guard command를 조립하지 않는다. `FreezeFile`은 exact `branch`, `head`, 모든 tracked file의 `release_input_sha256` map을 포함하는 native SHA256 Freeze JSON이다. `EvidenceRoot`는 새 run namespace를 만들 전용 evidence 디렉터리다.

```powershell
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ".\scripts\run_113_session_bootstrap.ps1" -Mode Start -ExpectedBranch "<frozen-branch>" -ExpectedHead "<40-character-frozen-head>" -FreezeFile "<source-freeze.json>" -EvidenceRoot "<evidence-root>"
```

Start는 provisional `run_id`와 `SESSION_BOOTSTRAPPING.json`을 만들고 source identity → guard stable → competing denial → protected baseline → final bootstrap recheck → guard-owned atomic `SESSION_ACTIVE.json` 순서를 소유한다. **`#113 ARTIFACT SESSION = ACTIVE` 출력 전에는 Fresh Local을 시작하지 않는다.** 이전 run evidence를 재사용하지 않는다. Windows 환경을 유지하고 hashing은 .NET SHA256으로 수행한다. guard의 Bypass는 harness process 범위뿐이며 artifact build process의 실제 Restricted 정책 계약을 바꾸지 않는다.

검증·운영도 같은 script를 사용한다.

```powershell
# Final-HEAD preflight PASS 후 새 Freeze JSON 생성 (session 생성 없음)
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ".\scripts\run_113_session_bootstrap.ps1" -Mode Freeze -FreezeFile "<new-source-freeze.json>"
# Probe only; 실제 run_id, protected baseline, artifact activation 없음
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ".\scripts\run_113_session_bootstrap.ps1" -Mode Probe
# 매 artifact stage boundary에서 Status PASS와 ACTIVE를 확인한다.
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ".\scripts\run_113_session_bootstrap.ps1" -Mode Status -SessionPath "<session-path>"
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ".\scripts\run_113_session_bootstrap.ps1" -Mode Stop -SessionPath "<session-path>"
```

Activation 전 실패는 `BOOTSTRAP FAILED / ARTIFACT SESSION NOT STARTED`; provisional evidence 보존과 owned-child cleanup 후 harness Issue 안에서 수정할 수 있다. Activation 후 guard loss는 HARD STOP이며 Status가 죽은 guard/heartbeat/lock을 검출해 invalidation을 기록한다. Final artifact evidence는 ACTIVE를 거친 run만 참조한다. Guard는 branch/local HEAD/upstream/tracked tree/index/lock/heartbeat를 감시하고 live upstream을 주기적으로 확인한다. 전체 release-input SHA는 Start와 activation, Status stage boundary에서 확인한다.

## Frontend

- React
- TypeScript
- Vite

Frontend 실행 방법:

```
cd frontend
npm install
npm run dev
```

Frontend 검증:

```
npm run lint
npm run build
```
