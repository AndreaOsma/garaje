"""Capacidad del depósito (o de la batería útil, si es eléctrico) de TU vehículo, buscada sola.

Con el mismo proveedor de IA que las averías (dtc_research): Claude con búsqueda web mira la
ficha técnica de esa marca, modelo, año y motor (y el bastidor, si lo hay); el resto, sin web,
da un valor «orientativo». Con la capacidad y el % que le dices, Garaje calcula cuánto queda y
la autonomía. Lo que escribas a mano en Ajustes del vehículo nunca se pisa.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import anthropic
import httpx

from . import ai, ai_providers
from .dtc_research import CLAUDE_MODEL, OLLAMA_MODEL_DEFAULT, _parse_json

logger = logging.getLogger("garaje.specs_research")

SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "capacity": {"type": "number"},
        "note": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["alta", "media", "baja"]},
    },
    "required": ["found", "capacity", "note", "sources", "confidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "Eres un técnico de automoción. Te dan un vehículo concreto. Averigua la capacidad de su depósito de "
    "combustible en litros (si es eléctrico: la capacidad ÚTIL de la batería en kWh). Usa la ficha técnica "
    "del fabricante o fuentes fiables para esa marca, modelo, generación, año y motor; si el depósito cambia "
    "entre versiones, elige la que encaje con el motor y el combustible. Si no encuentras un dato fiable, "
    "found=false y capacity=0 en vez de suponer. note: una frase corta en español con la versión a la que "
    "corresponde. sources: URLs consultadas."
)

UNIT = {"electric": "kWh"}
LIMITS = {"electric": (5.0, 250.0)}
DEFAULT_LIMITS = (5.0, 400.0)


@dataclass
class TankResult:
    capacity: float
    note: str = ""
    sources: list[str] = field(default_factory=list)
    confidence: str = "baja"
    provider: str = ""


def prompt_for(make: str, model: str, year: Optional[int], engine: str, fuel: str, vin: str = "", kind: str = "car") -> str:
    parts = [f"Tipo: {'moto' if kind == 'motorcycle' else 'coche'}", f"Marca: {make or 'desconocida'}"]
    if model:
        parts.append(f"Modelo: {model}")
    if year:
        parts.append(f"Año: {year}")
    if engine:
        parts.append(f"Motor: {engine}")
    parts.append(f"Combustible: {fuel}")
    if vin:
        parts.append(f"Bastidor (VIN): {vin}")
    return "\n".join(parts)


def _clean(data: Optional[dict], fuel: str, provider: str) -> Optional[TankResult]:
    if not data or not data.get("found"):
        return None
    try:
        cap = round(float(data.get("capacity") or 0), 1)
    except (TypeError, ValueError):
        return None
    lo, hi = LIMITS.get(fuel, DEFAULT_LIMITS)
    if not lo <= cap <= hi:
        logger.info("Capacidad descartada por fuera de rango: %s", cap)
        return None
    sources = [s for s in (str(u) for u in (data.get("sources") or [])) if s.startswith(("http://", "https://"))][:6]
    conf = data.get("confidence") if data.get("confidence") in ("alta", "media", "baja") else "baja"
    return TankResult(capacity=cap, note=" ".join(str(data.get("note", "")).split())[:200], sources=sources, confidence=conf, provider=provider)


def _claude(prompt: str, api_key: str, fuel: str) -> Optional[TankResult]:
    # Acotado: es un botón que la persona espera (y un 404 claro es mejor que colgarse >10 min).
    client = anthropic.Anthropic(api_key=api_key, timeout=90.0, max_retries=0)
    user = {"role": "user", "content": prompt}
    messages: list = [user]
    response = None
    for _ in range(2):  # pause_turn: la búsqueda web larga puede pausar el turno
        response = client.beta.messages.create(
            model=CLAUDE_MODEL, max_tokens=8000, system=SYSTEM_PROMPT, messages=messages,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        if response.stop_reason != "pause_turn":
            break
        messages = [user, {"role": "assistant", "content": response.content}]
    if response is None or response.stop_reason in ("refusal", "max_tokens", "pause_turn"):
        return None
    texts = [b.text for b in response.content if b.type == "text"]
    return _clean(_parse_json(texts[-1]) if texts else None, fuel, "claude")


def _offline(result: Optional[TankResult]) -> Optional[TankResult]:
    """Sin web no hay fuentes que lo respalden: orientativo."""
    if result:
        result.sources, result.confidence = [], "baja"
    return result


def _ollama(prompt: str, base_url: str, model: str, fuel: str, key: Optional[str] = None) -> Optional[TankResult]:
    body = {"model": model, "stream": False, "format": SCHEMA, "options": {"temperature": 0.1},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT + " No tienes acceso a internet: si no lo sabes con seguridad, found=false."},
                         {"role": "user", "content": prompt}]}
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    with httpx.Client(timeout=300.0, verify=os.getenv("SSL_CERT_FILE") or True) as client:
        resp = client.post(base_url.rstrip("/") + "/api/chat", json=body, headers=headers)
        resp.raise_for_status()
    return _offline(_clean(_parse_json(resp.json().get("message", {}).get("content", "")), fuel, "ollama"))


def research_tank(make: str, model: str = "", year: Optional[int] = None, engine: str = "", fuel: str = "gasoline",
                  vin: str = "", kind: str = "car") -> Optional[TankResult]:
    """Con el proveedor configurado (Claude con web; el resto orientativo). None si no lo sabe."""
    if not make:
        return None
    prompt = prompt_for(make, model, year, engine, fuel, vin, kind)
    r = ai.STORE.resolve()
    if not r.enabled:
        return None
    try:
        if r.provider == "anthropic":
            result = _claude(prompt, r.key or "", fuel)
            if result is None and r.source != "settings" and os.getenv("GARAJE_OLLAMA_URL", "").strip():
                result = _ollama(prompt, os.environ["GARAJE_OLLAMA_URL"], os.getenv("GARAJE_OLLAMA_MODEL", "").strip() or OLLAMA_MODEL_DEFAULT, fuel)
            return result
        if r.provider == "ollama":
            return _ollama(prompt, r.base_url, r.model or OLLAMA_MODEL_DEFAULT, fuel, key=r.key)
        hint = 'Formato: {"found": bool, "capacity": número, "note": str, "sources": [], "confidence": "baja"}'
        data = ai_providers.complete_json(r, SYSTEM_PROMPT + " No tienes acceso a internet. " + hint, prompt, max_tokens=600)
        return _offline(_clean(data, fuel, r.provider or ""))
    except (anthropic.APIError, ai_providers.AiError, httpx.HTTPError, ValueError) as exc:
        logger.warning("Búsqueda del depósito con %s fallida: %s", r.provider, exc.__class__.__name__)
    return None
