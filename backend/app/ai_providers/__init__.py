# GENERADO desde dev/lib/ai-providers (Homelab): no lo edites aquí, edita la librería y ejecuta su sync.mjs
"""Proveedor de IA que pone cada usuario: Claude, Gemini, OpenRouter o un servidor Ollama.

Librería compartida (dev/lib/ai-providers). Cada app lleva una copia generada por sync.mjs:
no la edites en la app.

- La configuración (proveedor, URL, modelo) va en ``<data_dir>/ai-settings.json``.
- La clave va **cifrada** (Fernet) en ``<data_dir>/ai-key.enc``, fuera de la base de datos y de
  los backups. La clave de cifrado sale de la variable ``secret_env`` o de
  ``<data_dir>/ai-secret.key`` (0600, se crea la primera vez). La API nunca devuelve la clave.
- Si el usuario no ha configurado nada, se usa lo que traiga el servidor por entorno (``fallback``):
  así una instalación existente sigue funcionando hasta que su dueña ponga lo suyo.

Uso: ``store = AiStore(data_dir, secret_env="GARAJE_SECRET_KEY", fallback=...)``,
``text = complete(store.resolve(), system, prompt, images=[...], json_mode=True)``.
"""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken

Provider = Literal["anthropic", "gemini", "openrouter", "ollama"]

PROVIDERS: dict[str, dict[str, Any]] = {
    "anthropic": {
        "label": "Claude (clave de API de Anthropic)",
        "needs_key": True,
        "needs_url": False,
        "url": "https://api.anthropic.com",
        "models": {"text": "claude-sonnet-5-5", "vision": "claude-sonnet-5-5"},
        "help": "Crea la clave en console.anthropic.com → API keys.",
    },
    "gemini": {
        "label": "Gemini (clave de Google AI Studio)",
        "needs_key": True,
        "needs_url": False,
        "url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": {"text": "gemini-2.5-flash", "vision": "gemini-2.5-flash"},
        "help": "Crea la clave en aistudio.google.com → Get API key.",
    },
    "openrouter": {
        "label": "OpenRouter",
        "needs_key": True,
        "needs_url": False,
        "url": "https://openrouter.ai/api/v1",
        "models": {"text": "openrouter/auto", "vision": "openrouter/auto"},
        "help": "Crea la clave en openrouter.ai/keys. El modelo usa el formato proveedor/modelo.",
    },
    "ollama": {
        "label": "Servidor Ollama",
        "needs_key": False,
        "needs_url": True,
        "url": "http://localhost:11434",
        "models": {"text": "qwen2.5:7b", "vision": "llava"},
        "help": "La URL de tu servidor Ollama. La clave es opcional (si va detrás de un proxy con token).",
    },
}

TIMEOUT_S = 180.0
_MODEL_RE = re.compile(r"^[\w.:/@+-]{1,200}$")

# En los tests se sustituye por un httpx.MockTransport.
TRANSPORT: Optional[httpx.BaseTransport] = None


class AiError(RuntimeError):
    """Fallo del proveedor (red, clave inválida, cuota…). El mensaje es apto para mostrarse."""


@dataclass
class Resolved:
    provider: Optional[str]
    base_url: str = ""
    model: str = ""
    key: Optional[str] = None
    source: Literal["settings", "server", "none"] = "none"

    @property
    def enabled(self) -> bool:
        return not self.problem

    @property
    def problem(self) -> str:
        if not self.provider:
            return "No hay ningún proveedor de IA configurado"
        meta = PROVIDERS[self.provider]
        if meta["needs_key"] and not self.key:
            return "Falta la clave de API"
        if not self.base_url:
            return "Falta la URL del servidor"
        if not self.model:
            return "Falta el nombre del modelo"
        return ""


@dataclass
class Fallback:
    """Lo que trae el servidor por entorno, para cuando el usuario no ha configurado nada."""

    provider: Optional[str] = None
    base_url: str = ""
    model: str = ""
    key: Optional[str] = None


