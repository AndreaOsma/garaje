"""Modo desktop: SQLite local, frontend estático, resolución de rutas de datos por SO.

Calco del patrón de dev/apps/soberan/backend/app/desktop.py (ver AGENTS.md, sección
"apps nativas"). NATIVE_API_PREFIXES vacío: todas las rutas de Garaje van bajo /api.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

logger = logging.getLogger("garaje.desktop")

DESKTOP_PORT = 17891
DESKTOP_HOST = "127.0.0.1"

NATIVE_API_PREFIXES: tuple[str, ...] = ()

_CONFIGURED = False


def is_desktop_mode() -> bool:
    return os.getenv("GARAJE_DESKTOP", "").strip() in ("1", "true", "yes")


def _app_support_base() -> Path:
    local_app = os.getenv("LOCALAPPDATA")
    if local_app:
        return Path(local_app) / "Garaje"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Garaje"
    return Path.home() / ".local" / "share" / "Garaje"


def desktop_data_dir() -> Path:
    data = _app_support_base() / "data"
    data.mkdir(parents=True, exist_ok=True)
    return data


def desktop_logs_dir() -> Path:
    logs = _app_support_base() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def sqlite_url_for_path(db_path: Path) -> str:
    return "sqlite:///" + db_path.resolve().as_posix()


def resolve_static_dir(explicit: Optional[str] = None) -> Optional[Path]:
    if explicit:
        path = Path(explicit)
        if path.is_dir():
            return path
    env = (os.getenv("GARAJE_STATIC_DIR") or "").strip()
    if env:
        path = Path(env)
        if path.is_dir():
            return path
    if getattr(sys, "frozen", False):
        bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for candidate in (
            bundle / "desktop" / "static",
            Path(sys.executable).parent / "desktop" / "static",
            Path(sys.executable).parent / "_internal" / "desktop" / "static",
        ):
            if candidate.is_dir():
                return candidate
    repo_static = Path(__file__).resolve().parent.parent / "desktop" / "static"
    if repo_static.is_dir() and any(repo_static.iterdir()):
        return repo_static
    return None


def rewrite_api_path(path: str) -> str:
    """Refleja el proxy de Vite/nginx: quita /api salvo para rutas nativas explícitas."""
    if not path.startswith("/api/"):
        return path
    if any(path.startswith(prefix) for prefix in NATIVE_API_PREFIXES):
        return path
    if path.startswith("/api/api/"):
        return path[4:] or "/"
    stripped = path[4:] or "/"
    return stripped if stripped.startswith("/") else f"/{stripped}"


def configure_desktop_environment(
    static_dir: Optional[str] = None,
    port: Optional[int] = None,
) -> dict[str, str]:
    """Fija variables de entorno antes de importar el engine de la base de datos. Idempotente."""
    global _CONFIGURED
    os.environ["GARAJE_DESKTOP"] = "1"

    data_dir = desktop_data_dir()
    db_path = data_dir / "garaje.db"
    os.environ.setdefault("DATABASE_URL", sqlite_url_for_path(db_path))

    bind_port = str(port or int(os.getenv("GARAJE_PORT", DESKTOP_PORT)))
    bind_host = os.getenv("GARAJE_HOST", DESKTOP_HOST)
    os.environ["GARAJE_PORT"] = bind_port
    os.environ["GARAJE_HOST"] = bind_host
    os.environ.setdefault(
        "CORS_ALLOW_ORIGINS",
        f"http://{bind_host}:{bind_port},http://127.0.0.1:{bind_port}",
    )

    static = resolve_static_dir(static_dir or os.getenv("GARAJE_STATIC_DIR"))
    if static:
        os.environ["GARAJE_STATIC_DIR"] = str(static)

    log_dir = desktop_logs_dir()
    log_file = log_dir / "garaje.log"
    if not _CONFIGURED:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(file_handler)
        logger.info("Desktop data: %s", data_dir)
        logger.info("Desktop static: %s", static)
        _CONFIGURED = True

    return {
        "data_dir": str(data_dir),
        "db_path": str(db_path),
        "static_dir": str(static) if static else "",
        "host": bind_host,
        "port": bind_port,
        "url": f"http://{bind_host}:{bind_port}",
    }


class ApiPrefixMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        original = request.scope["path"]
        rewritten = rewrite_api_path(original)
        if rewritten != original:
            request.scope["path"] = rewritten
            if request.scope.get("raw_path"):
                request.scope["raw_path"] = rewritten.encode("utf-8")
        return await call_next(request)


def mount_desktop_static(app, static_dir: Path) -> None:
    """Sirve el build de Vite + fallback SPA después de registrar las rutas de la API."""
    index_path = static_dir / "index.html"
    if not index_path.is_file():
        logger.warning("Desktop static index missing at %s", index_path)
        return

    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="desktop-assets")

    @app.get("/{full_path:path}")
    def desktop_spa_fallback(full_path: str):
        if full_path.startswith("api"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_path, media_type="text/html")
