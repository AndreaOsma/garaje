"""Herramientas para asistentes (ágora): estado del coche, repostajes, gastos, vencimientos y
averías. Ver dev/lib/agent-api; token en GARAJE_AGENT_TOKEN."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import schemas, services
from .agent_api import AgentError, AgentRegistry
from .models import Deadline, Expense, FuelEntry, Issue, MaintenanceTask, ServiceRecord, Vehicle

agent = AgentRegistry("garaje", "Garaje", "Tus vehículos: mantenimiento, repostajes, gastos, vencimientos (ITV, seguro…) y averías.",
                      token_env="GARAJE_AGENT_TOKEN")

LOW_FUEL_PCT = 15
VEH = Field(None, max_length=80, description="Nombre o matrícula del vehículo; si solo hay uno, no hace falta")


def _vehicle(db: Session, name: Optional[str]) -> Vehicle:
    rows = db.query(Vehicle).order_by(Vehicle.id).all()
    if not rows:
        raise AgentError("No hay ningún vehículo dado de alta en Garaje.", 404)
    if not name:
        if len(rows) == 1:
            return rows[0]
        raise AgentError("Hay varios vehículos: {}. Dime cuál.".format(", ".join(v.name for v in rows)))
    n = name.strip().lower().replace(" ", "")
    hits = [v for v in rows if v.name.lower().replace(" ", "") == n or (v.plate or "").lower().replace(" ", "") == n]
    hits = hits or [v for v in rows if n in v.name.lower().replace(" ", "")]
    if len(hits) != 1:
        raise AgentError("No sé a qué vehículo te refieres con «{}». Hay: {}.".format(name, ", ".join(v.name for v in rows)), 404)
    return hits[0]


class Veh(BaseModel):
    vehiculo: Optional[str] = VEH


def _utc(dt: datetime) -> datetime:
    """SQLite devuelve las fechas sin zona: son UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fuel_level(v: Vehicle, db: Optional[Session] = None) -> dict:
    """Nivel del depósito (o batería), cuánto es y la autonomía, si se ha apuntado alguna vez."""
    if v.fuel_level_pct is None:
        return {"capacidad_deposito": v.tank_capacity} if v.tank_capacity else {}
    avg = services.fuel_stats(db.query(FuelEntry).filter_by(vehicle_id=v.id).all())[1] if db is not None else None
    g = services.fuel_gauge(v, avg)
    what = "bateria" if v.fuel_type == "electric" else "deposito"
    out = {f"{what}_pct": g["pct"], "nivel_apuntado": g["at"]}
    if g["left"] is not None:
        out[f"quedan_{g['unit'].lower()}"] = g["left"]
    if g["range_km"] is not None:
        out["autonomia_km_aprox"] = g["range_km"]
    return out


@agent.tool("vehiculos", "Lista los vehículos con su kilometraje")
def vehiculos(db: Session):
    return [{"nombre": v.name, "marca": v.make, "modelo": v.model, "matricula": v.plate, "km": v.odometer_km, "combustible": v.fuel_type,
             **_fuel_level(v, db), "ver": f"/v/{v.id}"}
            for v in db.query(Vehicle).order_by(Vehicle.id)]


