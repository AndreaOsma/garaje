from datetime import date, timedelta


def _mech(client, vid):
    return client.get(f"/api/vehicles/{vid}/mechanics").json()


def test_readiness_go_then_caution_then_nogo(client):
    vid = client.post("/api/vehicles", json={"name": "Mecánica", "odometer_km": 1000, "with_default_plan": False}).json()["id"]
    assert _mech(client, vid)["readiness"] == {"status": "go", "reasons": []}

    # Incidencia limitante → precaución.
    lim = client.post(f"/api/vehicles/{vid}/issues", json={
        "reported_on": date.today().isoformat(), "title": "Ruido en la rueda delantera", "severity": "limiting",
    }).json()
    r = _mech(client, vid)["readiness"]
    assert r["status"] == "caution" and "Ruido" in r["reasons"][0]["text"]

    # ITV caducada → no circular (aunque haya otras cosas).
    client.post(f"/api/vehicles/{vid}/deadlines", json={
        "kind": "itv", "title": "ITV", "due_date": (date.today() - timedelta(days=2)).isoformat(),
    })
    r = _mech(client, vid)["readiness"]
    assert r["status"] == "nogo" and r["reasons"][0]["level"] == "nogo"
    dash = client.get(f"/api/vehicles/{vid}/dashboard").json()
    assert dash["readiness"]["status"] == "nogo"
    assert any(a["kind"] == "issue" for a in dash["alerts"])

    # Resolver con una intervención del taller.
    svc = client.post(f"/api/vehicles/{vid}/services", json={
        "date": date.today().isoformat(), "title": "Rodamiento delantero", "category": "suspensión", "cost": 120,
    }).json()
    bad = client.post(f"/api/vehicles/{vid}/issues/{lim['id']}/resolve", json={
        "resolved_on": (date.today() - timedelta(days=30)).isoformat(),
    })
    assert bad.status_code == 422
    ok = client.post(f"/api/vehicles/{vid}/issues/{lim['id']}/resolve", json={
        "resolved_on": date.today().isoformat(), "resolution": "Cambiado el rodamiento", "service_id": svc["id"],
    }).json()
    assert ok["resolved_on"] and ok["service_id"] == svc["id"]
    reasons = _mech(client, vid)["readiness"]["reasons"]
    assert all("Ruido" not in r["text"] for r in reasons)


def test_checklists_seeded_and_failed_items_open_issues(client):
    vid = client.post("/api/vehicles", json={"name": "Checklist", "odometer_km": 5000}).json()["id"]
    data = _mech(client, vid)
    names = [c["name"] for c in data["checklists"]]
    assert {"Revisión rápida mensual", "Antes de un viaje largo", "Antes de la ITV"} <= set(names)
    monthly = next(c for c in data["checklists"] if c["name"] == "Revisión rápida mensual")
    assert monthly["due"] is True and monthly["last_run_on"] is None

    items = [(s["title"], i) for s in monthly["sections"] for i in s["items"]]
    results = [
        {"section": sec, "label": it["label"], "check": it["check"], "ok": True} for sec, it in items
    ]
    results[0].update(ok=False, note="Por debajo de MIN", severity="limiting")
    results[1].update(ok=False, create_issue=False)
    run = client.post(f"/api/vehicles/{vid}/checklist-runs", json={
        "checklist_id": monthly["id"], "date": date.today().isoformat(), "odometer_km": 5100, "results": results,
    })
    assert run.status_code == 201, run.text
    assert run.json()["failed"] == 2 and run.json()["issues_created"] == 1

    data = _mech(client, vid)
    monthly = next(c for c in data["checklists"] if c["name"] == "Revisión rápida mensual")
    assert monthly["due"] is False and monthly["last_run_failed"] == 2
    issue = data["issues"][0]
    assert issue["severity"] == "limiting" and "Aceite" in issue["title"] and "Por debajo de MIN" in issue["description"]
    assert data["readiness"]["status"] == "caution"
    assert client.get(f"/api/vehicles/{vid}").json()["odometer_km"] == 5100


def test_custom_checklist_scoped_to_vehicle(client):
    a = client.post("/api/vehicles", json={"name": "A"}).json()["id"]
    b = client.post("/api/vehicles", json={"name": "B"}).json()["id"]
    cl = client.post(f"/api/vehicles/{a}/checklists", json={
        "name": "Remolque", "sections": [{"title": "Enganche", "items": [{"label": "Bola", "check": "Engrasada"}]}],
    }).json()
    assert any(c["id"] == cl["id"] for c in _mech(client, a)["checklists"])
    assert all(c["id"] != cl["id"] for c in _mech(client, b)["checklists"])
    assert client.delete(f"/api/vehicles/{b}/checklists/{cl['id']}").status_code == 404


def test_add_missing_suggestions(client):
    vid = client.post("/api/vehicles", json={"name": "Vacío", "fuel_type": "diesel", "with_default_plan": False}).json()["id"]
    sugg = _mech(client, vid)["suggestions"]
    assert any(s["name"] == "Aceite y filtro de aceite" for s in sugg)
    added = client.post(f"/api/vehicles/{vid}/tasks/from-suggestions", json={"names": ["Aceite y filtro de aceite", "Inventada"]}).json()
    assert [t["name"] for t in added] == ["Aceite y filtro de aceite"]
    assert all(s["name"] != "Aceite y filtro de aceite" for s in _mech(client, vid)["suggestions"])


def test_issue_from_dtc_normalizes_code(client, vehicle):
    r = client.post(f"/api/vehicles/{vehicle['id']}/issues", json={
        "reported_on": date.today().isoformat(), "title": "P0420", "dtc_code": "p0420", "severity": "info",
    })
    assert r.status_code == 201 and r.json()["dtc_code"] == "P0420"
