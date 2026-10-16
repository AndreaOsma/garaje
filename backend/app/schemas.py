"""Esquemas Pydantic de entrada/salida. Las entradas acotan longitudes y rangos."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from .obd.dtc import normalize_code


def _iso_utc(value: datetime) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


UtcDateTime = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]

FuelType = Literal["gasoline", "diesel", "hybrid", "phev", "electric", "lpg"]
DtcKind = Literal["stored", "pending", "permanent"]
Km = Annotated[int, Field(ge=0, le=5_000_000)]
Money = Annotated[float, Field(ge=0, le=10_000_000)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Vehículos ---------------------------------------------------------------

class VehicleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    make: str = Field("", max_length=60)
    model: str = Field("", max_length=60)
    year: Optional[int] = Field(None, ge=1886, le=2100)
    vin: str = Field("", max_length=17)
    plate: str = Field("", max_length=16)
    fuel_type: FuelType = "gasoline"
    engine: str = Field("", max_length=80)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    cylinders: Optional[int] = Field(None, ge=2, le=6)
    purchase_date: Optional[date] = None
    odometer_km: Km = 0
    notes: str = Field("", max_length=5000)
    archived: bool = False

    @field_validator("vin")
    @classmethod
    def _vin(cls, v: str) -> str:
        v = v.strip().upper()
        if v and (len(v) != 17 or any(c in "IOQ" for c in v) or not v.isalnum()):
            raise ValueError("El VIN tiene 17 caracteres alfanuméricos (sin I, O ni Q)")
        return v


class VehicleCreate(VehicleIn):
    with_default_plan: bool = True


class VehicleOut(ORM):
    id: int
    name: str
    make: str
    model: str
    year: Optional[int]
    vin: str
    plate: str
    fuel_type: str
    engine: str
    color: Optional[str] = None
    cylinders: Optional[int] = None
    purchase_date: Optional[date]
    odometer_km: int
    odometer_updated_at: Optional[UtcDateTime]
    notes: str
    archived: bool
    has_ingest_token: bool
    mil_on: Optional[bool]
    ecu_dtc_count: Optional[int]
    monitors: Optional[dict]
    last_obd_at: Optional[UtcDateTime]
    soberan_property_id: Optional[int] = None
    soberan_debt_id: Optional[int] = None
    market_value: Optional[float] = None
    market_value_at: Optional[UtcDateTime] = None
    market_value_confidence: Optional[str] = None
    debt_pending: Optional[float] = None
    debt_monthly: Optional[float] = None


class OdometerIn(BaseModel):
    odometer_km: Km


class TokenOut(BaseModel):
    token: str


# --- Mantenimiento -----------------------------------------------------------

class TaskIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field("otros", max_length=32)
    interval_km: Optional[int] = Field(None, ge=1, le=1_000_000)
    interval_months: Optional[int] = Field(None, ge=1, le=240)
    last_done_date: Optional[date] = None
    last_done_km: Optional[Km] = None
    notes: str = Field("", max_length=2000)
    active: bool = True


class TaskOut(ORM):
    id: int
    name: str
    category: str
    interval_km: Optional[int]
    interval_months: Optional[int]
    last_done_date: Optional[date]
    last_done_km: Optional[int]
    notes: str
    active: bool
    next_due_km: Optional[int] = None
    next_due_date: Optional[date] = None
    remaining_km: Optional[int] = None
    remaining_days: Optional[int] = None
    status: str = "unknown"


class ServiceIn(BaseModel):
    task_id: Optional[int] = None
    date: date
    odometer_km: Optional[Km] = None
    category: str = Field("otros", max_length=32)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field("", max_length=5000)
    parts: str = Field("", max_length=2000)
    workshop: str = Field("", max_length=120)
    cost: Money = 0


class ServiceOut(ORM):
    id: int
    task_id: Optional[int]
    date: date
    odometer_km: Optional[int]
    category: str
    title: str
    description: str
    parts: str
    workshop: str
    cost: float


# --- Repostajes, gastos y vencimientos ---------------------------------------

class FuelIn(BaseModel):
    date: date
    odometer_km: Km
    quantity: float = Field(gt=0, le=2000)
    # Lo pagado de verdad, ya descontado.
    total_cost: Money
    discount: Optional[Money] = 0
    # Alternativa cómoda: céntimos por litro/kWh. Si viene, manda sobre `discount`.
    discount_cents_per_unit: Optional[float] = Field(None, ge=0, le=200)
    full_tank: bool = True
    station: str = Field("", max_length=120)
    notes: str = Field("", max_length=2000)

    def to_record(self) -> dict:
        data = self.model_dump(exclude={"discount_cents_per_unit"})
        if self.discount_cents_per_unit:
            data["discount"] = round(self.discount_cents_per_unit * self.quantity / 100, 2)
        data["discount"] = data["discount"] or 0.0
        return data


class FuelOut(ORM):
    id: int
    date: date
    odometer_km: int
    quantity: float
    total_cost: float
    discount: float = 0.0
    full_tank: bool
    station: str
    notes: str
    # Precio efectivo (lo pagado / cantidad) y el del surtidor (antes del descuento).
    price_per_unit: Optional[float] = None
    pump_price_per_unit: Optional[float] = None
    consumption: Optional[float] = None


class FuelListOut(BaseModel):
    entries: list[FuelOut]
    avg_consumption: Optional[float]
    unit: str
    total_discount: float = 0.0


class ExpenseIn(BaseModel):
    date: date
    category: str = Field("otros", max_length=32)
    title: str = Field(min_length=1, max_length=160)
    amount: Money
    notes: str = Field("", max_length=2000)


class ExpenseOut(ORM):
    id: int
    date: date
    category: str
    title: str
    amount: float
    notes: str


class DeadlineIn(BaseModel):
    kind: str = Field("otro", max_length=16)
    title: str = Field(min_length=1, max_length=160)
    due_date: date
    notes: str = Field("", max_length=2000)
    done: bool = False


class DeadlineOut(ORM):
    id: int
    kind: str
    title: str
    due_date: date
    notes: str
    done: bool
    status: str = "ok"
    days_left: int = 0


# --- Diagnóstico -------------------------------------------------------------

class DtcIn(BaseModel):
    code: str = Field(min_length=5, max_length=5)
    kind: DtcKind = "stored"
    notes: str = Field("", max_length=2000)

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        code = normalize_code(v)
        if not code:
            raise ValueError("Formato de código no válido (ej. P0420)")
        return code


class DtcNotesIn(BaseModel):
    notes: str = Field("", max_length=2000)


class DtcOut(ORM):
    id: int
    code: str
    kind: str
    source: str
    first_seen: UtcDateTime
    last_seen: UtcDateTime
    occurrences: int
    cleared_at: Optional[UtcDateTime]
    notes: str
    description: str = ""
    system: str = ""
    severity: str = "media"
    generic: bool = True
    # manual | import | web | ia si la descripción sale de tu diccionario propio.
    learned: Optional[str] = None
    # Búsqueda automática: causas, consejo, fuentes, confianza, proveedor.
    details: Optional[dict] = None


class DtcDefinitionIn(BaseModel):
    description: str = Field(min_length=3, max_length=300)
    severity: Optional[Literal["baja", "media", "alta"]] = None
    all_makes: bool = False


class SessionOut(ORM):
    id: int
    source: str
    label: str
    started_at: UtcDateTime
    ended_at: UtcDateTime
    sample_count: int


class SensorSeries(BaseModel):
    key: str
    name: str
    unit: str
    group: str
    count: int
    min: float
    max: float
    avg: float
    # Serie reducida (máx. ~120 puntos) para la gráfica: [epoch_ms, valor].
    points: list[tuple[int, float]]


class SessionDetailOut(BaseModel):
    session: SessionOut
    series: list[SensorSeries]


class LiveValueOut(BaseModel):
    key: str
    name: str
    unit: str
    group: str
    value: float
    ts: UtcDateTime


# --- Ingesta -----------------------------------------------------------------

class SampleIn(BaseModel):
    ts: datetime
    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9:_\-.]+$")
    value: float = Field(allow_inf_nan=False)


class MonitorIn(BaseModel):
    mil_on: bool
    dtc_count: int = Field(ge=0, le=127)
    ignition: str = Field("", max_length=16)
    monitors: list[dict] = Field(default_factory=list, max_length=16)
    ready: bool = False


class SnapshotIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-.]+$")
    source: Literal["agent"] = "agent"
    samples: list[SampleIn] = Field(default_factory=list)
    dtcs: Optional[dict[DtcKind, list[str]]] = None
    monitor: Optional[MonitorIn] = None
    vin: Optional[str] = Field(None, max_length=17)

    @field_validator("dtcs")
    @classmethod
    def _dtcs(cls, v):
        if v is None:
            return v
        return {kind: [c for c in (normalize_code(x) for x in codes[:64]) if c] for kind, codes in v.items()}


class IngestResult(BaseModel):
    session_id: Optional[int]
    samples: int
    skipped_rows: int = 0
    # log (lecturas en el tiempo) | report (informe/foto: códigos, valores sueltos, VIN)
    kind: str = "log"
    dtcs: dict[str, list[str]] = Field(default_factory=dict)
    vin: Optional[str] = None
    learned: int = 0
    reprocessed: bool = False


# --- Inicio ------------------------------------------------------------------

class Alert(BaseModel):
    level: Literal["danger", "warning", "info"]
    kind: str
    title: str
    detail: str = ""
    target: str = ""


class CostSummary(BaseModel):
    total: float
    last_12_months: float
    by_category: dict[str, float]
    cost_per_km: Optional[float]
    km_tracked: int


class DashboardOut(BaseModel):
    vehicle: VehicleOut
    alerts: list[Alert]
    costs: CostSummary
    avg_consumption: Optional[float]
    consumption_unit: str
    active_dtcs: int
    live: list[LiveValueOut]
    next_tasks: list[TaskOut]
    inbox_pending: int = 0
    readiness: Optional["Readiness"] = None


# --- Soberan -----------------------------------------------------------------

class SoberanProperty(BaseModel):
    id: int
    nombre: str = Field("", max_length=200)
    marca: Optional[str] = Field(None, max_length=80)
    modelo: Optional[str] = Field(None, max_length=80)
    anio: Optional[int] = None
    matricula: Optional[str] = Field(None, max_length=20)
    bastidor: Optional[str] = Field(None, max_length=20)
    km: Optional[int] = None
    valor_estimado: Optional[float] = None
    valor_actualizado_en: Optional[datetime] = None
    confianza: Optional[str] = Field(None, max_length=8)


class SoberanDebt(BaseModel):
    id: int
    nombre: str = Field("", max_length=200)
    acreedor: str = Field("", max_length=200)
    pendiente: float
    cuota_mensual: Optional[float] = None


class SoberanTransaction(BaseModel):
    id: int
    date: date
    amount: float = Field(allow_inf_nan=False)
    description: str = Field("", max_length=500)
    category: str = Field("", max_length=80)


class SoberanSyncIn(BaseModel):
    properties: list[SoberanProperty] = Field(default_factory=list, max_length=200)
    debts: list[SoberanDebt] = Field(default_factory=list, max_length=200)
    categories: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=500)
    transactions: list[SoberanTransaction] = Field(default_factory=list, max_length=5000)


class SoberanLinkIn(BaseModel):
    property_id: Optional[int] = None
    debt_id: Optional[int] = None


class SoberanSettingsIn(BaseModel):
    categories: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=100)


class SoberanStateOut(BaseModel):
    last_sync_at: Optional[str]
    properties: list[dict]
    debts: list[dict]
    categories: list[str]
    selected_categories: list[str]


class InboxOut(ORM):
    id: int
    vehicle_id: Optional[int]
    date: date
    amount: float
    description: str
    category: str
    suggested_kind: str
    suggested_category: str
    status: str


class InboxResolveIn(BaseModel):
    status: Literal["accepted", "dismissed", "pending"]
    record_type: Optional[Literal["fuel", "service", "expense"]] = None
    record_id: Optional[int] = None
    vehicle_id: Optional[int] = None


# --- Mecánica ----------------------------------------------------------------

IssueSeverity = Literal["info", "limiting", "grounding"]


class IssueIn(BaseModel):
    reported_on: date
    odometer_km: Optional[Km] = None
    title: str = Field(min_length=1, max_length=160)
    description: str = Field("", max_length=5000)
    severity: IssueSeverity = "info"
    category: str = Field("otros", max_length=32)
    dtc_code: Optional[str] = Field(None, max_length=8)


class IssueResolveIn(BaseModel):
    resolved_on: date
    resolution: str = Field("", max_length=5000)
    service_id: Optional[int] = None


class IssueOut(ORM):
    id: int
    reported_on: date
    odometer_km: Optional[int]
    title: str
    description: str
    severity: str
    category: str
    dtc_code: Optional[str]
    resolved_on: Optional[date]
    resolution: str
    service_id: Optional[int]


class ChecklistItem(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    check: str = Field("", max_length=200)


class ChecklistSection(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    items: list[ChecklistItem] = Field(max_length=60)


class ChecklistIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    interval_days: Optional[int] = Field(None, ge=1, le=3650)
    sections: list[ChecklistSection] = Field(min_length=1, max_length=30)


class ChecklistOut(ORM):
    id: int
    vehicle_id: Optional[int]
    name: str
    interval_days: Optional[int]
    sections: list[ChecklistSection]
    last_run_on: Optional[date] = None
    last_run_failed: Optional[int] = None
    due: bool = False


class RunResultIn(BaseModel):
    section: str = Field("", max_length=80)
    label: str = Field(min_length=1, max_length=120)
    check: str = Field("", max_length=200)
    ok: Optional[bool] = None
    note: str = Field("", max_length=500)
    severity: IssueSeverity = "info"
    create_issue: bool = True


class ChecklistRunIn(BaseModel):
    checklist_id: int
    date: date
    odometer_km: Optional[Km] = None
    results: list[RunResultIn] = Field(max_length=500)


class ChecklistRunOut(ORM):
    id: int
    checklist_id: Optional[int]
    checklist_name: str
    date: date
    odometer_km: Optional[int]
    results: list[dict]
    failed: int
    issues_created: int = 0


class Readiness(BaseModel):
    status: Literal["go", "caution", "nogo"]
    reasons: list[dict]


class MechanicsOut(BaseModel):
    readiness: Readiness
    issues: list[IssueOut]
    checklists: list[ChecklistOut]
    runs: list[ChecklistRunOut]
    suggestions: list[dict]


class SuggestionsIn(BaseModel):
    names: list[Annotated[str, Field(max_length=120)]] = Field(min_length=1, max_length=50)


# DashboardOut referencia Readiness, definida más abajo.
DashboardOut.model_rebuild()
