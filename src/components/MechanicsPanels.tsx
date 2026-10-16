import { useState } from "react";
import { api, type Checklist, type ChecklistSection, type Issue, type Mechanics, type Vehicle } from "../api";
import { MAINTENANCE_CATEGORIES, capitalize, date, km, relative, today } from "../format";
import { ChecklistRunner, SEVERITY_LABEL } from "./ChecklistRunner";
import { CrudList } from "./CrudList";
import { Modal } from "./Modal";
import { RecordForm, type Field } from "./RecordForm";
import { confirmAndRun } from "./ui";

const SEVERITY_ICON = { info: "ℹ️", limiting: "⚠️", grounding: "⛔" } as const;

const ISSUE_FIELDS: Field[] = [
  { name: "title", label: "Qué pasa", required: true, wide: true, placeholder: "Chirrido al frenar, fuga bajo el motor…" },
  {
    name: "severity",
    label: "Gravedad",
    type: "select",
    required: true,
    options: Object.entries(SEVERITY_LABEL).map(([value, label]) => ({ value, label })),
    hint: "«No circular» pone el semáforo en rojo",
  },
  { name: "reported_on", label: "Desde", type: "date", required: true },
  { name: "odometer_km", label: "Km", type: "number", min: 0, step: "1" },
  { name: "category", label: "Sistema", type: "select", options: MAINTENANCE_CATEGORIES, required: true },
  { name: "description", label: "Detalle (cuándo pasa, ruido, olor…)", type: "textarea" },
  { name: "dtc_code", label: "Código de avería relacionado", placeholder: "P0420", advanced: true },
];

const RESOLVE_FIELDS: Field[] = [
  { name: "resolved_on", label: "Resuelta el", type: "date", required: true },
  { name: "resolution", label: "Qué se hizo", type: "textarea", required: true },
  { name: "create_service", label: "Registrarlo también en el historial de intervenciones", type: "checkbox", wide: true },
  { name: "cost", label: "Coste (€)", type: "number", min: 0, step: "0.01" },
  { name: "workshop", label: "Taller" },
];

// --- Incidencias ---------------------------------------------------------------

export function IssuesPanel({ vehicle, issues, detailed, onChanged }: { vehicle: Vehicle; issues: Issue[]; detailed: boolean; onChanged: () => void }) {
  const [resolving, setResolving] = useState<Issue | null>(null);
  const [showResolved, setShowResolved] = useState(false);
  const open = issues.filter((i) => !i.resolved_on);
  const resolved = issues.filter((i) => i.resolved_on);
  const visible = showResolved ? [...open, ...resolved] : open;

  return (
    <>
      <CrudList<Issue>
        title={`Incidencias${open.length ? ` (${open.length})` : ""}`}
        newLabel="Nueva incidencia"
        items={visible}
        fields={ISSUE_FIELDS}
        detailed={detailed}
        emptyTitle="Sin incidencias abiertas"
        emptyHint="Apunta aquí ruidos, fugas, testigos o cualquier cosa rara: cuenta para el semáforo hasta que la resuelvas."
        newDefaults={() => ({ reported_on: today(), odometer_km: vehicle.odometer_km, severity: "info", category: "otros" })}
        describe={(i) => `la incidencia «${i.title}»`}
        create={(d) => api.issues.create(vehicle.id, d)}
        update={(id, d) => api.issues.update(vehicle.id, id, d)}
        remove={(id) => api.issues.remove(vehicle.id, id)}
        onChanged={onChanged}
        headerExtra={
          resolved.length > 0 ? (
            <button type="button" className="btn btn--ghost btn--sm" aria-pressed={showResolved} onClick={() => setShowResolved((v) => !v)}>
              {showResolved ? "Ocultar resueltas" : `Resueltas (${resolved.length})`}
            </button>
          ) : undefined
        }
        extraActions={(i) =>
          i.resolved_on ? (
            <button type="button" className="btn btn--sm btn--ghost" onClick={() => confirmAndRun(`¿Reabrir «${i.title}»?`, () => api.issues.reopen(vehicle.id, i.id), onChanged)}>
              ↺ Reabrir
            </button>
          ) : (
            <button type="button" className="btn btn--sm btn--ghost" onClick={() => setResolving(i)}>
              ✓ Resolver
            </button>
          )
        }
        renderItem={(i) => (
          <div className={`issue issue--${i.severity}${i.resolved_on ? " is-resolved" : ""}`}>
            <div className="card__title">
              <strong>
                <span aria-hidden>{i.resolved_on ? "✅" : SEVERITY_ICON[i.severity as keyof typeof SEVERITY_ICON]} </span>
                {i.title}
              </strong>
              <span className={`badge badge--${i.resolved_on ? "done" : i.severity === "grounding" ? "overdue" : i.severity === "limiting" ? "soon" : "unknown"}`}>
                {i.resolved_on ? "Resuelta" : SEVERITY_LABEL[i.severity]}
              </span>
            </div>
            <div className="card__meta">
              <span>Desde {date(i.reported_on)}</span>
              {i.odometer_km != null && <span>{km(i.odometer_km)}</span>}
              <span>{capitalize(i.category)}</span>
              {i.dtc_code && <code>{i.dtc_code}</code>}
              {i.resolved_on && <span>Resuelta el {date(i.resolved_on)}</span>}
            </div>
            {(detailed || !i.resolved_on) && i.description && <p className="issue__desc">{i.description}</p>}
            {i.resolved_on && i.resolution && <p className="issue__desc">🔧 {i.resolution}</p>}
          </div>
        )}
      />
      {resolving && (
        <Modal title={`Resolver: ${resolving.title}`} onClose={() => setResolving(null)}>
          <RecordForm
            fields={RESOLVE_FIELDS}
            detailed
            submitLabel="Marcar como resuelta"
            initial={{ resolved_on: today(), create_service: true, cost: 0 }}
            onSubmit={async (d) => {
              let service_id: number | null = null;
              if (d.create_service) {
                const svc = await api.services.create(vehicle.id, {
                  date: String(d.resolved_on),
                  title: resolving.title,
                  description: String(d.resolution ?? ""),
                  category: resolving.category,
                  cost: Number(d.cost ?? 0),
                  workshop: String(d.workshop ?? ""),
                  odometer_km: vehicle.odometer_km,
                });
                service_id = svc.id;
              }
              return api.issues.resolve(vehicle.id, resolving.id, {
                resolved_on: String(d.resolved_on),
                resolution: String(d.resolution ?? ""),
                service_id,
              });
            }}
            onDone={() => {
              setResolving(null);
              onChanged();
            }}
            onCancel={() => setResolving(null)}
          />
        </Modal>
      )}
    </>
  );
}

