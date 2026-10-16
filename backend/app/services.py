"""Lógica de dominio sin HTTP: plan de mantenimiento, estados, consumo e ingesta OBD.

Todas las fechas-hora se guardan como UTC *naive* (SQLite no conserva la zona);
los esquemas de salida les añaden la "Z" al serializar.
"""
from __future__ import annotations

import calendar
import hashlib
import secrets
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import insert
from sqlalchemy.orm import Session

from . import config
from .models import (
    Dtc,
    FuelEntry,
    MaintenanceTask,
    ObdLatestValue,
    ObdSample,
    ObdSensor,
    ObdSession,
    Vehicle,
)

CATEGORIES = (
    "aceite", "filtros", "frenos", "neumáticos", "distribución", "encendido", "refrigeración",
    "eléctrico", "suspensión", "transmisión", "climatización", "carrocería", "otros",
)
EXPENSE_CATEGORIES = ("seguro", "impuesto", "itv", "parking", "peaje", "lavado", "multa", "financiación", "otros")
DEADLINE_KINDS = ("itv", "seguro", "impuesto", "garantía", "carnet", "revisión", "otro")
FUEL_TYPES = ("gasoline", "diesel", "hybrid", "phev", "electric", "lpg")
DTC_KINDS = ("stored", "pending", "permanent")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


# ---------------------------------------------------------------------------
# Plan de mantenimiento por defecto
# ---------------------------------------------------------------------------

def default_plan(fuel_type: str) -> list[dict]:
    """Intervalos orientativos y conservadores; el manual de cada coche manda (editables)."""
    combustion = fuel_type != "electric"
    spark = fuel_type in ("gasoline", "hybrid", "phev", "lpg")
    plan = [
        ("Revisión de pastillas y discos", "frenos", 20000, 12, ""),
        ("Cambio de líquido de frenos", "frenos", None, 24, "Es higroscópico: se cambia por tiempo, no por km."),
        ("Revisión y rotación de neumáticos", "neumáticos", 10000, 12, "Profundidad mínima legal: 1,6 mm."),
        ("Filtro de habitáculo", "filtros", 15000, 12, ""),
        ("Revisión de batería 12 V", "eléctrico", None, 12, "Con el motor parado debería marcar ≥ 12,4 V."),
        ("Escobillas limpiaparabrisas", "carrocería", None, 12, ""),
        ("Refrigerante", "refrigeración", None, 60, ""),
    ]
    if combustion:
        plan += [
            ("Aceite y filtro de aceite", "aceite", 15000, 12, "Ajusta al intervalo de tu manual (long-life: hasta 30.000 km)."),
            ("Filtro de aire", "filtros", 30000, 24, ""),
            ("Filtro de combustible", "filtros", 30000 if fuel_type == "diesel" else 60000, 24 if fuel_type == "diesel" else 48, ""),
            ("Kit de distribución", "distribución", 120000, 96, "Si tu motor lleva cadena, desactiva esta tarea."),
        ]
    if spark:
        plan.append(("Bujías", "encendido", 60000, 48, ""))
    if fuel_type == "lpg":
        plan.append(("Filtros de GLP", "filtros", 20000, 12, ""))
    return [
        {"name": n, "category": c, "interval_km": km, "interval_months": m, "notes": notes}
        for n, c, km, m, notes in plan
    ]


# ---------------------------------------------------------------------------
# Estados calculados
# ---------------------------------------------------------------------------

def task_status(task: MaintenanceTask, odometer_km: int, today: Optional[date] = None) -> dict:
    today = today or date.today()
    next_km = task.last_done_km + task.interval_km if task.interval_km and task.last_done_km is not None else None
    next_date = (
        add_months(task.last_done_date, task.interval_months)
        if task.interval_months and task.last_done_date
        else None
    )
    remaining_km = next_km - odometer_km if next_km is not None else None
    remaining_days = (next_date - today).days if next_date else None
    if not task.active:
        status = "inactive"
    elif remaining_km is None and remaining_days is None:
        status = "unknown"
    elif (remaining_km is not None and remaining_km < 0) or (remaining_days is not None and remaining_days < 0):
        status = "overdue"
    elif (remaining_km is not None and remaining_km <= config.SOON_KM) or (
        remaining_days is not None and remaining_days <= config.SOON_DAYS
    ):
        status = "soon"
    else:
        status = "ok"
    return {
        "next_due_km": next_km,
        "next_due_date": next_date,
        "remaining_km": remaining_km,
        "remaining_days": remaining_days,
        "status": status,
    }


def deadline_status(due: date, done: bool, today: Optional[date] = None) -> tuple[str, int]:
    days = (due - (today or date.today())).days
    if done:
        return "done", days
    if days < 0:
        return "overdue", days
    return ("soon" if days <= config.SOON_DAYS else "ok"), days


