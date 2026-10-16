from datetime import date, timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from .. import config, dtc_dictionary, mechanics, schemas, services
from ..database import get_db
from ..models import Dtc, Expense, FuelEntry, InboxItem, Issue, MaintenanceTask, ObdLatestValue, ServiceRecord, Vehicle
from .deps import get_vehicle
from .diagnostics import live_values

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


@router.get("", response_model=list[schemas.VehicleOut])
def list_vehicles(db: Session = Depends(get_db)):
    return db.query(Vehicle).order_by(Vehicle.archived, Vehicle.name).all()


@router.post("", response_model=schemas.VehicleOut, status_code=201)
def create_vehicle(payload: schemas.VehicleCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"with_default_plan"})
    vehicle = Vehicle(**data)
    if payload.odometer_km:
        vehicle.odometer_updated_at = services.utcnow()
    db.add(vehicle)
    db.flush()
    if payload.with_default_plan:
        for task in services.default_plan(payload.fuel_type):
            db.add(MaintenanceTask(vehicle_id=vehicle.id, **task))
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.get("/{vehicle_id}", response_model=schemas.VehicleOut)
def get_one(vehicle: Vehicle = Depends(get_vehicle)):
    return vehicle


@router.put("/{vehicle_id}", response_model=schemas.VehicleOut)
def update_vehicle(payload: schemas.VehicleIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    previous_km = vehicle.odometer_km
    for key, value in payload.model_dump().items():
        setattr(vehicle, key, value)
    if payload.odometer_km != previous_km:
        vehicle.odometer_updated_at = services.utcnow()
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.delete("/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    db.delete(vehicle)
    db.commit()
    return Response(status_code=204)


@router.post("/{vehicle_id}/odometer", response_model=schemas.VehicleOut)
def set_odometer(payload: schemas.OdometerIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    """Lectura manual del cuentakilómetros. Permite bajarlo (corrección de un error de tecleo)."""
    vehicle.odometer_km = payload.odometer_km
    vehicle.odometer_updated_at = services.utcnow()
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.post("/{vehicle_id}/ingest-token", response_model=schemas.TokenOut)
def rotate_ingest_token(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    """Genera (o regenera, invalidando el anterior) el token de ingesta OBD. Solo se muestra ahora."""
    token = services.new_ingest_token(vehicle)
    db.commit()
    return {"token": token}


@router.delete("/{vehicle_id}/ingest-token", status_code=204)
def revoke_ingest_token(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    vehicle.ingest_token_hash = None
    db.commit()
    return Response(status_code=204)


def _consumption_unit(vehicle: Vehicle) -> str:
    return "kWh/100 km" if vehicle.fuel_type == "electric" else "L/100 km"


def _cost_summary(db: Session, vehicle: Vehicle) -> schemas.CostSummary:
    since = date.today() - timedelta(days=365)
    by_category: dict[str, float] = {}
    total = recent = 0.0
    kms: list[int] = []

    def add(category: str, amount: float, day: date, km=None):
        nonlocal total, recent
        by_category[category] = round(by_category.get(category, 0.0) + amount, 2)
        total += amount
        if day >= since:
            recent += amount
        if km is not None:
            kms.append(km)

    for f in db.query(FuelEntry).filter_by(vehicle_id=vehicle.id):
        add("energía" if vehicle.fuel_type == "electric" else "combustible", f.total_cost, f.date, f.odometer_km)
    for s in db.query(ServiceRecord).filter_by(vehicle_id=vehicle.id):
        add("mantenimiento", s.cost, s.date, s.odometer_km)
    for e in db.query(Expense).filter_by(vehicle_id=vehicle.id):
        add(e.category, e.amount, e.date)
    kms.append(vehicle.odometer_km)
    km_tracked = max(kms) - min(kms) if kms else 0
    return schemas.CostSummary(
        total=round(total, 2),
        last_12_months=round(recent, 2),
        by_category=by_category,
        cost_per_km=round(total / km_tracked, 3) if km_tracked > 0 and total else None,
        km_tracked=km_tracked,
    )


def _battery_alert(db: Session, vehicle: Vehicle) -> schemas.Alert | None:
    latest = {lv.key: lv for lv in db.query(ObdLatestValue).filter_by(vehicle_id=vehicle.id)}
    batt = latest.get("BATT") or latest.get("42")
    if batt is None:
        return None
    rpm = latest.get("0C")
    running = rpm is not None and rpm.value > 300 and abs((rpm.ts - batt.ts).total_seconds()) < 120
    if running and batt.value < 13.2:
        return schemas.Alert(
            level="warning", kind="battery", title=f"Carga baja con el motor en marcha ({batt.value:.1f} V)",
            detail="Con el motor encendido debería estar entre 13,5 y 14,8 V: revisa alternador y correa.",
            target="diagnostics",
        )
    if not running and batt.value < config.LOW_BATTERY_VOLTS:
        return schemas.Alert(
            level="warning", kind="battery", title=f"Batería baja ({batt.value:.1f} V en reposo)",
            detail="Por debajo de 12,2 V la batería está a menos de la mitad de carga.", target="diagnostics",
        )
    return None


@router.get("/{vehicle_id}/dashboard", response_model=schemas.DashboardOut)
def dashboard(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    alerts: list[schemas.Alert] = []

    active = db.query(Dtc).filter(Dtc.vehicle_id == vehicle.id, Dtc.cleared_at.is_(None)).all()
    if vehicle.mil_on:
        alerts.append(schemas.Alert(level="danger", kind="mil", title="Testigo de avería (MIL) encendido", target="diagnostics"))
    for dtc in active:
        info = dtc_dictionary.describe(db, dtc.code, vehicle.make)
        level = "danger" if info["severity"] == "alta" and dtc.kind != "pending" else "warning"
        prefix = {"pending": "Avería pendiente", "permanent": "Avería permanente"}.get(dtc.kind, "Avería")
        alerts.append(schemas.Alert(level=level, kind="dtc", title=f"{prefix} {dtc.code}", detail=info["description"], target="diagnostics"))

    tasks = []
    for task in db.query(MaintenanceTask).filter_by(vehicle_id=vehicle.id, active=True):
        out = schemas.TaskOut.model_validate(task).model_copy(update=services.task_status(task, vehicle.odometer_km))
        tasks.append(out)
        if out.status in ("overdue", "soon"):
            bits = []
            if out.remaining_km is not None:
                bits.append(f"{abs(out.remaining_km):,} km".replace(",", ".") + (" de retraso" if out.remaining_km < 0 else " restantes"))
            if out.remaining_days is not None:
                bits.append(f"{abs(out.remaining_days)} días" + (" de retraso" if out.remaining_days < 0 else " restantes"))
            alerts.append(schemas.Alert(
                level="danger" if out.status == "overdue" else "warning", kind="maintenance",
                title=("Vencido: " if out.status == "overdue" else "Pronto: ") + task.name,
                detail=" · ".join(bits), target="maintenance",
            ))

    for deadline in vehicle.deadlines:
        status, days = services.deadline_status(deadline.due_date, deadline.done)
        if status in ("overdue", "soon"):
            alerts.append(schemas.Alert(
                level="danger" if status == "overdue" else "warning", kind="deadline",
                title=f"{deadline.title}: " + ("caducado" if days < 0 else f"vence en {days} días"),
                detail=deadline.due_date.strftime("%d/%m/%Y"), target="documents",
            ))

    battery = _battery_alert(db, vehicle)
    if battery:
        alerts.append(battery)
    if vehicle.monitors and not vehicle.monitors.get("ready", True):
        pending = [m["name"] for m in vehicle.monitors.get("monitors", []) if not m.get("complete")]
        alerts.append(schemas.Alert(
            level="info", kind="readiness", title="Monitores de emisiones incompletos",
            detail="No pases la ITV aún: " + ", ".join(pending), target="diagnostics",
        ))

    for issue in db.query(Issue).filter(Issue.vehicle_id == vehicle.id, Issue.resolved_on.is_(None), Issue.severity != "info"):
        alerts.append(schemas.Alert(
            level="danger" if issue.severity == "grounding" else "warning", kind="issue",
            title=("No circular: " if issue.severity == "grounding" else "Incidencia: ") + issue.title,
            detail=issue.description[:140], target="maintenance",
        ))

    inbox_pending = (
        db.query(InboxItem)
        .filter(InboxItem.status == "pending")
        .filter((InboxItem.vehicle_id == vehicle.id) | (InboxItem.vehicle_id.is_(None)))
        .count()
    )
    if inbox_pending:
        alerts.append(schemas.Alert(
            level="info", kind="inbox",
            title=f"{inbox_pending} movimiento{'s' if inbox_pending != 1 else ''} de Soberan por revisar",
            detail="Cargos del banco: confírmalos como repostaje, taller o gasto.", target="expenses",
        ))

    order = {"danger": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: order[a.level])
    rank = {"overdue": 0, "soon": 1, "ok": 2, "unknown": 3}
    tasks.sort(key=lambda t: (rank.get(t.status, 4), t.remaining_km if t.remaining_km is not None else 10**9))
    _, avg = services.fuel_stats(vehicle.fuel_entries)

    return schemas.DashboardOut(
        vehicle=schemas.VehicleOut.model_validate(vehicle),
        alerts=alerts,
        costs=_cost_summary(db, vehicle),
        avg_consumption=avg,
        consumption_unit=_consumption_unit(vehicle),
        active_dtcs=len(active),
        live=live_values(db, vehicle),
        next_tasks=tasks[:5],
        inbox_pending=inbox_pending,
        readiness=schemas.Readiness(**mechanics.readiness(db, vehicle)),
    )
