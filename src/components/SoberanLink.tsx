import { useEffect, useState } from "react";
import { api, type SoberanProperty, type Vehicle } from "../api";
import { money, km, relative } from "../format";
import { ErrorBox, Loading, useLoad } from "./ui";

type Props = { vehicle: Vehicle; onVehicleChanged: () => void };

const norm = (s: string | null | undefined) => (s ?? "").replace(/[\s-]/g, "").toUpperCase();

function propertyLabel(p: SoberanProperty) {
  const detail = [p.marca, p.modelo, p.anio].filter(Boolean).join(" ");
  return [p.nombre || detail, detail && p.nombre ? `(${detail})` : "", p.matricula ? `· ${p.matricula}` : ""].filter(Boolean).join(" ");
}

/** Enlace del vehículo con su coche del patrimonio de Soberan (y su financiación). */
export function SoberanLink({ vehicle, onVehicleChanged }: Props) {
  const state = useLoad(() => api.soberan.state(), []);
  const [propertyId, setPropertyId] = useState(vehicle.soberan_property_id?.toString() ?? "");
  const [debtId, setDebtId] = useState(vehicle.soberan_debt_id?.toString() ?? "");
  const [selected, setSelected] = useState<string[]>([]);
  const [status, setStatus] = useState<{ kind: "idle" | "loading" | "success" | "error"; message?: string }>({ kind: "idle" });

  useEffect(() => {
    if (state.data) setSelected(state.data.selected_categories);
  }, [state.data]);

  if (state.loading && !state.data) return <Loading />;
  if (state.error) return <ErrorBox message={state.error} onRetry={state.reload} />;
  const data = state.data!;

  const suggestion = data.properties.find(
    (p) => (vehicle.plate && norm(p.matricula) === norm(vehicle.plate)) || (vehicle.vin && norm(p.bastidor) === norm(vehicle.vin))
  );

  async function save() {
    setStatus({ kind: "loading" });
    try {
      await api.soberan.link(vehicle.id, propertyId ? Number(propertyId) : null, propertyId && debtId ? Number(debtId) : null);
      await api.soberan.setCategories(selected);
      setStatus({ kind: "success", message: "Guardado. Soberan lo aplicará en su próxima sincronización." });
      onVehicleChanged();
      state.reload();
    } catch (err) {
      setStatus({ kind: "error", message: err instanceof Error ? err.message : "No se pudo guardar" });
    }
  }

  return (
    <section className="panel" aria-label="Soberan">
      <header className="panel__header">
        <h2>Soberan</h2>
        <span className="muted small">
          {data.last_sync_at ? `Última sincronización ${relative(data.last_sync_at)}` : "Aún no se ha conectado"}
        </span>
      </header>

      {!data.last_sync_at ? (
        <p className="muted">
          Soberan se sincroniza solo al abrirlo, si tiene configurada la dirección de Garaje. Abre
          Soberan una vez y vuelve aquí para enlazar el coche.
        </p>
      ) : (
        <>
          <p className="muted small">
            Garaje envía a Soberan los km reales (mejor valoración de mercado) y recibe el valor del coche, lo que queda de financiación y los
            cargos del banco de las categorías que elijas.
          </p>
          <div className="record-form__grid">
            <div className="field">
              <label htmlFor="sb-property">Coche en el patrimonio</label>
              <select id="sb-property" value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
                <option value="">— Sin enlazar —</option>
                {data.properties.map((p) => (
                  <option key={p.id} value={p.id}>
                    {propertyLabel(p)}
                    {suggestion?.id === p.id ? " ★ coincide" : ""}
                  </option>
                ))}
              </select>
              {suggestion && !propertyId && (
                <small className="muted">
                  Sugerido: <button type="button" className="link-btn" onClick={() => setPropertyId(String(suggestion.id))}>{propertyLabel(suggestion)}</button>
                </small>
              )}
            </div>
            <div className="field">
              <label htmlFor="sb-debt">Financiación</label>
              <select id="sb-debt" value={debtId} disabled={!propertyId} onChange={(e) => setDebtId(e.target.value)}>
                <option value="">— Ninguna —</option>
                {data.debts.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.nombre || d.acreedor} · quedan {money(d.pendiente)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <fieldset className="categories">
            <legend>Categorías de Soberan con gastos del coche</legend>
            <p className="muted small">Común a todos los vehículos. Sus cargos llegan a Gastos para confirmarlos.</p>
            {data.categories.length === 0 ? (
              <p className="muted small">Soberan no ha enviado categorías todavía.</p>
            ) : (
              <div className="chips">
                {data.categories.map((c) => (
                  <label key={c} className={`chip${selected.includes(c) ? " is-on" : ""}`}>
                    <input
                      type="checkbox"
                      checked={selected.includes(c)}
                      onChange={(e) => setSelected((prev) => (e.target.checked ? [...prev, c] : prev.filter((x) => x !== c)))}
                    />
                    {c}
                  </label>
                ))}
              </div>
            )}
          </fieldset>

          {vehicle.soberan_property_id != null && (
            <dl className="sb-summary">
              <div>
                <dt>Valor de mercado</dt>
                <dd>{vehicle.market_value != null ? money(vehicle.market_value) : "—"}</dd>
              </div>
              <div>
                <dt>Financiación pendiente</dt>
                <dd>{vehicle.debt_pending != null ? money(vehicle.debt_pending) : "—"}</dd>
              </div>
              <div>
                <dt>Km que ve Soberan</dt>
                <dd>{km(data.properties.find((p) => p.id === vehicle.soberan_property_id)?.km ?? null)}</dd>
              </div>
            </dl>
          )}

          <div className="form-status" role="status" aria-live="polite">
            {status.kind === "error" && <p className="form-error">⚠️ {status.message}</p>}
            {status.kind === "success" && <p className="form-success">✓ {status.message}</p>}
          </div>
          <div className="form-actions">
            <button type="button" className="btn btn--primary" onClick={save} disabled={status.kind === "loading"}>
              {status.kind === "loading" ? "Guardando…" : "Guardar enlace"}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
