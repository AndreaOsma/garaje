from datetime import date, timedelta


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_vehicle_gets_default_plan_by_fuel(client):
    ev = client.post("/api/vehicles", json={"name": "Eléctrico", "fuel_type": "electric"}).json()
    names = {t["name"] for t in client.get(f"/api/vehicles/{ev['id']}/tasks").json()}
    assert "Aceite y filtro de aceite" not in names and "Cambio de líquido de frenos" in names


def test_invalid_vin_rejected(client):
    response = client.post("/api/vehicles", json={"name": "X", "vin": "OOOOOOOOOOOOOOOOO"})
    assert response.status_code == 422


def test_service_resets_task_and_bumps_odometer(client, vehicle):
    vid = vehicle["id"]
    oil = next(t for t in client.get(f"/api/vehicles/{vid}/tasks").json() if t["category"] == "aceite")
    assert oil["status"] == "unknown"
    today = date.today().isoformat()
    created = client.post(f"/api/vehicles/{vid}/services", json={
        "task_id": oil["id"], "date": today, "odometer_km": 101000, "category": "aceite",
        "title": "Cambio de aceite", "cost": 89.9,
    })
    assert created.status_code == 201
    oil = next(t for t in client.get(f"/api/vehicles/{vid}/tasks").json() if t["id"] == oil["id"])
    assert oil["status"] == "ok" and oil["next_due_km"] == 116000 and oil["remaining_km"] == 15000
    assert client.get(f"/api/vehicles/{vid}").json()["odometer_km"] == 101000


def test_overdue_task_alert(client, vehicle):
    vid = vehicle["id"]
    task = client.post(f"/api/vehicles/{vid}/tasks", json={
        "name": "Correa auxiliar", "interval_km": 1000, "last_done_km": 90000,
    }).json()
    assert task["status"] == "overdue"
    alerts = client.get(f"/api/vehicles/{vid}/dashboard").json()["alerts"]
    assert any(a["title"] == "Vencido: Correa auxiliar" for a in alerts)


def test_task_requires_interval(client, vehicle):
    response = client.post(f"/api/vehicles/{vehicle['id']}/tasks", json={"name": "Sin intervalo"})
    assert response.status_code == 422


def test_fuel_full_to_full_consumption(client, vehicle):
    vid = vehicle["id"]
    for km, liters, full in ((100000, 40, True), (100400, 15, False), (100800, 15, True)):
        client.post(f"/api/vehicles/{vid}/fuel", json={
            "date": date.today().isoformat(), "odometer_km": km, "quantity": liters, "total_cost": liters * 1.6, "full_tank": full,
        })
    data = client.get(f"/api/vehicles/{vid}/fuel").json()
    # 30 L en 800 km = 3,75 L/100 km
    assert data["avg_consumption"] == 3.75
    assert data["entries"][0]["consumption"] == 3.75


def test_deadline_status_and_alert(client, vehicle):
    vid = vehicle["id"]
    soon = (date.today() + timedelta(days=10)).isoformat()
    d = client.post(f"/api/vehicles/{vid}/deadlines", json={"kind": "itv", "title": "ITV", "due_date": soon}).json()
    assert d["status"] == "soon" and d["days_left"] == 10
    alerts = client.get(f"/api/vehicles/{vid}/dashboard").json()["alerts"]
    assert any(a["kind"] == "deadline" for a in alerts)


def test_cross_vehicle_access_is_404(client, vehicle):
    other = client.post("/api/vehicles", json={"name": "Otro"}).json()
    exp = client.post(f"/api/vehicles/{vehicle['id']}/expenses", json={"date": "2026-01-01", "title": "Seguro", "amount": 300}).json()
    assert client.delete(f"/api/vehicles/{other['id']}/expenses/{exp['id']}").status_code == 404


