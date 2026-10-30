"""API para asistentes (ágora)."""
import pytest

TOKEN = "g" * 40
H = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def on(monkeypatch):
    monkeypatch.setenv("GARAJE_AGENT_TOKEN", TOKEN)


def call(client, tool, args=None):
    return client.post(f"/agent/v1/call/{tool}", json=args or {}, headers=H)


def test_closed_without_token(client, monkeypatch):
    monkeypatch.delenv("GARAJE_AGENT_TOKEN", raising=False)
    assert client.get("/agent/v1/manifest", headers=H).status_code == 404


def test_refuel_expense_and_status(client, vehicle, on):
    plate = client.put(f"/api/vehicles/{vehicle['id']}", json={**vehicle, "name": "Agente", "plate": "1234 ABC"})
    assert plate.status_code == 200, plate.text
    r = call(client, "anadir_repostaje", {"vehiculo": "1234abc", "litros": 40, "total_eur": 60.5, "km": 100500})
    assert r.status_code == 200, r.text
    assert call(client, "anadir_gasto", {"vehiculo": "Agente", "concepto": "Parking", "importe_eur": 3}).status_code == 200
    assert call(client, "anadir_vencimiento", {"vehiculo": "Agente", "que": "ITV", "tipo": "itv", "fecha": "2020-01-01"}).status_code == 200
    st = call(client, "estado", {"vehiculo": "Agente"}).json()["result"]
    assert st["ver"] == f"/v/{vehicle['id']}" and st["km"] == 100500 and st["gastado_este_anio_eur"] >= 63.5
    assert any(d["que"] == "ITV" and d["estado"] == "overdue" for d in st["vencimientos"])
    assert call(client, "actualizar_km", {"vehiculo": "Agente", "km": 10}).status_code == 400
    assert call(client, "estado", {"vehiculo": "Inexistente"}).status_code == 404

def test_avisos(client, vehicle, on):
    client.put(f"/api/vehicles/{vehicle['id']}", json={**vehicle, "name": "Avisos"})
    call(client, "anadir_vencimiento", {"vehiculo": "Avisos", "que": "Seguro", "tipo": "seguro", "fecha": "2000-01-01"})
    av = call(client, "avisos").json()["result"]
    seguro = [a for a in av if "Avisos: Seguro" in a["texto"]]
    assert seguro and seguro[0]["nivel"] == "urgente" and seguro[0]["ver"].endswith("/documents")


def test_write_previews(client, vehicle, on):
    client.put(f"/api/vehicles/{vehicle['id']}", json={**vehicle, "name": "Previa"})
    def preview(tool, args):
        r = client.post(f"/agent/v1/validate/{tool}", json=args, headers=H)
        assert r.status_code == 200, r.text
        return r.json()["preview"]
    assert "40 litros por 60,50 €" in preview("anadir_repostaje", {"vehiculo": "Previa", "litros": 40, "total_eur": 60.5, "km": 1000, "fecha": "2026-10-30"})
    assert preview("anadir_gasto", {"vehiculo": "Previa", "concepto": "Parking", "importe_eur": 3, "fecha": "2026-10-30"}) == "Gasto de Previa: Parking (otros), 3,00 € el 30/10"
    assert preview("anadir_vencimiento", {"vehiculo": "Previa", "que": "ITV", "tipo": "itv", "fecha": "2027-01-15"}) == "Vencimiento de Previa: ITV (itv) el 15/01/2027"
    assert "«Ruido al frenar»" in preview("anotar_averia", {"vehiculo": "Previa", "que_pasa": "Ruido al frenar"})
    assert "en 150000 km" in preview("actualizar_km", {"vehiculo": "Previa", "km": 150000})
    assert client.post("/agent/v1/validate/actualizar_km", json={"vehiculo": "Previa", "km": 10}, headers=H).status_code == 400