def fuel_stats(entries: Iterable[FuelEntry]) -> tuple[dict[int, float], Optional[float]]:
    """Consumo por el método lleno-a-lleno → ({entry_id: L/100km}, media global)."""
    ordered = sorted(entries, key=lambda e: (e.odometer_km, e.date, e.id))
    per_entry: dict[int, float] = {}
    total_qty = total_km = 0.0
    last_full_km: Optional[int] = None
    acc = 0.0
    for entry in ordered:
        if last_full_km is None:
            if entry.full_tank:
                last_full_km = entry.odometer_km
            continue
        acc += entry.quantity
        if entry.full_tank:
            km = entry.odometer_km - last_full_km
            if km > 0:
                per_entry[entry.id] = round(acc / km * 100, 2)
                total_qty += acc
                total_km += km
            last_full_km, acc = entry.odometer_km, 0.0
    avg = round(total_qty / total_km * 100, 2) if total_km else None
    return per_entry, avg


def bump_odometer(vehicle: Vehicle, km: Optional[float]) -> None:
    if km is not None and km > (vehicle.odometer_km or 0):
        vehicle.odometer_km = int(km)
        vehicle.odometer_updated_at = utcnow()


# ---------------------------------------------------------------------------
# Token de ingesta
# ---------------------------------------------------------------------------

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_ingest_token(vehicle: Vehicle) -> str:
    token = "grj_" + secrets.token_urlsafe(32)
    vehicle.ingest_token_hash = hash_token(token)
    return token


def vehicle_for_token(db: Session, token: str) -> Optional[Vehicle]:
    if not token or len(token) > 128:
        return None
    return db.query(Vehicle).filter(Vehicle.ingest_token_hash == hash_token(token)).first()


# ---------------------------------------------------------------------------
# Ingesta OBD (agente y Car Scanner)
# ---------------------------------------------------------------------------

def ingest(
    db: Session,
    vehicle: Vehicle,
    *,
    source: str,
    external_id: str,
    samples: list[tuple[datetime, str, float]],
    label: str = "",
    sensors: Optional[dict[str, tuple[str, str]]] = None,
    dtcs: Optional[dict[str, list[str]]] = None,
    monitor: Optional[dict] = None,
    vin: Optional[str] = None,
) -> Optional[ObdSession]:
    now = utcnow()
    samples = [(to_utc_naive(ts), key, value) for ts, key, value in samples]
    session = None
    if samples:
        start, end = min(s[0] for s in samples), max(s[0] for s in samples)
        session = (
            db.query(ObdSession)
            .filter_by(vehicle_id=vehicle.id, source=source, external_id=external_id)
            .first()
        )
        if session is None:
            session = ObdSession(
                vehicle_id=vehicle.id, source=source, external_id=external_id,
                label=label, started_at=start, ended_at=end, sample_count=0,
            )
            db.add(session)
            db.flush()
        session.started_at = min(session.started_at, start)
        session.ended_at = max(session.ended_at, end)
        session.sample_count += len(samples)
        db.execute(
            insert(ObdSample),
            [{"session_id": session.id, "ts": ts, "key": key, "value": value} for ts, key, value in samples],
        )

        latest: dict[str, tuple[datetime, float]] = {}
        for ts, key, value in samples:
            if key not in latest or ts >= latest[key][0]:
                latest[key] = (ts, value)
        existing = {lv.key: lv for lv in db.query(ObdLatestValue).filter_by(vehicle_id=vehicle.id)}
        for key, (ts, value) in latest.items():
            row = existing.get(key)
            if row is None:
                db.add(ObdLatestValue(vehicle_id=vehicle.id, key=key, value=value, ts=ts))
            elif ts >= row.ts:
                row.value, row.ts = value, ts
        if "A6" in latest:
            bump_odometer(vehicle, max(v for _, k, v in samples if k == "A6"))
        vehicle.last_obd_at = max(vehicle.last_obd_at or end, end)

    for key, (name, unit) in (sensors or {}).items():
        sensor = db.get(ObdSensor, key)
        if sensor is None:
            db.add(ObdSensor(key=key, name=name, unit=unit))
        else:
            sensor.name, sensor.unit = name, unit or sensor.unit

    if dtcs is not None:
        reconcile_dtcs(db, vehicle, dtcs, source, now)
    if monitor:
        vehicle.mil_on = bool(monitor.get("mil_on"))
        vehicle.ecu_dtc_count = int(monitor.get("dtc_count") or 0)
        vehicle.monitors = monitor
        vehicle.last_obd_at = max(vehicle.last_obd_at or now, now)
    if vin and not vehicle.vin:
        vehicle.vin = vin[:17]
    db.commit()
    return session


def reconcile_dtcs(db: Session, vehicle: Vehicle, dtcs: dict[str, list[str]], source: str, now: datetime) -> None:
    """Los códigos leídos abren/actualizan su fila activa; los activos que la ECU ya no
    reporta se marcan como borrados (solo los de origen OBD: los manuales los gestiona el usuario)."""
    active = defaultdict(dict)
    for row in db.query(Dtc).filter(Dtc.vehicle_id == vehicle.id, Dtc.cleared_at.is_(None)):
        active[row.kind][row.code] = row
    for kind, codes in dtcs.items():
        if kind not in DTC_KINDS:
            continue
        current = set(codes)
        for code in current:
            row = active[kind].get(code)
            if row:
                row.last_seen = now
                row.occurrences += 1
            else:
                db.add(Dtc(vehicle_id=vehicle.id, code=code, kind=kind, source=source, first_seen=now, last_seen=now))
        for code, row in active[kind].items():
            if code not in current and row.source != "manual":
                row.cleared_at = now