@agent.tool("estado", "Resumen del coche: mantenimiento pendiente, vencimientos, averías abiertas, consumo y gasto del año")
def estado(db: Session, p: Veh):
    v = _vehicle(db, p.vehiculo)
    tasks = []
    for t in db.query(MaintenanceTask).filter_by(vehicle_id=v.id, active=True):
        st = services.task_status(t, v.odometer_km)
        if st["status"] in ("overdue", "soon"):
            tasks.append({"tarea": t.name, "estado": "vencida" if st["status"] == "overdue" else "pronto",
                          "faltan_km": st["remaining_km"], "faltan_dias": st["remaining_days"]})
    deadlines = []
    for d in db.query(Deadline).filter_by(vehicle_id=v.id, done=False).order_by(Deadline.due_date):
        st, days = services.deadline_status(d.due_date, d.done)
        deadlines.append({"que": d.title, "tipo": d.kind, "fecha": d.due_date, "dias": days, "estado": st})
    issues = [{"averia": i.title, "gravedad": i.severity, "desde": i.reported_on}
              for i in db.query(Issue).filter_by(vehicle_id=v.id, resolved_on=None)]
    _, avg = services.fuel_stats(db.query(FuelEntry).filter_by(vehicle_id=v.id).all())
    year = date(date.today().year, 1, 1)
    spent = (sum(f.total_cost for f in db.query(FuelEntry).filter(FuelEntry.vehicle_id == v.id, FuelEntry.date >= year))
             + sum(e.amount for e in db.query(Expense).filter(Expense.vehicle_id == v.id, Expense.date >= year))
             + sum(s.cost for s in db.query(ServiceRecord).filter(ServiceRecord.vehicle_id == v.id, ServiceRecord.date >= year)))
    return {"vehiculo": v.name, "ver": f"/v/{v.id}", "km": v.odometer_km, "mantenimiento_pendiente": tasks, "vencimientos": deadlines,
            "averias_abiertas": issues, "consumo_medio_l_100km": avg, "gastado_este_anio_eur": round(spent, 2), **_fuel_level(v, db)}


class Ultimos(BaseModel):
    vehiculo: Optional[str] = VEH
    limite: int = Field(10, ge=1, le=100)


@agent.tool("repostajes", "Últimos repostajes con consumo")
def repostajes(db: Session, p: Ultimos):
    v = _vehicle(db, p.vehiculo)
    rows = db.query(FuelEntry).filter_by(vehicle_id=v.id).all()
    per, avg = services.fuel_stats(rows)
    rows = sorted(rows, key=lambda e: (e.date, e.odometer_km), reverse=True)[: p.limite]
    return {"ver": f"/v/{v.id}/fuel", "consumo_medio": avg, "repostajes": [{"fecha": e.date, "km": e.odometer_km, "litros": e.quantity, "total_eur": e.total_cost,
                                                  "lleno": e.full_tank, "gasolinera": e.station, "consumo": per.get(e.id)} for e in rows]}


@agent.tool("gastos", "Últimos gastos (además de repostajes y taller)")
def gastos(db: Session, p: Ultimos):
    v = _vehicle(db, p.vehiculo)
    rows = db.query(Expense).filter_by(vehicle_id=v.id).order_by(Expense.date.desc()).limit(p.limite)
    return [{"fecha": e.date, "concepto": e.title, "categoria": e.category, "importe_eur": e.amount} for e in rows]


class Repostaje(BaseModel):
    vehiculo: Optional[str] = VEH
    litros: float = Field(gt=0, le=2000, description="Litros (o kWh si es eléctrico)")
    total_eur: float = Field(ge=0, le=100_000, description="Lo pagado, ya con descuentos")
    km: int = Field(ge=0, le=5_000_000, description="Lectura del cuentakilómetros")
    fecha: date = Field(default_factory=date.today)
    lleno: bool = True
    gasolinera: str = Field("", max_length=120)


def _eur(x: float) -> str:
    return f"{x:.2f} €".replace(".", ",")


def _repostaje_preview(db: Session, p: Repostaje) -> str:
    v = _vehicle(db, p.vehiculo)
    unidad = "kWh" if v.fuel_type == "electric" else "litros"
    return "Repostaje de {}: {:g} {} por {} el {} a {} km{}{}".format(
        v.name, p.litros, unidad, _eur(p.total_eur), p.fecha.strftime("%d/%m"), p.km,
        " (lleno)" if p.lleno else "", f" en {p.gasolinera}" if p.gasolinera else "")


