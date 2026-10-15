# Sorigul Colab Runtime

Google Colab GPU 런타임을 사용하여 Sorigul 전사를 수행하기 위한 부트스트랩 스크립트입니다.

## 사용 방법

1. Google Colab에서 새 노트를 생성합니다.
2. 런타임 유형을 **T4 GPU** 이상으로 설정합니다.
3. 첫 번째 셀에 다음 코드를 복사하여 실행합니다:

```bash
!git clone https://github.com/bongbong90/Sorigul.git
!cd Sorigul && pip install -r colab/requirements.txt
!python Sorigul/colab/sorigul_colab_bootstrap.py
```
4. Google Drive 마운트 권한을 허용합니다.
5. 터널이 생성되고 백엔드가 시작되면, Sorigul 데스크톱 앱에서 'Colab' 엔진을 선택합니다.
6. 'Colab 연결' 버튼을 누르면 자동으로 연결됩니다. 직접 URL 복사/붙여넣기를 할 필요가 없습니다.

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
