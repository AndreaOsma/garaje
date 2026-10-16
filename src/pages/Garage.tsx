import { api, type Vehicle } from "../api";
import { RecordForm } from "../components/RecordForm";
import { EmptyState } from "../components/ui";
import { AiSettingsCard } from "../vendor/ai-providers/AiSettingsCard";
import { FUEL_LABELS, km } from "../format";
import { VEHICLE_FIELDS } from "./VehicleSettings";

type GarageProps = {
  vehicles: Vehicle[];
  detailed: boolean;
  onOpen: (id: number) => void;
  onNew: () => void;
};

export function Garage({ vehicles, detailed, onOpen, onNew }: GarageProps) {
  const visible = detailed ? vehicles : vehicles.filter((v) => !v.archived);
  return (
    <>
    <section className="panel" aria-label="Tus vehículos">
      <header className="panel__header">
        <h2>Tus vehículos</h2>
        <button type="button" className="btn btn--primary btn--sm" onClick={onNew}>
          + Añadir vehículo
        </button>
      </header>
      {visible.length === 0 ? (
        <EmptyState title="Tu garaje está vacío">
          Añade tu coche para llevar su mantenimiento, gastos, documentación y diagnóstico OBD.
        </EmptyState>
      ) : (
        <ul className="vehicle-grid">
          {visible.map((v) => (
            <li key={v.id}>
              <button type="button" className={`vehicle-card${v.archived ? " is-archived" : ""}`} onClick={() => onOpen(v.id)}>
                <span className="vehicle-card__name">{v.name}</span>
                <span className="muted">{[v.make, v.model, v.year].filter(Boolean).join(" ") || FUEL_LABELS[v.fuel_type]}</span>
                <span className="vehicle-card__meta">
                  <span>{km(v.odometer_km)}</span>
                  {v.plate && <span className="plate">{v.plate}</span>}
                  {v.mil_on && <span className="badge badge--overdue">! MIL</span>}
                  {v.archived && <span className="badge badge--inactive">Archivado</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
    <AiSettingsCard purpose="Se usa para averiguar qué significa un código de avería de fabricante en tu marca y modelo. Pon tu propia clave o tu servidor Ollama: con Claude busca en la web; con el resto, la respuesta es orientativa." />
    </>
  );
}

type NewProps = { detailed: boolean; onCreated: (v: Vehicle) => void; onCancel: () => void };

export function NewVehicle({ detailed, onCreated, onCancel }: NewProps) {
  return (
    <section className="panel" aria-label="Nuevo vehículo">
      <header className="panel__header">
        <h2>Nuevo vehículo</h2>
      </header>
      <p className="muted">
        Se crea con un plan de mantenimiento orientativo según el combustible (aceite, filtros, frenos, distribución…). Ajústalo luego a
        tu manual.
      </p>
      <RecordForm
        fields={VEHICLE_FIELDS.filter((f) => f.name !== "archived")}
        detailed={detailed}
        initial={{ fuel_type: "gasoline", odometer_km: 0 }}
        submitLabel="Crear vehículo"
        onSubmit={async (d) => {
          const v = await api.vehicles.create({ ...d, with_default_plan: true });
          setTimeout(() => onCreated(v), 0);
          return v;
        }}
        onCancel={onCancel}
      />
    </section>
  );
}
