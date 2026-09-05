import os
import sys
import json
import time
import subprocess
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional
import urllib.request
import urllib.error

COLAB_RUNTIME_FOLDER = "Sorigul Runtime"
COLAB_CONNECTION_FILENAME = "colab_connection.json"
COLAB_SCHEMA_VERSION = 1
COLAB_READY_TTL_SECONDS = 3600
COLAB_REQUEST_TTL_SECONDS = 600
COLAB_CLOCK_SKEW_SECONDS = 60

def build_ready_metadata(request_payload: dict, base_url: str, now: Optional[datetime] = None) -> Optional[dict]:
    if not isinstance(request_payload, dict):
        return None

    expected_keys = {"schema_version", "request_id", "url", "status", "updated_at", "expires_at"}
    if set(request_payload.keys()) != expected_keys:
        return None

    if request_payload.get("schema_version") != COLAB_SCHEMA_VERSION:
        return None

    if request_payload.get("status") != "REQUESTED":
        return None

    req_id = request_payload.get("request_id")
    if not req_id or not isinstance(req_id, str):
        return None

    if request_payload.get("url") != "":
        return None

    if now is None:
        now = datetime.now(timezone.utc)

    try:
        updated_at = datetime.fromisoformat(request_payload["updated_at"])
        expires_at = datetime.fromisoformat(request_payload["expires_at"])
    except (ValueError, TypeError):
        return None

    if updated_at.tzinfo is None or updated_at.utcoffset() is None:
        return None
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        return None

    if expires_at <= now:
        return None

    if updated_at > now + timedelta(seconds=COLAB_CLOCK_SKEW_SECONDS):
        return None

    lifetime = (expires_at - updated_at).total_seconds()
    if lifetime <= 0 or lifetime > COLAB_REQUEST_TTL_SECONDS:
        return None

    ready_expires = datetime.fromtimestamp(now.timestamp() + COLAB_READY_TTL_SECONDS, timezone.utc)

    return {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": req_id,
        "url": base_url,
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": ready_expires.isoformat()
    }

def parse_cloudflare_url(log_path: str) -> str:
    if not os.path.exists(log_path):
        return ""
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if "trycloudflare.com" in line:
                parts = line.strip().split("https://")
                if len(parts) > 1:
                    host = parts[1].split()[0].strip()
                    if host.endswith("trycloudflare.com"):
                        return f"https://{host}"
    return ""

def rendezvous_loop(base_url: str):
    import google.colab.drive
    drive_root = "/content/drive/MyDrive"
    runtime_dir = os.path.join(drive_root, COLAB_RUNTIME_FOLDER)
    os.makedirs(runtime_dir, exist_ok=True)
    conn_file = os.path.join(runtime_dir, COLAB_CONNECTION_FILENAME)

    last_request_id = None

    while True:
        try:
            if os.path.exists(conn_file):
                with open(conn_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                req_id = data.get("request_id")
                if req_id and req_id != last_request_id:
                    ready_meta = build_ready_metadata(data, base_url)
                    if ready_meta:
                        temp_file = conn_file + ".tmp"
                        with open(temp_file, "w", encoding="utf-8") as fw:
                            json.dump(ready_meta, fw)
                        os.replace(temp_file, conn_file)
                        last_request_id = req_id
                        print(f"Rendezvous successful for request {req_id}")
        except Exception as e:
            pass

        time.sleep(3)

def run_uvicorn(app):
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

def main():
    print("Starting Sorigul Colab Bootstrap...")

    try:
        from google.colab import drive
        drive.mount('/content/drive')
    except ImportError:
        print("Not running in Google Colab. Drive mount skipped.")
        return

    print("Loading FastAPI and Whisper...")
    from fastapi import FastAPI, File, UploadFile
    from fastapi.responses import JSONResponse
    import tempfile
    import whisper
    import torch

    print("Loading Whisper Medium model...")
    model = whisper.load_model("medium")
    print("Model loaded.")

    app = FastAPI()

    @app.get("/health")
    def health():
        if model is None:
            return JSONResponse(status_code=503, content={"error": "Model not loaded"})
        return {"status": "ok"}

    @app.post("/transcribe")
    def transcribe(file: UploadFile = File(...)):
        if model is None:
            return JSONResponse(status_code=503, content={"error": "Model not loaded"})

        temp_audio_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
                content = file.file.read()
                temp_audio.write(content)
                temp_audio_path = temp_audio.name

            fp16 = torch.cuda.is_available()
            result = model.transcribe(
                temp_audio_path,
                language="ko",
                task="transcribe",
                temperature=0.0,
                beam_size=5,
                best_of=5,
                patience=1,
                condition_on_previous_text=False,
                fp16=fp16
            )

            return {
                "text": result["text"],
                "segments": [
                    {
                        "start": s["start"],
                        "end": s["end"],
                        "text": s["text"]
                    } for s in result["segments"]
                ],
                "language": "ko"
            }
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
        finally:
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except OSError:
                    pass

    print("Starting FastAPI server on port 8000 in background...")
    server_thread = threading.Thread(target=run_uvicorn, args=(app,), daemon=True)
    server_thread.start()

    # Wait for local health
    print("Waiting for local server health check...")
    health_ok = False
    for _ in range(10):
        try:
            req = urllib.request.Request("http://127.0.0.1:8000/health", method="GET")
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    health_ok = True
                    break
        except urllib.error.URLError:
            pass
        time.sleep(2)

    if not health_ok:
        print("Error: Local server did not become healthy. Tunnel will not start.")
        return

    print("Local server is healthy.")

    if not os.path.exists("cloudflared"):
        subprocess.run("wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared", shell=True)
        subprocess.run("chmod +x cloudflared", shell=True)

    print("Starting Cloudflare Tunnel...")
    tunnel_log = "tunnel.log"
    subprocess.Popen(f"./cloudflared tunnel --url http://127.0.0.1:8000 --no-autoupdate > {tunnel_log} 2>&1", shell=True)

    time.sleep(5)
    base_url = parse_cloudflare_url(tunnel_log)
    if not base_url:
        print("Failed to start tunnel.")
        return
    print(f"Tunnel URL: {base_url}")

    print("Starting Rendezvous Loop...")
    rendezvous_loop(base_url)

if __name__ == "__main__":
    main()