def validate_settings(provider: Optional[str], base_url: str, model: str) -> tuple[Optional[str], str, str]:
    if provider is not None and provider not in PROVIDERS:
        raise ValueError("Proveedor de IA no válido")
    base_url = (base_url or "").strip().rstrip("/")
    if base_url:
        u = urlparse(base_url)
        if u.scheme not in ("http", "https") or not u.netloc:
            raise ValueError("La URL debe empezar por http:// o https://")
    model = (model or "").strip()
    if model and not _MODEL_RE.match(model):
        raise ValueError("Nombre de modelo no válido")
    return provider, base_url, model


class AiStore:
    def __init__(self, data_dir: Path | str, *, secret_env: str, kind: Literal["text", "vision"] = "text",
                 fallback: Optional[Callable[[], Fallback]] = None):
        self.data_dir = Path(data_dir)
        self.secret_env = secret_env
        self.kind = kind
        self.fallback = fallback or (lambda: Fallback())

    # ----- ficheros -----
    @property
    def _settings_path(self) -> Path:
        return self.data_dir / "ai-settings.json"

    @property
    def _key_path(self) -> Path:
        return self.data_dir / "ai-key.enc"

    def _fernet(self) -> Fernet:
        env = os.getenv(self.secret_env, "").strip()
        if env:
            return Fernet(env.encode())
        path = self.data_dir / "ai-secret.key"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(Fernet.generate_key())
        return Fernet(path.read_bytes().strip())

    def settings(self) -> dict[str, Any]:
        try:
            raw = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        return {"provider": raw.get("provider"), "base_url": raw.get("base_url", ""), "model": raw.get("model", "")}

    def save(self, provider: Optional[str], base_url: str = "", model: str = "") -> None:
        provider, base_url, model = validate_settings(provider, base_url, model)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._settings_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"provider": provider, "base_url": base_url, "model": model}), encoding="utf-8")
        tmp.replace(self._settings_path)

    def save_key(self, secret: str) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._key_path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(self._fernet().encrypt(secret.strip().encode()))
        tmp.replace(self._key_path)

    def delete_key(self) -> None:
        self._key_path.unlink(missing_ok=True)

    def stored_key(self) -> Optional[str]:
        if not self._key_path.is_file():
            return None
        try:
            return self._fernet().decrypt(self._key_path.read_bytes()).decode() or None
        except (InvalidToken, ValueError):
            return None

    # ----- configuración efectiva -----
    def resolve(self) -> Resolved:
        s = self.settings()
        if s["provider"]:
            meta = PROVIDERS[s["provider"]]
            return Resolved(
                provider=s["provider"],
                base_url=s["base_url"] or meta["url"],
                model=s["model"] or meta["models"][self.kind],
                key=self.stored_key(),
                source="settings",
            )
        fb = self.fallback()
        if fb.provider in PROVIDERS:
            meta = PROVIDERS[fb.provider]
            return Resolved(provider=fb.provider, base_url=fb.base_url or meta["url"], model=fb.model or meta["models"][self.kind],
                            key=fb.key, source="server")
        return Resolved(provider=None)

    def public(self) -> dict[str, Any]:
        """Lo que puede ver el navegador: nunca la clave."""
        s = self.settings()
        r = self.resolve()
        return {
            "provider": s["provider"],
            "base_url": s["base_url"],
            "model": s["model"],
            "has_key": self.stored_key() is not None,
            "kind": self.kind,
            "status": {"enabled": r.enabled, "reason": r.problem, "source": r.source, "provider": r.provider, "model": r.model},
            "providers": {k: {kk: v[kk] for kk in ("label", "needs_key", "needs_url", "url", "help")} | {"model": v["models"][self.kind]}
                          for k, v in PROVIDERS.items()},
        }


# ---------- Llamadas ----------

def _client() -> httpx.Client:
    verify: Any = os.getenv("SSL_CERT_FILE") or True
    return httpx.Client(timeout=TIMEOUT_S, transport=TRANSPORT, verify=verify)


def _guess_mime(b64: str) -> str:
    head = base64.b64decode(b64[:24] + "=" * (-len(b64[:24]) % 4), validate=False)
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head[:4] == b"RIFF":
        return "image/webp"
    if head.startswith(b"GIF8"):
        return "image/gif"
    return "image/jpeg"


