"""Colab account actions: no caller tokens, scopes, endpoints or launch toggles."""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from src.services.colab_oauth import ColabOAuthError


class ColabAccountAction(BaseModel):
    model_config = ConfigDict(extra="forbid")


def trusted_origin(origin: str | None = Header(default=None)):
    if origin is not None and origin not in {
            "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
            "http://127.0.0.1:5173", "http://localhost:5173"}:
        raise HTTPException(403, "허용되지 않은 인증 요청입니다.")


def account_router(service, router=None):
    # Register directly when integrating with the product's flat router. This
    # preserves existing route introspection without deferred nested routers.
    router = router if router is not None else APIRouter()

    @router.get("/colab/auth/status")
    def status():
        return service.status()

    def action(method):
        try:
            return method()
        except ColabOAuthError as exc:
            raise HTTPException(409, detail=exc.user_message) from None
        except Exception:
            raise HTTPException(409, detail="Colab 계정 연결 상태를 확인해 주세요.") from None

    @router.post("/colab/auth/start", dependencies=[Depends(trusted_origin)])
    def start(req: ColabAccountAction):
        return action(service.start)

    @router.post("/colab/auth/cancel", dependencies=[Depends(trusted_origin)])
    def cancel(req: ColabAccountAction):
        return action(service.cancel)

    @router.post("/colab/auth/check", dependencies=[Depends(trusted_origin)])
    def check(req: ColabAccountAction):
        return action(service.check)

    @router.post("/colab/auth/disconnect", dependencies=[Depends(trusted_origin)])
    def disconnect(req: ColabAccountAction):
        return action(service.disconnect)

    return router
