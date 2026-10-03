from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from src.api.routes import router

app = FastAPI(title="Sorigul Core Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "tauri://localhost", "http://tauri.localhost"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DNS-rebinding guard (#125): the socket is 127.0.0.1-only, but a rebound
# browser page still sends its own hostname as Host. Added last so it is the
# outermost middleware and rejects before CORS or any route. Hostname-only
# (the runtime --port is ignored); no wildcards. Local-process auth is #53.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost"],
    www_redirect=False,
)

app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
