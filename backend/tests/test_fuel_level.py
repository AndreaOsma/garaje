"""Nivel del depósito (%), su capacidad (buscada o a mano) y la autonomía."""
from datetime import date

import pytest

from app import specs_research
from app.routers import vehicles as vehicles_router

from .test_agent import call, on  # noqa: F401 — fixture del token de agente


@pytest.fixture(autouse=True)
def no_research(monkeypatch):
    """Sin red en los tests: la búsqueda del depósito devuelve lo que diga cada test."""
    found = {"value": None}
    monkeypatch.setattr(specs_research, "research_tank", lambda *a, **k: found["value"])
    return found


def test_level_capacity_and_range(client, vehicle):
    vid = vehicle["id"]
    # Sin capacidad: solo el %.
    r = client.post(f"/api/vehicles/{vid}/fuel-level", json={"pct": 40})
    assert r.status_code == 200 and r.json()["fuel_level_pct"] == 40
    assert client.post(f"/api/vehicles/{vid}/fuel-level", json={"pct": 140}).status_code == 422
    # Capacidad a mano + consumo de dos llenos → litros que quedan y autonomía.
    v = client.put(f"/api/vehicles/{vid}", json={**vehicle, "tank_capacity": 50}).json()
    assert v["tank_capacity"] == 50 and v["tank_capacity_source"] == "manual"
    client.post(f"/api/vehicles/{vid}/fuel", json={"date": "2026-01-01", "odometer_km": 100000, "quantity": 40, "total_cost": 60, "full_tank": True})
    client.post(f"/api/vehicles/{vid}/fuel", json={"date": "2026-01-10", "odometer_km": 101000, "quantity": 50, "total_cost": 75, "full_tank": True})
    client.post(f"/api/vehicles/{vid}/fuel-level", json={"pct": 40})
    g = client.get(f"/api/vehicles/{vid}/dashboard").json()["fuel"]
    assert g["pct"] == 40 and g["left"] == 20.0 and g["unit"] == "L"
    assert g["range_km"] == 400  # 20 L a 5 L/100 km


def test_full_tank_today_fills_to_100(client, vehicle):
    vid = vehicle["id"]
    client.post(f"/api/vehicles/{vid}/fuel-level", json={"pct": 10})
    client.post(f"/api/vehicles/{vid}/fuel", json={"date": "2020-01-01", "odometer_km": 100100, "quantity": 30, "total_cost": 40, "full_tank": True})
    assert client.get(f"/api/vehicles/{vid}").json()["fuel_level_pct"] == 10, "un lleno antiguo no toca el nivel"
    client.post(f"/api/vehicles/{vid}/fuel", json={"date": date.today().isoformat(), "odometer_km": 100200, "quantity": 30, "total_cost": 40, "full_tank": True})
    assert client.get(f"/api/vehicles/{vid}").json()["fuel_level_pct"] == 100


def test_research_never_overrides_manual(client, vehicle, no_research):
    vid = vehicle["id"]
    no_research["value"] = specs_research.TankResult(capacity=45.0, note="1.5 BlueHDi", sources=["https://example.org"], provider="claude")
    r = client.post(f"/api/vehicles/{vid}/tank/research")
    assert r.status_code == 200 and r.json()["tank_capacity"] == 45.0 and r.json()["tank_capacity_source"] == "web"
    client.put(f"/api/vehicles/{vid}", json={**vehicle, "tank_capacity": 47})
    assert client.post(f"/api/vehicles/{vid}/tank/research").status_code == 409
    vehicles_router.research_tank_background(vid)
    assert client.get(f"/api/vehicles/{vid}").json()["tank_capacity"] == 47
    no_research["value"] = None
    client.put(f"/api/vehicles/{vid}", json={**vehicle, "tank_capacity": None})
    assert client.post(f"/api/vehicles/{vid}/tank/research").status_code == 404


