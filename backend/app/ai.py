"""IA de Garaje: el proveedor lo pone cada usuario en Ajustes (ver dev/lib/ai-providers).

Sin nada configurado se usa lo que traiga el servidor por entorno, como antes
(``GARAJE_ANTHROPIC_API_KEY`` o ``GARAJE_OLLAMA_URL``/``GARAJE_OLLAMA_MODEL``).
"""
from __future__ import annotations

import os
from pathlib import Path

from .ai_providers import AiStore, Fallback


def data_dir() -> Path:
    explicit = os.getenv("GARAJE_DATA_DIR", "").strip()
    if explicit:
        return Path(explicit)
    from .desktop import desktop_data_dir, is_desktop_mode

    if is_desktop_mode():
        return desktop_data_dir()
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("sqlite:///") and not url.endswith(":memory:"):
        return Path(url[len("sqlite:///"):]).resolve().parent
    return Path("./data").resolve()


def _env_fallback() -> Fallback:
    key = os.getenv("GARAJE_ANTHROPIC_API_KEY", "").strip()
    if key:
        return Fallback(provider="anthropic", key=key)
    url = os.getenv("GARAJE_OLLAMA_URL", "").strip()
    if url:
        return Fallback(provider="ollama", base_url=url, model=os.getenv("GARAJE_OLLAMA_MODEL", "").strip())
    return Fallback()


STORE = AiStore(data_dir(), secret_env="GARAJE_SECRET_KEY", fallback=_env_fallback)