// --- Revisiones (checklists) -----------------------------------------------------

/** Formato de texto para editar: "# Sección" y "Punto | Qué comprobar" por línea. */
export function checklistToText(sections: ChecklistSection[]): string {
  return sections.map((s) => [`# ${s.title}`, ...s.items.map((i) => (i.check ? `${i.label} | ${i.check}` : i.label))].join("\n")).join("\n\n");
}

export function textToChecklist(text: string): ChecklistSection[] {
  const sections: ChecklistSection[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("#")) {
      sections.push({ title: line.replace(/^#+/, "").trim() || "Sin título", items: [] });
      continue;
    }
    if (!sections.length) sections.push({ title: "General", items: [] });
    const [label, ...rest] = line.split("|");
    sections[sections.length - 1].items.push({ label: label.trim(), check: rest.join("|").trim() });
  }
  return sections.filter((s) => s.items.length > 0);
}

const CHECKLIST_FIELDS: Field[] = [
  { name: "name", label: "Nombre", required: true, wide: true },
  { name: "interval_days", label: "Recordar cada (días)", type: "number", min: 1, step: "1", hint: "Vacío = solo cuando toque" },
  {
    name: "text",
    label: "Puntos",
    type: "textarea",
    required: true,
    hint: "«# Sección» y una línea por punto: «Qué | Cómo debe estar»",
  },
];

export function ChecklistsPanel({ vehicle, mechanics, detailed, onChanged }: { vehicle: Vehicle; mechanics: Mechanics; detailed: boolean; onChanged: () => void }) {
  const [running, setRunning] = useState<Checklist | null>(null);
  const [editing, setEditing] = useState<Checklist | "new" | null>(null);
  const [message, setMessage] = useState("");

  return (
    <section className="panel" aria-label="Revisiones">
      <header className="panel__header">
        <h2>Revisiones</h2>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing("new")}>
          + Nueva revisión
        </button>
      </header>
      {message && (
        <p className="form-success" role="status">
          {message}
        </p>
      )}
      <ul className="card-list">
        {mechanics.checklists.map((cl) => {
          const count = cl.sections.reduce((n, s) => n + s.items.length, 0);
          return (
            <li key={cl.id} className="card">
              <div className="card__body">
                <div className="card__title">
                  <strong>{cl.name}</strong>
                  {cl.due && <span className="badge badge--soon">◔ Toca</span>}
                </div>
                <div className="card__meta">
                  <span>{count} puntos</span>
                  {cl.interval_days && <span>Cada {cl.interval_days} días</span>}
                  <span>
                    {cl.last_run_on ? `Última: ${relative(cl.last_run_on)}` : "Nunca hecha"}
                    {cl.last_run_failed ? ` · ${cl.last_run_failed} fallo${cl.last_run_failed === 1 ? "" : "s"}` : ""}
                  </span>
                  {detailed && <span className="muted">{cl.vehicle_id ? "Solo este vehículo" : "Común a todos"}</span>}
                </div>
              </div>
              <div className="card__actions">
                <button type="button" className="btn btn--primary btn--sm" onClick={() => setRunning(cl)}>
                  ▶ Empezar
                </button>
                <button type="button" className="icon-btn" aria-label={`Editar ${cl.name}`} title="Editar" onClick={() => setEditing(cl)}>
                  ✎
                </button>
                <button
                  type="button"
                  className="icon-btn icon-btn--danger"
                  aria-label={`Eliminar ${cl.name}`}
                  title="Eliminar"
                  onClick={() =>
                    confirmAndRun(
                      cl.vehicle_id ? `¿Eliminar «${cl.name}»?` : `«${cl.name}» es común a todos los vehículos. ¿Eliminarla igualmente?`,
                      () => api.checklists.remove(vehicle.id, cl.id),
                      onChanged
                    )
                  }
                >
                  🗑
                </button>
              </div>
            </li>
          );
        })}
      </ul>

      {detailed && mechanics.runs.length > 0 && (
        <div className="subsection">
          <h3 className="small">Últimas revisiones hechas</h3>
          <ul className="mini-list">
            {mechanics.runs.map((r) => (
              <li key={r.id}>
                <span>
                  {r.checklist_name} <span className="muted small">· {date(r.date)}{r.odometer_km != null && ` · ${km(r.odometer_km)}`}</span>
                </span>
                <span className={`badge badge--${r.failed ? "soon" : "ok"}`}>{r.failed ? `${r.failed} fallos` : "Todo OK"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {running && (
        <Modal title={running.name} onClose={() => setRunning(null)}>
          <ChecklistRunner
            vehicle={vehicle}
            checklist={running}
            onCancel={() => setRunning(null)}
            onDone={(msg) => {
              setRunning(null);
              setMessage(msg);
              onChanged();
            }}
          />
        </Modal>
      )}
      {editing && (
        <Modal title={editing === "new" ? "Nueva revisión" : `Editar: ${editing.name}`} onClose={() => setEditing(null)}>
          {editing !== "new" && !editing.vehicle_id && <p className="muted small">Es común a todos los vehículos: el cambio les afecta a todos.</p>}
          <RecordForm
            fields={CHECKLIST_FIELDS}
            detailed
            initial={
              editing === "new"
                ? { text: "# Exterior\nPunto | Cómo debe estar" }
                : { name: editing.name, interval_days: editing.interval_days, text: checklistToText(editing.sections) }
            }
            onSubmit={async (d) => {
              const sections = textToChecklist(String(d.text ?? ""));
              if (!sections.length) throw new Error("Añade al menos un punto");
              const body = { name: String(d.name), interval_days: (d.interval_days as number | null) ?? null, sections };
              return editing === "new" ? api.checklists.create(vehicle.id, body) : api.checklists.update(vehicle.id, editing.id, body);
            }}
            onDone={() => {
              setEditing(null);
              onChanged();
            }}
            onCancel={() => setEditing(null)}
          />
        </Modal>
      )}
    </section>
  );
}

// --- Sugerencias del plan ----------------------------------------------------------

export function SuggestionsButton({ vehicle, suggestions, onAdded }: { vehicle: Vehicle; suggestions: Mechanics["suggestions"]; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  if (suggestions.length === 0) return null;

  const interval = (s: Mechanics["suggestions"][number]) =>
    [s.interval_km ? km(s.interval_km) : "", s.interval_months ? `${s.interval_months} meses` : ""].filter(Boolean).join(" o ");

  return (
    <>
      <button
        type="button"
        className="btn btn--ghost btn--sm"
        onClick={() => {
          setPicked(suggestions.map((s) => s.name));
          setOpen(true);
        }}
      >
        Sugeridas ({suggestions.length})
      </button>
      {open && (
        <Modal title="Tareas sugeridas" onClose={() => setOpen(false)}>
          <p className="muted small">Intervalos orientativos para tu tipo de motor; ajústalos luego a tu manual.</p>
          <div className="stack-sm">
            {suggestions.map((s) => (
              <label key={s.name} className="check">
                <input
                  type="checkbox"
                  checked={picked.includes(s.name)}
                  onChange={(e) => setPicked((p) => (e.target.checked ? [...p, s.name] : p.filter((x) => x !== s.name)))}
                />
                <span>
                  {s.name} <span className="muted small">· {interval(s)}</span>
                </span>
              </label>
            ))}
          </div>
          <RecordForm
            fields={[]}
            detailed
            submitLabel={`Añadir ${picked.length}`}
            onSubmit={() => (picked.length ? api.addSuggestedTasks(vehicle.id, picked) : Promise.reject(new Error("Elige al menos una")))}
            onDone={() => {
              setOpen(false);
              onAdded();
            }}
            onCancel={() => setOpen(false)}
          />
        </Modal>
      )}
    </>
  );
}

