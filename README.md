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

Preflight는 Local Runtime/Core/MSI를 만들거나 Sorigul을 설치·제거하지 않는다. Frozen HEAD에서 preflight가 PASS한 뒤에만 새 #113 artifact `run_id`와 Single Writer session을 만든다.

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
