import { api, type Deadline, type Expense, type FuelEntry, type Vehicle } from "../api";
import { CrudList } from "../components/CrudList";
import { SoberanInbox } from "../components/SoberanInbox";
import type { Field } from "../components/RecordForm";
import { ErrorBox, Loading, Stat, StatusBadge, useLoad } from "../components/ui";
import { EXPENSE_FIELDS, fuelFields } from "../forms";
import { DEADLINE_KINDS, capitalize, date, km, money, num, today, unitPrice } from "../format";

type Props = { vehicle: Vehicle; detailed: boolean; onVehicleChanged: () => void };

// --- Repostajes --------------------------------------------------------------

export function Fuel({ vehicle, detailed, onVehicleChanged }: Props) {
  const { data, error, loading, reload } = useLoad(() => api.fuel.list(vehicle.id), [vehicle.id]);
  const electric = vehicle.fuel_type === "electric";
  const unit = electric ? "kWh" : "L";

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const fields = fuelFields(electric);

  const entries = data.entries;
  const totalCost = entries.reduce((sum, e) => sum + e.total_cost, 0);
  const last = entries.find((e) => e.price_per_unit != null);
  const lastPrice = last?.price_per_unit ?? null;

  return (
    <div className="stack">
      <section className="stats" aria-label="Resumen de repostajes">
        <Stat label="Consumo medio" value={data.avg_consumption != null ? num(data.avg_consumption, 2) : "—"} hint={data.unit} />
        <Stat
          label="Último precio pagado"
          value={unitPrice(lastPrice)}
          hint={
            last && last.discount > 0 && last.pump_price_per_unit != null
              ? `por ${unit} · surtidor ${unitPrice(last.pump_price_per_unit)}`
              : `por ${unit}`
          }
        />
        <Stat label="Gastado en total" value={money(totalCost)} hint={`${entries.length} repostajes`} />
        {data.total_discount > 0 && (
          <Stat label="Ahorrado en descuentos" value={money(data.total_discount)} hint={`${num((data.total_discount / (totalCost + data.total_discount)) * 100, 1)} % del surtidor`} />
        )}
      </section>
      <CrudList<FuelEntry>
        title="Repostajes"
        newLabel="Nuevo repostaje"
        items={entries}
        fields={fields}
        detailed={detailed}
        emptyTitle="Sin repostajes"
        emptyHint="Marca «depósito lleno» siempre que llenes: el consumo se calcula entre dos llenados."
        newDefaults={() => ({ date: today(), odometer_km: vehicle.odometer_km, full_tank: true })}
        describe={(e) => `el repostaje del ${date(e.date)}`}
        create={(d) => api.fuel.create(vehicle.id, d)}
        update={(id, d) => api.fuel.update(vehicle.id, id, d)}
        remove={(id) => api.fuel.remove(vehicle.id, id)}
        onChanged={() => {
          reload();
          onVehicleChanged();
        }}
        renderItem={(e) => (
          <>
            <div className="card__title">
              <strong>
                {num(e.quantity, 2)} {unit}
                {!e.full_tank && <span className="muted"> · parcial</span>}
              </strong>
              <span className="amount">{money(e.total_cost)}</span>
            </div>
            <div className="card__meta">
              <span>{date(e.date)}</span>
              <span>{km(e.odometer_km)}</span>
              {e.discount > 0 && <span className="discount">−{money(e.discount)} dto.</span>}
              {e.consumption != null && (
                <span>
                  {num(e.consumption, 2)} {data.unit}
                </span>
              )}
              {detailed && e.price_per_unit != null && (
                <span>
                  {unitPrice(e.price_per_unit)}/{unit}
                  {e.discount > 0 && e.pump_price_per_unit != null && ` (surtidor ${unitPrice(e.pump_price_per_unit)})`}
                </span>
              )}
              {detailed && e.station && <span>{e.station}</span>}
            </div>
          </>
        )}
      />
    </div>
  );
}

// --- Gastos ------------------------------------------------------------------


