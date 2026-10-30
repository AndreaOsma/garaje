"""Teórico de cada permiso como curso de lecciones por pasos, con repaso espaciado y XP.

Mismo formato de curso que Campus Pilot, Bitácora e Insignia (`format: "campus-pilot-course"`):
un JSON con unidades → lecciones → pasos, así un pack se puede llevar de una app a otra. Aquí
`subject_code` es el código del permiso («A2», «C»…). Tipos de paso y su `data`:

- ``info``: tarjeta de lectura, sin respuesta.
- ``choice``: ``{"options": [..], "correct": [índices], "option_feedback"?: [..]}``. Si el
  enunciado lleva ``___``, se presenta como frase con hueco.
- ``truefalse``: ``{"answer": true|false}``.
- ``order``: ``{"items": [..]}`` en el orden correcto; la app los baraja.
- ``match``: ``{"pairs": [["izquierda", "derecha"], …]}`` (3 a 6 parejas).

(Los tipos numéricos y paramétricos de Insignia no hacen falta en un teórico de conducir.)
Opcionales: ``hints`` y ``concepts``. Todo paso evaluable lleva ``source`` (la norma o el tema
del que sale). Reimportar actualiza por ``ref`` sin perder el progreso.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from . import clock, models

COURSE_FORMAT = "campus-pilot-course"
MAX_COURSE_BYTES = 2 * 1024 * 1024
LEITNER_DAYS = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}
XP_FIRST_TRY = 10
XP_RETRY = 4
XP_LESSON = 10

Ref = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")]
StepKind = Literal["info", "choice", "truefalse", "order", "match"]


class StepIn(BaseModel):
    ref: Ref
    kind: StepKind
    prompt: str = Field(min_length=1, max_length=4000)
    data: dict[str, Any] = Field(default_factory=dict)
    explanation: str = Field(default="", max_length=6000)
    source: str = Field(default="", max_length=300)
    hints: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(default_factory=list, max_length=3)
    concepts: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _check(self):
        self.concepts = sorted({c.strip().lower() for c in self.concepts if c.strip()})
        d = self.data
        if self.kind != "info" and not self.source.strip():
            raise ValueError(f"Paso {self.ref}: falta «source» (de dónde sale)")
        if self.kind == "choice":
            opts, correct = d.get("options"), d.get("correct")
            if not isinstance(opts, list) or not 2 <= len(opts) <= 8 or not all(isinstance(o, str) and o for o in opts):
                raise ValueError(f"Paso {self.ref}: «options» necesita de 2 a 8 textos")
            if not isinstance(correct, list) or not correct or not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(opts) for i in correct):
                raise ValueError(f"Paso {self.ref}: «correct» debe listar índices válidos")
            fb = d.get("option_feedback")
            if fb is not None and (not isinstance(fb, list) or len(fb) != len(opts) or not all(isinstance(x, str) for x in fb)):
                raise ValueError(f"Paso {self.ref}: «option_feedback» necesita un texto por opción")
        elif self.kind == "truefalse":
            if not isinstance(d.get("answer"), bool):
                raise ValueError(f"Paso {self.ref}: «answer» debe ser true o false")
        elif self.kind == "order":
            items = d.get("items")
            if not isinstance(items, list) or not 2 <= len(items) <= 10 or not all(isinstance(i, str) and i for i in items):
                raise ValueError(f"Paso {self.ref}: «items» necesita de 2 a 10 textos")
            if len(set(items)) != len(items):
                raise ValueError(f"Paso {self.ref}: «items» no puede repetir textos")
        elif self.kind == "match":
            pairs = d.get("pairs")
            ok = isinstance(pairs, list) and 3 <= len(pairs) <= 6 and all(
                isinstance(x, list) and len(x) == 2 and all(isinstance(y, str) and y.strip() for y in x) for x in pairs
            )
            if not ok:
                raise ValueError(f"Paso {self.ref}: «pairs» necesita de 3 a 6 parejas [izquierda, derecha]")
            if len({x[0] for x in pairs}) != len(pairs) or len({x[1] for x in pairs}) != len(pairs):
                raise ValueError(f"Paso {self.ref}: las parejas no pueden repetir textos")
        return self


class LessonIn(BaseModel):
    ref: Ref
    title: str = Field(min_length=1, max_length=200)
    steps: list[StepIn] = Field(min_length=1, max_length=60)


class UnitIn(BaseModel):
    ref: Ref
    source: Optional[Ref] = None
    title: str = Field(min_length=1, max_length=200)
    # Unidad opcional: no cuenta en el progreso, no bloquea el camino y no entra en simulacros.
    extra: bool = False
    lessons: list[LessonIn] = Field(min_length=1, max_length=40)


class CourseIn(BaseModel):
    format: Literal["campus-pilot-course"]
    format_version: Literal[1]
    slug: Ref
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    source_note: str = Field(default="", max_length=2000)
    subject_code: str = Field(default="", max_length=32)
    subject_name: str = Field(default="", max_length=200)
    units: list[UnitIn] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def _unique(self):
        seen: set[str] = set()
        units_seen: set[tuple[str, str]] = set()
        for u in self.units:
            if (u.source or "", u.ref) in units_seen:
                raise ValueError(f"Unidad repetida: {u.ref}")
            units_seen.add((u.source or "", u.ref))
            for lesson in u.lessons:
                key = f"{u.source or ''}:{u.ref}/{lesson.ref}"
                if key in seen:
                    raise ValueError(f"Lección repetida: {key}")
                seen.add(key)
                refs = [s.ref for s in lesson.steps]
                if len(set(refs)) != len(refs):
                    raise ValueError(f"Lección {key}: pasos con el mismo ref")
        return self


def describe_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    where = ".".join(str(p) for p in first.get("loc", ()))
    msg = str(first.get("msg", "")).replace("Value error, ", "")
    return f"{where}: {msg}" if where else msg


def load_course(data: bytes) -> CourseIn:
    if len(data) > MAX_COURSE_BYTES:
        raise ValueError("El curso supera los 2 MB")
    try:
        raw = json.loads(data)
    except ValueError:
        raise ValueError("JSON no válido")
    if not isinstance(raw, dict):
        raise ValueError("El curso debe ser un objeto JSON")
    return CourseIn.model_validate(raw)


# ---------- Importar ----------

def course_for_license(db: Session, code: str, title: str = "") -> models.Course:
    """El curso del permiso; se crea vacío si aún no tiene."""
    course = db.query(models.Course).filter_by(license_code=code).first()
    if course is None:
        course = models.Course(slug=f"permiso-{code.lower()}", license_code=code, title=title or f"Teórico {code}", description="", source_note="")
        db.add(course)
        db.flush()
    return course


def import_course(db: Session, course_in: CourseIn, code: str, title: str = "") -> models.Course:
    """Suma las unidades del JSON al curso del permiso. Reimportar la misma fuente reemplaza
    solo sus unidades (por `source`); las de otras fuentes se quedan."""
    course = course_for_license(db, code, title)
    if title:
        course.title = title
    if course_in.description and not course.description:
        course.description = course_in.description
    if course_in.source_note and course_in.source_note not in course.source_note:
        course.source_note = "\n".join(x for x in (course.source_note, course_in.source_note) if x)[:2000]
    db.flush()

    def source_of(u_in: UnitIn) -> str:
        return u_in.source or course_in.slug

    sources = {source_of(u) for u in course_in.units}
    others = [u for u in course.units if u.source not in sources]
    first_slot = next((i for i, u in enumerate(course.units) if u.source in sources), len(others))
    first_slot = min(first_slot, len(others))
    units = {(u.source, u.ref): u for u in course.units if u.source in sources}
    keep_units = set()
    imported: list[models.CourseUnit] = []
    for u_in in course_in.units:
        unit = units.get((source_of(u_in), u_in.ref))
        if unit is None:
            unit = models.CourseUnit(course_id=course.id, ref=u_in.ref, source=source_of(u_in), title=u_in.title, chest_claimed=False)
            db.add(unit)
            db.flush()
        unit.title, unit.extra = u_in.title, u_in.extra
        imported.append(unit)
        keep_units.add(unit.id)

        lessons = {lesson.ref: lesson for lesson in unit.lessons}
        keep_lessons = set()
        for lpos, l_in in enumerate(u_in.lessons):
            lesson = lessons.get(l_in.ref)
            if lesson is None:
                lesson = models.Lesson(unit_id=unit.id, ref=l_in.ref, title=l_in.title, runs=0)
                db.add(lesson)
                db.flush()
            lesson.title, lesson.position = l_in.title, lpos
            keep_lessons.add(lesson.id)

            steps = {s.ref: s for s in lesson.steps}
            keep_steps = set()
            for spos, s_in in enumerate(l_in.steps):
                step = steps.get(s_in.ref)
                if step is None:
                    step = models.LessonStep(lesson_id=lesson.id, ref=s_in.ref, kind=s_in.kind, prompt=s_in.prompt, box=0, correct=0, wrong=0, confident_wrong=0)
                    db.add(step)
                    db.flush()
                step.position, step.kind, step.prompt = spos, s_in.kind, s_in.prompt
                step.data, step.explanation, step.source = s_in.data, s_in.explanation, s_in.source
                step.hints, step.concepts = s_in.hints, s_in.concepts
                keep_steps.add(step.id)
            for step in list(lesson.steps):
                if step.id not in keep_steps:
                    db.delete(step)
        for lesson in list(unit.lessons):
            if lesson.id not in keep_lessons:
                db.delete(lesson)
    for unit in list(course.units):
        if unit.source in sources and unit.id not in keep_units:
            db.delete(unit)
    for pos, unit in enumerate(others[:first_slot] + imported + others[first_slot:]):
        unit.position = pos
    db.commit()
    db.refresh(course)
    return course


def export_course(course: models.Course, license_name: str = "") -> dict:
    """El curso sin progreso."""
    return {
        "format": COURSE_FORMAT,
        "format_version": 1,
        "slug": course.slug,
        "title": course.title,
        "description": course.description,
        "source_note": course.source_note,
        "subject_code": course.license_code,
        "subject_name": license_name,
        "units": [
            {
                "ref": u.ref,
                "source": u.source or None,
                "title": u.title,
                "extra": bool(u.extra),
                "lessons": [
                    {
                        "ref": lesson.ref,
                        "title": lesson.title,
                        "steps": [
                            {
                                "ref": s.ref, "kind": s.kind, "prompt": s.prompt, "explanation": s.explanation,
                                "data": s.data or {}, "source": s.source, "hints": s.hints or [], "concepts": s.concepts or [],
                            }
                            for s in lesson.steps
                        ],
                    }
                    for lesson in u.lessons
                ],
            }
            for u in course.units
        ],
    }


# ---------- Jugar ----------

def _shuffled(items: list, rng: random.Random) -> list:
    out = items[:]
    for _ in range(10):
        rng.shuffle(out)
        if out != items or len(items) < 2:
            break
    return out


def public_step(step: models.LessonStep, rng: Optional[random.Random] = None) -> dict:
    """Lo que ve la app antes de responder: nunca la solución."""
    rng = rng or random.Random()
    out: dict[str, Any] = {
        "id": step.id,
        "kind": step.kind,
        "prompt": step.prompt,
        "source": step.source,
        "hints": step.hints or [],
        "concepts": step.concepts or [],
    }
    d = step.data or {}
    if step.kind == "choice":
        out["options"] = d.get("options", [])
        out["multiple"] = len(d.get("correct", [])) > 1
    elif step.kind == "order":
        out["items"] = _shuffled(list(d.get("items", [])), rng)
    elif step.kind == "match":
        pairs = d.get("pairs", [])
        out["left"] = [p[0] for p in pairs]
        out["right"] = _shuffled([p[1] for p in pairs], rng)
    elif step.kind == "info":
        out["explanation"] = step.explanation
    return out


def check(step: models.LessonStep, response: Any) -> tuple[bool, str]:
    """(¿correcta?, solución en texto)."""
    d = step.data or {}
    if step.kind == "info":
        return True, ""
    if step.kind == "choice":
        opts, correct = d.get("options", []), sorted(d.get("correct", []))
        chosen = sorted(set(response)) if isinstance(response, list) and all(isinstance(i, int) and not isinstance(i, bool) for i in response) else None
        return chosen == correct, " · ".join(opts[i] for i in correct)
    if step.kind == "truefalse":
        return response is d.get("answer"), "Verdadero" if d.get("answer") else "Falso"
    if step.kind == "order":
        items = d.get("items", [])
        return response == items, " → ".join(items)
    if step.kind == "match":
        pairs = d.get("pairs", [])
        ok = isinstance(response, list) and len(response) == len(pairs) and all(r == p[1] for r, p in zip(response, pairs))
        return ok, " · ".join(f"{a} ↔ {b}" for a, b in pairs)
    return False, ""


def option_feedback(step: models.LessonStep, response: Any) -> list[str]:
    """Por qué fallan las opciones elegidas que no eran correctas."""
    d = step.data or {}
    fb, correct = d.get("option_feedback"), set(d.get("correct", []))
    if step.kind != "choice" or not isinstance(fb, list) or not isinstance(response, list):
        return []
    return [fb[i] for i in response if isinstance(i, int) and 0 <= i < len(fb) and i not in correct and fb[i]]


def record_answer(
    db: Session, step: models.LessonStep, ok: bool, first_try: bool, today: Optional[date] = None,
    confident: Optional[bool] = None, used_hint: bool = False, combo: int = 0,
) -> int:
    """Actualiza el repaso espaciado del paso y suma XP. Devuelve la XP ganada.

    Fallar con confianza alta es lo más valioso de detectar: vuelve a repaso mañana y queda
    contado aparte para el dominio por concepto."""
    today = today or clock.today()
    if step.kind == "info":
        return 0
    if confident and not ok:
        step.confident_wrong += 1
    if ok:
        step.correct += 1
        if step.box:  # solo entra en repaso lo que alguna vez se falló
            step.box = min(5, step.box + 1)
            step.due_on = today + timedelta(days=LEITNER_DAYS[step.box])
    else:
        step.wrong += 1
        step.box = 1
        step.due_on = today + timedelta(days=LEITNER_DAYS[1])
    xp = (XP_FIRST_TRY if first_try and not used_hint else XP_RETRY) if ok else 0
    add_xp(db, xp, today=today)
    from . import game

    row = game.day(db, today)
    if ok:
        row.correct += 1
    row.best_combo = max(row.best_combo, combo)
    db.commit()
    return xp


def add_xp(db: Session, xp: int, lessons: int = 0, today: Optional[date] = None) -> None:
    if not xp and not lessons:
        return
    from . import game

    row = game.day(db, today)  # única forma de crear la fila del día (evita duplicados)
    row.xp += xp
    row.lessons += lessons


def streak(db: Session, today: Optional[date] = None) -> int:
    from . import game

    return game.streak(db, today)