def test_research_result_is_validated():
    assert specs_research._clean({"found": True, "capacity": 9999, "note": "", "sources": [], "confidence": "alta"}, "gasoline", "x") is None
    assert specs_research._clean({"found": False, "capacity": 45}, "gasoline", "x") is None
    r = specs_research._clean({"found": True, "capacity": 44.6, "note": " 1.2  PureTech ", "sources": ["javascript:x", "https://a.b"], "confidence": "x"}, "gasoline", "claude")
    assert r.capacity == 44.6 and r.note == "1.2 PureTech" and r.sources == ["https://a.b"] and r.confidence == "baja"


def test_agent_level_status_and_low_alert(client, vehicle, on):  # noqa: F811
    client.put(f"/api/vehicles/{vehicle['id']}", json={**vehicle, "name": "Depósito", "tank_capacity": 40})
    r = call(client, "nivel_combustible", {"vehiculo": "Depósito", "porcentaje": 10})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert res["deposito_pct"] == 10 and res["quedan_l"] == 4.0
    st = call(client, "estado", {"vehiculo": "Depósito"}).json()["result"]
    assert st["deposito_pct"] == 10
    av = call(client, "avisos").json()["result"]
    assert any("Depósito: queda poco en el depósito (10 %)" == a["texto"] and a["nivel"] == "pronto" for a in av)


def _gz(raw: bytes) -> str:
    import base64
    import gzip

    return base64.b64encode(gzip.compress(raw)).decode()


CSV = (
    '"SECONDS";"PID";"VALUE";"UNITS"\n'
    '"49700.5";"Engine RPM";"850";"rpm"\n'
    '"49700.5";"Engine coolant temperature";"88";"°C"\n'
    '"49701.5";"Engine RPM";"900";"rpm"\n'
).encode()


def test_agent_imports_carscanner_csv_with_preview(client, vehicle, on):  # noqa: F811
    client.put(f"/api/vehicles/{vehicle['id']}", json={**vehicle, "name": "OBD ágora"})
    args = {"vehiculo": "OBD ágora", "nombre": "car-scanner.csv", "contenido_gz_b64": _gz(CSV), "fecha": "2026-10-01"}
    v = client.post("/agent/v1/validate/importar_obd", json=args, headers={"Authorization": "Bearer " + "g" * 40})
    assert v.status_code == 200, v.text
    assert "3 lecturas de 2 sensores" in v.json()["preview"] and "OBD ágora" in v.json()["preview"]
    r = call(client, "importar_obd", args)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["lecturas"] == 3
    assert call(client, "importar_obd", args).status_code == 409, "el mismo fichero no se importa dos veces"


def test_agent_obd_rejects_garbage(client, vehicle, on):  # noqa: F811
    client.put(f"/api/vehicles/{vehicle['id']}", json={**vehicle, "name": "OBD basura"})
    assert call(client, "importar_obd", {"vehiculo": "OBD basura", "contenido_gz_b64": "no es base64!!"}).status_code == 422
    nada = _gz(b"hola, esto no es un log del coche")
    assert call(client, "importar_obd", {"vehiculo": "OBD basura", "contenido_gz_b64": nada}).status_code == 422


def test_ai_tank_capacity_is_confirmed_by_the_person(client, vehicle, no_research):
    vid = vehicle["id"]
    assert client.post(f"/api/vehicles/{vid}/tank/confirm").status_code == 422  # nada que confirmar
    no_research["value"] = specs_research.TankResult(capacity=45.0, note="orientativa", sources=[], provider="ollama")
    assert client.post(f"/api/vehicles/{vid}/tank/research").json()["tank_capacity_source"] == "ia"
    r = client.post(f"/api/vehicles/{vid}/tank/confirm")
    assert r.status_code == 200 and r.json()["tank_capacity"] == 45.0 and r.json()["tank_capacity_source"] == "manual"
    assert client.post(f"/api/vehicles/{vid}/tank/research").status_code == 409  # confirmada: ya no se vuelve a buscar