def _error(resp: httpx.Response, who: str) -> AiError:
    if resp.status_code in (401, 403):
        return AiError(f"{who} rechazó la clave (HTTP {resp.status_code})")
    if resp.status_code == 429:
        return AiError(f"{who}: límite de uso alcanzado (HTTP 429)")
    if resp.status_code == 404:
        return AiError(f"{who}: modelo o URL no encontrados (HTTP 404)")
    return AiError(f"{who} respondió HTTP {resp.status_code}")


def complete(r: Resolved, system: str, prompt: str, *, images: Optional[list[str]] = None, json_mode: bool = False,
             max_tokens: int = 2000) -> str:
    """Texto de respuesta del modelo. ``images`` son base64 sin cabecera. Lanza AiError."""
    if not r.enabled:
        raise AiError(r.problem)
    images = images or []
    try:
        with _client() as http:
            if r.provider == "anthropic":
                content: list[dict[str, Any]] = [
                    {"type": "image", "source": {"type": "base64", "media_type": _guess_mime(b), "data": b}} for b in images
                ]
                content.append({"type": "text", "text": prompt})
                resp = http.post(f"{r.base_url}/v1/messages", headers={"x-api-key": r.key or "", "anthropic-version": "2023-06-01"},
                                 json={"model": r.model, "max_tokens": max_tokens, "system": system,
                                       "messages": [{"role": "user", "content": content}]})
                if resp.status_code >= 400:
                    raise _error(resp, "Claude")
                return "".join(b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text")
            if r.provider == "ollama":
                msg: dict[str, Any] = {"role": "user", "content": prompt}
                if images:
                    msg["images"] = images
                headers = {"Authorization": f"Bearer {r.key}"} if r.key else {}
                body: dict[str, Any] = {"model": r.model, "stream": False,
                                        "messages": [{"role": "system", "content": system}, msg]}
                if json_mode:
                    body["format"] = "json"
                resp = http.post(f"{r.base_url}/api/chat", headers=headers, json=body)
                if resp.status_code >= 400:
                    raise _error(resp, "Ollama")
                return resp.json().get("message", {}).get("content", "")
            # gemini y openrouter: API compatible con OpenAI (/chat/completions)
            parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            parts += [{"type": "image_url", "image_url": {"url": f"data:{_guess_mime(b)};base64,{b}"}} for b in images]
            body = {"model": r.model, "max_tokens": max_tokens,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": parts if images else prompt}]}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            who = "Gemini" if r.provider == "gemini" else "OpenRouter"
            resp = http.post(f"{r.base_url}/chat/completions", headers={"Authorization": f"Bearer {r.key}"}, json=body)
            if resp.status_code >= 400:
                raise _error(resp, who)
            choices = resp.json().get("choices") or [{}]
            return (choices[0].get("message") or {}).get("content") or ""
    except httpx.TimeoutException:
        raise AiError("El proveedor de IA tardó demasiado en responder")
    except httpx.HTTPError as exc:
        raise AiError(f"No se pudo conectar con el proveedor de IA ({exc.__class__.__name__})")


def complete_json(r: Resolved, system: str, prompt: str, **kw) -> dict:
    """Como complete(), pero exige y devuelve un objeto JSON (tolera ```json …``` alrededor)."""
    text = complete(r, system + "\nResponde SOLO con un objeto JSON válido, sin texto alrededor.", prompt, json_mode=True, **kw)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise AiError("La IA no devolvió un JSON")
    try:
        data = json.loads(m.group(0))
    except ValueError:
        raise AiError("La IA devolvió un JSON no válido")
    if not isinstance(data, dict):
        raise AiError("La IA no devolvió un objeto JSON")
    return data


def test_connection(r: Resolved) -> str:
    """Prueba corta con la configuración efectiva. Devuelve un mensaje para el usuario. Lanza AiError."""
    reply = complete(r, "Responde solo con la palabra OK.", "Di OK.", max_tokens=10)
    return f"Conectado con {PROVIDERS[r.provider]['label']} · {r.model}" + ("" if reply.strip() else " (respuesta vacía)")
