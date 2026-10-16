"""Gemelo digital: estado de cada pieza del coche para el modelo 3D de Inicio.

Cada pieza junta lo que Garaje sabe de ella: averías OBD (por rango de código),
incidencias (por sistema), tareas del plan (por categoría y nombre) y lecturas (batería,
temperaturas). El estado de la pieza es lo peor de todo eso.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from . import config, dtc_dictionary, services
from .models import Dtc, Issue, MaintenanceTask, ObdLatestValue, Vehicle

# id, nombre, combustibles en los que existe (None = todos)
COMPONENTS: list[tuple[str, str, Optional[set[str]]]] = [
    ("engine", "Motor", {"gasoline", "diesel", "hybrid", "phev", "lpg"}),
    ("injection", "Inyección y combustible", {"gasoline", "diesel", "hybrid", "phev", "lpg"}),
    ("turbo", "Turbo", {"diesel"}),
    ("egr", "Válvula EGR", {"diesel"}),
    ("intake", "Admisión y filtro de aire", {"gasoline", "diesel", "hybrid", "phev", "lpg"}),
    ("cooling", "Refrigeración (radiador)", None),
    ("exhaust", "Escape y anticontaminación", {"gasoline", "diesel", "hybrid", "phev", "lpg"}),
    ("fuel_tank", "Depósito de combustible", {"gasoline", "diesel", "hybrid", "phev", "lpg"}),
    ("gearbox", "Caja de cambios", None),
    ("battery", "Batería 12 V", None),
    ("hv_battery", "Batería de tracción", {"electric", "hybrid", "phev"}),
    ("emotor", "Motor eléctrico", {"electric", "hybrid", "phev"}),
    ("ecu", "Centralitas y red CAN", None),
    ("brakes", "Frenos y ABS", None),
    ("tyres", "Neumáticos", None),
    ("suspension", "Suspensión y dirección", None),
    ("cabin", "Habitáculo y climatización", None),
    ("body", "Carrocería, luces y lunas", None),
]

_LEVEL_RANK = {"ok": 0, "info": 1, "warn": 2, "danger": 3}

# Rangos de códigos P genéricos → pieza (el primero que encaje manda: lo específico, antes).
_P_RANGES: list[tuple[int, int, str]] = [
    (0x0010, 0x0026, "engine"),       # distribución variable
    (0x0045, 0x0049, "turbo"),
    (0x0087, 0x0095, "injection"),
    (0x0100, 0x0114, "intake"),       # MAF, MAP, temperatura de admisión
    (0x0115, 0x0119, "cooling"),
    (0x0120, 0x0124, "intake"),       # mariposa
    (0x0125, 0x0129, "cooling"),      # termostato
    (0x0130, 0x0167, "exhaust"),      # sondas lambda
    (0x0170, 0x0199, "injection"),    # mezcla, presión del rail
    (0x0200, 0x0233, "injection"),    # inyectores
    (0x0234, 0x0249, "turbo"),
    (0x0299, 0x0299, "turbo"),        # antes que el rango amplio de inyección
    (0x0250, 0x0298, "injection"),
    (0x0300, 0x0399, "engine"),       # encendido / calentadores
    (0x0400, 0x0409, "egr"),
    (0x0410, 0x0419, "exhaust"),
    (0x0420, 0x0439, "exhaust"),      # catalizador
    (0x0440, 0x0469, "fuel_tank"),    # EVAP
    (0x0470, 0x0479, "exhaust"),
    (0x0480, 0x0487, "cooling"),      # ventiladores
    (0x0488, 0x0490, "egr"),
    (0x0500, 0x0503, "brakes"),       # sensor de velocidad (ABS comparte)
    (0x0520, 0x0524, "engine"),       # presión de aceite
    (0x0560, 0x0563, "battery"),
    (0x0670, 0x0684, "engine"),       # calentadores (antes que el rango de centralita)
    (0x0600, 0x0699, "ecu"),
    (0x0700, 0x09FF, "gearbox"),
    (0x0A00, 0x0CFF, "hv_battery"),
    (0x2000, 0x2003, "exhaust"),      # DPF
    (0x2096, 0x2097, "exhaust"),
    (0x2135, 0x2135, "intake"),
    (0x2187, 0x2188, "injection"),
    (0x2263, 0x2263, "turbo"),
    (0x2279, 0x2279, "intake"),
    (0x242F, 0x242F, "exhaust"),
    (0x2452, 0x2463, "exhaust"),
    (0x2BAD, 0x2BAD, "exhaust"),
]

_ISSUE_CATEGORY = {
    "aceite": "engine", "encendido": "engine", "distribución": "engine", "refrigeración": "cooling",
    "eléctrico": "battery", "frenos": "brakes", "neumáticos": "tyres", "suspensión": "suspension",
    "transmisión": "gearbox", "climatización": "cabin", "carrocería": "body", "filtros": "intake",
}

_TASK_KEYWORDS: list[tuple[str, str]] = [
    ("filtro de aire", "intake"), ("filtro de combustible", "injection"), ("glp", "injection"),
    ("habitáculo", "cabin"), ("batería", "battery"), ("bujía", "engine"), ("distribución", "engine"),
    ("aceite", "engine"), ("frenos", "brakes"), ("pastillas", "brakes"), ("neumático", "tyres"),
    ("escobillas", "body"), ("refrigerante", "cooling"),
]


def dtc_component(code: str) -> Optional[str]:
    letter = code[:1]
    if letter == "U":
        return "ecu"
    if letter == "B":
        return "cabin"
    if letter == "C":
        return "brakes" if code[1] == "0" else None  # C0xxx: ABS/ESP; C1xxx+: fabricante
    if letter == "P" and code[1] in "02":
        n = int(code[1:], 16)
        for lo, hi, comp in _P_RANGES:
            if lo <= n <= hi:
                return comp
        return "engine" if code[1] == "0" else None
    return None


def task_component(task: MaintenanceTask) -> Optional[str]:
    name = task.name.lower()
    for word, comp in _TASK_KEYWORDS:
        if word in name:
            return comp
    return _ISSUE_CATEGORY.get(task.category)


def build_twin(db: Session, vehicle: Vehicle, today: Optional[date] = None) -> dict:
    today = today or date.today()
    present = [(cid, name) for cid, name, fuels in COMPONENTS if fuels is None or vehicle.fuel_type in fuels]
    ids = {cid for cid, _ in present}
    items: dict[str, list[dict]] = {cid: [] for cid in ids}
    unassigned: list[dict] = []

    def add(comp: Optional[str], item: dict) -> None:
        if comp == "hv_battery" and "hv_battery" not in ids:
            comp = "battery"
        (items[comp] if comp in ids else unassigned).append(item)

    for dtc in db.query(Dtc).filter(Dtc.vehicle_id == vehicle.id, Dtc.cleared_at.is_(None)):
        info = dtc_dictionary.describe(db, dtc.code, vehicle.make)
        level = "danger" if info["severity"] == "alta" and dtc.kind != "pending" else "warn" if dtc.kind != "pending" else "info"
        kind = {"pending": "pendiente", "permanent": "permanente"}.get(dtc.kind, "confirmada")
        add(dtc_component(dtc.code), {
            "kind": "dtc", "level": level, "target": "diagnostics",
            "text": f"{dtc.code} ({kind}): {info['description']}",
        })

    for issue in db.query(Issue).filter(Issue.vehicle_id == vehicle.id, Issue.resolved_on.is_(None)):
        level = {"grounding": "danger", "limiting": "warn"}.get(issue.severity, "info")
        comp = dtc_component(issue.dtc_code) if issue.dtc_code else None
        add(comp or _ISSUE_CATEGORY.get(issue.category), {"kind": "issue", "level": level, "target": "maintenance", "text": issue.title})

    for task in db.query(MaintenanceTask).filter_by(vehicle_id=vehicle.id, active=True):
        st = services.task_status(task, vehicle.odometer_km, today)
        if st["status"] in ("overdue", "soon"):
            when = []
            if st["remaining_km"] is not None:
                when.append(f"{abs(st['remaining_km']):,} km".replace(",", ".") + (" de retraso" if st["remaining_km"] < 0 else " restantes"))
            if st["remaining_days"] is not None:
                when.append(f"{abs(st['remaining_days'])} días" + (" de retraso" if st["remaining_days"] < 0 else " restantes"))
            add(task_component(task), {
                "kind": "task", "level": "warn" if st["status"] == "overdue" else "info", "target": "maintenance",
                "text": f"{'Vencido' if st['status'] == 'overdue' else 'Pronto'}: {task.name}" + (f" ({', '.join(when)})" if when else ""),
            })

    latest = {lv.key: lv for lv in db.query(ObdLatestValue).filter_by(vehicle_id=vehicle.id)}
    batt, rpm = latest.get("BATT") or latest.get("42"), latest.get("0C")
    if batt is not None:
        running = rpm is not None and rpm.value > 300 and abs((rpm.ts - batt.ts).total_seconds()) < 120
        if running and batt.value < 13.2:
            add("battery", {"kind": "reading", "level": "warn", "target": "diagnostics", "text": f"Carga baja en marcha: {batt.value:.1f} V (alternador)"})
        elif not running and batt.value < config.LOW_BATTERY_VOLTS:
            add("battery", {"kind": "reading", "level": "warn", "target": "diagnostics", "text": f"Batería baja: {batt.value:.1f} V en reposo"})
        else:
            add("battery", {"kind": "reading", "level": "ok", "target": "diagnostics", "text": f"Última tensión: {batt.value:.1f} V"})
    coolant = latest.get("05")
    if coolant is not None:
        hot = coolant.value >= 110
        add("cooling", {"kind": "reading", "level": "danger" if hot else "ok", "target": "diagnostics",
                        "text": f"Refrigerante a {coolant.value:.0f} °C" + (" (sobrecalentamiento)" if hot else "")})
    if vehicle.mil_on:
        add("ecu", {"kind": "reading", "level": "warn", "target": "diagnostics", "text": "Testigo de avería (MIL) encendido"})

    def status(entries: list[dict]) -> str:
        return max((e["level"] for e in entries), key=_LEVEL_RANK.__getitem__, default="ok")

    for entries in items.values():
        entries.sort(key=lambda e: -_LEVEL_RANK[e["level"]])
    return {
        "fuel_type": vehicle.fuel_type,
        "components": [{"id": cid, "name": name, "status": status(items[cid]), "items": items[cid]} for cid, name in present],
        "unassigned": unassigned,
    }


# ---------------------------------------------------------------------------
# Motor por dentro: estado de cada subpieza del motor (y de cada cilindro).
# ---------------------------------------------------------------------------

# Rangos de códigos → subpieza del motor (lo específico primero). "cylN" se resuelve aparte.
_ENGINE_RANGES: list[tuple[int, int, str]] = [
    (0x0010, 0x0015, "camshaft"),     # distribución variable
    (0x0016, 0x0019, "timing"),       # correlación cigüeñal/levas
    (0x0045, 0x0049, "turbo"),
    (0x0087, 0x0095, "fuel_rail"),
    (0x0100, 0x0114, "intake"),
    (0x0115, 0x0119, "cooling"),
    (0x0120, 0x0124, "intake"),
    (0x0125, 0x0129, "cooling"),
    (0x0130, 0x0167, "exhaust"),
    (0x0170, 0x0175, "injectors"),
    (0x0190, 0x0193, "fuel_rail"),
    (0x0201, 0x0212, "injectors"),
    (0x0234, 0x0238, "turbo"),
    (0x0251, 0x0251, "fuel_rail"),
    (0x0299, 0x0299, "turbo"),
    (0x0300, 0x0312, "ignition"),     # fallos de encendido (P030N → cilindro N)
    (0x0325, 0x0334, "block"),        # sensor de picado
    (0x0335, 0x0349, "sensors"),      # posición de cigüeñal / levas
    (0x0351, 0x0362, "ignition"),     # bobinas
    (0x0380, 0x0384, "glow"),
    (0x0400, 0x0409, "egr"),
    (0x0420, 0x0439, "exhaust"),
    (0x0471, 0x0473, "exhaust"),
    (0x0480, 0x0485, "cooling"),
    (0x0488, 0x0490, "egr"),
    (0x0520, 0x0524, "oil"),
    (0x0560, 0x0563, "alternator"),
    (0x0627, 0x0627, "fuel_rail"),
    (0x0670, 0x0684, "glow"),
    (0x2000, 0x2003, "dpf"),
    (0x2135, 0x2135, "intake"),
    (0x2187, 0x2188, "injectors"),
    (0x2263, 0x2263, "turbo"),
    (0x2279, 0x2279, "intake"),
    (0x242F, 0x242F, "dpf"),
    (0x2452, 0x2463, "dpf"),
]

_ENGINE_TASK_KEYWORDS: list[tuple[str, str]] = [
    ("aceite", "oil"), ("bujía", "ignition"), ("distribución", "timing"), ("filtro de aire", "intake"),
    ("filtro de combustible", "fuel_rail"), ("refrigerante", "cooling"), ("glp", "fuel_rail"),
]
_ENGINE_ISSUE_CATEGORY = {"aceite": "oil", "encendido": "ignition", "distribución": "timing", "refrigeración": "cooling"}


def engine_part_for_code(code: str) -> tuple[Optional[str], Optional[int]]:
    """Código → (subpieza, cilindro). P0302 → ("ignition", 2); P0203 → ("injectors", 3)."""
    if code[:1] != "P" or code[1] not in "02":
        return None, None
    n = int(code[1:], 16)
    part = next((p for lo, hi, p in _ENGINE_RANGES if lo <= n <= hi), None)
    cyl = None
    if 0x0301 <= n <= 0x0306:
        cyl = n - 0x0300
    elif 0x0201 <= n <= 0x0206:
        cyl = n - 0x0200
    elif 0x0351 <= n <= 0x0356:
        cyl = n - 0x0350
    elif 0x0671 <= n <= 0x0676:
        cyl = n - 0x0670
    return part, cyl


def build_engine_twin(db: Session, vehicle: Vehicle, today: Optional[date] = None) -> dict:
    today = today or date.today()
    parts: dict[str, list[dict]] = {}

    def add(key: Optional[str], item: dict) -> None:
        if key:
            parts.setdefault(key, []).append(item)

    diesel = vehicle.fuel_type == "diesel"
    for dtc in db.query(Dtc).filter(Dtc.vehicle_id == vehicle.id, Dtc.cleared_at.is_(None)):
        info = dtc_dictionary.describe(db, dtc.code, vehicle.make)
        level = "danger" if info["severity"] == "alta" and dtc.kind != "pending" else "warn" if dtc.kind != "pending" else "info"
        part, cyl = engine_part_for_code(dtc.code)
        if diesel and part == "ignition":
            # Un diésel no tiene bujías: un fallo de combustión apunta a la inyección.
            part = "injectors"
        item = {"kind": "dtc", "level": level, "text": f"{dtc.code}: {info['description']}", "target": "diagnostics"}
        add(part, item)
        if cyl:
            add(f"cyl{cyl}", item)
    for issue in db.query(Issue).filter(Issue.vehicle_id == vehicle.id, Issue.resolved_on.is_(None)):
        part = engine_part_for_code(issue.dtc_code)[0] if issue.dtc_code else _ENGINE_ISSUE_CATEGORY.get(issue.category)
        add(part, {"kind": "issue", "level": {"grounding": "danger", "limiting": "warn"}.get(issue.severity, "info"),
                   "text": issue.title, "target": "maintenance"})
    for task in db.query(MaintenanceTask).filter_by(vehicle_id=vehicle.id, active=True):
        st = services.task_status(task, vehicle.odometer_km, today)
        name = task.name.lower()
        part = next((p for w, p in _ENGINE_TASK_KEYWORDS if w in name), None)
        if part and st["status"] in ("overdue", "soon"):
            add(part, {"kind": "task", "level": "warn" if st["status"] == "overdue" else "info",
                       "text": f"{'Vencido' if st['status'] == 'overdue' else 'Pronto'}: {task.name}", "target": "maintenance"})

    kind = "inline-diesel" if vehicle.fuel_type == "diesel" else "inline-gasoline"
    out = {}
    for key, entries in parts.items():
        entries.sort(key=lambda e: -_LEVEL_RANK[e["level"]])
        out[key] = {"status": entries[0]["level"], "items": entries}
    return {"kind": kind, "cylinders": vehicle.cylinders or 4, "parts": out}
