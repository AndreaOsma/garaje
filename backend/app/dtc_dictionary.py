"""Descripción de un código de avería combinando el diccionario propio (BD) con el base.

Prioridad: definición de la marca del vehículo → definición sin marca → diccionario
base (SAE, en código) → descripción genérica deducida de la estructura del código.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .models import DtcDefinition
from .obd.dtc import describe_dtc
from .services import utcnow


def norm_make(make: Optional[str]) -> str:
    return (make or "").strip().lower()


def lookup(db: Session, code: str, make: Optional[str] = None) -> Optional[DtcDefinition]:
    rows = db.query(DtcDefinition).filter(DtcDefinition.code == code.upper()).all()
    m = norm_make(make)
    return next((r for r in rows if m and r.make == m), None) or next((r for r in rows if not r.make), None)


def describe(db: Session, code: str, make: Optional[str] = None) -> dict:
    info = describe_dtc(code)
    row = lookup(db, code, make)
    if row is not None:
        info = {
            **info,
            "description": row.description,
            "severity": row.severity or info["severity"],
            "learned": row.source,
            "definition_make": row.make,
            "details": row.details,
        }
    return info


def learn(db: Session, code: str, description: str, make: Optional[str]) -> bool:
    """Guarda lo que trae un informe importado. Nunca pisa lo escrito a mano; si el código
    es específico del fabricante, se asocia a la marca del vehículo."""
    description = " ".join(description.split())[:300]
    if len(description) < 6:
        return False
    generic = describe_dtc(code)["generic"]
    make_key = "" if generic else norm_make(make)
    row = db.query(DtcDefinition).filter_by(code=code.upper(), make=make_key).first()
    if row is None:
        db.add(DtcDefinition(code=code.upper(), make=make_key, description=description, source="import"))
        return True
    if row.source == "import" and row.description != description:
        row.description, row.updated_at = description, utcnow()
        return True
    return False


# --- Búsqueda automática -------------------------------------------------------

ATTEMPTS_KEY = "dtc_research_attempts"


def needs_research(db: Session, code: str, make: Optional[str], claude_available: bool) -> bool:
    from .obd.dtc import DTC_DICTIONARY

    info = describe_dtc(code)
    row = lookup(db, code, make)
    if row is not None:
        # Lo escrito a mano o aprendido de un informe manda; lo de Ollama se mejora con Claude.
        return row.source == "ia" and claude_available
    return not info["generic"] or code.upper() not in DTC_DICTIONARY


def research_and_store(db: Session, code: str, vehicle, force: bool = False) -> Optional[DtcDefinition]:
    """Investiga un código para la marca/modelo del vehículo y lo guarda en el diccionario."""
    from . import dtc_research
    from .models import AppSetting

    code = code.upper()
    claude = "claude" in dtc_research.configured_providers()
    if not dtc_research.configured_providers() or (not force and not needs_research(db, code, vehicle.make, claude)):
        return None
    generic = describe_dtc(code)["generic"]
    make_key = "" if generic else norm_make(vehicle.make)
    attempt_key = f"{code}|{make_key}"
    setting = db.get(AppSetting, ATTEMPTS_KEY)
    attempts = dict(setting.value or {}) if setting else {}
    if not force and not dtc_research.should_retry(attempts.get(attempt_key)):
        return None

    result = dtc_research.research(
        code, vehicle.make or "", vehicle.model or "", vehicle.year, vehicle.engine or "", vehicle.fuel_type or "",
    )
    attempts[attempt_key] = utcnow().isoformat()
    if setting is None:
        db.add(AppSetting(key=ATTEMPTS_KEY, value=attempts))
    else:
        setting.value = attempts
    if result is None or not result.found:
        # Si al repetir la búsqueda ya no se sostiene, se retira lo orientativo anterior.
        stale = db.query(DtcDefinition).filter_by(code=code, make=make_key, source="ia").first()
        if force and stale is not None:
            db.delete(stale)
        db.commit()
        return None

    row = db.query(DtcDefinition).filter_by(code=code, make=make_key).first()
    if row is not None and row.source in ("manual", "import"):
        db.commit()
        return row
    if row is None:
        row = DtcDefinition(code=code, make=make_key)
        db.add(row)
    if result.provider != "claude":
        # Sin búsqueda web no hay respaldo: siempre «orientativo».
        result.confidence, result.sources = "baja", []
    row.description = result.description
    row.severity = result.severity
    row.source = "web" if result.provider == "claude" else "ia"
    row.details = result.details()
    row.updated_at = utcnow()
    db.commit()
    return row


def research_missing(vehicle_id: int) -> int:
    """Tarea en segundo plano: investiga los códigos activos del vehículo que no se entienden."""
    from .database import SessionLocal
    from .models import Dtc, Vehicle

    db = SessionLocal()
    try:
        vehicle = db.get(Vehicle, vehicle_id)
        if vehicle is None:
            return 0
        codes = {d.code for d in db.query(Dtc).filter(Dtc.vehicle_id == vehicle_id, Dtc.cleared_at.is_(None))}
        return sum(1 for code in sorted(codes) if research_and_store(db, code, vehicle) is not None)
    finally:
        db.close()