export function Expenses({ vehicle, detailed, onVehicleChanged }: Props) {
  const { data, error, loading, reload } = useLoad(() => api.expenses.list(vehicle.id), [vehicle.id]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;

  const year = String(new Date().getFullYear());
  const thisYear = (data ?? []).filter((e) => e.date.startsWith(year)).reduce((s, e) => s + e.amount, 0);

  return (
    <div className="stack">
      <SoberanInbox
        vehicle={vehicle}
        detailed={detailed}
        onChanged={() => {
          reload();
          onVehicleChanged();
        }}
      />
      <section className="stats" aria-label="Resumen de gastos">
        <Stat label={`Gastos ${year}`} value={money(thisYear)} hint="sin combustible ni taller" />
      </section>
      <CrudList<Expense>
        title="Otros gastos"
        newLabel="Nuevo gasto"
        items={data ?? []}
        fields={EXPENSE_FIELDS}
        detailed={detailed}
        emptyTitle="Sin gastos"
        emptyHint="Seguro, impuesto de circulación, ITV, parking, peajes, multas…"
        newDefaults={() => ({ date: today(), category: "seguro" })}
        describe={(e) => `«${e.title}»`}
        create={(d) => api.expenses.create(vehicle.id, d)}
        update={(id, d) => api.expenses.update(vehicle.id, id, d)}
        remove={(id) => api.expenses.remove(vehicle.id, id)}
        onChanged={reload}
        renderItem={(e) => (
          <>
            <div className="card__title">
              <strong>{e.title}</strong>
              <span className="amount">{money(e.amount)}</span>
            </div>
            <div className="card__meta">
              <span>{date(e.date)}</span>
              <span>{capitalize(e.category)}</span>
              {detailed && e.notes && <span className="muted">{e.notes}</span>}
            </div>
          </>
        )}
      />
    </div>
  );
}

// --- Documentos y vencimientos -----------------------------------------------

const DEADLINE_FIELDS: Field[] = [
  { name: "title", label: "Documento", required: true, wide: true, placeholder: "ITV, póliza de seguro…" },
  { name: "kind", label: "Tipo", type: "select", options: DEADLINE_KINDS, required: true },
  { name: "due_date", label: "Caduca el", type: "date", required: true },
  { name: "done", label: "Renovado / ya no aplica", type: "checkbox" },
  { name: "notes", label: "Notas (nº de póliza, estación de ITV…)", type: "textarea", advanced: true },
];

export function Documents({ vehicle, detailed }: Props) {
  const { data, error, loading, reload } = useLoad(() => api.deadlines.list(vehicle.id), [vehicle.id]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;

  const items = (data ?? []).filter((d) => detailed || !d.done);

  return (
    <CrudList<Deadline>
      title="Documentos y vencimientos"
      newLabel="Nuevo vencimiento"
      items={items}
      fields={DEADLINE_FIELDS}
      detailed={detailed}
      emptyTitle="Sin vencimientos"
      emptyHint="Apunta la próxima ITV, la renovación del seguro y el impuesto: te avisará 30 días antes."
      newDefaults={() => ({ kind: "itv", title: "ITV" })}
      describe={(d) => `«${d.title}»`}
      create={(d) => api.deadlines.create(vehicle.id, d)}
      update={(id, d) => api.deadlines.update(vehicle.id, id, d)}
      remove={(id) => api.deadlines.remove(vehicle.id, id)}
      onChanged={reload}
      renderItem={(d) => (
        <>
          <div className="card__title">
            <strong>{d.title}</strong>
            <StatusBadge
              status={d.status}
              label={d.done ? "Hecho" : d.days_left < 0 ? `Caducado hace ${-d.days_left} d` : `${d.days_left} días`}
            />
          </div>
          <div className="card__meta">
            <span>{capitalize(d.kind)}</span>
            <span>Caduca el {date(d.due_date)}</span>
            {detailed && d.notes && <span className="muted">{d.notes}</span>}
          </div>
        </>
      )}
    />
  );
}