@agent.tool("anadir_repostaje", "Registra un repostaje (y actualiza los km del coche)", write=True, preview=_repostaje_preview)
def anadir_repostaje(db: Session, p: Repostaje):
    v = _vehicle(db, p.vehiculo)
    data = schemas.FuelIn(date=p.fecha, odometer_km=p.km, quantity=p.litros, total_cost=p.total_eur,
                          full_tank=p.lleno, station=p.gasolinera).to_record()
    e = FuelEntry(vehicle_id=v.id, **data)
    db.add(e)
    services.bump_odometer(v, e.odometer_km)
    services.fuel_level_after_refuel(v, e.date, e.full_tank)
    db.commit()
    return {"vehiculo": v.name, "fecha": e.date, "litros": e.quantity, "total_eur": e.total_cost, "km": e.odometer_km}


class Gasto(BaseModel):
    vehiculo: Optional[str] = VEH
    concepto: str = Field(min_length=1, max_length=160)
    importe_eur: float = Field(ge=0, le=1_000_000)
    categoria: str = Field("otros", max_length=32, description="p. ej. seguro, impuestos, parking, peajes, lavado, multas, otros")
    fecha: date = Field(default_factory=date.today)
    notas: str = Field("", max_length=2000)


def _gasto_preview(db: Session, p: Gasto) -> str:
    v = _vehicle(db, p.vehiculo)
    return f"Gasto de {v.name}: {p.concepto} ({p.categoria}), {_eur(p.importe_eur)} el {p.fecha.strftime('%d/%m')}"


@agent.tool("anadir_gasto", "Registra un gasto del coche (seguro, parking, peaje, lavado…)", write=True, preview=_gasto_preview)
def anadir_gasto(db: Session, p: Gasto):
    v = _vehicle(db, p.vehiculo)
    data = schemas.ExpenseIn(date=p.fecha, category=p.categoria, title=p.concepto, amount=p.importe_eur, notes=p.notas)
    e = Expense(vehicle_id=v.id, **data.model_dump())
    db.add(e)
    db.commit()
    return {"vehiculo": v.name, "fecha": e.date, "concepto": e.title, "importe_eur": e.amount}


class Km(BaseModel):
    vehiculo: Optional[str] = VEH
    km: int = Field(ge=0, le=5_000_000)


def _km_preview(db: Session, p: Km) -> str:
    v = _vehicle(db, p.vehiculo)
    if p.km < (v.odometer_km or 0):
        raise AgentError(f"{v.name} ya tiene {v.odometer_km} km; el cuentakilómetros no baja.")
    return f"Poner el cuentakilómetros de {v.name} en {p.km} km (ahora {v.odometer_km or 0})"


@agent.tool("actualizar_km", "Anota la lectura actual del cuentakilómetros", write=True, preview=_km_preview)
def actualizar_km(db: Session, p: Km):
    v = _vehicle(db, p.vehiculo)
    if p.km < (v.odometer_km or 0):
        raise AgentError(f"{v.name} ya tiene {v.odometer_km} km; el cuentakilómetros no baja.")
    v.odometer_km = p.km
    db.commit()
    return {"vehiculo": v.name, "km": v.odometer_km}


class Nivel(BaseModel):
    vehiculo: Optional[str] = VEH
    porcentaje: int = Field(ge=0, le=100, description="Lo que queda en el depósito (o la batería), de 0 a 100")


def _nivel_preview(db: Session, p: Nivel) -> str:
    v = _vehicle(db, p.vehiculo)
    return "Apuntar que a {} le queda el {} % de {}".format(v.name, p.porcentaje, "batería" if v.fuel_type == "electric" else "depósito")


@agent.tool("nivel_combustible", "Apunta cuánto queda en el depósito (o la batería), en %", write=True, preview=_nivel_preview)
def nivel_combustible(db: Session, p: Nivel):
    v = _vehicle(db, p.vehiculo)
    services.set_fuel_level(v, p.porcentaje)
    db.commit()
    return {"vehiculo": v.name, **_fuel_level(v, db)}


class Vencimiento(BaseModel):
    vehiculo: Optional[str] = VEH
    que: str = Field(min_length=1, max_length=160, description="p. ej. «ITV», «Seguro a todo riesgo»")
    tipo: str = Field("otro", max_length=16, description="itv, seguro, impuesto, carnet u otro")
    fecha: date


