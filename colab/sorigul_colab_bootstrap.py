import os
import sys
import json
import time
import subprocess
import threading
from datetime import datetime, timezone

# Optional imports handled gracefully
try:
    from pydantic import BaseModel, ConfigDict
except ImportError:
    BaseModel = object
    ConfigDict = dict

COLAB_RUNTIME_FOLDER = "Sorigul Runtime"
COLAB_CONNECTION_FILENAME = "colab_connection.json"
COLAB_SCHEMA_VERSION = 1
COLAB_READY_TTL_SECONDS = 3600

def parse_cloudflare_url(log_path: str) -> str:
    # A simple helper to parse Cloudflare tunnel URL from logs
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
    import google.colab.drive # fails outside colab, handled below
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
                
                if data.get("schema_version") == COLAB_SCHEMA_VERSION:
                    if data.get("status") == "REQUESTED":
                        req_id = data.get("request_id")
                        if req_id and req_id != last_request_id:
                            # Write READY
                            now = datetime.now(timezone.utc)
                            expires = datetime.fromtimestamp(now.timestamp() + COLAB_READY_TTL_SECONDS, timezone.utc)
                            ready_data = {
                                "schema_version": COLAB_SCHEMA_VERSION,
                                "request_id": req_id,
                                "url": base_url,
                                "status": "READY",
                                "updated_at": now.isoformat(),
                                "expires_at": expires.isoformat()
                            }
                            temp_file = conn_file + ".tmp"
                            with open(temp_file, "w", encoding="utf-8") as fw:
                                json.dump(ready_data, fw)
                            os.replace(temp_file, conn_file)
                            last_request_id = req_id
                            print(f"Rendezvous successful for request {req_id}")
        except Exception as e:
            print(f"Rendezvous loop error: {e}")
            
        time.sleep(3)

def main():
    print("Starting Sorigul Colab Bootstrap...")
    
    try:
        from google.colab import drive
        drive.mount('/content/drive')
    except ImportError:
        print("Not running in Google Colab. Drive mount skipped.")
        return
        
    # Start Cloudflare Tunnel
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
    
    # Start Rendezvous Thread
    print("Starting Rendezvous Thread...")
    t = threading.Thread(target=rendezvous_loop, args=(base_url,), daemon=True)
    t.start()
    
    print("Loading FastAPI server...")
    from fastapi import FastAPI, File, UploadFile
    from fastapi.responses import JSONResponse
    import uvicorn
    import tempfile
    
    app = FastAPI()
    
    model = None
    
    @app.on_event("startup")
    def load_model():
        nonlocal model
        print("Loading Whisper Medium model...")
        try:
            import whisper
            model = whisper.load_model("medium")
            print("Model loaded.")
        except Exception as e:
            print(f"Error loading model: {e}")
    
    @app.get("/health")
    def health():
        return {"status": "ok"}
        
    @app.post("/transcribe")
    def transcribe(file: UploadFile = File(...)):
        if model is None:
            return JSONResponse(status_code=500, content={"error": "Model not loaded"})
            
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
                content = file.file.read()
                temp_audio.write(content)
                temp_audio_path = temp_audio.name
                
            result = model.transcribe(
                temp_audio_path,
                language="ko",
                task="transcribe",
                temperature=0.0,
                beam_size=5,
                best_of=5,
                patience=1,
                condition_on_previous_text=False
            )
            os.remove(temp_audio_path)
            
            # Compatible with TranscriptionResult.from_engine_payload
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
            
    print("Starting server on port 8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)

if __name__ == "__main__":
    main()
