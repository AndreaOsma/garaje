from app.soberan import classify


def _sync_payload(**overrides):
    payload = {
        "properties": [
            {"id": 7, "nombre": "Suzuki", "marca": "Suzuki", "modelo": "Vitara", "anio": 2019,
             "matricula": "1234ABC", "km": 60000, "valor_estimado": 12500.0,
             "valor_actualizado_en": "2026-10-01T10:00:00", "confianza": "alta"},
        ],
        "debts": [{"id": 3, "nombre": "Coche Suzuki", "acreedor": "Banco", "pendiente": 4200.5, "cuota_mensual": 210}],
        "categories": ["Transporte", "Ocio"],
        "transactions": [
            {"id": 101, "date": "2026-10-02", "amount": -62.3, "description": "COMPRA REPSOL E.S. MADRID", "category": "Transporte"},
            {"id": 102, "date": "2026-10-03", "amount": -420, "description": "RECIBO MAPFRE SEGUROS", "category": "Transporte"},
            {"id": 103, "date": "2026-10-04", "amount": -35, "description": "CINE", "category": "Ocio"},
            {"id": 104, "date": "2026-10-05", "amount": 50, "description": "DEVOLUCION REPSOL", "category": "Transporte"},
        ],
    }
    payload.update(overrides)
    return payload


def test_classify_merchants():
    assert classify("COMPRA REPSOL E.S. MADRID") == ("fuel", "combustible")
    assert classify("Plenoil Getafe") == ("fuel", "combustible")
    assert classify("RECIBO MAPFRE SEGUROS") == ("expense", "seguro")
    assert classify("Applus ITV Alcorcón") == ("expense", "itv")
    assert classify("NORAUTO LEGANES") == ("service", "otros")
    assert classify("AUTOPISTA AP-6 PEAJE") == ("expense", "peaje")
    assert classify("Mercadona") == ("expense", "otros")


def test_full_soberan_round_trip(client):
    v = client.post("/api/vehicles", json={"name": "Suzuki", "fuel_type": "gasoline", "odometer_km": 61500}).json()
    vid = v["id"]

    # 1) Primera sincronización sin vínculos: solo se guarda la instantánea.
    first = client.post("/api/integrations/soberan/sync", json=_sync_payload(transactions=[])).json()
    assert first["vehicles_updated"] == 0
    state = client.get("/api/integrations/soberan").json()
    assert state["properties"][0]["id"] == 7 and "Transporte" in state["categories"]

    # 2) La UI enlaza el vehículo y elige categorías: se rellena al momento con la instantánea.
    linked = client.put(f"/api/vehicles/{vid}/soberan-link", json={"property_id": 7, "debt_id": 3}).json()
    assert linked["market_value"] == 12500.0 and linked["debt_pending"] == 4200.5
    client.put("/api/integrations/soberan/settings", json={"categories": ["Transporte"]})

    # 3) Soberan lee la config: vínculo + km de Garaje + categorías.
    config = client.get("/api/integrations/soberan/config").json()
    link = next(l for l in config["links"] if l["garaje_vehicle_id"] == vid)
    assert link["property_id"] == 7 and link["debt_id"] == 3 and link["odometer_km"] == 61500
    assert config["categories"] == ["Transporte"]

    # 4) Sincronización con movimientos: solo gastos de las categorías elegidas, sin duplicar.
    result = client.post("/api/integrations/soberan/sync", json=_sync_payload()).json()
    assert result == {"vehicles_updated": 1, "inbox_created": 2}
    again = client.post("/api/integrations/soberan/sync", json=_sync_payload()).json()
    assert again["inbox_created"] == 0

    inbox = client.get(f"/api/vehicles/{vid}/inbox").json()
    kinds = {i["description"]: (i["suggested_kind"], i["suggested_category"], i["amount"]) for i in inbox}
    assert kinds["COMPRA REPSOL E.S. MADRID"] == ("fuel", "combustible", 62.3)
    assert kinds["RECIBO MAPFRE SEGUROS"] == ("expense", "seguro", 420.0)
    assert all(i["vehicle_id"] == vid for i in inbox)

    dash = client.get(f"/api/vehicles/{vid}/dashboard").json()
    assert any(a["kind"] == "inbox" for a in dash["alerts"]) and dash["inbox_pending"] == 2
    assert dash["vehicle"]["market_value"] == 12500.0

    # 5) Confirmar uno como repostaje y descartar el otro.
    fuel_item = next(i for i in inbox if i["suggested_kind"] == "fuel")
    entry = client.post(f"/api/vehicles/{vid}/fuel", json={
        "date": fuel_item["date"], "odometer_km": 61700, "quantity": 40, "total_cost": fuel_item["amount"],
    }).json()
    ok = client.post(f"/api/inbox/{fuel_item['id']}/resolve", json={"status": "accepted", "record_type": "fuel", "record_id": entry["id"]})
    assert ok.status_code == 200 and ok.json()["status"] == "accepted"
    other = next(i for i in inbox if i["id"] != fuel_item["id"])
    client.post(f"/api/inbox/{other['id']}/resolve", json={"status": "dismissed"})
    assert client.get(f"/api/vehicles/{vid}/inbox").json() == []

    # Aceptar sin registro creado es un error.
    bad = client.post(f"/api/inbox/{other['id']}/resolve", json={"status": "accepted"})
    assert bad.status_code == 422


def test_property_cannot_link_twice(client):
    a = client.post("/api/vehicles", json={"name": "A"}).json()
    b = client.post("/api/vehicles", json={"name": "B"}).json()
    assert client.put(f"/api/vehicles/{a['id']}/soberan-link", json={"property_id": 99}).status_code == 200
    assert client.put(f"/api/vehicles/{b['id']}/soberan-link", json={"property_id": 99}).status_code == 409
    # Desenlazar libera el coche de Soberan.
    client.put(f"/api/vehicles/{a['id']}/soberan-link", json={"property_id": None})
    assert client.put(f"/api/vehicles/{b['id']}/soberan-link", json={"property_id": 99}).status_code == 200
