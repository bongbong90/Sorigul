from fastapi import FastAPI
from src.api.routes import router

app = FastAPI(title="Sorigul Core Backend")

app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
