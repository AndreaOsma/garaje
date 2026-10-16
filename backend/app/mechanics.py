"""Mecánica: semáforo «¿listo para circular?», incidencias y revisiones con checklist.

Calcado del concepto de dev/apps/bitacora (mecánica de la aeronave: incidencias con
gravedad + mantenimiento vencido → apto / con limitaciones / no apto), adaptado al
coche: aquí también cuentan la ITV y el seguro (circular sin ellos es ilegal), el
testigo MIL, las averías OBD graves y la batería.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from . import config, dtc_dictionary, services
from .models import Checklist, ChecklistRun, Deadline, Dtc, Issue, MaintenanceTask, ObdLatestValue, Vehicle

SEVERITIES = ("info", "limiting", "grounding")

# --- Checklists por defecto ---------------------------------------------------

def _items(*pairs: tuple[str, str]) -> list[dict]:
    return [{"label": label, "check": check} for label, check in pairs]


_LIGHTS = _items(
    ("Cruce y carretera", "Encienden las dos"),
    ("Intermitentes y emergencia", "Los cuatro + laterales"),
    ("Freno y marcha atrás", "Con ayuda o reflejo en una pared"),
    ("Antiniebla y matrícula", "Funcionan"),
)
_TYRES = _items(
    ("Presión", "La de la etiqueta del marco de la puerta, en frío"),
    ("Desgaste", "≥ 1,6 mm (mejor ≥ 3 mm), sin desgaste irregular"),
    ("Flancos", "Sin cortes, grietas ni bultos"),
    ("Repuesto o kit antipinchazos", "Inflado / sin caducar"),
)
_LEVELS = _items(
    ("Aceite del motor", "Entre MIN y MAX, en llano y en frío"),
    ("Refrigerante", "Entre MIN y MAX en el vaso de expansión, en frío"),
    ("Líquido de frenos", "Por encima de MIN"),
    ("Lavaparabrisas", "Lleno"),
)

DEFAULT_CHECKLISTS: list[dict] = [
    {
        "name": "Revisión rápida mensual",
        "interval_days": 30,
        "sections": [
            {"title": "Niveles", "items": _LEVELS},
            {"title": "Neumáticos", "items": _TYRES},
            {"title": "Luces", "items": _LIGHTS},
            {"title": "Visibilidad", "items": _items(
                ("Escobillas", "Barren sin dejar marcas"),
                ("Lunas", "Sin impactos en el campo de visión"),
            )},
            {"title": "Bajos", "items": _items(("Fugas", "Sin manchas en el suelo donde aparcas"))},
        ],
    },
    {
        "name": "Antes de un viaje largo",
        "interval_days": None,
        "sections": [
            {"title": "Niveles", "items": _LEVELS},
            {"title": "Neumáticos", "items": _TYRES + _items(("Presión con carga", "Sube a la presión de carga completa si vas cargado"))},
            {"title": "Luces", "items": _LIGHTS},
            {"title": "Documentación", "items": _items(
                ("Permiso de circulación y ficha técnica", "En el coche o en miDGT"),
                ("Seguro e ITV", "En vigor durante todo el viaje"),
            )},
            {"title": "Equipamiento", "items": _items(
                ("Baliza V16 conectada", "Obligatoria desde 2026; con batería"),
                ("Chaleco reflectante", "Al alcance desde el asiento"),
                ("Equipaje", "Sujeto; lo pesado abajo y adelante"),
            )},
            {"title": "Batería", "items": _items(("Bornes", "Apretados y sin sulfato"))},
        ],
    },
    {
        "name": "Antes de la ITV",
        "interval_days": None,
        "sections": [
            {"title": "Luces y señalización", "items": _LIGHTS + _items(("Claxon", "Suena"), ("Matrículas", "Legibles y bien fijadas"))},
            {"title": "Visibilidad", "items": _items(
                ("Lunas", "Sin impactos ni láminas no homologadas"),
                ("Limpia y lavaparabrisas", "Funcionan y barren bien"),
                ("Retrovisores", "Completos y sin roturas"),
            )},
            {"title": "Seguridad", "items": _items(
                ("Cinturones", "Anclan y se recogen solos"),
                ("Freno de mano", "Sujeta el coche en pendiente"),
                ("Neumáticos", "≥ 1,6 mm, mismas medidas por eje"),
            )},
            {"title": "Motor y emisiones", "items": _items(
                ("Testigos del cuadro", "Ninguno encendido (MIL apagado)"),
                ("Monitores OBD", "Completos (míralo en Diagnóstico)"),
                ("Fugas", "Sin pérdidas de aceite ni refrigerante"),
            )},
            {"title": "Documentación", "items": _items(("Ficha técnica y permiso", "Originales o en miDGT"), ("Seguro", "En vigor"))},
        ],
    },
]


def ensure_default_checklists(db: Session) -> None:
    if db.query(Checklist).filter(Checklist.vehicle_id.is_(None)).first():
        return
    for pos, tpl in enumerate(DEFAULT_CHECKLISTS):
        db.add(Checklist(vehicle_id=None, position=pos, **tpl))
    db.commit()


def checklists_for(db: Session, vehicle: Vehicle) -> list[Checklist]:
    ensure_default_checklists(db)
    return (
        db.query(Checklist)
        .filter((Checklist.vehicle_id.is_(None)) | (Checklist.vehicle_id == vehicle.id))
        .order_by(Checklist.vehicle_id.isnot(None), Checklist.position, Checklist.id)
        .all()
    )


def last_runs(db: Session, vehicle: Vehicle) -> dict[int, ChecklistRun]:
    out: dict[int, ChecklistRun] = {}
    for run in db.query(ChecklistRun).filter_by(vehicle_id=vehicle.id).order_by(ChecklistRun.date, ChecklistRun.id):
        if run.checklist_id is not None:
            out[run.checklist_id] = run
    return out


def missing_suggestions(vehicle: Vehicle) -> list[dict]:
    have = {t.name.strip().lower() for t in vehicle.tasks}
    return [t for t in services.default_plan(vehicle.fuel_type) if t["name"].lower() not in have]


# --- Semáforo -----------------------------------------------------------------

def readiness(db: Session, vehicle: Vehicle, today: Optional[date] = None) -> dict:
    """{status: go | caution | nogo, reasons: [{level, text, target}]} — lo peor manda."""
    today = today or date.today()
    reasons: list[dict] = []

    def add(level: str, text: str, target: str) -> None:
        reasons.append({"level": level, "text": text, "target": target})

    for issue in db.query(Issue).filter(Issue.vehicle_id == vehicle.id, Issue.resolved_on.is_(None)):
        if issue.severity == "grounding":
            add("nogo", f"No circular: {issue.title}", "maintenance")
        elif issue.severity == "limiting":
            add("caution", f"Precaución: {issue.title}", "maintenance")

    for deadline in db.query(Deadline).filter_by(vehicle_id=vehicle.id, done=False):
        status, days = services.deadline_status(deadline.due_date, deadline.done, today)
        if status == "overdue" and deadline.kind in ("itv", "seguro"):
            add("nogo", f"{deadline.title} caducado: circular es ilegal", "documents")
        elif status == "overdue":
            add("caution", f"{deadline.title} caducado", "documents")

    for task in db.query(MaintenanceTask).filter_by(vehicle_id=vehicle.id, active=True):
        if services.task_status(task, vehicle.odometer_km, today)["status"] == "overdue":
            add("caution", f"Mantenimiento vencido: {task.name}", "maintenance")

    if vehicle.mil_on:
        add("caution", "Testigo de avería (MIL) encendido", "diagnostics")
    for dtc in db.query(Dtc).filter(Dtc.vehicle_id == vehicle.id, Dtc.cleared_at.is_(None), Dtc.kind != "pending"):
        info = dtc_dictionary.describe(db, dtc.code, vehicle.make)
        if info["severity"] == "alta":
            add("caution", f"Avería grave {dtc.code}: {info['description']}", "diagnostics")

    batt = db.query(ObdLatestValue).filter_by(vehicle_id=vehicle.id, key="BATT").first()
    rpm = db.query(ObdLatestValue).filter_by(vehicle_id=vehicle.id, key="0C").first()
    running = rpm is not None and rpm.value > 300 and batt is not None and abs((rpm.ts - batt.ts).total_seconds()) < 120
    if batt is not None and not running and batt.value < config.LOW_BATTERY_VOLTS:
        add("caution", f"Batería baja ({batt.value:.1f} V): puede no arrancar", "diagnostics")

    status = "nogo" if any(r["level"] == "nogo" for r in reasons) else "caution" if reasons else "go"
    reasons.sort(key=lambda r: r["level"] != "nogo")
    return {"status": status, "reasons": reasons}


def create_issues_from_run(db: Session, vehicle: Vehicle, run: ChecklistRun, results: list[dict]) -> int:
    created = 0
    for item in results:
        if item.get("ok") is False and item.get("create_issue", True):
            note = (item.get("note") or "").strip()
            db.add(Issue(
                vehicle_id=vehicle.id,
                reported_on=run.date,
                odometer_km=run.odometer_km,
                title=f"{item['label']} ({item.get('section', '')})".replace(" ()", "")[:160],
                description=(f"Revisión «{run.checklist_name}»: esperado «{item.get('check', '')}»." + (f" {note}" if note else "")),
                severity=item.get("severity") if item.get("severity") in SEVERITIES else "info",
                category="otros",
            ))
            created += 1
    return created
