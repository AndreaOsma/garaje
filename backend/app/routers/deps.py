from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Vehicle


def get_vehicle(vehicle_id: int, db: Session = Depends(get_db)) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return vehicle


def get_child(db: Session, model, vehicle: Vehicle, item_id: int):
    """Fila hija de un vehículo; 404 si no existe o es de otro vehículo."""
    item = db.get(model, item_id)
    if item is None or item.vehicle_id != vehicle.id:
        raise HTTPException(status_code=404, detail="No encontrado")
    return item
