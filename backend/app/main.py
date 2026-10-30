"""Punto de entrada de FastAPI: migra el esquema, monta la API y sirve el frontend
estático si lo encuentra (Docker/desktop)."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .security_headers import SecurityHeadersMiddleware
from . import config
from .ai import STORE as AI_STORE
from .agent_api.fastapi import create_agent_router
from .agent_tools import agent
from .ai_providers.router import create_ai_router
from .database import get_db
from .desktop import mount_desktop_static, resolve_static_dir
from .routers import diagnostics, ingest, learn, licenses, maintenance, mechanics, records, soberan, vehicles


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(cfg, "head")


_run_migrations()


def _import_content() -> None:
    from .content_loader import import_packs
    from .database import SessionLocal

    db = SessionLocal()
    try:
        import_packs(db)
    finally:
        db.close()


_import_content()

app = FastAPI(title=config.APP_NAME)
app.add_middleware(SecurityHeadersMiddleware)

if config.CORS_ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
def health():
    return {"status": "ok", "app": config.APP_NAME}


app.include_router(vehicles.router)
app.include_router(maintenance.router)
app.include_router(mechanics.router)
app.include_router(records.router)
app.include_router(diagnostics.router)
app.include_router(ingest.router)
app.include_router(soberan.router)
app.include_router(licenses.router)
app.include_router(learn.router)
app.include_router(create_ai_router(AI_STORE))
# Asistentes (ágora): /agent/v1, apagada sin GARAJE_AGENT_TOKEN.
app.include_router(create_agent_router(agent, get_db))


_static_dir = resolve_static_dir()
if _static_dir:
    mount_desktop_static(app, _static_dir)
