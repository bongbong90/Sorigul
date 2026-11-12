# Sorigul Colab Runtime

Google Colab GPU 런타임을 사용하여 Sorigul 전사를 수행하기 위한 부트스트랩 스크립트입니다.

## 무료 Notebook 직접 실행 / #48

현재 무료 LIVE 검증은 `Sorigul_large_v3_notebook.ipynb`를 사용자가 직접 열고 셀을 실행하는 방식입니다. 아래의 기존 터널 안내는 이 경로에 적용하지 않습니다. #60의 운영 제한 때문에 무료 desktop HTTP/Quick Tunnel LIVE는 보류합니다.

1. 검토된 작업 commit에서 `python tools/prepare_notebook_package.py --output <로컬 출력 폴더>/sorigul_notebook_code.zip`으로 코드 패키지를 만듭니다. 정확한 Git HEAD의 필요한 소스 6개만 포함하며 인증정보·사용자 데이터는 포함하지 않습니다.
2. 사용자 별도 승인 후 Colab에서 **파일 → Notebook 업로드**로 이 `.ipynb`를 직접 엽니다. 무료 GPU Runtime을 직접 선택합니다. 유료 세션·Compute Unit 사용이면 중단합니다.
3. 셀을 순서대로 직접 실행합니다. 코드 ZIP 업로드, 실제 model/device/compute_type 확인, 승인된 자체 제작 MP3 1개와 SHA-256 대조, 추론 1회, 결과 ZIP 다운로드 순서입니다. GPU가 없으면 유료로 전환하지 않습니다.
4. 원래 MP3를 보관한 Sorigul **폴더** 화면에서 그 MP3를 선택하고 **Notebook 결과 ZIP → 결과 가져오기**를 누릅니다. ZIP 안의 TXT/JSON/SRT는 원본 이름으로 저장됩니다. 원본 MP3의 이름·크기·SHA-256·길이, UTF-8, timestamp, 전사 내용 및 체크섬을 확인합니다. 기존 결과가 하나라도 있으면 거부합니다.
5. 가져오기는 로컬 결과 생성입니다. **Drive로 전송**은 별도 명시적 요청이며 자동 업로드 기본값을 켜지 않습니다. **전송 상태 확인**으로 로컬 Job의 Drive 결과를 확인하고 실패했을 때만 명시적으로 재시도합니다. 완료된 같은 Import Job은 중복 전송하지 않습니다. 실패해도 가져온 결과는 보존합니다.

이 경로는 300초 이하/64 MiB 이하 MP3와 압축 해제 총 8 MiB 이하 결과 ZIP을 지원합니다. Notebook 업로드는 Sorigul에서 원격으로 제어하지 않습니다. 서버·터널·Drive mount·OAuth·백그라운드 폴링을 시작하지 않습니다. Notebook 성공과 데스크톱 자동 전사 성공은 별도 판정입니다. Runtime 비용 조건은 코드가 확인할 수 없으므로 사용자가 무료 세션임을 확인해야 합니다.

## 사용 방법

다음은 기존 desktop tunnel 경로의 소스 설명입니다. **이번 무료 Notebook 검증에서 실행하지 않습니다.**

1. Sorigul 데스크톱 앱에서 `Colab` 엔진을 선택하고 `Colab 열기`를 누릅니다.
2. 열린 새 Colab 노트에서 GPU 런타임을 직접 선택합니다.
3. 첫 번째 셀에 다음 코드를 입력하여 실행합니다:

```bash
!git clone https://github.com/bongbong90/Sorigul.git
!cd Sorigul && pip install -r colab/requirements.txt
!python Sorigul/colab/sorigul_colab_bootstrap.py
```
4. Google Drive 마운트 권한을 허용합니다.
5. 터널이 생성되고 백엔드가 시작되면, Sorigul 데스크톱 앱으로 돌아갑니다.
6. `Colab 연결` 버튼을 누르면 자동으로 연결됩니다. 직접 URL 복사/붙여넣기를 할 필요가 없습니다.

> **참고**: 자동 연결에 문제가 있는 경우, 출력된 \https://xxxxx.trycloudflare.com\ 주소를 Sorigul의 '직접 URL 입력' 메뉴에 붙여넣어 수동으로 연결할 수도 있습니다.

# Security notes

The Desktop pairs with this runtime using an ephemeral Ed25519 key. The private
key remains in Desktop process memory; Drive carries only the opaque request ID
containing the public key. Both `/health` and `/transcribe` require fresh signed
requests, and uploaded audio is checked against the signed SHA-256 before
Whisper runs.

The bootstrap pins `cloudflared` 2026.9.3 for `linux-amd64` and verifies SHA-256
`77e26d8d900e0b8469f416239d14b5f296525fdf79fee6f511ef55609e3fbac2`
before execution. The checksum is published in Cloudflare's official GitHub
release notes for 2026.9.3.

## Zero-cost boundary

Sorigul never creates or purchases a Colab runtime, selects a paid GPU,
enables billing, changes a subscription, or buys compute credits. This script
connects only to the runtime that the user started manually and uses an
anonymous Cloudflare Quick Tunnel; it does not create an account-owned tunnel
or paid Cloudflare resource.

Sorigul cannot reliably determine whether a user-started Colab runtime belongs
to a paid subscription or consumes existing credits. Use the Local engine when
an absolute guarantee of zero paid-credit consumption is required.

Package E release/operations carry-forward: Cloudflare documents anonymous
Quick Tunnels as free and accountless, but also as testing/development-only.
Release validation must treat tunnel availability as best-effort, and Sorigul
must not automatically provision a paid or managed replacement.
