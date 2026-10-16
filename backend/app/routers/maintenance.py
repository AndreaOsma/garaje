from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import schemas, services
from ..database import get_db
from ..models import MaintenanceTask, ServiceRecord, Vehicle
from .deps import get_child, get_vehicle

router = APIRouter(prefix="/api/vehicles/{vehicle_id}", tags=["maintenance"])


def _task_out(task: MaintenanceTask, vehicle: Vehicle) -> schemas.TaskOut:
    return schemas.TaskOut.model_validate(task).model_copy(update=services.task_status(task, vehicle.odometer_km))


@router.get("/tasks", response_model=list[schemas.TaskOut])
def list_tasks(vehicle: Vehicle = Depends(get_vehicle)):
    rank = {"overdue": 0, "soon": 1, "unknown": 2, "ok": 3, "inactive": 4}
    tasks = [_task_out(t, vehicle) for t in vehicle.tasks]
    return sorted(tasks, key=lambda t: (rank[t.status], t.remaining_km if t.remaining_km is not None else 10**9, t.name))


@router.post("/tasks", response_model=schemas.TaskOut, status_code=201)
def create_task(payload: schemas.TaskIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    if not (payload.interval_km or payload.interval_months):
        raise HTTPException(status_code=422, detail="Indica un intervalo en km, en meses o ambos")
    task = MaintenanceTask(vehicle_id=vehicle.id, **payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_out(task, vehicle)


@router.put("/tasks/{task_id}", response_model=schemas.TaskOut)
def update_task(task_id: int, payload: schemas.TaskIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    if not (payload.interval_km or payload.interval_months):
        raise HTTPException(status_code=422, detail="Indica un intervalo en km, en meses o ambos")
    task = get_child(db, MaintenanceTask, vehicle, task_id)
    for key, value in payload.model_dump().items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return _task_out(task, vehicle)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    db.delete(get_child(db, MaintenanceTask, vehicle, task_id))
    db.commit()
    return Response(status_code=204)


@router.get("/services", response_model=list[schemas.ServiceOut])
def list_services(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    return (
        db.query(ServiceRecord).filter_by(vehicle_id=vehicle.id)
        .order_by(ServiceRecord.date.desc(), ServiceRecord.id.desc()).all()
    )


def _apply_service(db: Session, vehicle: Vehicle, record: ServiceRecord) -> None:
    services.bump_odometer(vehicle, record.odometer_km)
    if record.task_id is None:
        return
    task = get_child(db, MaintenanceTask, vehicle, record.task_id)
    # Solo avanza la tarea si esta intervención es la más reciente (editar una antigua no la retrocede).
    if task.last_done_date is None or record.date >= task.last_done_date:
        task.last_done_date = record.date
        if record.odometer_km is not None:
            task.last_done_km = record.odometer_km


@router.post("/services", response_model=schemas.ServiceOut, status_code=201)
def create_service(payload: schemas.ServiceIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    record = ServiceRecord(vehicle_id=vehicle.id, **payload.model_dump())
    db.add(record)
    _apply_service(db, vehicle, record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/services/{service_id}", response_model=schemas.ServiceOut)
def update_service(service_id: int, payload: schemas.ServiceIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    record = get_child(db, ServiceRecord, vehicle, service_id)
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    _apply_service(db, vehicle, record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/services/{service_id}", status_code=204)
def delete_service(service_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    db.delete(get_child(db, ServiceRecord, vehicle, service_id))
    db.commit()
    return Response(status_code=204)
