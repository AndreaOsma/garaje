"""Ingesta automática autenticada con el token del vehículo (Authorization: Bearer).

- POST /api/ingest/snapshot  → agente ELM327 (JSON: lecturas + averías + monitores).
- POST /api/ingest/file (alias /carscanner) → CSV o TXT del OBD (multipart), pensado para
  un Atajo de iOS que recibe el fichero desde la hoja de compartir y lo sube.
"""
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import config, schemas, services
from ..database import get_db
from ..models import Vehicle
from .diagnostics import import_file, schedule_research

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def vehicle_from_token(authorization: str = Header("", max_length=200), db: Session = Depends(get_db)) -> Vehicle:
    # «Bearer <token>» o el token a secas (fácil de equivocarse al montar un Atajo de iOS).
    raw = authorization.strip().strip('"')
    token = raw[7:].strip() if raw.lower().startswith("bearer ") else raw
    vehicle = services.vehicle_for_token(db, token) if token else None
    if vehicle is None:
        detail = (
            "Falta el token de ingesta: añade la cabecera «Authorization: Bearer <token>»"
            if not token
            else "Token de ingesta no válido: genera uno nuevo en Garaje (Vehículo → Conexión OBD) y pégalo entero"
        )
        raise HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})
    return vehicle


@router.get("/whoami")
def whoami(vehicle: Vehicle = Depends(vehicle_from_token)):
    """Para comprobar el token desde el agente o el Atajo antes de subir nada."""
    return {"vehicle_id": vehicle.id, "name": vehicle.name}


@router.post("/snapshot", response_model=schemas.IngestResult, status_code=201)
def ingest_snapshot(payload: schemas.SnapshotIn, background: BackgroundTasks, vehicle: Vehicle = Depends(vehicle_from_token), db: Session = Depends(get_db)):
    if len(payload.samples) > config.MAX_SAMPLES_PER_REQUEST:
        raise HTTPException(status_code=413, detail="Demasiadas lecturas en un solo envío")
    session = services.ingest(
        db, vehicle,
        source=payload.source,
        external_id=payload.session_id,
        samples=[(s.ts, s.key, s.value) for s in payload.samples],
        label="Agente OBD",
        dtcs=payload.dtcs,
        monitor=payload.monitor.model_dump() if payload.monitor else None,
        vin=payload.vin,
    )
    if payload.dtcs:
        schedule_research(background, vehicle.id)
    return schemas.IngestResult(session_id=session.id if session else None, samples=len(payload.samples))


@router.post("/file", response_model=schemas.IngestResult, status_code=201)
@router.post("/carscanner", response_model=schemas.IngestResult, status_code=201, include_in_schema=False)
async def ingest_file(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    day: date | None = Form(None, alias="date"),
    tz: str | None = Form(None, max_length=64),
    label: str = Form("", max_length=160),
    vehicle: Vehicle = Depends(vehicle_from_token),
    db: Session = Depends(get_db),
):
    return await import_file(db, vehicle, file, day, tz, label, background)
