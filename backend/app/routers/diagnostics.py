"""Diagnóstico: averías (DTC), valores en vivo, sesiones OBD e importación de CSV desde la UI."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from .. import config, dtc_dictionary, dtc_research, schemas, services
from ..database import get_db
from ..models import Dtc, DtcDefinition, ObdLatestValue, ObdSample, ObdSensor, ObdSession, Vehicle
from ..obd.carscanner import CsvFormatError, parse_csv
from ..obd.dtc import describe_dtc, normalize_code
from ..obd.pids import describe_key
from ..obd.textreport import parse_text
from .deps import get_child, get_vehicle

router = APIRouter(prefix="/api", tags=["diagnostics"])

MAX_POINTS = 120


def _sensor_names(db: Session, keys) -> dict[str, tuple[str, str, str]]:
    custom = {s.key: s for s in db.query(ObdSensor).filter(ObdSensor.key.in_(list(keys)))} if keys else {}
    out = {}
    for key in keys:
        if key in custom:
            out[key] = (custom[key].name, custom[key].unit, "otros")
        else:
            out[key] = describe_key(key)
    return out


def live_values(db: Session, vehicle: Vehicle) -> list[schemas.LiveValueOut]:
    rows = db.query(ObdLatestValue).filter_by(vehicle_id=vehicle.id).all()
    names = _sensor_names(db, {r.key for r in rows})
    out = [
        schemas.LiveValueOut(key=r.key, name=names[r.key][0], unit=names[r.key][1], group=names[r.key][2], value=r.value, ts=r.ts)
        for r in rows
    ]
    return sorted(out, key=lambda v: (v.group, v.name))


def _dtc_out(db: Session, row: Dtc, make: str | None) -> schemas.DtcOut:
    info = dtc_dictionary.describe(db, row.code, make)
    return schemas.DtcOut.model_validate(row).model_copy(update={
        "description": info["description"], "system": info["system"], "severity": info["severity"],
        "generic": info["generic"], "learned": info.get("learned"), "details": info.get("details"),
    })


# --- Averías -----------------------------------------------------------------

@router.get("/vehicles/{vehicle_id}/dtcs", response_model=list[schemas.DtcOut])
def list_dtcs(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    rows = db.query(Dtc).filter_by(vehicle_id=vehicle.id).order_by(Dtc.cleared_at.isnot(None), Dtc.last_seen.desc()).all()
    return [_dtc_out(db, r, vehicle.make) for r in rows]


@router.post("/vehicles/{vehicle_id}/dtcs", response_model=schemas.DtcOut, status_code=201)
def add_dtc(payload: schemas.DtcIn, background: BackgroundTasks, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    """Alta manual (p.ej. códigos leídos con Car Scanner, que no los exporta en el CSV)."""
    now = services.utcnow()
    row = (
        db.query(Dtc)
        .filter(Dtc.vehicle_id == vehicle.id, Dtc.code == payload.code, Dtc.kind == payload.kind, Dtc.cleared_at.is_(None))
        .first()
    )
    if row:
        row.last_seen = now
        row.occurrences += 1
        if payload.notes:
            row.notes = payload.notes
    else:
        row = Dtc(vehicle_id=vehicle.id, code=payload.code, kind=payload.kind, source="manual",
                  first_seen=now, last_seen=now, notes=payload.notes)
        db.add(row)
    db.commit()
    db.refresh(row)
    schedule_research(background, vehicle.id)
    return _dtc_out(db, row, vehicle.make)


@router.put("/vehicles/{vehicle_id}/dtcs/{dtc_id}", response_model=schemas.DtcOut)
def update_dtc_notes(dtc_id: int, payload: schemas.DtcNotesIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    row = get_child(db, Dtc, vehicle, dtc_id)
    row.notes = payload.notes
    db.commit()
    db.refresh(row)
    return _dtc_out(db, row, vehicle.make)


@router.post("/vehicles/{vehicle_id}/dtcs/{dtc_id}/clear", response_model=schemas.DtcOut)
def mark_dtc_cleared(dtc_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    """Marca la avería como resuelta en Garaje (no toca la ECU: eso lo hace el agente con --clear-dtc)."""
    row = get_child(db, Dtc, vehicle, dtc_id)
    row.cleared_at = row.cleared_at or services.utcnow()
    db.commit()
    db.refresh(row)
    return _dtc_out(db, row, vehicle.make)


@router.delete("/vehicles/{vehicle_id}/dtcs/{dtc_id}", status_code=204)
def delete_dtc(dtc_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    db.delete(get_child(db, Dtc, vehicle, dtc_id))
    db.commit()
    return Response(status_code=204)


def schedule_research(background: BackgroundTasks, vehicle_id: int) -> None:
    """Tras guardar códigos, busca en segundo plano el significado de los que no se entienden."""
    if dtc_research.configured_providers():
        background.add_task(dtc_dictionary.research_missing, vehicle_id)


@router.get("/research/status")
def research_status():
    return {"providers": dtc_research.configured_providers()}


@router.post("/vehicles/{vehicle_id}/dtcs/{dtc_id}/research", response_model=schemas.DtcOut)
def research_dtc(dtc_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    """Busca ahora el significado del código para esta marca/modelo (aunque ya hubiera uno automático)."""
    row = get_child(db, Dtc, vehicle, dtc_id)
    if not dtc_research.configured_providers():
        raise HTTPException(status_code=503, detail="La búsqueda automática no está configurada (falta Claude u Ollama)")
    found = dtc_dictionary.research_and_store(db, row.code, vehicle, force=True)
    if found is None:
        raise HTTPException(status_code=404, detail=f"No he encontrado una fuente fiable para {row.code} en {vehicle.make or 'tu marca'}")
    return _dtc_out(db, row, vehicle.make)


@router.get("/dtc/{code}")
def lookup_dtc(code: str, make: str | None = None, db: Session = Depends(get_db)):
    clean = normalize_code(code)
    if not clean:
        raise HTTPException(status_code=422, detail="Formato de código no válido (ej. P0420)")
    return dtc_dictionary.describe(db, clean, make)


@router.put("/vehicles/{vehicle_id}/dtc-definitions/{code}")
def set_definition(code: str, payload: schemas.DtcDefinitionIn, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    """Tu descripción para un código (p.ej. lo que te dijo el taller). Los códigos del
    fabricante se guardan para la marca del vehículo; los genéricos, para todas."""
    clean = normalize_code(code)
    if not clean:
        raise HTTPException(status_code=422, detail="Formato de código no válido (ej. P0420)")
    make = "" if describe_dtc(clean)["generic"] or payload.all_makes else dtc_dictionary.norm_make(vehicle.make)
    row = db.query(DtcDefinition).filter_by(code=clean, make=make).first()
    if row is None:
        row = DtcDefinition(code=clean, make=make)
        db.add(row)
    row.description, row.severity, row.source = payload.description.strip(), payload.severity, "manual"
    db.commit()
    return dtc_dictionary.describe(db, clean, vehicle.make)


@router.delete("/vehicles/{vehicle_id}/dtc-definitions/{code}")
def reset_definition(code: str, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    """Vuelve a la descripción del diccionario base (borra la propia de esta marca y la general)."""
    clean = normalize_code(code) or ""
    makes = {"", dtc_dictionary.norm_make(vehicle.make)}
    db.query(DtcDefinition).filter(DtcDefinition.code == clean, DtcDefinition.make.in_(makes)).delete(synchronize_session=False)
    db.commit()
    return dtc_dictionary.describe(db, clean, vehicle.make)


# --- Valores en vivo y sesiones ----------------------------------------------

@router.get("/vehicles/{vehicle_id}/live", response_model=list[schemas.LiveValueOut])
def get_live(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    return live_values(db, vehicle)


@router.get("/vehicles/{vehicle_id}/sessions", response_model=list[schemas.SessionOut])
def list_sessions(vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    return db.query(ObdSession).filter_by(vehicle_id=vehicle.id).order_by(ObdSession.started_at.desc()).limit(200).all()


@router.get("/vehicles/{vehicle_id}/sessions/{session_id}", response_model=schemas.SessionDetailOut)
def session_detail(session_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    session = get_child(db, ObdSession, vehicle, session_id)
    by_key: dict[str, list[tuple]] = defaultdict(list)
    for ts, key, value in (
        db.query(ObdSample.ts, ObdSample.key, ObdSample.value).filter_by(session_id=session.id).order_by(ObdSample.ts)
    ):
        by_key[key].append((ts, value))
    names = _sensor_names(db, set(by_key))
    series = []
    for key, rows in by_key.items():
        values = [v for _, v in rows]
        # Media por cubos para no mandar miles de puntos a una gráfica de 300 px.
        step = max(1, -(-len(rows) // MAX_POINTS))
        points = []
        for i in range(0, len(rows), step):
            chunk = rows[i : i + step]
            epoch_ms = int(chunk[0][0].replace(tzinfo=timezone.utc).timestamp() * 1000)
            points.append((epoch_ms, round(sum(v for _, v in chunk) / len(chunk), 3)))
        name, unit, group = names[key]
        series.append(schemas.SensorSeries(
            key=key, name=name, unit=unit, group=group, count=len(values),
            min=min(values), max=max(values), avg=round(sum(values) / len(values), 3), points=points,
        ))
    series.sort(key=lambda s: (s.group, s.name))
    return schemas.SessionDetailOut(session=schemas.SessionOut.model_validate(session), series=series)


@router.delete("/vehicles/{vehicle_id}/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, vehicle: Vehicle = Depends(get_vehicle), db: Session = Depends(get_db)):
    db.delete(get_child(db, ObdSession, vehicle, session_id))
    db.commit()
    return Response(status_code=204)


# --- Importación de CSV (compartida con la ingesta por token) ----------------

def resolve_tz(name: str | None):
    try:
        return ZoneInfo(name or config.DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail=f"Zona horaria desconocida: {name}")


async def import_file(
    db: Session, vehicle: Vehicle, file: UploadFile, day: date | None, tz_name: str | None, label: str,
    background: BackgroundTasks | None = None,
) -> schemas.IngestResult:
    """CSV de lecturas (Car Scanner y similares) o TXT del OBD (informe de diagnóstico o
    log del ELM327). Se detecta por el contenido, no por la extensión."""
    content = await file.read(config.MAX_CSV_UPLOAD_BYTES + 1)
    if len(content) > config.MAX_CSV_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="El fichero supera el tamaño máximo (20 MB)")
    if not content.strip():
        raise HTTPException(status_code=422, detail="El fichero está vacío")
    external_id = hashlib.sha256(content).hexdigest()[:32]
    previous = db.query(ObdSession).filter_by(vehicle_id=vehicle.id, external_id=external_id).first()
    name = (file.filename or "OBD")[:160]

    try:
        parsed = parse_csv(content, day or date.today(), resolve_tz(tz_name))
    except CsvFormatError:
        parsed = None
    if parsed is not None and parsed.samples:
        if previous is not None:
            # Una grabación repetida duplicaría todas sus lecturas.
            raise HTTPException(status_code=409, detail="Este fichero ya se importó")
        if len(parsed.samples) > config.MAX_SAMPLES_PER_REQUEST:
            raise HTTPException(status_code=413, detail="Demasiadas lecturas en un solo fichero")
        session = services.ingest(
            db, vehicle, source="carscanner", external_id=external_id, samples=parsed.samples,
            label=label or name, sensors=parsed.sensors,
        )
        return schemas.IngestResult(session_id=session.id if session else None, samples=len(parsed.samples), skipped_rows=parsed.skipped_rows)

    report = parse_text(content)
    if report.empty:
        raise HTTPException(
            status_code=422,
            detail="No reconozco nada en el fichero: ni lecturas en el tiempo, ni códigos de avería, ni valores de sensores",
        )
    # Un informe sí se puede volver a subir: se reprocesa (códigos y diccionario) sin
    # duplicar sus valores, p.ej. tras mejorar el diccionario o el lector de TXT.
    learned = sum(dtc_dictionary.learn(db, code, desc, vehicle.make) for code, desc in report.descriptions.items())
    if background is not None and report.dtcs:
        schedule_research(background, vehicle.id)
    now = services.utcnow()
    session = services.ingest(
        db, vehicle, source="txt", external_id=external_id,
        samples=[] if previous else [(now, key, value) for key, value in report.values.items()],
        label=label or name, sensors=report.sensors,
        dtcs=report.dtcs or None, vin=report.vin,
    )
    if session is None and previous is None:
        # Informe solo con códigos: se deja su sesión (0 lecturas) para reconocerlo si se resube.
        session = ObdSession(vehicle_id=vehicle.id, source="txt", external_id=external_id, label=label or name,
                             started_at=now, ended_at=now, sample_count=0)
        db.add(session)
        db.commit()
    return schemas.IngestResult(
        session_id=(session or previous).id if (session or previous) else None, samples=len(report.values), kind="report",
        dtcs=report.dtcs, vin=report.vin, learned=learned, reprocessed=previous is not None,
    )


@router.post("/vehicles/{vehicle_id}/import/obd-file", response_model=schemas.IngestResult, status_code=201)
@router.post("/vehicles/{vehicle_id}/import/carscanner", response_model=schemas.IngestResult, status_code=201, include_in_schema=False)
async def import_obd_file(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    day: date | None = Form(None, alias="date"),
    tz: str | None = Form(None, max_length=64),
    label: str = Form("", max_length=160),
    vehicle: Vehicle = Depends(get_vehicle),
    db: Session = Depends(get_db),
):
    return await import_file(db, vehicle, file, day, tz, label, background)
