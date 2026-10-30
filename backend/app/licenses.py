"""Carnés: catálogo de permisos de conducir españoles y tu progreso hacia cada uno.

El catálogo resume el Reglamento General de Conductores (RD 818/2009) desde el punto de vista
de quien ya tiene el B: qué deja conducir cada permiso, la edad mínima, qué permiso previo
pide y por qué pasos hay que pasar. Es **orientativo**: la DGT cambia procedimientos (tasas,
formato de los exámenes, cursos) y lo que manda es su web. Cada permiso enlaza a ella.

Solo los permisos con `exam` tienen el formato del teórico confirmado (número de preguntas y
fallos admitidos); el resto usa un simulacro genérico hasta tener un pack de su teórico.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from . import clock, models
from .services import add_months

DGT_URL = "https://www.dgt.es/nuestros-servicios/permisos-de-conducir/"

STEPS: dict[str, str] = {
    "medico": "Certificado médico (centro de reconocimiento)",
    "autoescuela": "Matrícula en la autoescuela",
    "teorico": "Teórico específico aprobado",
    "pista": "Prueba de pista (circuito cerrado) aprobada",
    "circulacion": "Prueba en circulación aprobada",
    "curso": "Curso de formación completado",
    "cap": "CAP (si vas a conducir profesionalmente)",
    "expedido": "Permiso expedido",
}

STATUSES = ("none", "planning", "studying", "obtained")

# Simulacro por defecto de un permiso sin formato confirmado.
GENERIC_EXAM = {"questions": 20, "max_errors": 2, "minutes": 20, "official": False}

CATALOG: list[dict] = [
    {
        "code": "AM", "name": "Ciclomotores", "icon": "🛵", "group": "moto",
        "allows": "Ciclomotores de dos y tres ruedas (hasta 45 km/h y 50 cm³) y cuadriciclos ligeros.",
        "age": 15, "requires": [], "included_by": ["A1", "A2", "A", "B"],
        "steps": ["medico", "teorico", "pista", "circulacion", "expedido"],
        "notes": "Va incluido en el B: no tienes que sacártelo.",
    },
    {
        "code": "A1", "name": "Motos ligeras", "icon": "🏍️", "group": "moto",
        "allows": "Motos de hasta 125 cm³, 11 kW y 0,1 kW/kg, y triciclos de hasta 15 kW.",
        "age": 16, "requires": [], "included_by": ["A2", "A"],
        "steps": ["medico", "teorico", "pista", "circulacion", "expedido"],
        "notes": "Con más de 3 años de B ya puedes llevar motos de esta clase en España (no en el extranjero) sin sacarte el A1.",
        "b_years_shortcut": 3,
    },
    {
        "code": "A2", "name": "Motos de potencia media", "icon": "🏍️", "group": "moto",
        "allows": "Motos de hasta 35 kW y 0,2 kW/kg. Si está limitada, la moto original no puede pasar de 70 kW.",
        "age": 18, "requires": [], "included_by": ["A"],
        "steps": ["medico", "autoescuela", "teorico", "pista", "circulacion", "expedido"],
        "notes": "Con el B no repites el teórico común: solo el específico de moto, la prueba de pista y la de circulación.",
        "exam": {"questions": 20, "max_errors": 2, "minutes": 20, "official": True},
    },
    {
        "code": "A", "name": "Motos sin límite", "icon": "🏍️", "group": "moto",
        "allows": "Cualquier moto y triciclo de motor.",
        "age": 20, "requires": [{"code": "A2", "years": 2}], "included_by": [],
        "steps": ["curso", "expedido"],
        "notes": "Tras 2 años con el A2 se pasa al A con un curso práctico en autoescuela, sin examen.",
    },
    {
        "code": "B", "name": "Turismos", "icon": "🚗", "group": "coche",
        "allows": "Vehículos de hasta 3.500 kg y 9 plazas con el conductor; remolque de hasta 750 kg (o más si el conjunto no pasa de 3.500 kg).",
        "age": 18, "requires": [], "included_by": [],
        "steps": ["medico", "teorico", "pista", "circulacion", "expedido"], "notes": "",
    },
    {
        "code": "BE", "name": "Turismo con remolque pesado", "icon": "🚙", "group": "coche",
        "allows": "Un vehículo del B con un remolque de hasta 3.500 kg (caravanas, remolques de caballos o de barco).",
        "age": 18, "requires": [{"code": "B", "years": 0}], "included_by": ["CE", "C1E", "DE", "D1E"],
        "steps": ["medico", "autoescuela", "pista", "circulacion", "expedido"],
        "notes": "Pruebas prácticas con el conjunto. Confirma en la DGT si te piden alguna prueba teórica.",
    },
    {
        "code": "C1", "name": "Camiones medianos", "icon": "🚚", "group": "camion",
        "allows": "Camiones de entre 3.500 y 7.500 kg de masa máxima, con remolque de hasta 750 kg.",
        "age": 18, "requires": [{"code": "B", "years": 0}], "included_by": ["C"],
        "steps": ["medico", "autoescuela", "teorico", "pista", "circulacion", "cap", "expedido"], "notes": "",
    },
    {
        "code": "C", "name": "Camiones", "icon": "🚛", "group": "camion",
        "allows": "Camiones de más de 3.500 kg sin límite de masa, con remolque de hasta 750 kg.",
        "age": 21, "requires": [{"code": "B", "years": 0}], "included_by": [],
        "steps": ["medico", "autoescuela", "teorico", "pista", "circulacion", "cap", "expedido"],
        "notes": "Con el CAP se puede a partir de los 18.",
    },
    {
        "code": "C1E", "name": "Camión mediano con remolque", "icon": "🚚", "group": "camion",
        "allows": "Un C1 con remolque de más de 750 kg (conjunto de hasta 12.000 kg).",
        "age": 18, "requires": [{"code": "C1", "years": 0}], "included_by": ["CE"],
        "steps": ["medico", "autoescuela", "teorico", "pista", "circulacion", "expedido"], "notes": "",
    },
    {
        "code": "CE", "name": "Camión con remolque (tráiler)", "icon": "🚛", "group": "camion",
        "allows": "Un camión del C con remolque o semirremolque de más de 750 kg.",
        "age": 21, "requires": [{"code": "C", "years": 0}], "included_by": [],
        "steps": ["medico", "autoescuela", "teorico", "pista", "circulacion", "expedido"], "notes": "",
    },
    {
        "code": "D1", "name": "Minibuses", "icon": "🚐", "group": "autobus",
        "allows": "Autobuses de hasta 16 pasajeros más el conductor y 8 m de longitud.",
        "age": 21, "requires": [{"code": "B", "years": 0}], "included_by": ["D"],
        "steps": ["medico", "autoescuela", "teorico", "pista", "circulacion", "cap", "expedido"], "notes": "",
    },
    {
        "code": "D", "name": "Autobuses", "icon": "🚌", "group": "autobus",
        "allows": "Autobuses de más de 8 plazas además del conductor, sin límite.",
        "age": 24, "requires": [{"code": "B", "years": 0}], "included_by": [],
        "steps": ["medico", "autoescuela", "teorico", "pista", "circulacion", "cap", "expedido"],
        "notes": "Con el CAP se puede a partir de los 21.",
    },
]

BY_CODE = {e["code"]: e for e in CATALOG}


def progress(db: Session, code: str) -> models.LicenseProgress:
    row = db.get(models.LicenseProgress, code)
    if row is None:
        row = models.LicenseProgress(code=code, status="none", steps={}, notes="")
        db.add(row)
        db.flush()
    return row


def _held_since(rows: dict[str, models.LicenseProgress], code: str) -> tuple[bool, Optional[date]]:
    row = rows.get(code)
    if row is None or row.status != "obtained":
        return False, None
    return True, row.obtained_on


def requirements(rows: dict[str, models.LicenseProgress], entry: dict, today: Optional[date] = None) -> list[dict]:
    """Cada requisito de permiso previo con su estado: ok | wait (te falta antigüedad) | missing."""
    today = today or clock.today()
    out = []
    for req in entry["requires"]:
        held, since = _held_since(rows, req["code"])
        years = req.get("years", 0)
        label = f"Tener el {req['code']}" + (f" desde hace {years} años" if years else "")
        if not held:
            out.append({"label": label, "state": "missing", "until": None})
        elif years and since is None:
            out.append({"label": label, "state": "unknown", "until": None})
        elif years and add_months(since, 12 * years) > today:
            out.append({"label": label, "state": "wait", "until": add_months(since, 12 * years).isoformat()})
        else:
            out.append({"label": label, "state": "ok", "until": None})
    return out


def covered_by(rows: dict[str, models.LicenseProgress], entry: dict, today: Optional[date] = None) -> Optional[str]:
    """Si un permiso que ya tienes cubre este, qué texto mostrarlo (p. ej. AM con el B)."""
    today = today or clock.today()
    for code in entry.get("included_by", []):
        if _held_since(rows, code)[0]:
            return f"Incluido en tu {code}"
    years = entry.get("b_years_shortcut")
    held, since = _held_since(rows, "B")
    if years and held and since and add_months(since, 12 * years) <= today:
        return f"Con más de {years} años de B ya puedes llevarlas en España"
    return None


def summary(db: Session, entry: dict, rows: dict[str, models.LicenseProgress], course: Optional[models.Course]) -> dict:
    row = rows.get(entry["code"])
    lessons = [lesson for u in course.units if not u.extra for lesson in u.lessons] if course else []
    exam = entry.get("exam") or GENERIC_EXAM
    return {
        **{k: v for k, v in entry.items() if k not in ("exam", "b_years_shortcut")},
        "steps": [{"key": k, "label": STEPS[k], "done_on": ((row.steps or {}).get(k) if row else None)} for k in entry["steps"]],
        "status": row.status if row else "none",
        "next_exam_on": row.next_exam_on.isoformat() if row and row.next_exam_on else None,
        "obtained_on": row.obtained_on.isoformat() if row and row.obtained_on else None,
        "user_notes": row.notes if row else "",
        "requirements": requirements(rows, entry),
        "covered_by": covered_by(rows, entry),
        "exam": exam,
        "course": {
            "id": course.id,
            "lessons_total": len(lessons),
            "lessons_done": sum(1 for lesson in lessons if lesson.completed_at),
        } if course else None,
        "dgt_url": DGT_URL,
    }


def all_summaries(db: Session) -> list[dict]:
    rows = {r.code: r for r in db.query(models.LicenseProgress)}
    courses = {c.license_code: c for c in db.query(models.Course)}
    return [summary(db, e, rows, courses.get(e["code"])) for e in CATALOG]


def exam_format(code: str) -> dict:
    entry = BY_CODE.get(code)
    return (entry or {}).get("exam") or GENERIC_EXAM
