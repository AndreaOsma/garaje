import type { Readiness } from "../api";
import type { TabId } from "../router";
import { CircleCheck, Icon, OctagonAlert, TriangleAlert } from "../vendor/icons";

const STATUS = {
  go: { icon: CircleCheck, title: "Listo para circular", hint: "Sin incidencias abiertas, mantenimiento al día y papeles en regla." },
  caution: { icon: TriangleAlert, title: "Circular con precaución", hint: "Hay cosas pendientes que conviene resolver pronto." },
  nogo: { icon: OctagonAlert, title: "No circular", hint: "Hay al menos un motivo para no circular con él." },
} as const;

type Props = { readiness: Readiness; goTab?: (tab: TabId) => void; compact?: boolean };

/** Semáforo «¿listo para circular?» (mismo concepto que el apto/no apto de Bitácora). */
export function ReadinessCard({ readiness, goTab, compact = false }: Props) {
  const s = STATUS[readiness.status];
  const reasons = compact ? readiness.reasons.slice(0, 3) : readiness.reasons;
  return (
    <section className={`readiness readiness--${readiness.status}`} aria-label="¿Listo para circular?">
      <div className="readiness__head">
        <span className="readiness__icon">
          <Icon svg={s.icon} size={28} />
        </span>
        <div>
          <h2>{s.title}</h2>
          {readiness.reasons.length === 0 && <p className="muted small">{s.hint}</p>}
        </div>
      </div>
      {reasons.length > 0 && (
        <ul className="readiness__reasons">
          {reasons.map((r, i) => (
            <li key={i}>
              {goTab ? (
                <button type="button" className="link-btn" onClick={() => goTab(r.target as TabId)}>
                  <Icon svg={r.level === "nogo" ? OctagonAlert : TriangleAlert} /> {r.text}
                </button>
              ) : (
                <span>
                  <Icon svg={r.level === "nogo" ? OctagonAlert : TriangleAlert} /> {r.text}
                </span>
              )}
            </li>
          ))}
          {compact && readiness.reasons.length > reasons.length && (
            <li className="muted small">y {readiness.reasons.length - reasons.length} más…</li>
          )}
        </ul>
      )}
    </section>
  );
}
