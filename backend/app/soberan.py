"""Enlace con Soberan (finanzas personales).

Soberan es quien inicia la sincronización (nunca al revés): lee aquí qué vehículo va
con qué coche de su patrimonio y qué categorías de gasto interesan, y nos envía su
valoración de mercado, la deuda de la financiación y los movimientos de esas
categorías. Así Garaje no necesita ninguna credencial de Soberan, que daría acceso a
todas las finanzas.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import AppSetting, InboxItem, Vehicle
from .services import to_utc_naive

SNAPSHOT_KEY = "soberan_snapshot"
CATEGORIES_KEY = "soberan_categories"
LAST_SYNC_KEY = "soberan_last_sync"

# Ventana de movimientos que se piden a Soberan en cada sincronización.
IMPORT_WINDOW_DAYS = 120


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9&]+", " ", text)).strip()


def _any(desc: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", desc) for w in words)


_FUEL = (
    "repsol", "cepsa", "moeve", "bp", "galp", "shell", "plenoil", "ballenoil", "petronor", "esso",
    "avia", "petroprix", "bonarea", "gasolinera", "estacion de servicio", "carburante",
    "combustible", "gasoleo", "tesla supercharger", "ionity", "zunder", "iberdrola recarga", "wenea",
)
_SERVICE = (
    "taller", "norauto", "feu vert", "midas", "speedy", "euromaster", "confortauto", "point s",
    "carglass", "aurgi", "neumaticos", "recambios", "chapa", "mecanica", "concesionario",
)
_EXPENSE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("seguro", ("seguro", "seguros", "mapfre", "mutua", "allianz", "axa", "linea directa", "generali", "reale", "zurich", "verti", "genesis")),
    ("itv", ("itv", "applus", "sgs", "tuv", "veiasa", "itevelesa")),
    ("parking", ("parking", "aparcamiento", "empark", "telpark", "saba", "easypark", "elparking", "ora")),
    ("peaje", ("peaje", "autopista", "abertis", "via t", "viat", "bip&drive", "bip drive")),
    ("impuesto", ("ivtm", "impuesto vehiculo", "impuesto circulacion", "tributos")),
    ("multa", ("multa", "sancion")),
    ("lavado", ("lavado", "lavadero", "elefante azul", "car wash")),
)


def classify(description: str) -> tuple[str, str]:
    """Descripción bancaria → (tipo sugerido, categoría de gasto sugerida)."""
    desc = _norm(description)
    # Seguro e ITV primero: son los más específicos (una póliza "AXA … REPSOL" es seguro).
    for category, words in _EXPENSE_RULES[:2]:
        if _any(desc, words):
            return "expense", category
    if _any(desc, _FUEL):
        return "fuel", "combustible"
    if _any(desc, _SERVICE):
        return "service", "otros"
    for category, words in _EXPENSE_RULES[2:]:
        if _any(desc, words):
            return "expense", category
    return "expense", "otros"


def get_setting(db: Session, key: str, default=None):
    row = db.get(AppSetting, key)
    return row.value if row and row.value is not None else default


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


def linked_vehicles(db: Session) -> list[Vehicle]:
    return db.query(Vehicle).filter(Vehicle.soberan_property_id.isnot(None)).all()


def default_vehicle_id(db: Session) -> Optional[int]:
    """Si solo hay un vehículo enlazado (y activo), los movimientos son suyos sin preguntar."""
    active = [v for v in linked_vehicles(db) if not v.archived]
    return active[0].id if len(active) == 1 else None


def config_for_soberan(db: Session) -> dict:
    return {
        "links": [
            {
                "garaje_vehicle_id": v.id,
                "property_id": v.soberan_property_id,
                "debt_id": v.soberan_debt_id,
                "odometer_km": v.odometer_km,
                "odometer_updated_at": v.odometer_updated_at.isoformat() + "Z" if v.odometer_updated_at else None,
                "vin": v.vin or None,
                "plate": v.plate or None,
            }
            for v in linked_vehicles(db)
        ],
        "categories": get_setting(db, CATEGORIES_KEY, []),
        "since": (date.today() - timedelta(days=IMPORT_WINDOW_DAYS)).isoformat(),
    }


def apply_sync(db: Session, payload, now) -> dict:
    """Guarda la instantánea, actualiza valor/deuda de los vehículos enlazados y mete los
    movimientos nuevos en la bandeja. Idempotente: un movimiento ya visto no se toca."""
    props = {p.id: p for p in payload.properties}
    debts = {d.id: d for d in payload.debts}
    set_setting(db, SNAPSHOT_KEY, {
        "properties": [p.model_dump(mode="json") for p in payload.properties],
        "debts": [d.model_dump(mode="json") for d in payload.debts],
        "categories": sorted(set(payload.categories)),
    })
    set_setting(db, LAST_SYNC_KEY, now.isoformat() + "Z")

    updated = 0
    for vehicle in linked_vehicles(db):
        prop = props.get(vehicle.soberan_property_id)
        if prop is not None:
            vehicle.market_value = prop.valor_estimado
            vehicle.market_value_at = to_utc_naive(prop.valor_actualizado_en) if prop.valor_actualizado_en else None
            vehicle.market_value_confidence = prop.confianza
            updated += 1
        debt = debts.get(vehicle.soberan_debt_id) if vehicle.soberan_debt_id else None
        if debt is not None:
            vehicle.debt_pending = debt.pendiente
            vehicle.debt_monthly = debt.cuota_mensual
        elif vehicle.soberan_debt_id is None:
            vehicle.debt_pending = vehicle.debt_monthly = None

    selected = set(get_setting(db, CATEGORIES_KEY, []))
    owner = default_vehicle_id(db)
    seen = {
        ext for (ext,) in db.query(InboxItem.external_id).filter(
            InboxItem.source == "soberan",
            InboxItem.external_id.in_([str(t.id) for t in payload.transactions]),
        )
    }
    created = 0
    for tx in payload.transactions:
        # Soberan ya filtra por categoría; se revisa también aquí por si la selección
        # cambió entre su lectura de /config y este envío.
        if str(tx.id) in seen or (selected and tx.category not in selected) or tx.amount >= 0:
            continue
        kind, category = classify(tx.description)
        db.add(InboxItem(
            source="soberan", external_id=str(tx.id), vehicle_id=owner, date=tx.date,
            amount=round(abs(tx.amount), 2), description=tx.description[:255], category=tx.category[:80],
            suggested_kind=kind, suggested_category=category,
        ))
        created += 1
    db.commit()
    return {"vehicles_updated": updated, "inbox_created": created}
