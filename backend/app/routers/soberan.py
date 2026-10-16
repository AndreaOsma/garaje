"""Enlace con Soberan: endpoints que llama Soberan (config/sync) y los de la UI
(estado, vínculos, categorías y bandeja de movimientos)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, services
from .. import soberan as sb
from ..database import get_db
from ..models import InboxItem, Vehicle
from .deps import get_vehicle

router = APIRouter(prefix="/api", tags=["soberan"])


# --- Lo que llama Soberan ----------------------------------------------------

@router.get("/integrations/soberan/config")
def soberan_config(db: Session = Depends(get_db)):
    return sb.config_for_soberan(db)


@router.post("/integrations/soberan/sync")
def soberan_sync(payload: schemas.SoberanSyncIn, db: Session = Depends(get_db)):
    return sb.apply_sync(db, payload, services.utcnow())


# --- UI ----------------------------------------------------------------------

@router.get("/integrations/soberan", response_model=schemas.SoberanStateOut)
def soberan_state(db: Session = Depends(get_db)):
    snapshot = sb.get_setting(db, sb.SNAPSHOT_KEY, {}) or {}
    return schemas.SoberanStateOut(
        last_sync_at=sb.get_setting(db, sb.LAST_SYNC_KEY),
        properties=snapshot.get("properties", []),
        debts=snapshot.get("debts", []),
        categories=snapshot.get("categories", []),
        selected_categories=sb.get_setting(db, sb.CATEGORIES_KEY, []),
    )


@router.put("/integrations/soberan/settings", response_model=schemas.SoberanStateOut)
def soberan_settings(payload: schemas.SoberanSettingsIn, db: Session = Depends(get_db)):
    sb.set_setting(db, sb.CATEGORIES_KEY, sorted({c.strip() for c in payload.categories if c.strip()}))
    db.commit()
    return soberan_state(db)


@router.put("/vehicles/{vehicle_id}/soberan-link", response_model=schemas.VehicleOut)
def link_vehicle(payload: schemas.SoberanLinkIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    if payload.property_id is not None:
        other = db.query(Vehicle).filter(Vehicle.soberan_property_id == payload.property_id, Vehicle.id != vehicle.id).first()
        if other:
            raise HTTPException(status_code=409, detail=f"Ese coche de Soberan ya está enlazado con «{other.name}»")
    changed_property = payload.property_id != vehicle.soberan_property_id
    vehicle.soberan_property_id = payload.property_id
    vehicle.soberan_debt_id = payload.debt_id if payload.property_id is not None else None

    # Rellenar al momento con la última instantánea, sin esperar a la próxima sincronización.
    snapshot = sb.get_setting(db, sb.SNAPSHOT_KEY, {}) or {}
    prop = next((p for p in snapshot.get("properties", []) if p.get("id") == payload.property_id), None)
    debt = next((d for d in snapshot.get("debts", []) if d.get("id") == vehicle.soberan_debt_id), None)
    if changed_property or prop is None:
        vehicle.market_value = prop.get("valor_estimado") if prop else None
        vehicle.market_value_confidence = prop.get("confianza") if prop else None
        vehicle.market_value_at = None
    vehicle.debt_pending = debt.get("pendiente") if debt else None
    vehicle.debt_monthly = debt.get("cuota_mensual") if debt else None
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.get("/vehicles/{vehicle_id}/inbox", response_model=list[schemas.InboxOut])
def vehicle_inbox(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    """Pendientes de este vehículo + los que aún no tienen vehículo asignado."""
    return (
        db.query(InboxItem)
        .filter(InboxItem.status == "pending")
        .filter((InboxItem.vehicle_id == vehicle.id) | (InboxItem.vehicle_id.is_(None)))
        .order_by(InboxItem.date.desc(), InboxItem.id.desc())
        .all()
    )


@router.post("/inbox/{item_id}/resolve", response_model=schemas.InboxOut)
def resolve_inbox(item_id: int, payload: schemas.InboxResolveIn, db: Session = Depends(get_db)):
    item = db.get(InboxItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    if payload.status == "accepted" and not (payload.record_type and payload.record_id):
        raise HTTPException(status_code=422, detail="Falta el registro creado a partir del movimiento")
    if payload.vehicle_id is not None:
        if db.get(Vehicle, payload.vehicle_id) is None:
            raise HTTPException(status_code=404, detail="Vehículo no encontrado")
        item.vehicle_id = payload.vehicle_id
    item.status = payload.status
    item.record_type = payload.record_type if payload.status == "accepted" else None
    item.record_id = payload.record_id if payload.status == "accepted" else None
    db.commit()
    db.refresh(item)
    return item