def _vencimiento_preview(db: Session, p: Vencimiento) -> str:
    v = _vehicle(db, p.vehiculo)
    return f"Vencimiento de {v.name}: {p.que} ({p.tipo}) el {p.fecha.strftime('%d/%m/%Y')}"


@agent.tool("anadir_vencimiento", "Añade un vencimiento con fecha (ITV, seguro, impuesto…)", write=True, preview=_vencimiento_preview)
def anadir_vencimiento(db: Session, p: Vencimiento):
    v = _vehicle(db, p.vehiculo)
    data = schemas.DeadlineIn(kind=p.tipo, title=p.que, due_date=p.fecha)
    d = Deadline(vehicle_id=v.id, **data.model_dump())
    db.add(d)
    db.commit()
    return {"vehiculo": v.name, "que": d.title, "fecha": d.due_date}


class Averia(BaseModel):
    vehiculo: Optional[str] = VEH
    que_pasa: str = Field(min_length=1, max_length=160)
    detalle: str = Field("", max_length=5000)
    gravedad: schemas.IssueSeverity = "info"


def _averia_preview(db: Session, p: Averia) -> str:
    v = _vehicle(db, p.vehiculo)
    return f"Anotar en {v.name} la avería «{p.que_pasa}» (gravedad {p.gravedad})"


@agent.tool("anotar_averia", "Anota una avería o algo raro del coche", write=True, preview=_averia_preview)
def anotar_averia(db: Session, p: Averia):
    v = _vehicle(db, p.vehiculo)
    data = schemas.IssueIn(reported_on=date.today(), odometer_km=v.odometer_km, title=p.que_pasa, description=p.detalle, severity=p.gravedad)
    i = Issue(vehicle_id=v.id, **data.model_dump())
    db.add(i)
    db.commit()
    return {"vehiculo": v.name, "averia": i.title, "gravedad": i.severity}

# ---------- Avisos (para el parte de la mañana y los avisos por umbral de ágora) ----------
# Formato común: {"nivel": "urgente" | "pronto", "clave": id estable (para no repetir), "texto", "ver"?}


@agent.tool("avisos", "Vencimientos (ITV, seguro…) a 30 días o pasados, mantenimiento vencido o próximo y averías que impiden circular")
def avisos(db: Session):
    out = []
    for v in db.query(Vehicle).order_by(Vehicle.id):
        for d in db.query(Deadline).filter_by(vehicle_id=v.id, done=False):
            st, days = services.deadline_status(d.due_date, d.done)
            if days <= 30:
                out.append({"nivel": "urgente" if days <= 7 else "pronto", "clave": f"venc-{d.id}-{d.due_date}",
                            "texto": "{}: {} {}".format(v.name, d.title, f"venció hace {-days} días" if days < 0 else "hoy" if days == 0 else f"en {days} días ({d.due_date:%d/%m})"),
                            "ver": f"/v/{v.id}/documents"})
        for t in db.query(MaintenanceTask).filter_by(vehicle_id=v.id, active=True):
            st = services.task_status(t, v.odometer_km)
            if st["status"] in ("overdue", "soon"):
                bits = [f"{st['remaining_km']} km" if st["remaining_km"] is not None else None,
                        f"{st['remaining_days']} días" if st["remaining_days"] is not None else None]
                out.append({"nivel": "urgente" if st["status"] == "overdue" else "pronto", "clave": f"mant-{t.id}-{t.last_done_date}-{t.last_done_km}",
                            "texto": "{}: {} {}".format(v.name, t.name, "vencido" if st["status"] == "overdue" else "pronto (faltan " + ", ".join(b for b in bits if b) + ")"),
                            "ver": f"/v/{v.id}/maintenance"})
        # Depósito casi vacío, si el dato es reciente (uno de hace una semana ya no dice nada).
        if v.fuel_level_pct is not None and v.fuel_level_pct <= LOW_FUEL_PCT and v.fuel_level_at \
                and _utc(services.utcnow()) - _utc(v.fuel_level_at) < timedelta(days=3):
            what = "batería" if v.fuel_type == "electric" else "depósito"
            out.append({"nivel": "pronto", "clave": f"nivel-{v.id}-{v.fuel_level_at:%Y%m%d%H%M}",
                        "texto": f"{v.name}: queda poco en el {what} ({v.fuel_level_pct} %)", "ver": f"/v/{v.id}"})
        for i in db.query(Issue).filter_by(vehicle_id=v.id, resolved_on=None, severity="grounding"):
            out.append({"nivel": "urgente", "clave": f"averia-{i.id}", "texto": f"{v.name}: «{i.title}» impide circular", "ver": f"/v/{v.id}/maintenance"})
    return out


