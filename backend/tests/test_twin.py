from datetime import date

from app.twin import dtc_component


def test_dtc_component_mapping():
    assert dtc_component("P0490") == "egr"
    assert dtc_component("P0401") == "egr"
    assert dtc_component("P0299") == "turbo"
    assert dtc_component("P0420") == "exhaust"
    assert dtc_component("P2002") == "exhaust"
    assert dtc_component("P0301") == "engine"
    assert dtc_component("P0671") == "engine"
    assert dtc_component("P0606") == "ecu"
    assert dtc_component("P0171") == "injection"
    assert dtc_component("P0455") == "fuel_tank"
    assert dtc_component("P0730") == "gearbox"
    assert dtc_component("C0035") == "brakes"
    assert dtc_component("U0100") == "ecu"
    assert dtc_component("C163A") is None  # de fabricante: sin pieza conocida
    assert dtc_component("P1234") is None


def test_twin_states_for_diesel(client):
    vid = client.post("/api/vehicles", json={"name": "208", "make": "Peugeot", "fuel_type": "diesel", "odometer_km": 120000}).json()["id"]
    client.post(f"/api/vehicles/{vid}/dtcs", json={"code": "P0490", "kind": "stored"})
    client.post(f"/api/vehicles/{vid}/dtcs", json={"code": "C163A", "kind": "pending"})
    client.post(f"/api/vehicles/{vid}/issues", json={
        "reported_on": date.today().isoformat(), "title": "Chirrido al frenar", "severity": "limiting", "category": "frenos",
    })
    twin = client.get(f"/api/vehicles/{vid}/twin").json()
    comps = {c["id"]: c for c in twin["components"]}
    assert "egr" in comps and "turbo" in comps and "hv_battery" not in comps
    assert comps["egr"]["status"] == "warn" and "P0490" in comps["egr"]["items"][0]["text"]
    assert comps["brakes"]["status"] == "warn"
    assert comps["tyres"]["status"] in ("ok", "info")
    assert any("C163A" in u["text"] for u in twin["unassigned"])

    ev = client.post("/api/vehicles", json={"name": "EV", "fuel_type": "electric"}).json()["id"]
    ev_ids = {c["id"] for c in client.get(f"/api/vehicles/{ev}/twin").json()["components"]}
    assert {"hv_battery", "emotor"} <= ev_ids and "exhaust" not in ev_ids and "engine" not in ev_ids



def test_engine_twin_maps_codes_to_engine_parts_and_cylinders(client):
    from app.twin import engine_part_for_code

    assert engine_part_for_code("P0302") == ("ignition", 2)
    assert engine_part_for_code("P0203") == ("injectors", 3)
    assert engine_part_for_code("P0490") == ("egr", None)
    assert engine_part_for_code("P0299") == ("turbo", None)
    assert engine_part_for_code("P0087") == ("fuel_rail", None)
    assert engine_part_for_code("P0672") == ("glow", 2)
    assert engine_part_for_code("C0035") == (None, None)

    vid = client.post("/api/vehicles", json={"name": "Motor", "fuel_type": "diesel"}).json()["id"]
    client.post(f"/api/vehicles/{vid}/dtcs", json={"code": "P0302"})
    client.post(f"/api/vehicles/{vid}/dtcs", json={"code": "P0490"})
    eng = client.get(f"/api/vehicles/{vid}/twin/engine").json()
    assert eng["kind"] == "inline-diesel" and eng["cylinders"] == 4
    assert eng["parts"]["cyl2"]["status"] == "danger" and eng["parts"]["egr"]["status"] == "warn"
    assert "ignition" not in eng["parts"] and eng["parts"]["injectors"]["status"] == "danger"
    ev = client.post("/api/vehicles", json={"name": "EV", "fuel_type": "electric"}).json()["id"]
    assert client.get(f"/api/vehicles/{ev}/twin/engine").status_code == 404



def test_engine_twin_uses_vehicle_cylinders(client):
    vid = client.post("/api/vehicles", json={"name": "1.2 PureTech", "fuel_type": "gasoline", "cylinders": 3}).json()["id"]
    assert client.get(f"/api/vehicles/{vid}/twin/engine").json()["cylinders"] == 3
    assert client.post("/api/vehicles", json={"name": "X", "cylinders": 12}).status_code == 422
