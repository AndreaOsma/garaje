"""Carnés: catálogo, progreso, requisitos y el teórico A2 importado de content/."""
from datetime import date, timedelta


def _a2(client):
    return next(x for x in client.get("/api/licenses").json() if x["code"] == "A2")


def test_catalog_and_a2_course_imported(client):
    rows = client.get("/api/licenses").json()
    codes = [x["code"] for x in rows]
    assert {"AM", "A1", "A2", "A", "B", "C", "D"} <= set(codes)
    a2 = _a2(client)
    assert a2["exam"] == {"questions": 20, "max_errors": 2, "minutes": 20, "official": True}
    assert a2["course"] and a2["course"]["lessons_total"] >= 10
    assert [s["key"] for s in a2["steps"]][:3] == ["medico", "autoescuela", "teorico"]


def test_requirements_and_coverage(client):
    a = next(x for x in client.get("/api/licenses").json() if x["code"] == "A")
    assert a["requirements"][0]["state"] == "missing"
    # B desde hace 4 años: cubre AM y deja llevar motos de 125 en España.
    since = (date.today() - timedelta(days=4 * 366)).isoformat()
    r = client.put("/api/licenses/B", json={"status": "obtained", "obtained_on": since, "steps": {}})
    assert r.status_code == 200, r.text
    rows = {x["code"]: x for x in client.get("/api/licenses").json()}
    assert rows["AM"]["covered_by"] == "Incluido en tu B"
    assert rows["A1"]["covered_by"].startswith("Con más de 3 años de B")
    assert rows["C1"]["requirements"][0]["state"] == "ok"
    # A2 recién obtenido: al A le falta antigüedad.
    client.put("/api/licenses/A2", json={"status": "obtained", "obtained_on": date.today().isoformat()})
    a = client.get("/api/licenses/A").json()
    assert a["requirements"][0]["state"] == "wait" and a["requirements"][0]["until"]
    client.put("/api/licenses/A2", json={"status": "studying"})


def test_progress_validation(client):
    assert client.put("/api/licenses/A2", json={"status": "studying", "steps": {"cap": "2026-01-01"}}).status_code == 422
    assert client.put("/api/licenses/A2", json={"status": "studying", "steps": {"nada": "2026-01-01"}}).status_code == 422
    assert client.put("/api/licenses/ZZ", json={"status": "studying"}).status_code == 404
    r = client.put("/api/licenses/A2", json={"status": "studying", "steps": {"medico": "2026-10-01", "teorico": None}, "next_exam_on": "2026-11-20"})
    a2 = r.json()
    assert {s["key"]: s["done_on"] for s in a2["steps"]}["medico"] == "2026-10-01"
    assert a2["next_exam_on"] == "2026-11-20" and a2["obtained_on"] is None


def test_lesson_answer_and_exam(client):
    course = client.get(f"/api/learn/courses/{_a2(client)['course']['id']}").json()
    first = course["units"][0]["lessons"][0]
    assert not first["locked"] and course["units"][0]["lessons"][1]["locked"]
    lesson = client.get(f"/api/learn/lessons/{first['id']}").json()
    step = next(s for s in lesson["steps"] if s["kind"] == "choice")
    assert "correct" not in step and "options" in step
    wrong = client.post(f"/api/learn/steps/{step['id']}/answer", json={"response": [0], "confidence": "high"}).json()
    assert wrong["correct"] is False and wrong["solution"] == "35 kW" and wrong["confident_wrong"]
    assert wrong["option_feedback"]
    ok = client.post(f"/api/learn/steps/{step['id']}/answer", json={"response": [1]}).json()
    assert ok["correct"] and ok["xp"] == 10
    done = client.post(f"/api/learn/lessons/{first['id']}/complete", json={"correct": 4, "total": 5}).json()
    assert done["xp"] == 10 and done["game"]["today_xp"] >= 20
    assert client.get("/api/learn/review").json()["steps"] == []  # el fallo se repasa mañana

    exam = client.get(f"/api/learn/courses/{course['id']}/exam").json()
    assert len(exam["steps"]) == 20 and exam["max_errors"] == 2
    assert all(s.get("unit_title") != "Cómo son las pruebas" for s in exam["steps"])
    passed = client.post("/api/learn/exams/complete", json={"course_id": course["id"], "correct": 18, "total": 20}).json()
    failed = client.post("/api/learn/exams/complete", json={"course_id": course["id"], "correct": 17, "total": 20}).json()
    assert passed["passed"] and not failed["passed"]


def test_import_rejects_other_license(client):
    pack = b'{"format":"campus-pilot-course","format_version":1,"slug":"x","title":"X","subject_code":"C","units":[{"ref":"u","title":"U","lessons":[{"ref":"l","title":"L","steps":[{"ref":"s","kind":"truefalse","prompt":"?","data":{"answer":true},"source":"x"}]}]}]}'
    r = client.post("/api/learn/import/A2", files={"file": ("x.json", pack, "application/json")})
    assert r.status_code == 422
    r = client.post("/api/learn/import/C", files={"file": ("x.json", pack, "application/json")})
    assert r.status_code == 200 and r.json()["license_code"] == "C"


def test_learn_settings(client):
    assert client.get("/api/learn/settings").json() == {"daily_xp": 30, "sounds": True}
    assert client.put("/api/learn/settings", json={"daily_xp": 2, "sounds": True}).status_code == 422
    assert client.put("/api/learn/settings", json={"daily_xp": 50, "sounds": False}).json()["daily_xp"] == 50
    assert client.get("/api/learn/game").json()["goal"] == 50
    client.put("/api/learn/settings", json={"daily_xp": 30, "sounds": True})
