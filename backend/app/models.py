"""Modelos SQLAlchemy de Garaje.

Un Vehicle es la raíz de todo: mantenimiento (plan + historial), repostajes,
gastos, vencimientos y diagnóstico OBD (DTC, sesiones, muestras, últimos valores)
cuelgan de él y se borran en cascada.
"""
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from .database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"
    # Índice único (no constraint): SQLite no admite añadir UNIQUE con ALTER TABLE.
    __table_args__ = (Index("ix_vehicles_soberan_property_id", "soberan_property_id", unique=True),)

    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    make = Column(String(60), default="")
    model = Column(String(60), default="")
    year = Column(Integer, nullable=True)
    vin = Column(String(17), default="")
    plate = Column(String(16), default="")
    # gasoline | diesel | hybrid | phev | electric | lpg
    fuel_type = Column(String(16), nullable=False, default="gasoline")
    engine = Column(String(80), default="")
    # Cilindros del motor (en línea) para el visor «Motor por dentro»; nulo = 4.
    cylinders = Column(Integer, nullable=True)
    # Color de la carrocería (#rrggbb) para el modelo 3D en modo «Exterior».
    color = Column(String(7), nullable=True)
    purchase_date = Column(Date, nullable=True)
    odometer_km = Column(Integer, nullable=False, default=0)
    odometer_updated_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, default="")
    archived = Column(Boolean, nullable=False, default=False)
    # sha256 del token de ingesta OBD; el token en claro solo se muestra al generarlo.
    ingest_token_hash = Column(String(64), nullable=True, unique=True, index=True)
    # Último estado conocido de la ECU (PID 01 + ATRV), actualizado por la ingesta.
    mil_on = Column(Boolean, nullable=True)
    ecu_dtc_count = Column(Integer, nullable=True)
    monitors = Column(JSON, nullable=True)
    last_obd_at = Column(DateTime(timezone=True), nullable=True)
    # Enlace con Soberan (patrimonio + finanzas): ids de su Property (tipo vehiculo) y de
    # la Debt de la financiación, y lo último que Soberan nos ha contado de ellas.
    soberan_property_id = Column(Integer, nullable=True)
    soberan_debt_id = Column(Integer, nullable=True)
    market_value = Column(Float, nullable=True)
    market_value_at = Column(DateTime(timezone=True), nullable=True)
    market_value_confidence = Column(String(8), nullable=True)
    debt_pending = Column(Float, nullable=True)
    debt_monthly = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tasks = relationship("MaintenanceTask", back_populates="vehicle", cascade="all, delete-orphan", passive_deletes=True)
    services = relationship("ServiceRecord", back_populates="vehicle", cascade="all, delete-orphan", passive_deletes=True)
    fuel_entries = relationship("FuelEntry", back_populates="vehicle", cascade="all, delete-orphan", passive_deletes=True)
    expenses = relationship("Expense", back_populates="vehicle", cascade="all, delete-orphan", passive_deletes=True)
    deadlines = relationship("Deadline", back_populates="vehicle", cascade="all, delete-orphan", passive_deletes=True)
    dtcs = relationship("Dtc", back_populates="vehicle", cascade="all, delete-orphan", passive_deletes=True)
    obd_sessions = relationship("ObdSession", back_populates="vehicle", cascade="all, delete-orphan", passive_deletes=True)
    latest_values = relationship("ObdLatestValue", back_populates="vehicle", cascade="all, delete-orphan", passive_deletes=True)
    issues = relationship("Issue", back_populates="vehicle", cascade="all, delete-orphan", passive_deletes=True)
    checklist_runs = relationship("ChecklistRun", back_populates="vehicle", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def has_ingest_token(self) -> bool:
        return bool(self.ingest_token_hash)


class MaintenanceTask(Base):
    """Tarea del plan de mantenimiento: se repite cada interval_km y/o interval_months."""

    __tablename__ = "maintenance_tasks"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    category = Column(String(32), nullable=False, default="otros")
    interval_km = Column(Integer, nullable=True)
    interval_months = Column(Integer, nullable=True)
    last_done_date = Column(Date, nullable=True)
    last_done_km = Column(Integer, nullable=True)
    notes = Column(Text, default="")
    active = Column(Boolean, nullable=False, default=True)

    vehicle = relationship("Vehicle", back_populates="tasks")


class ServiceRecord(Base):
    """Intervención real (taller o bricolaje). Si task_id apunta a una tarea, la reinicia."""

    __tablename__ = "service_records"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("maintenance_tasks.id", ondelete="SET NULL"), nullable=True)
    date = Column(Date, nullable=False)
    odometer_km = Column(Integer, nullable=True)
    category = Column(String(32), nullable=False, default="otros")
    title = Column(String(160), nullable=False)
    description = Column(Text, default="")
    parts = Column(Text, default="")
    workshop = Column(String(120), default="")
    cost = Column(Float, nullable=False, default=0.0)

    vehicle = relationship("Vehicle", back_populates="services")


