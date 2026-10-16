import { useState, type FormEvent } from "react";
import { api, type Vehicle } from "../api";
import { km, money, num, reading, relative } from "../format";
import type { TabId } from "../router";
import { CarTwin } from "../components/CarTwin";
import { ReadinessCard } from "../components/ReadinessCard";
import { ErrorBox, Loading, Stat, StatusBadge, useLoad } from "../components/ui";

type Props = {
  vehicle: Vehicle;
  detailed: boolean;
  dark: boolean;
  goTab: (tab: TabId) => void;
  onVehicleChanged: () => void;
};

const LEVEL_ICON = { danger: "⛔", warning: "⚠️", info: "ℹ️" } as const;
const LEVEL_LABEL = { danger: "Urgente", warning: "Atención", info: "Aviso" } as const;

function OdometerForm({ vehicle, onSaved }: { vehicle: Vehicle; onSaved: () => void }) {
  const [value, setValue] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    const n = Number(value);
    if (!Number.isFinite(n) || n < 0) {
      setState("error");
      setError("Introduce un número de km válido");
      return;
    }
    if (n < vehicle.odometer_km && !window.confirm("Es menos de lo registrado. ¿Corregir el odómetro igualmente?")) return;
    setState("loading");
    try {
      await api.vehicles.setOdometer(vehicle.id, Math.round(n));
      setValue("");
      setState("idle");
      onSaved();
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "No se pudo guardar");
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <label htmlFor="odo-input" className="sr-only">
        Kilómetros actuales
      </label>
      <input
        id="odo-input"
        type="number"
        inputMode="numeric"
        min={0}
        placeholder="Km actuales"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={state === "loading"}
        required
      />
      <button type="submit" className="btn btn--sm btn--primary" disabled={state === "loading"}>
        {state === "loading" ? "…" : "Actualizar"}
      </button>
      {state === "error" && (
        <span className="form-error" role="alert">
          {error}
        </span>
      )}
    </form>
  );
}

export function Home({ vehicle, detailed, dark, goTab, onVehicleChanged }: Props) {
  const { data, error, loading, reload } = useLoad(() => api.vehicles.dashboard(vehicle.id), [vehicle.id, vehicle.odometer_km]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const categories = Object.entries(data.costs.by_category).sort((a, b) => b[1] - a[1]);
  const maxCat = categories[0]?.[1] ?? 0;
  const shownCats = detailed ? categories : categories.slice(0, 4);
  const live = detailed ? data.live : data.live.filter((v) => ["0C", "05", "BATT", "42", "2F", "5C"].includes(v.key));

  return (
    <div className="stack">
      <CarTwin vehicle={vehicle} detailed={detailed} dark={dark} goTab={goTab} />
      {data.readiness && <ReadinessCard readiness={data.readiness} goTab={goTab} compact />}
      <section className="panel" aria-label="Avisos">
        <header className="panel__header">
          <h2>Avisos</h2>
        </header>
        {data.alerts.length === 0 ? (
          <p className="all-good">✅ Todo al día. Nada vencido, sin averías activas.</p>
        ) : (
          <ul className="alerts">
            {data.alerts.map((a, i) => (
              <li key={i}>
                <button type="button" className={`alert alert--${a.level}`} onClick={() => goTab(a.target as TabId)}>
                  <span className="alert__icon" aria-hidden>
                    {LEVEL_ICON[a.level]}
                  </span>
                  <span className="alert__text">
                    <span className="sr-only">{LEVEL_LABEL[a.level]}: </span>
                    <strong>{a.title}</strong>
                    {a.detail && <span className="muted">{a.detail}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="stats" aria-label="Resumen">
        <Stat label="Odómetro" value={km(vehicle.odometer_km)} hint={<OdometerForm vehicle={vehicle} onSaved={onVehicleChanged} />} />
        <Stat
          label="Consumo medio"
          value={data.avg_consumption != null ? `${num(data.avg_consumption, 2)}` : "—"}
          hint={data.avg_consumption != null ? data.consumption_unit : "Necesita dos repostajes con depósito lleno"}
        />
        <Stat label="Gasto últimos 12 meses" value={money(data.costs.last_12_months)} hint={`Total: ${money(data.costs.total)}`} />
        {vehicle.market_value != null && (
          <Stat
            label="Valor de mercado"
            value={money(vehicle.market_value)}
            hint={
              vehicle.debt_pending
                ? `Quedan ${money(vehicle.debt_pending)} de financiación · neto ${money(vehicle.market_value - vehicle.debt_pending)}`
                : `Desde Soberan${vehicle.market_value_confidence ? ` · confianza ${vehicle.market_value_confidence}` : ""}`
            }
          />
        )}
        <Stat
          label="Coste por km"
          value={data.costs.cost_per_km != null ? `${num(data.costs.cost_per_km, 3)} €` : "—"}
          hint={data.costs.km_tracked ? `sobre ${km(data.costs.km_tracked)}` : "Registra km en repostajes o talleres"}
        />
      </section>

      <div className="grid-2">
        <section className="panel" aria-label="Próximo mantenimiento">
          <header className="panel__header">
            <h2>Próximo mantenimiento</h2>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => goTab("maintenance")}>
              Ver plan
            </button>
          </header>
          <ul className="mini-list">
            {data.next_tasks.map((t) => (
              <li key={t.id}>
                <span>{t.name}</span>
                <span className="mini-list__meta">
                  {t.remaining_km != null && <span className="muted">{km(t.remaining_km)}</span>}
                  <StatusBadge status={t.status} />
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel" aria-label="Últimos datos OBD">
          <header className="panel__header">
            <h2>Últimos datos OBD</h2>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => goTab("diagnostics")}>
              Diagnóstico
            </button>
          </header>
          {data.live.length === 0 ? (
            <p className="muted">
              Aún no hay lecturas. Configura Car Scanner o el agente OBD en{" "}
              <button type="button" className="link-btn" onClick={() => goTab("diagnostics")}>
                Diagnóstico
              </button>
              .
            </p>
          ) : (
            <>
              <p className="muted small">Última lectura {relative(vehicle.last_obd_at)}</p>
              <dl className="live-grid">
                {live.map((v) => (
                  <div key={v.key} className="live-grid__item">
                    <dt>{v.name}</dt>
                    <dd>
                      {reading(v.value)} <span className="muted">{v.unit}</span>
                    </dd>
                  </div>
                ))}
              </dl>
            </>
          )}
        </section>
      </div>

      {categories.length > 0 && (
        <section className="panel" aria-label="Gasto por categoría">
          <header className="panel__header">
            <h2>Gasto por categoría</h2>
          </header>
          <ul className="bars">
            {shownCats.map(([cat, value]) => (
              <li key={cat} className="bars__row" title={`${cat}: ${money(value)}`}>
                <span className="bars__label">{cat.charAt(0).toUpperCase() + cat.slice(1)}</span>
                <span className="bars__track" aria-hidden>
                  <span className="bars__fill" style={{ width: `${maxCat ? (value / maxCat) * 100 : 0}%` }} />
                </span>
                <span className="bars__value">{money(value)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
