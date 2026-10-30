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
from .models import AppSetting, Checklist, ChecklistRun, Deadline, Dtc, Issue, MaintenanceTask, ObdLatestValue, Vehicle

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
        "vehicle_kind": "car",
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
        "vehicle_kind": "car",
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
        "vehicle_kind": "car",
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


_MOTO_TYRES = _items(
    ("Presión", "La del manual o la pegatina del basculante, en frío (delante y detrás son distintas)"),
    ("Desgaste", "≥ 1,6 mm en toda la banda; sin escalones ni zona central plana"),
    ("Flancos y fecha", "Sin cortes ni grietas; DOT de menos de ~5 años"),
)
_MOTO_CONTROLS = _items(
    ("Puño de gas", "Vuelve solo a ralentí al soltarlo, girando el manillar a tope a ambos lados"),
    ("Maneta de freno y pedal", "Firmes, sin tacto esponjoso; la moto no avanza al empujarla frenada"),
    ("Maneta de embrague", "Holgura correcta y sin tirones"),
    ("Dirección", "Gira libre, sin puntos duros ni holgura"),
)
_MOTO_LIGHTS = _items(
    ("Cruce y carretera", "Funcionan (el cruce va siempre encendido, también de día)"),
    ("Intermitentes", "Los cuatro, y se apagan bien"),
    ("Freno", "Se enciende con la maneta y con el pedal, por separado"),
    ("Claxon", "Suena"),
)
_MOTO_CHAIN = _items(
    ("Holgura de la cadena", "La del manual (suele ser 20–35 mm), medida a mitad del tramo inferior"),
    ("Engrase", "Engrasada, sin óxido ni eslabones agarrotados"),
    ("Piñón y corona", "Dientes sin forma de gancho ni puntas afiladas"),
)

DEFAULT_CHECKLISTS += [
    {
        "name": "Antes de salir (moto)",
        "vehicle_kind": "motorcycle",
        "interval_days": None,
        "sections": [
            {"title": "Neumáticos", "items": _MOTO_TYRES[:2]},
            {"title": "Mandos", "items": _MOTO_CONTROLS},
            {"title": "Luces", "items": _MOTO_LIGHTS},
            {"title": "Niveles", "items": _items(("Aceite", "En la mirilla o la varilla, moto recta"), ("Fugas", "Sin manchas debajo"))},
            {"title": "Chasis", "items": _items(("Cadena", "Ni floja ni tensa, engrasada"), ("Retrovisores", "Firmes y bien orientados"))},
            {"title": "Caballete", "items": _items(("Pata de cabra", "Recoge sola con el muelle; el corte de encendido funciona"))},
        ],
    },
    {
        "name": "Revisión mensual (moto)",
        "vehicle_kind": "motorcycle",
        "interval_days": 30,
        "sections": [
            {"title": "Neumáticos", "items": _MOTO_TYRES},
            {"title": "Transmisión", "items": _MOTO_CHAIN},
            {"title": "Frenos", "items": _items(
                ("Pastillas", "Con material por encima de la marca de desgaste"),
                ("Líquido", "Por encima de MIN en los dos depósitos, color claro"),
                ("Discos", "Sin surcos profundos ni alabeo"),
            )},
            {"title": "Mandos", "items": _MOTO_CONTROLS},
            {"title": "Suspensión", "items": _items(
                ("Horquilla", "Barras sin aceite ni picaduras (retenes sanos)"),
                ("Amortiguador", "Sin fugas; la moto no rebota al comprimirla"),
            )},
            {"title": "Eléctrico", "items": _MOTO_LIGHTS + _items(("Batería", "Bornes apretados; ≥ 12,6 V en reposo"))},
            {"title": "Tornillería", "items": _items(("Ejes, pinzas y estriberas", "Apretados, sin holgura"))},
        ],
    },
    {
        "name": "Antes de la ITV (moto)",
        "vehicle_kind": "motorcycle",
        "interval_days": None,
        "sections": [
            {"title": "Luces y señalización", "items": _MOTO_LIGHTS + _items(("Matrícula", "Legible, bien fijada y con su luz"))},
            {"title": "Seguridad", "items": _MOTO_TYRES[:2] + _items(
                ("Frenos", "Los dos frenan bien; ABS sin testigo encendido"),
                ("Retrovisores", "Los dos, homologados y sin roturas"),
                ("Dirección y horquilla", "Sin holguras ni fugas"),
            )},
            {"title": "Emisiones y ruido", "items": _items(
                ("Escape", "El original u homologado (con su placa); sin fugas"),
                ("Testigos del cuadro", "Ninguno encendido"),
            )},
            {"title": "Documentación", "items": _items(("Ficha técnica y permiso", "Originales o en miDGT"), ("Seguro", "En vigor"))},
        ],
    },
]

# Plantillas ya sembradas (por nombre): así las nuevas llegan a las instalaciones existentes
# y una que hayas borrado no vuelve a aparecer.
_SEEDED_KEY = "_checklist_templates_seeded"


def ensure_default_checklists(db: Session) -> None:
    row = db.get(AppSetting, _SEEDED_KEY)
    if row is not None and all(t["name"] in (row.value or []) for t in DEFAULT_CHECKLISTS):
        return
    if row is None:
        has_templates = db.query(Checklist).filter(Checklist.vehicle_id.is_(None)).first() is not None
        # Instalación de antes de este registro: las de coche ya se sembraron entonces.
        row = AppSetting(key=_SEEDED_KEY, value=[t["name"] for t in DEFAULT_CHECKLISTS if t["vehicle_kind"] == "car"] if has_templates else [])
        db.add(row)
    seeded = set(row.value or [])
    for pos, tpl in enumerate(DEFAULT_CHECKLISTS):
        if tpl["name"] not in seeded:
            db.add(Checklist(vehicle_id=None, position=pos, **tpl))
            seeded.add(tpl["name"])
    row.value = sorted(seeded)
    db.commit()


def checklists_for(db: Session, vehicle: Vehicle) -> list[Checklist]:
    ensure_default_checklists(db)
    return (
        db.query(Checklist)
        .filter((Checklist.vehicle_id.is_(None)) | (Checklist.vehicle_id == vehicle.id))
        .filter((Checklist.vehicle_kind.is_(None)) | (Checklist.vehicle_kind == vehicle.kind))
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
    return [t for t in services.default_plan(vehicle.fuel_type, vehicle.kind) if t["name"].lower() not in have]


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
