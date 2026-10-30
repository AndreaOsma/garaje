"""Repaso mixto del teórico: solo lo visto, con el carné y la lección de cada pregunta."""
from app import models
from app.database import SessionLocal


def test_mixed_only_seen_steps(client):
    a2 = next(x for x in client.get("/api/licenses").json() if x["code"] == "A2")
    course = client.get(f"/api/learn/courses/{a2['course']['id']}").json()
    first = course["units"][0]["lessons"][0]
    step = next(s for s in client.get(f"/api/learn/lessons/{first['id']}").json()["steps"] if s["kind"] != "info")
    client.post(f"/api/learn/steps/{step['id']}/answer", json={"response": [0]})

    with SessionLocal() as db:  # lo visto = lección terminada o pregunta ya respondida (otros tests comparten la base)
        seen = {
            s.id for s in db.query(models.LessonStep)
            if s.kind != "info" and s.lesson.unit.course_id == course["id"] and (s.lesson.completed_at or s.correct or s.wrong)
        }
    assert step["id"] in seen
    groups = client.get("/api/learn/mixed/groups").json()
    assert {"id": course["id"], "title": course["title"], "count": len(seen)} in groups
    steps = client.get("/api/learn/mixed", params={"courses": str(course["id"]), "n": 30}).json()["steps"]
    assert len(steps) == min(len(seen), 30) and {s["id"] for s in steps} <= seen
    assert all(s["course_title"] == course["title"] and s["lesson_title"] for s in steps)
