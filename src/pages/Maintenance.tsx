import { useState } from "react";
import { api, type Task, type Vehicle } from "../api";
import { CrudList } from "../components/CrudList";
import { Modal } from "../components/Modal";
import { RecordForm, type Field } from "../components/RecordForm";
import { IssuesPanel, ChecklistsPanel, SuggestionsButton } from "../components/MechanicsPanels";
import { ReadinessCard } from "../components/ReadinessCard";
import { serviceFields, toServicePayload } from "../forms";
import { ErrorBox, Loading, StatusBadge, useLoad } from "../components/ui";
import type { TabId } from "../router";
import { MAINTENANCE_CATEGORIES, capitalize, date, km, money, today } from "../format";

type Props = { vehicle: Vehicle; detailed: boolean; onVehicleChanged: () => void; goTab: (tab: TabId) => void };

const TASK_FIELDS: Field[] = [
  { name: "name", label: "Tarea", required: true, wide: true },
  { name: "category", label: "Categoría", type: "select", options: MAINTENANCE_CATEGORIES, required: true },
  { name: "interval_km", label: "Cada (km)", type: "number", min: 1, step: "1" },
  { name: "interval_months", label: "Cada (meses)", type: "number", min: 1, step: "1" },
  { name: "last_done_date", label: "Última vez (fecha)", type: "date" },
  { name: "last_done_km", label: "Última vez (km)", type: "number", min: 0, step: "1" },
  { name: "active", label: "Activa", type: "checkbox" },
  { name: "notes", label: "Notas", type: "textarea", advanced: true },
];

function interval(t: Task) {
  const parts = [];
  if (t.interval_km) parts.push(km(t.interval_km));
  if (t.interval_months) parts.push(`${t.interval_months} meses`);
  return parts.join(" o ");
}

/** Mecánica: semáforo, incidencias, revisiones, plan de mantenimiento e historial de taller. */
export function Maintenance({ vehicle, detailed, onVehicleChanged, goTab }: Props) {
  const mechanics = useLoad(() => api.mechanics(vehicle.id), [vehicle.id, vehicle.odometer_km]);
  const tasks = useLoad(() => api.tasks.list(vehicle.id), [vehicle.id, vehicle.odometer_km]);
  const services = useLoad(() => api.services.list(vehicle.id), [vehicle.id]);
  const [completing, setCompleting] = useState<Task | null>(null);

  if ((tasks.loading && !tasks.data) || (services.loading && !services.data) || (mechanics.loading && !mechanics.data)) return <Loading />;
  if (mechanics.error) return <ErrorBox message={mechanics.error} onRetry={mechanics.reload} />;
  if (tasks.error) return <ErrorBox message={tasks.error} onRetry={tasks.reload} />;
  if (services.error) return <ErrorBox message={services.error} onRetry={services.reload} />;

  const allTasks = tasks.data ?? [];
  const visibleTasks = detailed ? allTasks : allTasks.filter((t) => t.status !== "inactive");
  const fields = serviceFields(allTasks);
  const refreshAll = () => {
    tasks.reload();
    services.reload();
    mechanics.reload();
    onVehicleChanged();
  };
  const mech = mechanics.data!;

  return (
    <div className="stack">
      <ReadinessCard readiness={mech.readiness} goTab={goTab} />
      <IssuesPanel vehicle={vehicle} issues={mech.issues} detailed={detailed} onChanged={refreshAll} />
      <ChecklistsPanel vehicle={vehicle} mechanics={mech} detailed={detailed} onChanged={refreshAll} />
      <CrudList<Task>
        title="Plan de mantenimiento"
        newLabel="Nueva tarea"
        items={visibleTasks}
        fields={TASK_FIELDS}
        detailed={detailed}
        emptyTitle="Sin tareas en el plan"
        emptyHint="Añade las revisiones periódicas de tu manual de mantenimiento."
        newDefaults={() => ({ category: "otros", active: true })}
        describe={(t) => `la tarea «${t.name}»`}
        create={(d) => api.tasks.create(vehicle.id, d)}
        update={(id, d) => api.tasks.update(vehicle.id, id, d)}
        remove={(id) => api.tasks.remove(vehicle.id, id)}
        onChanged={refreshAll}
        headerExtra={<SuggestionsButton vehicle={vehicle} suggestions={mech.suggestions} onAdded={refreshAll} />}
        extraActions={(t) => (
          <button type="button" className="btn btn--sm btn--ghost" onClick={() => setCompleting(t)} title="Registrar como hecha">
            ✓ Hecho
          </button>
        )}
        renderItem={(t) => (
          <>
            <div className="card__title">
              <strong>{t.name}</strong>
              <StatusBadge status={t.status} />
            </div>
            <div className="card__meta">
              <span>Cada {interval(t) || "—"}</span>
              {t.next_due_km != null && (
                <span>
                  Próxima: {km(t.next_due_km)}
                  {t.remaining_km != null && ` (${t.remaining_km < 0 ? "pasada " : "faltan "}${km(Math.abs(t.remaining_km))})`}
                </span>
              )}
              {t.next_due_date && <span>Antes del {date(t.next_due_date)}</span>}
              {t.status === "unknown" && <span>Registra cuándo se hizo por última vez</span>}
            </div>
            {detailed && (
              <div className="card__meta muted">
                <span>{capitalize(t.category)}</span>
                <span>
                  Última: {date(t.last_done_date)} · {km(t.last_done_km)}
                </span>
                {t.notes && <span>{t.notes}</span>}
              </div>
            )}
          </>
        )}
      />

      <CrudList
        title="Historial de intervenciones"
        newLabel="Nueva intervención"
        items={services.data ?? []}
        fields={fields}
        detailed={detailed}
        emptyTitle="Sin intervenciones registradas"
        emptyHint="Cada visita al taller (o cada cosa que hagas tú) queda aquí con su coste."
        newDefaults={() => ({ date: today(), odometer_km: vehicle.odometer_km, category: "otros" })}
        describe={(s) => `«${s.title}»`}
        create={(d) => api.services.create(vehicle.id, toServicePayload(d))}
        update={(id, d) => api.services.update(vehicle.id, id, toServicePayload(d))}
        remove={(id) => api.services.remove(vehicle.id, id)}
        onChanged={refreshAll}
        renderItem={(s) => (
          <>
            <div className="card__title">
              <strong>{s.title}</strong>
              <span className="amount">{money(s.cost)}</span>
            </div>
            <div className="card__meta">
              <span>{date(s.date)}</span>
              {s.odometer_km != null && <span>{km(s.odometer_km)}</span>}
              <span>{capitalize(s.category)}</span>
              {s.workshop && <span>{s.workshop}</span>}
            </div>
            {detailed && (s.parts || s.description) && (
              <div className="card__meta muted">
                {s.parts && <span>Piezas: {s.parts}</span>}
                {s.description && <span>{s.description}</span>}
              </div>
            )}
          </>
        )}
      />

      {completing && (
        <Modal title={`Hecho: ${completing.name}`} onClose={() => setCompleting(null)}>
          <RecordForm
            fields={fields}
            detailed={detailed}
            submitLabel="Registrar"
            initial={{
              title: completing.name,
              date: today(),
              odometer_km: vehicle.odometer_km,
              task_id: completing.id,
              category: completing.category,
            }}
            onSubmit={(d) => api.services.create(vehicle.id, toServicePayload(d))}
            onDone={() => {
              setCompleting(null);
              refreshAll();
            }}
            onCancel={() => setCompleting(null)}
          />
        </Modal>
      )}
    </div>
  );
}
