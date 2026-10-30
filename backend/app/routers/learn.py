"""Teórico de los carnés: lecciones paso a paso, corrección en el servidor, repaso, simulacro y XP."""
from __future__ import annotations

import random
from datetime import date, datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from .. import clock, game, learn, licenses, models
from ..database import get_db
from ..learn_game import mixed as lg_mixed

router = APIRouter(prefix="/api/learn", tags=["learn"])

SETTINGS_KEY = "learn_settings"


class LearnSettings(BaseModel):
    daily_xp: int = Field(default=30, ge=5, le=1000)
    sounds: bool = True


class AnswerIn(BaseModel):
    response: Any = None
    first_try: bool = True
    confidence: Optional[Literal["high", "low"]] = None
    used_hint: bool = False
    # Aciertos seguidos que lleva quien estudia (para la misión de racha de aciertos).
    combo: int = Field(default=0, ge=0, le=1000)


class CompleteIn(BaseModel):
    correct: int = Field(ge=0, le=1000)
    total: int = Field(ge=0, le=1000)
    seconds: int = Field(default=0, ge=0, le=24 * 3600)


class ExamDoneIn(BaseModel):
    course_id: int
    correct: int = Field(ge=0, le=1000)
    total: int = Field(ge=1, le=1000)


def load_settings(db: Session) -> LearnSettings:
    row = db.get(models.AppSetting, SETTINGS_KEY)
    try:
        return LearnSettings.model_validate(row.value if row and isinstance(row.value, dict) else {})
    except ValidationError:
        return LearnSettings()


def _goal(db: Session) -> int:
    return load_settings(db).daily_xp


def _get(db: Session, model, item_id: int, what: str):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{what} no encontrado")
    return item


def _lesson_summary(lesson: models.Lesson, locked: bool) -> dict:
    return {
        "id": lesson.id,
        "title": lesson.title,
        "steps": len([s for s in lesson.steps if s.kind != "info"]),
        "done": lesson.completed_at is not None,
        "best_ratio": lesson.best_ratio,
        # Nivel = veces completada, hasta 5.
        "level": min(5, lesson.runs),
        "locked": locked,
    }


def _course_out(course: models.Course) -> dict:
    # Las unidades extra no cuentan en el progreso ni marcan el orden del camino.
    lessons = [lesson for u in course.units if not u.extra for lesson in u.lessons]
    next_lesson = next((lesson for lesson in lessons if not lesson.completed_at), None)
    # Camino lineal: abierta la primera sin hacer y todo lo anterior; lo demás, con candado.
    first_pending = next((i for i, lesson in enumerate(lessons) if not lesson.completed_at), len(lessons))
    index = {lesson.id: i for i, lesson in enumerate(lessons)}
    entry = licenses.BY_CODE.get(course.license_code, {})
    return {
        "id": course.id,
        "slug": course.slug,
        "title": course.title,
        "description": course.description,
        "source_note": course.source_note,
        "license_code": course.license_code,
        "license_name": entry.get("name", ""),
        "exam": licenses.exam_format(course.license_code),
        "lessons_total": len(lessons),
        "lessons_done": sum(1 for lesson in lessons if lesson.completed_at),
        "next_lesson_id": next_lesson.id if next_lesson else None,
        "units": [
            {
                "id": u.id,
                "title": u.title,
                "extra": bool(u.extra),
                "done": bool(u.lessons) and all(lesson.completed_at for lesson in u.lessons),
                "chest_claimed": u.chest_claimed,
                "lessons": [_lesson_summary(lesson, not u.extra and index[lesson.id] > first_pending) for lesson in u.lessons],
            }
            for u in course.units
        ],
    }


@router.get("/settings", response_model=LearnSettings)
def get_settings(db: Session = Depends(get_db)):
    return load_settings(db)


@router.put("/settings", response_model=LearnSettings)
def put_settings(payload: LearnSettings, db: Session = Depends(get_db)):
    row = db.get(models.AppSetting, SETTINGS_KEY)
    if row is None:
        db.add(models.AppSetting(key=SETTINGS_KEY, value=payload.model_dump()))
    else:
        row.value = payload.model_dump()
    db.commit()
    return payload


