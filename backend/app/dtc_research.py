"""Búsqueda automática del significado de un código de avería para TU coche.

Los códigos del fabricante (P1xxx, C1xxx, B1xxx, U1xxx…) significan cosas distintas
según la marca: no hay una base de datos pública fiable, así que se investiga con:

el proveedor de IA que haya puesto el usuario en Ajustes (ver ai.py; sin nada configurado, lo
del servidor por entorno: GARAJE_ANTHROPIC_API_KEY o GARAJE_OLLAMA_URL):

1. Claude + búsqueda web: busca fuentes de esa marca y modelo y devuelve significado,
   gravedad, causas típicas y enlaces.
2. Ollama, Gemini u OpenRouter, sin acceso a la web: se guarda marcado como «orientativo»
   (puede equivocarse).

El resultado se guarda en el diccionario propio (DtcDefinition), una vez por código y
marca; lo escrito a mano nunca se pisa.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import anthropic
import httpx

from . import ai, ai_providers

logger = logging.getLogger("garaje.dtc_research")

CLAUDE_MODEL = "claude-opus-5-5"
OLLAMA_MODEL_DEFAULT = "qwen2.5:7b"
RETRY_AFTER = timedelta(days=7)

SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "description": {"type": "string"},
        "severity": {"type": "string", "enum": ["baja", "media", "alta"]},
        "system": {"type": "string"},
        "causes": {"type": "array", "items": {"type": "string"}},
        "advice": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["alta", "media", "baja"]},
    },
    "required": ["found", "description", "severity", "system", "causes", "advice", "sources", "confidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "Eres un técnico de diagnóstico de automoción. Te dan un código de avería OBD y el vehículo "
    "concreto. Averigua qué significa ese código en ESA marca (y, si cambia, en ese modelo o motor). "
    "Los códigos de fabricante (segundo carácter 1 o 3) significan cosas distintas en cada marca: "
    "usa solo fuentes de esa marca o de su grupo (p. ej. PSA/Stellantis para Peugeot, Citroën, DS u "
    "Opel desde 2018) y descarta lo que valga para otras marcas. Si no encuentras una fuente fiable, "
    "responde found=false en vez de suponer. Responde en español, con una descripción corta (una "
    "frase, sin el código), la gravedad para circular, hasta 5 causas típicas, un consejo práctico y "
    "las URLs de las fuentes que hayas usado."
)


@dataclass
class Research:
    found: bool
    description: str
    severity: str
    system: str
    causes: list[str] = field(default_factory=list)
    advice: str = ""
    sources: list[str] = field(default_factory=list)
    confidence: str = "baja"
    provider: str = ""

    def details(self) -> dict:
        return {
            "system": self.system, "causes": self.causes[:5], "advice": self.advice,
            "sources": self.sources[:8], "confidence": self.confidence, "provider": self.provider,
        }


def _clean(data: dict, provider: str) -> Optional[Research]:
    try:
        r = Research(
            found=bool(data.get("found")),
            description=" ".join(str(data.get("description", "")).split())[:300],
            severity=data.get("severity") if data.get("severity") in ("baja", "media", "alta") else "media",
            system=str(data.get("system", ""))[:120],
            causes=[str(c)[:200] for c in (data.get("causes") or [])][:5],
            advice=str(data.get("advice", ""))[:500],
            sources=[s for s in (str(u) for u in (data.get("sources") or [])) if re.match(r"^https?://", s)][:8],
            confidence=data.get("confidence") if data.get("confidence") in ("alta", "media", "baja") else "baja",
            provider=provider,
        )
    except (TypeError, ValueError):
        return None
    if r.found and len(r.description) < 6:
        return None
    return r


def _parse_json(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except ValueError:
                return None
    return None


def vehicle_prompt(code: str, make: str, model: str, year: Optional[int], engine: str, fuel: str) -> str:
    parts = [f"Código: {code}"]
    family = _LETTER_SYSTEM.get(code[:1].upper())
    if family:
        parts.append(f"Familia del código: {family[0]}")
    parts.append(f"Marca: {make or 'desconocida'}")
    if model:
        parts.append(f"Modelo: {model}")
    if year:
        parts.append(f"Año: {year}")
    if engine:
        parts.append(f"Motor: {engine}")
    parts.append(f"Combustible: {fuel}")
    return "\n".join(parts)


# --- Proveedores -------------------------------------------------------------

def research_claude(prompt: str, api_key: str, client=None) -> Optional[Research]:
    client = client or anthropic.Anthropic(api_key=api_key, timeout=180.0, max_retries=2)
    user = {"role": "user", "content": prompt}
    messages: list = [user]
    response = None
    for _ in range(4):  # pause_turn: la búsqueda web larga puede pausar el turno
        response = client.beta.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 6}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason != "pause_turn":
            break
        messages = [user, {"role": "assistant", "content": response.content}]
    if response is None or response.stop_reason in ("refusal", "max_tokens", "pause_turn"):
        logger.info("Claude no completó la búsqueda (%s)", getattr(response, "stop_reason", None))
        return None
    texts = [b.text for b in response.content if b.type == "text"]
    data = _parse_json(texts[-1]) if texts else None
    return _clean(data, "claude") if data else None


# Familia que marca la primera letra del código (SAE J2012): una respuesta que hable de
# otro sistema es una invención (visto en real: un C163A «del filtro de combustible»).
_LETTER_SYSTEM = {
    "P": ("Motor y transmisión", ("motor", "inyecc", "combust", "encend", "escape", "emision", "turbo", "transmis", "cambio",
                                   "admis", "refriger", "aceite", "egr", "catalizador", "sonda", "lambda", "bujia", "mezcla")),
    "C": ("Chasis: ABS, ESP, frenos, suspensión, dirección", ("abs", "esp", "freno", "chasis", "suspens", "direcc", "rueda",
                                                             "tracci", "estabilidad", "velocidad de rueda", "amortigu")),
    "B": ("Carrocería: airbag, climatización, luces, cierres, confort", ("carroc", "airbag", "clima", "luz", "luces", "cierre",
                                                                         "asiento", "confort", "habit", "cinturon", "ventan", "puerta")),
    "U": ("Red de comunicación entre centralitas (CAN)", ("comunic", "can", "red", "bus", "modulo", "centralita", "señal perdida")),
}


def _fold(text: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def consistent_with_code(code: str, result: Research) -> bool:
    family = _LETTER_SYSTEM.get(code[:1].upper())
    if family is None:
        return True
    text = _fold(f"{result.system} {result.description}")
    return any(_fold(word) in text for word in family[1])


def research_ollama(prompt: str, base_url: str, model: str, http: Optional[httpx.Client] = None, code: str = "",
                    key: Optional[str] = None) -> Optional[Research]:
    body = {
        "model": model,
        "stream": False,
        "format": SCHEMA,
        "options": {"temperature": 0.1},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + " No tienes acceso a internet: si no lo sabes con seguridad, found=false. sources debe ir vacío."},
            {"role": "user", "content": prompt},
        ],
    }
    # En CPU, un modelo de 7B frío puede tardar un par de minutos. SSL_CERT_FILE: una CA
    # propia si tu Ollama va detrás de un proxy con certificado interno.
    client = http or httpx.Client(timeout=300.0, verify=os.getenv("SSL_CERT_FILE") or True)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    resp = client.post(base_url.rstrip("/") + "/api/chat", json=body, headers=headers)
    resp.raise_for_status()
    data = _parse_json(resp.json().get("message", {}).get("content", ""))
    result = _clean(data, "ollama") if data else None
    if result:
        # Sin web no hay fuentes que respalden la respuesta: nunca más que «baja».
        result.sources, result.confidence = [], "baja"
        if code and result.found and not consistent_with_code(code, result):
            logger.info("Respuesta de Ollama descartada para %s: no encaja con su familia", code)
            return None
    return result


def research_generic(prompt: str, r: ai_providers.Resolved, code: str = "") -> Optional[Research]:
    """Gemini u OpenRouter, sin web: como Ollama, «orientativo»."""
    schema_hint = ("Formato: {\"found\": bool, \"description\": str, \"severity\": \"baja|media|alta\", \"system\": str, "
                   "\"causes\": [str], \"advice\": str, \"sources\": [], \"confidence\": \"baja\"}")
    data = ai_providers.complete_json(
        r, SYSTEM_PROMPT + " No tienes acceso a internet: si no lo sabes con seguridad, found=false. sources debe ir vacío. " + schema_hint,
        prompt, max_tokens=1500,
    )
    result = _clean(data, r.provider or "")
    if result:
        result.sources, result.confidence = [], "baja"
        if code and result.found and not consistent_with_code(code, result):
            logger.info("Respuesta de %s descartada para %s: no encaja con su familia", r.provider, code)
            return None
    return result


def configured_providers() -> list[str]:
    """Proveedor activo, con el nombre que espera el frontend ("claude" para Anthropic)."""
    r = ai.STORE.resolve()
    if not r.enabled:
        return []
    return ["claude" if r.provider == "anthropic" else r.provider]


def research(code: str, make: str, model: str = "", year: Optional[int] = None, engine: str = "", fuel: str = "") -> Optional[Research]:
    """Con el proveedor configurado (Claude con web; el resto orientativo). None si no responde."""
    prompt = vehicle_prompt(code, make, model, year, engine, fuel)
    r = ai.STORE.resolve()
    if not r.enabled:
        return None
    try:
        if r.provider == "anthropic":
            if r.source == "settings":
                return research_claude(prompt, r.key or "")
            # Configuración del servidor: si Claude no responde o falla, se intenta con su Ollama (como antes).
            try:
                result = research_claude(prompt, r.key or "")
                if result is not None:
                    return result
            except (anthropic.APIError, ValueError) as exc:
                logger.warning("Búsqueda con Claude fallida: %s", exc.__class__.__name__)
            url = os.getenv("GARAJE_OLLAMA_URL", "").strip()
            return research_ollama(prompt, url, (os.getenv("GARAJE_OLLAMA_MODEL", "").strip() or OLLAMA_MODEL_DEFAULT), code=code) if url else None
        if r.provider == "ollama":
            return research_ollama(prompt, r.base_url, r.model or OLLAMA_MODEL_DEFAULT, code=code, key=r.key)
        return research_generic(prompt, r, code=code)
    except (anthropic.APIError, ai_providers.AiError, httpx.HTTPError, ValueError) as exc:  # red, cuota, clave inválida…
        logger.warning("Búsqueda con %s fallida: %s", r.provider, exc.__class__.__name__)
    return None


def should_retry(last_attempt_iso: Optional[str], now: Optional[datetime] = None) -> bool:
    if not last_attempt_iso:
        return True
    try:
        last = datetime.fromisoformat(last_attempt_iso)
    except ValueError:
        return True
    return (now or datetime.utcnow()) - last >= RETRY_AFTER
