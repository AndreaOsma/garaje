"""Mecánica: semáforo, incidencias, revisiones con checklist y sugerencias del plan."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import mechanics as mx
from .. import twin
from .. import schemas, services
from ..database import get_db
from ..models import Checklist, ChecklistRun, Issue, MaintenanceTask, ServiceRecord, Vehicle
from ..obd.dtc import normalize_code
from .deps import get_child, get_vehicle

router = APIRouter(prefix="/api/vehicles/{vehicle_id}", tags=["mechanics"])


def _checklist_out(cl: Checklist, last: ChecklistRun | None, today: date) -> schemas.ChecklistOut:
    due = bool(cl.interval_days) and (last is None or (today - last.date).days >= cl.interval_days)
    return schemas.ChecklistOut.model_validate(cl).model_copy(update={
        "last_run_on": last.date if last else None,
        "last_run_failed": last.failed if last else None,
        "due": due,
    })


@router.get("/mechanics", response_model=schemas.MechanicsOut)
def mechanics_summary(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    today = date.today()
    issues = (
        db.query(Issue).filter_by(vehicle_id=vehicle.id)
        .order_by(Issue.resolved_on.isnot(None), Issue.resolved_on.desc(), Issue.reported_on.desc(), Issue.id.desc())
        .all()
    )
    last = mx.last_runs(db, vehicle)
    runs = db.query(ChecklistRun).filter_by(vehicle_id=vehicle.id).order_by(ChecklistRun.date.desc(), ChecklistRun.id.desc()).limit(20).all()
    return schemas.MechanicsOut(
        readiness=schemas.Readiness(**mx.readiness(db, vehicle, today)),
        issues=[schemas.IssueOut.model_validate(i) for i in issues],
        checklists=[_checklist_out(cl, last.get(cl.id), today) for cl in mx.checklists_for(db, vehicle)],
        runs=[schemas.ChecklistRunOut.model_validate(r) for r in runs],
        suggestions=mx.missing_suggestions(vehicle),
    )


# --- Incidencias -------------------------------------------------------------

def _apply_issue(issue: Issue, payload: schemas.IssueIn, vehicle: Vehicle) -> None:
    for key, value in payload.model_dump().items():
        setattr(issue, key, value)
    issue.dtc_code = normalize_code(payload.dtc_code) if payload.dtc_code else None
    services.bump_odometer(vehicle, payload.odometer_km)


@router.post("/issues", response_model=schemas.IssueOut, status_code=201)
def create_issue(payload: schemas.IssueIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    issue = Issue(vehicle_id=vehicle.id)
    _apply_issue(issue, payload, vehicle)
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue


@router.put("/issues/{issue_id}", response_model=schemas.IssueOut)
def update_issue(issue_id: int, payload: schemas.IssueIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    issue = get_child(db, Issue, vehicle, issue_id)
    _apply_issue(issue, payload, vehicle)
    db.commit()
    db.refresh(issue)
    return issue


@router.post("/issues/{issue_id}/resolve", response_model=schemas.IssueOut)
def resolve_issue(issue_id: int, payload: schemas.IssueResolveIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    issue = get_child(db, Issue, vehicle, issue_id)
    if payload.resolved_on < issue.reported_on:
        raise HTTPException(status_code=422, detail="La resolución no puede ser anterior a la incidencia")
    if payload.service_id is not None:
        get_child(db, ServiceRecord, vehicle, payload.service_id)
    issue.resolved_on = payload.resolved_on
    issue.resolution = payload.resolution
    issue.service_id = payload.service_id
    db.commit()
    db.refresh(issue)
    return issue


@router.post("/issues/{issue_id}/reopen", response_model=schemas.IssueOut)
def reopen_issue(issue_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    issue = get_child(db, Issue, vehicle, issue_id)
    issue.resolved_on = None
    db.commit()
    db.refresh(issue)
    return issue


@router.delete("/issues/{issue_id}", status_code=204)
def delete_issue(issue_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    db.delete(get_child(db, Issue, vehicle, issue_id))
    db.commit()
    return Response(status_code=204)


# --- Checklists --------------------------------------------------------------

def _get_checklist(db: Session, vehicle: Vehicle, checklist_id: int) -> Checklist:
    cl = db.get(Checklist, checklist_id)
    if cl is None or cl.vehicle_id not in (None, vehicle.id):
        raise HTTPException(status_code=404, detail="Revisión no encontrada")
    return cl


@router.post("/checklists", response_model=schemas.ChecklistOut, status_code=201)
def create_checklist(payload: schemas.ChecklistIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    cl = Checklist(vehicle_id=vehicle.id, position=100, **payload.model_dump())
    db.add(cl)
    db.commit()
    db.refresh(cl)
    return _checklist_out(cl, None, date.today())


@router.put("/checklists/{checklist_id}", response_model=schemas.ChecklistOut)
def update_checklist(checklist_id: int, payload: schemas.ChecklistIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    """Las plantillas comunes también se pueden editar (afecta a todos los vehículos)."""
    cl = _get_checklist(db, vehicle, checklist_id)
    for key, value in payload.model_dump().items():
        setattr(cl, key, value)
    db.commit()
    db.refresh(cl)
    return _checklist_out(cl, mx.last_runs(db, vehicle).get(cl.id), date.today())


@router.delete("/checklists/{checklist_id}", status_code=204)
def delete_checklist(checklist_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    db.delete(_get_checklist(db, vehicle, checklist_id))
    db.commit()
    return Response(status_code=204)


@router.post("/checklist-runs", response_model=schemas.ChecklistRunOut, status_code=201)
def create_run(payload: schemas.ChecklistRunIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    cl = _get_checklist(db, vehicle, payload.checklist_id)
    results = [r.model_dump() for r in payload.results]
    run = ChecklistRun(
        vehicle_id=vehicle.id, checklist_id=cl.id, checklist_name=cl.name, date=payload.date,
        odometer_km=payload.odometer_km, failed=sum(1 for r in results if r["ok"] is False),
        results=[{k: r[k] for k in ("section", "label", "check", "ok", "note")} for r in results],
    )
    db.add(run)
    db.flush()
    services.bump_odometer(vehicle, payload.odometer_km)
    created = mx.create_issues_from_run(db, vehicle, run, results)
    db.commit()
    db.refresh(run)
    return schemas.ChecklistRunOut.model_validate(run).model_copy(update={"issues_created": created})


@router.delete("/checklist-runs/{run_id}", status_code=204)
def delete_run(run_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    db.delete(get_child(db, ChecklistRun, vehicle, run_id))
    db.commit()
    return Response(status_code=204)


# --- Sugerencias del plan ----------------------------------------------------

@router.post("/tasks/from-suggestions", response_model=list[schemas.TaskOut], status_code=201)
def add_suggestions(payload: schemas.SuggestionsIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    wanted = {n.strip().lower() for n in payload.names}
    added = []
    for tpl in mx.missing_suggestions(vehicle):
        if tpl["name"].lower() in wanted:
            task = MaintenanceTask(vehicle_id=vehicle.id, **tpl)
            db.add(task)
            added.append(task)
    db.commit()
    return [
        schemas.TaskOut.model_validate(t).model_copy(update=services.task_status(t, vehicle.odometer_km))
        for t in added
    ]


@router.get("/twin")
def vehicle_twin(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    """Estado de cada pieza para el modelo 3D (gemelo digital) de Inicio."""
    return twin.build_twin(db, vehicle)


@router.get("/twin/engine")
def vehicle_engine_twin(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    """Estado de cada subpieza del motor (y de cada cilindro) para el visor «Motor por dentro»."""
    if vehicle.fuel_type == "electric":
        raise HTTPException(status_code=404, detail="Un eléctrico no tiene motor de combustión que ver por dentro")
    return twin.build_engine_twin(db, vehicle)