def test_ingest_requires_valid_token(client, vehicle):
    assert client.post("/api/ingest/snapshot", json={"session_id": "x"}).status_code == 401
    assert client.post("/api/ingest/snapshot", json={"session_id": "x"}, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_agent_snapshot_flow(client, vehicle):
    vid = vehicle["id"]
    token = client.post(f"/api/vehicles/{vid}/ingest-token").json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/ingest/whoami", headers=auth).json()["vehicle_id"] == vid

    payload = {
        "session_id": "20261008-agent",
        "samples": [
            {"ts": "2026-10-08T10:00:00Z", "key": "0C", "value": 850},
            {"ts": "2026-10-08T10:00:00Z", "key": "BATT", "value": 12.9},
            {"ts": "2026-10-08T10:00:02Z", "key": "0C", "value": 900},
            {"ts": "2026-10-08T10:00:02Z", "key": "A6", "value": 123456.7},
        ],
        "dtcs": {"stored": ["P0420", "basura"], "pending": [], "permanent": []},
        "monitor": {"mil_on": True, "dtc_count": 1, "ignition": "chispa",
                    "monitors": [{"name": "Catalizador", "complete": False}], "ready": False},
        "vin": "VSSZZZ5FZJR000001",
    }
    result = client.post("/api/ingest/snapshot", json=payload, headers=auth)
    assert result.status_code == 201, result.text

    v = client.get(f"/api/vehicles/{vid}").json()
    assert v["odometer_km"] == 123456 and v["mil_on"] is True and v["vin"] == "VSSZZZ5FZJR000001"
    dtcs = client.get(f"/api/vehicles/{vid}/dtcs").json()
    assert [d["code"] for d in dtcs] == ["P0420"] and "catalizador" in dtcs[0]["description"].lower()

    live = {l["key"]: l["value"] for l in client.get(f"/api/vehicles/{vid}/live").json()}
    assert live["0C"] == 900

    dash = client.get(f"/api/vehicles/{vid}/dashboard").json()
    kinds = {a["kind"] for a in dash["alerts"]}
    assert {"mil", "dtc", "readiness"} <= kinds and dash["active_dtcs"] == 1

    # Segunda lectura sin códigos: la avería pasa a borrada; la sesión se extiende.
    payload2 = {"session_id": "20261008-agent", "samples": [{"ts": "2026-10-08T10:01:00Z", "key": "0C", "value": 0}],
                "dtcs": {"stored": [], "pending": [], "permanent": []}}
    client.post("/api/ingest/snapshot", json=payload2, headers=auth)
    assert client.get(f"/api/vehicles/{vid}/dtcs").json()[0]["cleared_at"] is not None
    sessions = client.get(f"/api/vehicles/{vid}/sessions").json()
    assert len(sessions) == 1 and sessions[0]["sample_count"] == 5

    detail = client.get(f"/api/vehicles/{vid}/sessions/{sessions[0]['id']}").json()
    rpm = next(s for s in detail["series"] if s["key"] == "0C")
    assert rpm["max"] == 900 and rpm["unit"] == "rpm"

    # Regenerar el token invalida el anterior.
    client.post(f"/api/vehicles/{vid}/ingest-token")
    assert client.get("/api/ingest/whoami", headers=auth).status_code == 401


def test_carscanner_upload_via_token_and_dedupe(client, vehicle):
    vid = vehicle["id"]
    token = client.post(f"/api/vehicles/{vid}/ingest-token").json()["token"]
    csv = b'"SECONDS";"PID";"VALUE";"UNITS"\n"36000";"Engine RPM";"800";"rpm"\n"36001";"Boost pressure";"1.1";"bar"\n'
    files = {"file": ("viaje.csv", csv, "text/csv")}
    r = client.post("/api/ingest/carscanner", files=files, data={"date": "2026-10-08", "tz": "Europe/Madrid"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert r.json()["samples"] == 2
    again = client.post(f"/api/vehicles/{vid}/import/carscanner", files={"file": ("viaje.csv", csv, "text/csv")})
    assert again.status_code == 409
    live = {l["key"]: l for l in client.get(f"/api/vehicles/{vid}/live").json()}
    assert live["cs:boost-pressure"]["name"] == "Boost pressure" and live["cs:boost-pressure"]["unit"] == "bar"


def test_manual_dtc_and_lookup(client, vehicle):
    vid = vehicle["id"]
    r = client.post(f"/api/vehicles/{vid}/dtcs", json={"code": "p0300", "notes": "tras lavar el motor"})
    assert r.status_code == 201 and r.json()["code"] == "P0300" and r.json()["severity"] == "alta"
    assert client.post(f"/api/vehicles/{vid}/dtcs", json={"code": "X1234"}).status_code == 422
    assert client.get("/api/dtc/P0171").json()["description"].startswith("Mezcla")
    cleared = client.post(f"/api/vehicles/{vid}/dtcs/{r.json()['id']}/clear").json()
    assert cleared["cleared_at"]


def test_delete_vehicle_cascades(client):
    v = client.post("/api/vehicles", json={"name": "Temporal"}).json()
    client.post(f"/api/vehicles/{v['id']}/fuel", json={"date": "2026-01-01", "odometer_km": 10, "quantity": 5, "total_cost": 8})
    assert client.delete(f"/api/vehicles/{v['id']}").status_code == 204
    assert client.get(f"/api/vehicles/{v['id']}").status_code == 404


def test_fuel_discounts(client, vehicle):
    vid = vehicle["id"]
    # 40 L a 1,60 € en surtidor con 10 c€/L de descuento → pagado 60 €, descuento 4 €.
    e = client.post(f"/api/vehicles/{vid}/fuel", json={
        "date": "2026-10-01", "odometer_km": 101500, "quantity": 40, "total_cost": 60, "discount_cents_per_unit": 10,
    })
    assert e.status_code == 201, e.text
    assert e.json()["discount"] == 4.0
    # Descuento en € directamente (cupón).
    client.post(f"/api/vehicles/{vid}/fuel", json={
        "date": "2026-10-05", "odometer_km": 102000, "quantity": 30, "total_cost": 43, "discount": 2.5,
    })
    data = client.get(f"/api/vehicles/{vid}/fuel").json()
    first = next(x for x in data["entries"] if x["odometer_km"] == 101500)
    assert first["price_per_unit"] == 1.5 and first["pump_price_per_unit"] == 1.6
    assert data["total_discount"] == 6.5
    # Lo que cuenta como gasto es lo pagado, no el precio de surtidor.
    costs = client.get(f"/api/vehicles/{vid}/dashboard").json()["costs"]["by_category"]
    assert costs["combustible"] == 103.0
    assert client.post(f"/api/vehicles/{vid}/fuel", json={
        "date": "2026-10-05", "odometer_km": 1, "quantity": 1, "total_cost": 1, "discount": -1,
    }).status_code == 422