# ---------- Ficheros del OBD (Car Scanner) que le pasas a ágora ----------

MAX_OBD_GZ_B64 = 240_000  # cabe en una petición de la API de asistentes (256 KB)


class ObdFile(BaseModel):
    vehiculo: Optional[str] = VEH
    nombre: str = Field("OBD", max_length=160, description="Nombre del fichero")
    contenido_gz_b64: str = Field(min_length=4, max_length=MAX_OBD_GZ_B64,
                                  description="El CSV o TXT de Car Scanner comprimido con gzip y en base64 (lo prepara ágora)")
    fecha: Optional[date] = Field(None, description="Día de la grabación si el CSV solo trae horas; vacío = hoy")


def _obd_bytes(p: ObdFile) -> bytes:
    import base64
    import gzip

    try:
        raw = gzip.decompress(base64.b64decode(p.contenido_gz_b64, validate=True))
    except (ValueError, OSError):
        raise AgentError("El contenido no es un gzip en base64 válido.", 422)
    from . import config

    if len(raw) > config.MAX_CSV_UPLOAD_BYTES:
        raise AgentError("El fichero supera el tamaño máximo (20 MB).", 413)
    return raw


def _obd_preview(db: Session, p: ObdFile) -> str:
    from .obd.carscanner import CsvFormatError, parse_csv
    from .obd.textreport import parse_text
    from .routers.diagnostics import resolve_tz

    v = _vehicle(db, p.vehiculo)
    raw = _obd_bytes(p)
    try:
        parsed = parse_csv(raw, p.fecha or date.today(), resolve_tz(None))
    except CsvFormatError:
        parsed = None
    if parsed is not None and parsed.samples:
        times = [t for t, _, _ in parsed.samples]
        return "Importar en {} «{}»: {} lecturas de {} sensores ({:%d/%m %H:%M}–{:%H:%M})".format(
            v.name, p.nombre, len(parsed.samples), len({k for _, k, _ in parsed.samples}), min(times), max(times))
    report = parse_text(raw)
    if report.empty:
        raise AgentError("No reconozco nada en el fichero: ni lecturas, ni códigos de avería, ni valores de sensores.", 422)
    bits = [f"{len(report.values)} valores"]
    if report.dtcs:
        codes = sorted({c for found in report.dtcs.values() for c in found})
        if codes:
            bits.append("códigos " + ", ".join(codes[:6]))
    return "Importar en {} el informe «{}»: {}".format(v.name, p.nombre, ", ".join(bits))


@agent.tool("importar_obd", "Importa un CSV o TXT de Car Scanner (lecturas del OBD, códigos de avería) que Andrea le pasa a ágora",
            write=True, preview=_obd_preview)
def importar_obd(db: Session, p: ObdFile):
    from fastapi import HTTPException

    from .routers.diagnostics import import_content

    v = _vehicle(db, p.vehiculo)
    try:
        res = import_content(db, v, _obd_bytes(p), p.nombre, p.fecha, None, p.nombre)
    except HTTPException as e:
        raise AgentError(str(e.detail), e.status_code)
    out = {"vehiculo": v.name, "lecturas": res.samples, "ver": f"/v/{v.id}/diagnostics"}
    if res.dtcs:
        out["codigos"] = res.dtcs
    if res.vin:
        out["bastidor"] = res.vin
    return out
