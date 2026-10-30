"""Motos: plan de mantenimiento, revisiones y piezas propias."""


def _moto(client, **extra):
    r = client.post("/api/vehicles", json={"name": "MT-07", "kind": "motorcycle", "make": "Yamaha", "fuel_type": "gasoline", "odometer_km": 12000, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_moto_plan_has_chain_and_no_car_tasks(client):
    moto = _moto(client)
    assert moto["kind"] == "motorcycle"
    tasks = client.get(f"/api/vehicles/{moto['id']}/tasks").json()
    names = {t["name"] for t in tasks}
    assert "Engrase y tensado de cadena" in names
    assert "Holgura de válvulas" in names
    assert "Filtro de habitáculo" not in names and "Escobillas limpiaparabrisas" not in names


def test_short_interval_is_not_always_soon(client):
    moto = _moto(client)
    tasks = client.get(f"/api/vehicles/{moto['id']}/tasks").json()
    chain = next(t for t in tasks if t["name"].startswith("Engrase y tensado"))
    r = client.put(f"/api/vehicles/{moto['id']}/tasks/{chain['id']}", json={**{k: chain[k] for k in ("name", "category", "interval_km", "interval_months", "notes", "active")}, "last_done_km": 12000})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"  # 800 km por delante: con el umbral fijo de 1.000 sería «pronto»


def test_checklists_by_kind(client):
    moto = _moto(client)
    names = [c["name"] for c in client.get(f"/api/vehicles/{moto['id']}/mechanics").json()["checklists"]]
    assert "Antes de salir (moto)" in names
    assert "Antes de un viaje largo" not in names
    car = client.post("/api/vehicles", json={"name": "Ibiza", "fuel_type": "gasoline", "odometer_km": 1}).json()
    car_names = [c["name"] for c in client.get(f"/api/vehicles/{car['id']}/mechanics").json()["checklists"]]
    assert "Antes de un viaje largo" in car_names and "Antes de salir (moto)" not in car_names
    moto_only = next(c for c in client.get(f"/api/vehicles/{moto['id']}/mechanics").json()["checklists"] if c["name"] == "Antes de salir (moto)")
    assert client.delete(f"/api/vehicles/{car['id']}/checklists/{moto_only['id']}").status_code == 404


def test_moto_twin_components(client):
    moto = _moto(client)
    twin = client.get(f"/api/vehicles/{moto['id']}/twin").json()
    assert twin["kind"] == "motorcycle"
    ids = {c["id"] for c in twin["components"]}
    assert {"chain", "engine", "brakes", "suspension"} <= ids
    assert not ids & {"cabin", "turbo", "egr"}
    # Una B (carrocería/confort) va al carenado y cuadro.
    client.post(f"/api/vehicles/{moto['id']}/dtcs", json={"code": "B1234", "kind": "stored"})
    twin = client.get(f"/api/vehicles/{moto['id']}/twin").json()
    body = next(c for c in twin["components"] if c["id"] == "body")
    assert any("B1234" in it["text"] for it in body["items"])


def test_single_cylinder_allowed(client):
    assert _moto(client, cylinders=1)["cylinders"] == 1
