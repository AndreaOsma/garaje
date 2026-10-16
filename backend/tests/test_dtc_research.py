import json
from types import SimpleNamespace

import httpx

from app import dtc_research
from app.dtc_research import research_claude, research_ollama

ANSWER = {
    "found": True,
    "description": "Sensor de velocidad de rueda trasera izquierda: señal incoherente",
    "severity": "media",
    "system": "ABS / ESP",
    "causes": ["Sensor sucio", "Cableado dañado", "Corona del rodamiento"],
    "advice": "Revisa el sensor y su conector antes de cambiar piezas.",
    "sources": ["https://ejemplo.test/psa-c163a", "no-es-url"],
    "confidence": "media",
}


class FakeBeta:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _resp(stop, text=None):
    content = [SimpleNamespace(type="server_tool_use")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(stop_reason=stop, content=content)


def test_claude_handles_pause_turn_and_parses_json():
    beta = FakeBeta([_resp("pause_turn"), _resp("end_turn", json.dumps(ANSWER))])
    client = SimpleNamespace(beta=SimpleNamespace(messages=beta))
    r = research_claude("Código: C163A\nMarca: Peugeot", "key", client=client)
    assert r.found and r.provider == "claude" and r.sources == ["https://ejemplo.test/psa-c163a"]
    first = beta.calls[0]
    assert first["model"] == "claude-opus-5-5" and first["fallbacks"] == "default"
    assert first["tools"][0]["type"] == "web_search_20260209"
    # El turno pausado se reenvía como asistente para que continúe.
    assert beta.calls[1]["messages"][1]["role"] == "assistant"


def test_claude_refusal_returns_none():
    client = SimpleNamespace(beta=SimpleNamespace(messages=FakeBeta([_resp("refusal")])))
    assert research_claude("x", "key", client=client) is None


def test_ollama_is_marked_low_confidence_without_sources():
    def handler(request):
        assert request.url.path == "/api/chat"
        return httpx.Response(200, json={"message": {"content": json.dumps(ANSWER)}})

    r = research_ollama("x", "http://ollama.test", "qwen2.5:7b", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert r.provider == "ollama" and r.confidence == "baja" and r.sources == []


def test_auto_research_stores_definition_and_never_overrides_manual(client, monkeypatch):
    monkeypatch.setenv("GARAJE_OLLAMA_URL", "http://ollama.test")
    calls = []

    def fake_research(code, make, model="", year=None, engine="", fuel=""):
        calls.append((code, make, model))
        return dtc_research.Research(provider="ollama", **{k: v for k, v in ANSWER.items() if k != "sources"}, sources=[])

    monkeypatch.setattr(dtc_research, "research", fake_research)
    vid = client.post("/api/vehicles", json={"name": "208 auto", "make": "Citroën", "model": "C3", "fuel_type": "diesel"}).json()["id"]
    added = client.post(f"/api/vehicles/{vid}/dtcs", json={"code": "C163A", "kind": "pending"})
    assert added.status_code == 201
    # La tarea en segundo plano ya ha corrido (TestClient la ejecuta tras responder).
    assert calls == [("C163A", "Citroën", "C3")]
    dtc = next(d for d in client.get(f"/api/vehicles/{vid}/dtcs").json() if d["code"] == "C163A")
    assert dtc["learned"] == "ia" and dtc["description"].startswith("Sensor de velocidad")
    assert dtc["details"]["causes"][0] == "Sensor sucio" and dtc["details"]["confidence"] == "baja"

    # Un código genérico que ya está en el diccionario base no se investiga.
    client.post(f"/api/vehicles/{vid}/dtcs", json={"code": "P0420"})
    assert [c[0] for c in calls] == ["C163A"]

    # Lo escrito a mano manda: «Buscar de nuevo» no lo pisa.
    client.put(f"/api/vehicles/{vid}/dtc-definitions/C163A", json={"description": "ABS trasero (taller)"})
    r = client.post(f"/api/vehicles/{vid}/dtcs/{dtc['id']}/research")
    assert r.status_code == 200 and r.json()["description"] == "ABS trasero (taller)"


def test_research_endpoint_without_providers(client, vehicle, monkeypatch):
    monkeypatch.delenv("GARAJE_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GARAJE_OLLAMA_URL", raising=False)
    d = client.post(f"/api/vehicles/{vehicle['id']}/dtcs", json={"code": "P1234"}).json()
    assert client.post(f"/api/vehicles/{vehicle['id']}/dtcs/{d['id']}/research").status_code == 503
    assert client.get("/api/research/status").json() == {"providers": []}


def test_ollama_answer_from_wrong_family_is_discarded():
    wrong = dict(ANSWER, description="Problema con el sensor de presión del filtro de combustible", system="inyección")

    def handler(request):
        return httpx.Response(200, json={"message": {"content": json.dumps(wrong)}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert research_ollama("Código: C163A", "http://o.test", "m", http=http, code="C163A") is None
    # Un código P sí puede hablar del combustible.
    assert research_ollama("Código: P1490", "http://o.test", "m", http=http, code="P1490") is not None
    assert "Chasis" in dtc_research.vehicle_prompt("C163A", "Peugeot", "208", 2013, "", "diesel")
