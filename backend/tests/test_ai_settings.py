"""El proveedor de IA lo pone el usuario en Ajustes y gana a lo que traiga el servidor."""
import json

import httpx
import pytest

from app import ai, ai_providers, dtc_research

ANSWER = {
    "found": True, "description": "Sensor de velocidad de rueda trasera izquierda: señal incoherente",
    "severity": "media", "system": "ABS / ESP", "causes": ["Sensor sucio"], "advice": "Revisa el conector.",
    "sources": ["https://inventada.test"], "confidence": "alta",
}


@pytest.fixture(autouse=True)
def _clean_store():
    ai.STORE.save(None)
    ai.STORE.delete_key()
    yield
    ai.STORE.save(None)
    ai.STORE.delete_key()
    ai_providers.TRANSPORT = None


def test_settings_key_never_returned_and_status_follows(client, monkeypatch):
    monkeypatch.delenv("GARAJE_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GARAJE_OLLAMA_URL", raising=False)
    assert client.get("/api/research/status").json() == {"providers": []}
    r = client.put("/api/ai", json={"provider": "openrouter", "key": "sk-or-mia"})
    assert r.status_code == 200 and "sk-or-mia" not in r.text and r.json()["has_key"] is True
    assert client.get("/api/research/status").json() == {"providers": ["openrouter"]}


def test_user_provider_wins_over_server_env(client, monkeypatch):
    monkeypatch.setenv("GARAJE_OLLAMA_URL", "http://ollama-del-servidor.test")
    seen = {}

    def handler(req):
        seen["url"], seen["auth"] = str(req.url), req.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ANSWER)}}]})

    ai_providers.TRANSPORT = httpx.MockTransport(handler)
    client.put("/api/ai", json={"provider": "gemini", "key": "g-mia"})
    res = dtc_research.research("C163A", "Citroën", "C3")
    assert seen["url"].startswith("https://generativelanguage.googleapis.com/") and seen["auth"] == "Bearer g-mia"
    # Sin web: orientativo y sin fuentes, aunque el modelo las invente.
    assert res and res.provider == "gemini" and res.sources == [] and res.confidence == "baja"


def test_user_ollama_server_with_token(client, monkeypatch):
    seen = {}

    def handler(req):
        seen["url"], seen["auth"] = str(req.url), req.headers.get("authorization")
        return httpx.Response(200, json={"message": {"content": json.dumps(ANSWER)}})

    real_client = httpx.Client
    monkeypatch.setattr(dtc_research.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))
    client.put("/api/ai", json={"provider": "ollama", "base_url": "http://mi-ollama.test:11434", "model": "qwen2.5:14b", "key": "tok"})
    res = dtc_research.research("C163A", "Citroën")
    assert seen["url"] == "http://mi-ollama.test:11434/api/chat" and seen["auth"] == "Bearer tok"
    assert res and res.provider == "ollama"