class FuelEntry(Base):
    __tablename__ = "fuel_entries"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    odometer_km = Column(Integer, nullable=False)
    # Litros (o kWh en eléctricos).
    quantity = Column(Float, nullable=False)
    # Lo realmente pagado (lo que sale del banco), ya con el descuento aplicado.
    total_cost = Column(Float, nullable=False)
    # Descuento en € (club de fidelidad, cupón, c€/L de supermercado…): surtidor = total_cost + discount.
    discount = Column(Float, nullable=False, default=0.0, server_default="0")
    full_tank = Column(Boolean, nullable=False, default=True)
    station = Column(String(120), default="")
    notes = Column(Text, default="")

    vehicle = relationship("Vehicle", back_populates="fuel_entries")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    category = Column(String(32), nullable=False, default="otros")
    title = Column(String(160), nullable=False)
    amount = Column(Float, nullable=False)
    notes = Column(Text, default="")

    vehicle = relationship("Vehicle", back_populates="expenses")


class Deadline(Base):
    """Vencimiento de documentación: ITV, seguro, impuesto, garantía…"""

    __tablename__ = "deadlines"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(16), nullable=False, default="otro")
    title = Column(String(160), nullable=False)
    due_date = Column(Date, nullable=False)
    notes = Column(Text, default="")
    done = Column(Boolean, nullable=False, default=False)

    vehicle = relationship("Vehicle", back_populates="deadlines")


class Dtc(Base):
    """Código de avería. Una fila por aparición: al borrarse en la ECU se marca cleared_at
    y, si vuelve a salir, se abre una fila nueva (así queda el historial)."""

    __tablename__ = "dtcs"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(8), nullable=False)
    # stored | pending | permanent
    kind = Column(String(12), nullable=False, default="stored")
    # agent | carscanner | manual
    source = Column(String(16), nullable=False, default="manual")
    first_seen = Column(DateTime(timezone=True), nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=False)
    occurrences = Column(Integer, nullable=False, default=1)
    cleared_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, default="")

    vehicle = relationship("Vehicle", back_populates="dtcs")


class ObdSession(Base):
    __tablename__ = "obd_sessions"
    __table_args__ = (UniqueConstraint("vehicle_id", "source", "external_id", name="uq_obd_session_external"),)

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    # agent | carscanner
    source = Column(String(16), nullable=False)
    external_id = Column(String(64), nullable=False)
    label = Column(String(160), default="")
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=False)
    sample_count = Column(Integer, nullable=False, default=0)

    vehicle = relationship("Vehicle", back_populates="obd_sessions")
    samples = relationship("ObdSample", back_populates="session", cascade="all, delete-orphan", passive_deletes=True)


class ObdSample(Base):
    __tablename__ = "obd_samples"
    __table_args__ = (Index("ix_obd_samples_session_key_ts", "session_id", "key", "ts"),)

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("obd_sessions.id", ondelete="CASCADE"), nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False)
    # PID estándar en hex ("0C"), clave especial ("BATT") o sensor libre ("cs:engine-oil-temperature").
    key = Column(String(64), nullable=False)
    value = Column(Float, nullable=False)

    session = relationship("ObdSession", back_populates="samples")


class ObdLatestValue(Base):
    """Último valor conocido por sensor y vehículo, para pintar Inicio sin recorrer muestras."""

    __tablename__ = "obd_latest_values"
    __table_args__ = (UniqueConstraint("vehicle_id", "key", name="uq_obd_latest_vehicle_key"),)

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(64), nullable=False)
    value = Column(Float, nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False)

    vehicle = relationship("Vehicle", back_populates="latest_values")


