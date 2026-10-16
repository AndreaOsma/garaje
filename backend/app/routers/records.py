"""Repostajes, gastos y vencimientos: CRUD sencillo colgado de un vehículo."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from .. import schemas, services
from ..database import get_db
from ..models import Deadline, Expense, FuelEntry, Vehicle
from .deps import get_child, get_vehicle

router = APIRouter(prefix="/api/vehicles/{vehicle_id}", tags=["records"])


# --- Repostajes --------------------------------------------------------------

@router.get("/fuel", response_model=schemas.FuelListOut)
def list_fuel(vehicle: Vehicle = Depends(get_vehicle)):
    per_entry, avg = services.fuel_stats(vehicle.fuel_entries)
    entries = sorted(vehicle.fuel_entries, key=lambda e: (e.date, e.odometer_km), reverse=True)
    out = [
        schemas.FuelOut.model_validate(e).model_copy(update={
            "price_per_unit": round(e.total_cost / e.quantity, 3) if e.quantity else None,
            "pump_price_per_unit": round((e.total_cost + (e.discount or 0)) / e.quantity, 3) if e.quantity else None,
            "consumption": per_entry.get(e.id),
        })
        for e in entries
    ]
    unit = "kWh/100 km" if vehicle.fuel_type == "electric" else "L/100 km"
    total_discount = round(sum(e.discount or 0 for e in entries), 2)
    return schemas.FuelListOut(entries=out, avg_consumption=avg, unit=unit, total_discount=total_discount)


@router.post("/fuel", response_model=schemas.FuelOut, status_code=201)
def create_fuel(payload: schemas.FuelIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    entry = FuelEntry(vehicle_id=vehicle.id, **payload.to_record())
    db.add(entry)
    services.bump_odometer(vehicle, entry.odometer_km)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/fuel/{entry_id}", response_model=schemas.FuelOut)
def update_fuel(entry_id: int, payload: schemas.FuelIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    entry = get_child(db, FuelEntry, vehicle, entry_id)
    for key, value in payload.to_record().items():
        setattr(entry, key, value)
    services.bump_odometer(vehicle, entry.odometer_km)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/fuel/{entry_id}", status_code=204)
def delete_fuel(entry_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    db.delete(get_child(db, FuelEntry, vehicle, entry_id))
    db.commit()
    return Response(status_code=204)


# --- Gastos ------------------------------------------------------------------

@router.get("/expenses", response_model=list[schemas.ExpenseOut])
def list_expenses(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    return db.query(Expense).filter_by(vehicle_id=vehicle.id).order_by(Expense.date.desc(), Expense.id.desc()).all()


@router.post("/expenses", response_model=schemas.ExpenseOut, status_code=201)
def create_expense(payload: schemas.ExpenseIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    expense = Expense(vehicle_id=vehicle.id, **payload.model_dump())
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.put("/expenses/{expense_id}", response_model=schemas.ExpenseOut)
def update_expense(expense_id: int, payload: schemas.ExpenseIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    expense = get_child(db, Expense, vehicle, expense_id)
    for key, value in payload.model_dump().items():
        setattr(expense, key, value)
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    db.delete(get_child(db, Expense, vehicle, expense_id))
    db.commit()
    return Response(status_code=204)


# --- Vencimientos ------------------------------------------------------------

def _deadline_out(deadline: Deadline) -> schemas.DeadlineOut:
    status, days = services.deadline_status(deadline.due_date, deadline.done)
    return schemas.DeadlineOut.model_validate(deadline).model_copy(update={"status": status, "days_left": days})


@router.get("/deadlines", response_model=list[schemas.DeadlineOut])
def list_deadlines(vehicle: Vehicle = Depends(get_vehicle)):
    return [_deadline_out(d) for d in sorted(vehicle.deadlines, key=lambda d: (d.done, d.due_date))]


@router.post("/deadlines", response_model=schemas.DeadlineOut, status_code=201)
def create_deadline(payload: schemas.DeadlineIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    deadline = Deadline(vehicle_id=vehicle.id, **payload.model_dump())
    db.add(deadline)
    db.commit()
    db.refresh(deadline)
    return _deadline_out(deadline)


@router.put("/deadlines/{deadline_id}", response_model=schemas.DeadlineOut)
def update_deadline(deadline_id: int, payload: schemas.DeadlineIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    deadline = get_child(db, Deadline, vehicle, deadline_id)
    for key, value in payload.model_dump().items():
        setattr(deadline, key, value)
    db.commit()
    db.refresh(deadline)
    return _deadline_out(deadline)


@router.delete("/deadlines/{deadline_id}", status_code=204)
def delete_deadline(deadline_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    db.delete(get_child(db, Deadline, vehicle, deadline_id))
    db.commit()
    return Response(status_code=204)
