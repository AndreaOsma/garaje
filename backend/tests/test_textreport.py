from app.obd.textreport import parse_text

REPORT_ES = """Car Scanner ELM OBD2 - Informe de diagnóstico
Vehículo: Suzuki Vitara  VIN: VSSZZZ5FZJR000001
Fecha: 09/10/2026

Códigos de error confirmados:
P0420 - Eficiencia del catalizador por debajo del umbral (Banco 1)
P0171 - Sistema demasiado pobre (Banco 1)

Códigos pendientes:
P0300 - Fallo de encendido aleatorio

Códigos permanentes:
No se encontraron códigos

Revoluciones del motor: 850 rpm
Temperatura del refrigerante: 88 °C
Presión del turbo: 1,2 bar
"""

REPORT_EN = """Stored DTCs: P0133 P0300
Pending DTCs:
P2002
"""

ELM_LOG = """>ATZ
ELM327 v1.5
>03
43 02 01 33 03 00
>07
47 00
>010C
41 0C 1A F8
>0105
41 05 7B
"""


def test_spanish_report_sections_values_and_vin():
    r = parse_text(REPORT_ES.encode())
    assert r.dtcs["stored"] == ["P0420", "P0171"]
    assert r.dtcs["pending"] == ["P0300"]
    assert r.dtcs["permanent"] == []
    assert r.vin == "VSSZZZ5FZJR000001"
    assert r.values["0C"] == 850 and r.values["05"] == 88
    assert r.values["cs:presion-del-turbo"] == 1.2 and r.sensors["cs:presion-del-turbo"] == ("Presión del turbo", "bar")


def test_english_inline_codes():
    r = parse_text(REPORT_EN.encode())
    assert r.dtcs == {"stored": ["P0133", "P0300"], "pending": ["P2002"]}


def test_raw_elm327_terminal_log():
    r = parse_text(ELM_LOG.encode())
    assert r.dtcs["stored"] == ["P0133", "P0300"] and r.dtcs["pending"] == []
    assert r.values["0C"] == 1726.0 and r.values["05"] == 83.0


def test_nothing_recognised():
    assert parse_text(b"hola, esto no es un informe").empty


def test_txt_upload_via_ui_and_token_without_bearer(client, vehicle):
    vid = vehicle["id"]
    r = client.post(f"/api/vehicles/{vid}/import/obd-file", files={"file": ("informe.txt", REPORT_ES.encode(), "text/plain")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "report" and body["dtcs"]["stored"] == ["P0420", "P0171"] and body["vin"] == "VSSZZZ5FZJR000001"
    codes = {(d["code"], d["kind"]) for d in client.get(f"/api/vehicles/{vid}/dtcs").json() if not d["cleared_at"]}
    assert {("P0420", "stored"), ("P0171", "stored"), ("P0300", "pending")} <= codes
    live = {l["key"]: l["value"] for l in client.get(f"/api/vehicles/{vid}/live").json()}
    assert live["0C"] == 850
    # Un informe se puede volver a subir (se reprocesa sin duplicar sus valores).
    again = client.post(f"/api/vehicles/{vid}/import/obd-file", files={"file": ("informe.txt", REPORT_ES.encode(), "text/plain")})
    assert again.status_code == 201 and again.json()["reprocessed"] is True
    sessions = [s for s in client.get(f"/api/vehicles/{vid}/sessions").json() if s["source"] == "txt"]
    assert len(sessions) == 1 and sessions[0]["sample_count"] == 3

    token = client.post(f"/api/vehicles/{vid}/ingest-token").json()["token"]
    # Token sin «Bearer » (error típico al montar el Atajo): se acepta igual.
    ok = client.post("/api/ingest/file", headers={"Authorization": token}, files={"file": ("log.txt", ELM_LOG.encode(), "text/plain")})
    assert ok.status_code == 201, ok.text
    bad = client.post("/api/ingest/file", headers={"Authorization": "Bearer <tu token>"}, files={"file": ("x.txt", b"P0420", "text/plain")})
    assert bad.status_code == 401 and "genera uno nuevo" in bad.json()["detail"]
    junk = client.post(f"/api/vehicles/{vid}/import/obd-file", files={"file": ("x.txt", b"nada util", "text/plain")})
    assert junk.status_code == 422


PEUGEOT_TXT = """Car Scanner - Informe
Peugeot 208 1.6 BlueHDi
DTCs: 2
Protocolo: 6
Códigos confirmados:
P0490 - Circuito de control EGR A alto
Códigos pendientes:
C163A - Sensor de velocidad de la rueda trasera izquierda (pendiente)
"""


def test_report_learns_descriptions_and_ignores_counts():
    r = parse_text(PEUGEOT_TXT.encode())
    assert r.descriptions["C163A"] == "Sensor de velocidad de la rueda trasera izquierda"
    assert "cs:dtcs" not in r.values and not any(k.startswith("cs:protocolo") for k in r.values)


def test_learned_dictionary_by_make_and_manual_override(client):
    vid = client.post("/api/vehicles", json={"name": "208", "make": "Peugeot", "fuel_type": "diesel"}).json()["id"]
    other = client.post("/api/vehicles", json={"name": "Otro", "make": "Seat"}).json()["id"]
    up = lambda: client.post(f"/api/vehicles/{vid}/import/obd-file", files={"file": ("obd.txt", PEUGEOT_TXT.encode(), "text/plain")})
    first = up().json()
    assert first["learned"] == 2 and first["reprocessed"] is False
    # Un informe se puede volver a subir: se reprocesa sin error.
    again = up()
    assert again.status_code == 201 and again.json()["reprocessed"] is True

    dtcs = {d["code"]: d for d in client.get(f"/api/vehicles/{vid}/dtcs").json()}
    assert dtcs["C163A"]["description"].startswith("Sensor de velocidad") and dtcs["C163A"]["learned"] == "import"
    # P0490 ya está en el diccionario base, pero lo aprendido del informe manda.
    assert dtcs["P0490"]["learned"] == "import"
    # El código de fabricante aprendido es solo para Peugeot.
    assert "fabricante" in client.get("/api/dtc/C163A?make=Seat").json()["description"]
    assert client.get("/api/dtc/C163A?make=Peugeot").json()["description"].startswith("Sensor de velocidad")

    # Lo escrito a mano manda y no lo pisa una nueva importación.
    put = client.put(f"/api/vehicles/{vid}/dtc-definitions/C163A", json={"description": "ABS trasero izq. (taller)", "severity": "alta"})
    assert put.status_code == 200 and put.json()["severity"] == "alta"
    up()
    assert client.get("/api/dtc/C163A?make=Peugeot").json()["description"] == "ABS trasero izq. (taller)"
    # Volver al diccionario base.
    reset = client.delete(f"/api/vehicles/{vid}/dtc-definitions/P0490").json()
    assert reset["description"] == "Circuito de control de la EGR A: señal alta"
    assert other  # el otro vehículo existe y no ve la definición de Peugeot (comprobado arriba)