class ObdSensor(Base):
    """Nombre/unidad de sensores no estándar descubiertos al importar (p.ej. columnas de Car Scanner)."""

    __tablename__ = "obd_sensors"

    key = Column(String(64), primary_key=True)
    name = Column(String(120), nullable=False)
    unit = Column(String(24), default="")


class AppSetting(Base):
    """Clave/valor JSON para estado global (p.ej. la última instantánea de Soberan)."""

    __tablename__ = "app_settings"

    key = Column(String(64), primary_key=True)
    value = Column(JSON, nullable=True)


class InboxItem(Base):
    """Movimiento bancario llegado de Soberan, pendiente de convertir en repostaje,
    intervención o gasto (o de descartar). Nunca se crea el registro sin confirmación:
    a un cargo de gasolinera le faltan los litros y los km."""

    __tablename__ = "inbox_items"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_inbox_source_external"),)

    id = Column(Integer, primary_key=True)
    source = Column(String(16), nullable=False, default="soberan")
    external_id = Column(String(64), nullable=False)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True, index=True)
    date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String(255), default="")
    category = Column(String(80), default="")
    # fuel | service | expense
    suggested_kind = Column(String(8), nullable=False, default="expense")
    suggested_category = Column(String(32), default="otros")
    # pending | accepted | dismissed
    status = Column(String(10), nullable=False, default="pending", index=True)
    record_type = Column(String(8), nullable=True)
    record_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Issue(Base):
    """Incidencia mecánica detectada (ruido, fuga, testigo, fallo en una revisión…) y su
    resolución. La gravedad alimenta el semáforo «¿listo para circular?»."""

    __tablename__ = "issues"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    reported_on = Column(Date, nullable=False)
    odometer_km = Column(Integer, nullable=True)
    title = Column(String(160), nullable=False)
    description = Column(Text, default="")
    # info (aviso) | limiting (circular con precaución) | grounding (no circular)
    severity = Column(String(12), nullable=False, default="info")
    category = Column(String(32), nullable=False, default="otros")
    dtc_code = Column(String(8), nullable=True)
    resolved_on = Column(Date, nullable=True)
    resolution = Column(Text, default="")
    service_id = Column(Integer, ForeignKey("service_records.id", ondelete="SET NULL"), nullable=True)

    vehicle = relationship("Vehicle", back_populates="issues")


class Checklist(Base):
    """Revisión punto a punto. vehicle_id nulo = plantilla común a todos los vehículos."""

    __tablename__ = "checklists"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    # Cada cuánto conviene hacerla (para avisar); nulo = cuando toque (p.ej. antes de un viaje).
    interval_days = Column(Integer, nullable=True)
    # [{"title": "Niveles", "items": [{"label": "Aceite", "check": "Entre MIN y MAX"}]}]
    sections = Column(JSON, nullable=False, default=list)
    position = Column(Integer, nullable=False, default=0)


class ChecklistRun(Base):
    __tablename__ = "checklist_runs"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id", ondelete="SET NULL"), nullable=True)
    checklist_name = Column(String(120), nullable=False)
    date = Column(Date, nullable=False)
    odometer_km = Column(Integer, nullable=True)
    # [{"section", "label", "check", "ok": bool, "note"}]
    results = Column(JSON, nullable=False, default=list)
    failed = Column(Integer, nullable=False, default=0)

    vehicle = relationship("Vehicle", back_populates="checklist_runs")


class DtcDefinition(Base):
    """Diccionario propio de códigos: lo que se aprende de los informes importados
    (source=import) y lo que escribes a mano (source=manual, nunca se pisa). make vacío =
    vale para cualquier marca; si no, solo para esa (los códigos P1/C1/B1/U1… cambian de
    significado entre fabricantes)."""

    __tablename__ = "dtc_definitions"
    __table_args__ = (UniqueConstraint("code", "make", name="uq_dtc_definition_code_make"),)

    id = Column(Integer, primary_key=True)
    code = Column(String(8), nullable=False, index=True)
    make = Column(String(60), nullable=False, default="")
    description = Column(String(300), nullable=False)
    # baja | media | alta; nulo = la del diccionario base (o media).
    severity = Column(String(8), nullable=True)
    # manual | import | web (Claude con búsqueda web) | ia (Ollama local, orientativo)
    source = Column(String(8), nullable=False, default="manual")
    # Búsqueda automática: sistema, causas, consejo, fuentes, confianza, proveedor.
    details = Column(JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