@router.get("/courses/{course_id}")
def get_course(course_id: int, db: Session = Depends(get_db)):
    return _course_out(_get(db, models.Course, course_id, "Curso"))


@router.get("/courses/{course_id}/export")
def export_course(course_id: int, db: Session = Depends(get_db)):
    course = _get(db, models.Course, course_id, "Curso")
    name = licenses.BY_CODE.get(course.license_code, {}).get("name", "")
    return JSONResponse(learn.export_course(course, name), headers={"Content-Disposition": f'attachment; filename="{course.slug}.json"'})


@router.post("/import/{code}")
async def import_course(code: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    entry = licenses.BY_CODE.get(code)
    if entry is None:
        raise HTTPException(status_code=404, detail="Permiso no encontrado")
    data = await file.read(learn.MAX_COURSE_BYTES + 1)
    try:
        course_in = learn.load_course(data)
        if course_in.subject_code and course_in.subject_code != code:
            raise ValueError(f"Este pack es del permiso {course_in.subject_code}, no del {code}")
        course = learn.import_course(db, course_in, code)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Curso no válido — {learn.describe_error(exc)}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _course_out(course)


@router.get("/lessons/{lesson_id}")
def get_lesson(lesson_id: int, db: Session = Depends(get_db)):
    lesson = _get(db, models.Lesson, lesson_id, "Lección")
    course = lesson.unit.course
    # «Siguiente lección» se queda dentro de su tramo: el camino principal no salta a los extras.
    ordered = [x for u in course.units if u.extra == lesson.unit.extra for x in u.lessons]
    idx = ordered.index(lesson)
    rng = random.Random()
    return {
        "id": lesson.id,
        "title": lesson.title,
        "unit_title": lesson.unit.title,
        "course_id": course.id,
        "license_code": course.license_code,
        "done": lesson.completed_at is not None,
        "next_lesson_id": ordered[idx + 1].id if idx + 1 < len(ordered) else None,
        "steps": [learn.public_step(s, rng) for s in lesson.steps],
    }


@router.post("/steps/{step_id}/answer")
def answer(step_id: int, payload: AnswerIn, db: Session = Depends(get_db)):
    step = _get(db, models.LessonStep, step_id, "Paso")
    ok, solution = learn.check(step, payload.response)
    xp = learn.record_answer(
        db, step, ok, payload.first_try, confident=payload.confidence == "high" if payload.confidence else None,
        used_hint=payload.used_hint, combo=payload.combo,
    )
    return {
        "correct": ok,
        "solution": solution,
        "explanation": step.explanation,
        "source": step.source,
        "xp": xp,
        "option_feedback": [] if ok else learn.option_feedback(step, payload.response),
        "confident_wrong": bool(payload.confidence == "high" and not ok),
    }


@router.post("/lessons/{lesson_id}/complete")
def complete(lesson_id: int, payload: CompleteIn, db: Session = Depends(get_db)):
    lesson = _get(db, models.Lesson, lesson_id, "Lección")
    ratio = payload.correct / payload.total if payload.total else 1.0
    first_time = lesson.completed_at is None
    perfect = payload.total > 0 and payload.correct >= payload.total
    lesson.completed_at = lesson.completed_at or datetime.now(timezone.utc).replace(tzinfo=None)
    lesson.best_ratio = max(lesson.best_ratio or 0, min(1.0, ratio))
    lesson.runs += 1
    bonus = (learn.XP_LESSON if first_time else learn.XP_LESSON // 2) + (game.PERFECT_BONUS_XP if perfect else 0)
    learn.add_xp(db, bonus, lessons=1)
    if perfect:
        game.day(db).perfect_lessons += 1
    db.commit()
    unit = lesson.unit
    unit_done = all(x.completed_at for x in unit.lessons)
    return {
        "xp": bonus,
        "perfect": perfect,
        "ratio": ratio,
        "level": min(5, lesson.runs),
        "streak": learn.streak(db),
        "unit_done": unit_done,
        "unit_id": unit.id,
        "chest_available": unit_done and not unit.chest_claimed,
        "game": game.state(db, _goal(db)),
    }


@router.post("/exams/complete")
def complete_exam(payload: ExamDoneIn, db: Session = Depends(get_db)):
    course = _get(db, models.Course, payload.course_id, "Curso")
    if payload.correct > payload.total:
        raise HTTPException(status_code=422, detail="Más aciertos que preguntas")
    res = game.exam_done(db, payload.correct, payload.total, licenses.exam_format(course.license_code)["max_errors"])
    out = {**res, "game": game.state(db, _goal(db))}
    db.commit()
    return out


@router.get("/game")
def game_state(db: Session = Depends(get_db)):
    out = game.state(db, _goal(db))
    db.commit()
    return out


@router.post("/quests/{quest_id}/claim")
def claim_quest(quest_id: str, db: Session = Depends(get_db)):
    try:
        gems = game.claim_quest(db, quest_id, _goal(db))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return {"gems": gems, "game": game.state(db, _goal(db))}


@router.post("/units/{unit_id}/chest")
def open_chest(unit_id: int, db: Session = Depends(get_db)):
    unit = _get(db, models.CourseUnit, unit_id, "Unidad")
    try:
        gems = game.open_chest(db, unit)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return {"gems": gems, "game": game.state(db, _goal(db))}


@router.post("/shop/{item}")
def shop(item: str, db: Session = Depends(get_db)):
    try:
        game.buy(db, item)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return game.state(db, _goal(db))


@router.get("/review")
def review(limit: int = 15, db: Session = Depends(get_db)):
    """Pasos fallados cuyo repaso toca hoy (o antes), mezclados."""
    today = clock.today()
    steps = (
        db.query(models.LessonStep)
        .filter(models.LessonStep.box > 0, models.LessonStep.due_on <= today)
        .order_by(models.LessonStep.box, models.LessonStep.due_on)
        .limit(max(1, min(limit, 50)))
        .all()
    )
    rng = random.Random()
    rng.shuffle(steps)
    return {"steps": [learn.public_step(s, rng) | {"lesson_title": s.lesson.title} for s in steps]}


def _mixed_pool(db: Session) -> list[tuple[models.Course, list[models.LessonStep]]]:
    """Por curso, las preguntas ya vistas: de lecciones terminadas o que ya se respondieron alguna vez."""
    return [
        (course, [
            s for u in course.units for lesson in u.lessons for s in lesson.steps
            if s.kind != "info" and (lesson.completed_at or s.correct or s.wrong)
        ])
        for course in db.query(models.Course).order_by(models.Course.id)
    ]


@router.get("/mixed/groups")
def mixed_groups(db: Session = Depends(get_db)):
    """Cursos que pueden entrar en el repaso mixto, con cuántas preguntas vistas tiene cada uno."""
    return [{"id": c.id, "title": c.title, "count": len(steps)} for c, steps in _mixed_pool(db) if steps]


@router.get("/mixed")
def mixed(courses: str = "", n: int = lg_mixed.DEFAULT_N, db: Session = Depends(get_db)):
    """Repaso mixto: preguntas al azar de cursos al azar, solo de lo ya visto (`courses`: ids separados por comas; vacío = todos)."""
    wanted = {int(x) for x in courses.split(",") if x.strip().isdigit()}
    today = clock.today()
    found: dict[int, tuple[models.LessonStep, str]] = {}
    candidates = []
    for course, steps in _mixed_pool(db):
        if wanted and course.id not in wanted:
            continue
        for s in steps:
            found[s.id] = (s, course.title)
            due = bool(s.box and s.due_on and s.due_on <= today)
            candidates.append(lg_mixed.Candidate(s.id, course.id, s.correct, s.wrong, s.confident_wrong, due))
    rng = random.Random()
    out = []
    for c in lg_mixed.pick(candidates, n, rng):
        step, title = found[c.id]
        out.append(learn.public_step(step, rng) | {"lesson_title": step.lesson.title, "course_title": title})
    return {"title": "Repaso mixto", "steps": out}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    today = clock.today()
    row = db.get(models.LearnDay, today)
    due = db.query(models.LessonStep).filter(models.LessonStep.box > 0, models.LessonStep.due_on <= today).count()
    return {
        "today_xp": row.xp if row else 0,
        "goal": _goal(db),
        "streak": learn.streak(db, today),
        "review_due": due,
        "total_xp": sum(d.xp for d in db.query(models.LearnDay)),
        "week": {d.date.isoformat(): d.xp for d in db.query(models.LearnDay).filter(models.LearnDay.date > date.fromordinal(today.toordinal() - 7))},
    }


# ---------- Dominio por concepto, práctica dirigida y simulacro ----------

def _course_steps(course: models.Course, include_extra: bool = False) -> list[models.LessonStep]:
    """Pasos evaluables del curso. Sin `include_extra`, fuera las unidades extra (simulacro y
    práctica deben parecerse al examen real)."""
    return [s for u in course.units if include_extra or not u.extra for lesson in u.lessons for s in lesson.steps if s.kind != "info"]


@router.get("/courses/{course_id}/concepts")
def concepts(course_id: int, db: Session = Depends(get_db)):
    """Dominio por concepto: aciertos / intentos, con los fallos con confianza aparte."""
    course = _get(db, models.Course, course_id, "Curso")
    agg: dict[str, dict] = {}
    for s in _course_steps(course, include_extra=True):
        for c in s.concepts or []:
            row = agg.setdefault(c, {"concept": c, "steps": 0, "correct": 0, "wrong": 0, "confident_wrong": 0})
            row["steps"] += 1
            row["correct"] += s.correct
            row["wrong"] += s.wrong
            row["confident_wrong"] += s.confident_wrong
    out = []
    for row in agg.values():
        tries = row["correct"] + row["wrong"]
        row["mastery"] = round(row["correct"] / tries, 3) if tries else None
        out.append(row)
    # Lo más flojo primero; lo no practicado al final.
    return sorted(out, key=lambda r: (r["mastery"] is None, r["mastery"] if r["mastery"] is not None else 2, r["concept"]))


@router.get("/courses/{course_id}/practice")
def practice(course_id: int, concept: str = "", limit: int = 10, db: Session = Depends(get_db)):
    """Pasos de un concepto (o de los más flojos), mezclados de todas las lecciones."""
    course = _get(db, models.Course, course_id, "Curso")
    steps = _course_steps(course)
    if concept:
        steps = [s for s in steps if concept.lower() in (s.concepts or [])]
    else:
        steps.sort(key=lambda s: (s.correct - 2 * s.wrong - 3 * s.confident_wrong))
        steps = steps[: max(limit * 2, 10)]
    rng = random.Random()
    rng.shuffle(steps)
    return {
        "title": f"Práctica: {concept}" if concept else "Práctica de lo más flojo",
        "steps": [learn.public_step(s, rng) | {"lesson_title": s.lesson.title} for s in steps[: max(1, min(limit, 30))]],
    }


@router.get("/courses/{course_id}/exam")
def exam(course_id: int, db: Session = Depends(get_db)):
    """Simulacro con el formato del examen del permiso (preguntas, fallos admitidos y tiempo)."""
    course = _get(db, models.Course, course_id, "Curso")
    fmt = licenses.exam_format(course.license_code)
    steps = _course_steps(course)
    rng = random.Random()
    rng.shuffle(steps)
    return {
        "title": f"Simulacro · {course.title}",
        "minutes": fmt["minutes"],
        "max_errors": fmt["max_errors"],
        "steps": [learn.public_step(s, rng) | {"lesson_title": s.lesson.title, "unit_title": s.lesson.unit.title} for s in steps[: fmt["questions"]]],
    }
