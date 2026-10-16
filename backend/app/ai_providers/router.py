# GENERADO desde dev/lib/ai-providers (Homelab): no lo edites aquí, edita la librería y ejecuta su sync.mjs
"""Router FastAPI para configurar el proveedor de IA desde Ajustes.

    from .ai_providers import AiStore
    from .ai_providers.router import create_ai_router
    app.include_router(create_ai_router(store))     # GET/PUT /api/ai, POST /api/ai/test

La clave entra por PUT y nunca sale: GET solo dice si hay una guardada (`has_key`).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import AiError, AiStore, test_connection


class AiSettingsIn(BaseModel):
    provider: Optional[str] = None  # None = lo que traiga el servidor
    base_url: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)
    # None = no tocar la guardada; "" = borrarla; texto = sustituirla.
    key: Optional[str] = Field(default=None, max_length=2000)


def create_ai_router(store: AiStore, prefix: str = "/api/ai") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["ai"])

    @router.get("")
    def get_ai():
        return store.public()

    @router.put("")
    def put_ai(payload: AiSettingsIn):
        try:
            store.save(payload.provider, payload.base_url, payload.model)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        if payload.key is not None:
            if payload.key.strip():
                store.save_key(payload.key)
            else:
                store.delete_key()
        return store.public()

    @router.post("/test")
    def test_ai():
        try:
            return {"ok": True, "message": test_connection(store.resolve())}
        except AiError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    return router
