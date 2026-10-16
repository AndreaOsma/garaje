import { useState } from "react";
import { api, type InboxItem, type Vehicle } from "../api";
import { EXPENSE_FIELDS, fuelFields, serviceFields, toServicePayload } from "../forms";
import { EXPENSE_CATEGORIES, date, money } from "../format";
import { Modal } from "./Modal";
import { RecordForm } from "./RecordForm";
import { confirmAndRun, useLoad } from "./ui";

type Kind = "fuel" | "service" | "expense";

const KIND_LABEL: Record<Kind, string> = { fuel: "⛽ Repostaje", service: "🔧 Taller", expense: "💶 Gasto" };

type Props = { vehicle: Vehicle; detailed: boolean; onChanged: () => void };

/** Cargos del banco llegados de Soberan, a confirmar como repostaje, taller o gasto. */
export function SoberanInbox({ vehicle, detailed, onChanged }: Props) {
  const inbox = useLoad(() => api.soberan.inbox(vehicle.id), [vehicle.id]);
  const tasks = useLoad(() => api.tasks.list(vehicle.id), [vehicle.id]);
  const [open, setOpen] = useState<{ item: InboxItem; kind: Kind } | null>(null);

  const items = inbox.data ?? [];
  if (items.length === 0) return null;

  const done = () => {
    setOpen(null);
    inbox.reload();
    onChanged();
  };

  function form(item: InboxItem, kind: Kind) {
    const resolve = (record_id: number) =>
      api.soberan.resolve(item.id, { status: "accepted", record_type: kind, record_id, vehicle_id: vehicle.id });
    if (kind === "fuel") {
      return (
        <RecordForm
          fields={fuelFields(vehicle.fuel_type === "electric")}
          detailed={detailed}
          submitLabel="Guardar repostaje"
          initial={{ date: item.date, total_cost: item.amount, odometer_km: vehicle.odometer_km, full_tank: true, station: item.description }}
          onSubmit={async (d) => resolve((await api.fuel.create(vehicle.id, d)).id)}
          onDone={done}
          onCancel={() => setOpen(null)}
        />
      );
    }
    if (kind === "service") {
      return (
        <RecordForm
          fields={serviceFields(tasks.data ?? [])}
          detailed={detailed}
          submitLabel="Guardar intervención"
          initial={{ date: item.date, cost: item.amount, title: item.description, category: "otros", workshop: item.description }}
          onSubmit={async (d) => resolve((await api.services.create(vehicle.id, toServicePayload(d))).id)}
          onDone={done}
          onCancel={() => setOpen(null)}
        />
      );
    }
    const category = EXPENSE_CATEGORIES.includes(item.suggested_category) ? item.suggested_category : "otros";
    return (
      <RecordForm
        fields={EXPENSE_FIELDS}
        detailed={detailed}
        submitLabel="Guardar gasto"
        initial={{ date: item.date, amount: item.amount, title: item.description, category }}
        onSubmit={async (d) => resolve((await api.expenses.create(vehicle.id, d)).id)}
        onDone={done}
        onCancel={() => setOpen(null)}
      />
    );
  }

  return (
    <section className="panel panel--inbox" aria-label="Movimientos de Soberan por revisar">
      <header className="panel__header">
        <h2>
          Desde Soberan <span className="count count--info">{items.length}</span>
        </h2>
        <span className="muted small">Cargos del banco: confírmalos o descártalos</span>
      </header>
      <ul className="card-list">
        {items.map((item) => (
          <li key={item.id} className="card inbox-item">
            <div className="card__body">
              <div className="card__title">
                <strong>{item.description || "Movimiento sin concepto"}</strong>
                <span className="amount">{money(item.amount)}</span>
              </div>
              <div className="card__meta">
                <span>{date(item.date)}</span>
                {item.category && <span>{item.category}</span>}
                {item.vehicle_id == null && <span className="badge badge--unknown">Sin vehículo asignado</span>}
              </div>
            </div>
            <div className="card__actions inbox-item__actions">
              {(["fuel", "service", "expense"] as Kind[]).map((kind) => (
                <button
                  key={kind}
                  type="button"
                  className={`btn btn--sm ${item.suggested_kind === kind ? "btn--primary" : "btn--ghost"}`}
                  onClick={() => setOpen({ item, kind })}
                  title={item.suggested_kind === kind ? "Sugerido por el comercio" : undefined}
                >
                  {KIND_LABEL[kind]}
                </button>
              ))}
              <button
                type="button"
                className="icon-btn icon-btn--danger"
                aria-label="Descartar"
                title="Descartar (no es del coche)"
                onClick={() =>
                  confirmAndRun(
                    "¿Descartar este movimiento? No volverá a aparecer.",
                    () => api.soberan.resolve(item.id, { status: "dismissed" }),
                    inbox.reload
                  )
                }
              >
                ✕
              </button>
            </div>
          </li>
        ))}
      </ul>
      {open && (
        <Modal title={`${KIND_LABEL[open.kind]} · ${money(open.item.amount)}`} onClose={() => setOpen(null)}>
          {open.kind === "fuel" && <p className="muted small">Añade los litros y los km: el banco solo sabe el importe.</p>}
          {form(open.item, open.kind)}
        </Modal>
      )}
    </section>
  );
}
