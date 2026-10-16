import { useState } from "react";
import { api, type Checklist, type IssueSeverity, type RunResult, type Vehicle } from "../api";
import { today } from "../format";

export const SEVERITY_LABEL: Record<IssueSeverity, string> = {
  info: "Aviso",
  limiting: "Circular con precaución",
  grounding: "No circular",
};

type Props = { vehicle: Vehicle; checklist: Checklist; onDone: (message: string) => void; onCancel: () => void };

type ItemState = { ok: boolean | null; note: string; severity: IssueSeverity; create_issue: boolean };

/** Recorre una revisión punto a punto (como las checklists de Bitácora). Cada fallo
 * puede abrir su incidencia, que alimenta el semáforo. */
export function ChecklistRunner({ vehicle, checklist, onDone, onCancel }: Props) {
  const items = checklist.sections.flatMap((s, si) => s.items.map((it, ii) => ({ key: `${si}-${ii}`, section: s.title, ...it })));
  const [state, setState] = useState<Record<string, ItemState>>({});
  const [odometer, setOdometer] = useState(String(vehicle.odometer_km));
  const [saving, setSaving] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  const get = (key: string): ItemState => state[key] ?? { ok: null, note: "", severity: "info", create_issue: true };
  const set = (key: string, patch: Partial<ItemState>) => setState((prev) => ({ ...prev, [key]: { ...get(key), ...patch } }));
  const answered = items.filter((it) => get(it.key).ok !== null).length;
  const failed = items.filter((it) => get(it.key).ok === false).length;

  async function finish() {
    setSaving("loading");
    try {
      const results: RunResult[] = items.map((it) => ({ section: it.section, label: it.label, check: it.check, ...get(it.key) }));
      const km = Number(odometer);
      const run = await api.checklists.run(vehicle.id, {
        checklist_id: checklist.id,
        date: today(),
        odometer_km: Number.isFinite(km) && odometer !== "" ? Math.round(km) : null,
        results,
      });
      onDone(
        run.failed === 0
          ? `✓ «${checklist.name}» sin fallos`
          : `«${checklist.name}»: ${run.failed} fallo${run.failed === 1 ? "" : "s"}${run.issues_created ? `, ${run.issues_created} incidencia${run.issues_created === 1 ? "" : "s"} abierta${run.issues_created === 1 ? "" : "s"}` : ""}`
      );
    } catch (err) {
      setSaving("error");
      setError(err instanceof Error ? err.message : "No se pudo guardar la revisión");
    }
  }

  let lastSection = "";
  return (
    <div className="runner">
      <div className="runner__top">
        <span className="muted small">
          {answered}/{items.length} revisados{failed > 0 && ` · ${failed} con fallo`}
        </span>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setState(Object.fromEntries(items.map((it) => [it.key, { ...get(it.key), ok: get(it.key).ok ?? true }])))}>
          Marcar el resto OK
        </button>
      </div>
      <div className="progress" aria-hidden>
        <div className={`progress__fill${answered === items.length ? " is-done" : ""}`} style={{ width: `${items.length ? (answered / items.length) * 100 : 0}%` }} />
      </div>

      <ul className="runner__list">
        {items.map((it) => {
          const st = get(it.key);
          const header = it.section !== lastSection ? it.section : null;
          lastSection = it.section;
          return (
            <li key={it.key}>
              {header && <h3 className="runner__section">{header}</h3>}
              <div className={`runner__item${st.ok === true ? " is-ok" : st.ok === false ? " is-fail" : ""}`}>
                <div className="runner__text">
                  <strong>{it.label}</strong>
                  {it.check && <span className="muted small">{it.check}</span>}
                </div>
                <div className="runner__buttons" role="group" aria-label={it.label}>
                  <button type="button" className={`btn btn--sm ${st.ok === true ? "btn--ok" : "btn--ghost"}`} aria-pressed={st.ok === true} onClick={() => set(it.key, { ok: st.ok === true ? null : true })}>
                    ✓ OK
                  </button>
                  <button type="button" className={`btn btn--sm ${st.ok === false ? "btn--danger" : "btn--ghost"}`} aria-pressed={st.ok === false} onClick={() => set(it.key, { ok: st.ok === false ? null : false })}>
                    ✗ Falla
                  </button>
                </div>
                {st.ok === false && (
                  <div className="runner__fail">
                    <label className="sr-only" htmlFor={`note-${it.key}`}>
                      Qué pasa
                    </label>
                    <input id={`note-${it.key}`} placeholder="Qué pasa (opcional)" value={st.note} onChange={(e) => set(it.key, { note: e.target.value })} />
                    <label className="check">
                      <input type="checkbox" checked={st.create_issue} onChange={(e) => set(it.key, { create_issue: e.target.checked })} />
                      <span>Abrir incidencia</span>
                    </label>
                    {st.create_issue && (
                      <select aria-label="Gravedad" value={st.severity} onChange={(e) => set(it.key, { severity: e.target.value as IssueSeverity })}>
                        {Object.entries(SEVERITY_LABEL).map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <div className="runner__finish">
        <div className="field">
          <label htmlFor="runner-km">Km actuales</label>
          <input id="runner-km" type="number" inputMode="numeric" min={0} value={odometer} onChange={(e) => setOdometer(e.target.value)} />
        </div>
        <div className="form-status" role="status" aria-live="polite">
          {saving === "error" && <p className="form-error">⚠️ {error}</p>}
        </div>
        <div className="form-actions">
          <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={saving === "loading"}>
            Cancelar
          </button>
          <button type="button" className="btn btn--primary" onClick={finish} disabled={saving === "loading" || answered === 0}>
            {saving === "loading" ? "Guardando…" : "Terminar revisión"}
          </button>
        </div>
      </div>
    </div>
  );
}
