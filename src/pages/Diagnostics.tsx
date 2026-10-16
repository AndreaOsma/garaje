import { useState, type FormEvent } from "react";
import { api, type Dtc, type Vehicle } from "../api";
import { LineChart } from "../components/LineChart";
import { Modal } from "../components/Modal";
import { RecordForm, type Field } from "../components/RecordForm";
import { EmptyState, ErrorBox, Loading, confirmAndRun, useLoad } from "../components/ui";
import { dateTime, num, reading, relative, today } from "../format";
import type { TabId } from "../router";

type Props = { vehicle: Vehicle; detailed: boolean; goTab: (tab: TabId) => void; onVehicleChanged: () => void };

const KIND_LABEL = { stored: "Confirmada", pending: "Pendiente", permanent: "Permanente" } as const;
const SEVERITY_ICON = { alta: "⛔", media: "⚠️", baja: "ℹ️" } as const;
// Sensores que se grafican en modo minimal (el resto, en detailed).
const KEY_SENSORS = new Set(["0C", "0D", "05", "5C", "04", "BATT", "42", "06", "07", "10", "0B"]);

const DTC_FIELDS: Field[] = [
  { name: "code", label: "Código", required: true, placeholder: "P0420" },
  {
    name: "kind",
    label: "Tipo",
    type: "select",
    required: true,
    options: [
      { value: "stored", label: "Confirmada" },
      { value: "pending", label: "Pendiente" },
      { value: "permanent", label: "Permanente" },
    ],
  },
  { name: "notes", label: "Notas", type: "textarea" },
];

function EcuStatus({ vehicle }: { vehicle: Vehicle }) {
  const monitors = vehicle.monitors;
  return (
    <section className="panel" aria-label="Estado de la centralita">
      <header className="panel__header">
        <h2>Estado de la centralita</h2>
        <span className="muted small">Última lectura {relative(vehicle.last_obd_at)}</span>
      </header>
      {vehicle.mil_on == null ? (
        <p className="muted">
          Sin datos de la ECU todavía. El agente OBD lee el testigo MIL y los monitores de emisiones; Car Scanner solo exporta
          lecturas de sensores.
        </p>
      ) : (
        <>
          <p className={`ecu-mil ${vehicle.mil_on ? "is-on" : "is-off"}`}>
            <span aria-hidden>{vehicle.mil_on ? "🟠" : "🟢"}</span>
            {vehicle.mil_on ? "Testigo de avería encendido" : "Testigo de avería apagado"}
            {vehicle.ecu_dtc_count != null && (
              <span className="muted">
                {" "}
                · {vehicle.ecu_dtc_count} {vehicle.ecu_dtc_count === 1 ? "código" : "códigos"} en la ECU
              </span>
            )}
          </p>
          {monitors && monitors.monitors.length > 0 && (
            <>
              <p className="readiness">
                {monitors.ready ? "✅ Monitores completos: lista para la prueba OBD de la ITV" : "⏳ Monitores incompletos: conduce más antes de la ITV"}
              </p>
              <ul className="monitors">
                {monitors.monitors.map((m) => (
                  <li key={m.name} className={m.complete ? "is-complete" : "is-pending"}>
                    <span aria-hidden>{m.complete ? "✓" : "…"}</span> {m.name}
                    <span className="sr-only">{m.complete ? " completo" : " incompleto"}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}

const LEARNED_TAG = {
  manual: { label: "✎ tuya", title: "Descripción escrita por ti" },
  import: { label: "📖 del informe", title: "Aprendida de un informe importado" },
  web: { label: "🔎 buscado en la web", title: "Buscado automáticamente con fuentes de tu marca" },
  ia: { label: "🤖 orientativo", title: "Sugerido por la IA local sin acceso a internet: compruébalo" },
} as const;

function DtcCard({
  dtc,
  detailed,
  canResearch,
  researching,
  onAction,
}: {
  dtc: Dtc;
  detailed: boolean;
  canResearch: boolean;
  researching: boolean;
  onAction: (a: "clear" | "notes" | "delete" | "issue" | "define" | "research") => void;
}) {
  const [showMore, setShowMore] = useState(false);
  const d = dtc.details;
  return (
    <li className={`card dtc dtc--${dtc.severity}${dtc.cleared_at ? " is-cleared" : ""}`}>
      <div className="card__body">
        <div className="card__title">
          <strong>
            <span aria-hidden>{SEVERITY_ICON[dtc.severity]} </span>
            <code>{dtc.code}</code> · {KIND_LABEL[dtc.kind]}
          </strong>
          <span className="muted small">Gravedad {dtc.severity}</span>
        </div>
        <p className="dtc__desc">
          {dtc.description}{" "}
          {dtc.learned && (
            <span className="tag" title={LEARNED_TAG[dtc.learned].title}>
              {LEARNED_TAG[dtc.learned].label}
            </span>
          )}
          <button type="button" className="link-btn small" onClick={() => onAction("define")}>
            {dtc.learned ? "Editar descripción" : dtc.generic ? "Añadir mi descripción" : "¿Qué significa en tu marca? Añádelo"}
          </button>
        </p>
        {d && (d.causes.length > 0 || d.advice || d.sources.length > 0) && (
          <div className="dtc__more">
            <button type="button" className="link-btn small" aria-expanded={showMore} onClick={() => setShowMore((v) => !v)}>
              {showMore ? "Ocultar" : "Causas típicas y consejo"}
            </button>
            {showMore && (
              <div className="dtc__details">
                {d.causes.length > 0 && (
                  <ul>
                    {d.causes.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                )}
                {d.advice && <p>💡 {d.advice}</p>}
                {d.sources.length > 0 && (
                  <p className="small">
                    Fuentes:{" "}
                    {d.sources.map((u, i) => (
                      <span key={u}>
                        {i > 0 && " · "}
                        <a href={u} target="_blank" rel="noopener noreferrer">
                          {(() => {
                            try {
                              return new URL(u).hostname.replace(/^www\./, "");
                            } catch {
                              return u;
                            }
                          })()}
                        </a>
                      </span>
                    ))}
                  </p>
                )}
                <p className="muted small">Confianza {d.confidence}</p>
              </div>
            )}
          </div>
        )}
        <div className="card__meta">
          <span>{dtc.system}</span>
          <span>Visto {relative(dtc.last_seen)}</span>
          {dtc.cleared_at && <span>Resuelta {dateTime(dtc.cleared_at)}</span>}
        </div>
        {detailed && (
          <div className="card__meta muted">
            <span>Primera vez {dateTime(dtc.first_seen)}</span>
            <span>{dtc.occurrences} lecturas</span>
            <span>Origen: {dtc.source}</span>
          </div>
        )}
        {dtc.notes && <p className="dtc__notes">📝 {dtc.notes}</p>}
      </div>
      <div className="card__actions">
        {!dtc.cleared_at && (
          <button type="button" className="btn btn--sm btn--ghost" onClick={() => onAction("issue")} title="Abrir una incidencia en Mecánica">
            🔧 Incidencia
          </button>
        )}
        {!dtc.cleared_at && (
          <button type="button" className="btn btn--sm btn--ghost" onClick={() => onAction("clear")} title="Marcar como resuelta">
            ✓ Resuelta
          </button>
        )}
        {canResearch && (dtc.learned === null || dtc.learned === "ia" || dtc.learned === "web") && (
          <button
            type="button"
            className="btn btn--sm btn--ghost"
            onClick={() => onAction("research")}
            disabled={researching}
            title="Buscar qué significa este código en tu marca y modelo"
          >
            {researching ? "Buscando…" : dtc.learned ? "🔎 Buscar de nuevo" : "🔎 Buscar significado"}
          </button>
        )}
        <button type="button" className="icon-btn" aria-label="Notas" title="Notas" onClick={() => onAction("notes")}>
          📝
        </button>
        <button type="button" className="icon-btn icon-btn--danger" aria-label="Eliminar" title="Eliminar" onClick={() => onAction("delete")}>
          🗑
        </button>
      </div>
    </li>
  );
}

function CsvImport({ vehicle, onImported }: { vehicle: Vehicle; onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [day, setDay] = useState(today());
  const [state, setState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setState("loading");
    try {
      const result = await api.importObdFile(vehicle.id, file, day);
      setState("success");
      if (result.kind === "report") {
        const parts = [
          ...(["stored", "pending", "permanent"] as const)
            .filter((k) => result.dtcs[k] !== undefined)
            .map((k) => {
              const codes = result.dtcs[k] ?? [];
              const label = { stored: "confirmados", pending: "pendientes", permanent: "permanentes" }[k];
              return codes.length ? `${label}: ${codes.join(", ")}` : `sin códigos ${label}`;
            }),
          result.samples ? `${result.samples} valores de sensores` : "",
          result.vin ? `VIN ${result.vin}` : "",
        ].filter(Boolean);
        if (result.learned) parts.push(`${result.learned} descripción${result.learned === 1 ? "" : "es"} al diccionario`);
        setMessage(`${result.reprocessed ? "Informe reprocesado" : "Informe importado"} — ${parts.join(" · ")}`);
      } else {
        setMessage(`${result.samples} lecturas importadas${result.skipped_rows ? ` (${result.skipped_rows} filas ignoradas)` : ""}`);
      }
      setFile(null);
      (e.target as HTMLFormElement).reset();
      onImported();
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "No se pudo importar");
    }
  }

  return (
    <form className="csv-import" onSubmit={submit}>
      <div className="field">
        <label htmlFor="csv-file">Archivo del OBD (CSV o TXT)</label>
        <input
          id="csv-file"
          type="file"
          accept=".csv,.txt,.log,text/csv,text/plain"
          required
          aria-describedby="csv-file-hint"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <small id="csv-file-hint" className="muted">
          Grabación de sensores, informe de diagnóstico o log del ELM327
        </small>
      </div>
      <div className="field">
        <label htmlFor="csv-date">Día de la grabación (solo CSV)</label>
        <input id="csv-date" type="date" value={day} required onChange={(e) => setDay(e.target.value)} />
      </div>
      <button type="submit" className="btn btn--primary" disabled={!file || state === "loading"}>
        {state === "loading" ? "Importando…" : "Importar"}
      </button>
      <p role="status" aria-live="polite" className={state === "error" ? "form-error" : "form-success"}>
        {state === "error" && `⚠️ ${message}`}
        {state === "success" && `✓ ${message}`}
      </p>
    </form>
  );
}

function SessionView({ vehicle, sessionId, detailed }: { vehicle: Vehicle; sessionId: number; detailed: boolean }) {
  const { data, error, loading, reload } = useLoad(() => api.sessions.get(vehicle.id, sessionId), [vehicle.id, sessionId]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  const series = detailed ? data.series : data.series.filter((s) => KEY_SENSORS.has(s.key));

  return (
    <div className="stack">
      <div className="charts">
        {series.map((s) => (
          <figure key={s.key} className="chart-card">
            <figcaption>
              <strong>{s.name}</strong>
              <span className="muted small">
                {" "}
                mín {num(s.min)} · media {num(s.avg)} · máx {num(s.max)} {s.unit}
              </span>
            </figcaption>
            <LineChart points={s.points} unit={s.unit} label={s.name} />
          </figure>
        ))}
      </div>
      {detailed && (
        <table className="table">
          <caption className="sr-only">Resumen por sensor</caption>
          <thead>
            <tr>
              <th scope="col">Sensor</th>
              <th scope="col">Clave</th>
              <th scope="col">Mín</th>
              <th scope="col">Media</th>
              <th scope="col">Máx</th>
              <th scope="col">Lecturas</th>
            </tr>
          </thead>
          <tbody>
            {data.series.map((s) => (
              <tr key={s.key}>
                <td>{s.name}</td>
                <td>
                  <code>{s.key}</code>
                </td>
                <td>{num(s.min, 2)}</td>
                <td>{num(s.avg, 2)}</td>
                <td>{num(s.max, 2)}</td>
                <td>{s.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function Diagnostics({ vehicle, detailed, goTab, onVehicleChanged }: Props) {
  const dtcs = useLoad(() => api.dtcs.list(vehicle.id), [vehicle.id, vehicle.last_obd_at]);
  const live = useLoad(() => api.live(vehicle.id), [vehicle.id, vehicle.last_obd_at]);
  const sessions = useLoad(() => api.sessions.list(vehicle.id), [vehicle.id, vehicle.last_obd_at]);
  const [adding, setAdding] = useState(false);
  const [notesFor, setNotesFor] = useState<Dtc | null>(null);
  const [defining, setDefining] = useState<Dtc | null>(null);
  const research = useLoad(() => api.researchStatus(), []);
  const canResearch = (research.data?.providers.length ?? 0) > 0;
  const [researchingId, setResearchingId] = useState<number | null>(null);
  const [researchMsg, setResearchMsg] = useState("");
  const [openSession, setOpenSession] = useState<number | null>(() => Number(new URLSearchParams(window.location.search).get("s")) || null);
  const [showCleared, setShowCleared] = useState(false);

  const refreshObd = () => {
    sessions.reload();
    live.reload();
    onVehicleChanged();
  };

  function onDtcAction(dtc: Dtc, action: "clear" | "notes" | "delete" | "issue" | "define" | "research") {
    if (action === "notes") return setNotesFor(dtc);
    if (action === "research") {
      setResearchingId(dtc.id);
      setResearchMsg("");
      void api.dtcs
        .research(vehicle.id, dtc.id)
        .then(() => dtcs.reload())
        .catch((err) => setResearchMsg(err instanceof Error ? err.message : "No se pudo buscar"))
        .finally(() => setResearchingId(null));
      return;
    }
    if (action === "define") return setDefining(dtc);
    if (action === "issue") {
      return confirmAndRun(
        `¿Abrir una incidencia en Mecánica para ${dtc.code}?`,
        () =>
          api.issues.create(vehicle.id, {
            reported_on: today(),
            odometer_km: vehicle.odometer_km,
            title: `${dtc.code} · ${dtc.description}`.slice(0, 160),
            description: [dtc.system, dtc.notes].filter(Boolean).join(". "),
            severity: dtc.severity === "alta" ? "limiting" : "info",
            category: "otros",
            dtc_code: dtc.code,
          }),
        () => goTab("maintenance")
      );
    }
    if (action === "clear") {
      return confirmAndRun(
        `¿Marcar ${dtc.code} como resuelta? (No borra el código de la centralita: eso lo hace el agente con --clear-dtc.)`,
        () => api.dtcs.clear(vehicle.id, dtc.id),
        dtcs.reload
      );
    }
    return confirmAndRun(`¿Eliminar ${dtc.code} del historial?`, () => api.dtcs.remove(vehicle.id, dtc.id), dtcs.reload);
  }

  const active = (dtcs.data ?? []).filter((d) => !d.cleared_at);
  const cleared = (dtcs.data ?? []).filter((d) => d.cleared_at);

  return (
    <div className="stack">
      <EcuStatus vehicle={vehicle} />

      <section className="panel" aria-label="Averías">
        <header className="panel__header">
          <h2>Averías {active.length > 0 && <span className="count">{active.length}</span>}</h2>
          <button type="button" className="btn btn--primary btn--sm" onClick={() => setAdding(true)}>
            + Añadir código
          </button>
        </header>
        {dtcs.error && <ErrorBox message={dtcs.error} onRetry={dtcs.reload} />}
        {researchMsg && (
          <p className="form-error" role="alert">
            ⚠️ {researchMsg}
          </p>
        )}
        {research.data && !canResearch && active.some((d) => d.learned === null) && (
          <p className="muted">
            Para averiguar qué significan los códigos de tu marca, configura tu IA (tu clave de Claude, Gemini u OpenRouter, o tu servidor Ollama) en Garaje → Inteligencia artificial.
          </p>
        )}
        {dtcs.loading && !dtcs.data ? (
          <Loading />
        ) : active.length === 0 ? (
          <p className="all-good">✅ Sin averías activas.</p>
        ) : (
          <ul className="card-list">
            {active.map((d) => (
              <DtcCard
                key={d.id}
                dtc={d}
                detailed={detailed}
                canResearch={canResearch}
                researching={researchingId === d.id}
                onAction={(a) => onDtcAction(d, a)}
              />
            ))}
          </ul>
        )}
        {cleared.length > 0 && (
          <div className="subsection">
            <button type="button" className="link-btn" aria-expanded={showCleared} onClick={() => setShowCleared((v) => !v)}>
              {showCleared ? "Ocultar" : "Ver"} historial de averías resueltas ({cleared.length})
            </button>
            {showCleared && (
              <ul className="card-list">
                {cleared.map((d) => (
                  <DtcCard
                key={d.id}
                dtc={d}
                detailed={detailed}
                canResearch={canResearch}
                researching={researchingId === d.id}
                onAction={(a) => onDtcAction(d, a)}
              />
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      <section className="panel" aria-label="Valores en vivo">
        <header className="panel__header">
          <h2>Últimos valores</h2>
        </header>
        {live.error && <ErrorBox message={live.error} onRetry={live.reload} />}
        {(live.data ?? []).length === 0 ? (
          <EmptyState title="Sin lecturas OBD">
            Importa un CSV de Car Scanner abajo o automatízalo desde{" "}
            <button type="button" className="link-btn" onClick={() => goTab("settings")}>
              Vehículo → Conexión OBD
            </button>
            .
          </EmptyState>
        ) : (
          <dl className="live-grid">
            {(live.data ?? []).map((v) => (
              <div key={v.key} className="live-grid__item" title={detailed ? `${v.key} · ${dateTime(v.ts)}` : undefined}>
                <dt>{v.name}</dt>
                <dd>
                  {reading(v.value)} <span className="muted">{v.unit}</span>
                </dd>
                {detailed && <span className="muted small">{relative(v.ts)}</span>}
              </div>
            ))}
          </dl>
        )}
      </section>

      <section className="panel" aria-label="Sesiones de conducción">
        <header className="panel__header">
          <h2>Sesiones</h2>
        </header>
        <CsvImport vehicle={vehicle} onImported={refreshObd} />
        <p className="muted small">
          Para subirlo sin abrir Garaje, usa el Atajo de iOS descrito en{" "}
          <button type="button" className="link-btn" onClick={() => goTab("settings")}>
            Vehículo → Conexión OBD
          </button>
          .
        </p>
        {sessions.error && <ErrorBox message={sessions.error} onRetry={sessions.reload} />}
        {(sessions.data ?? []).length > 0 && (
          <ul className="session-list">
            {(sessions.data ?? []).map((s) => (
              <li key={s.id}>
                <div className={`session${openSession === s.id ? " is-open" : ""}`}>
                  <button
                    type="button"
                    className="session__toggle"
                    aria-expanded={openSession === s.id}
                    onClick={() => setOpenSession(openSession === s.id ? null : s.id)}
                  >
                    <span>
                      <strong>{dateTime(s.started_at)}</strong>
                      <span className="muted small">
                        {" "}
                        · {Math.max(1, Math.round((new Date(s.ended_at).getTime() - new Date(s.started_at).getTime()) / 60000))} min ·{" "}
                        {s.source === "agent" ? "Agente OBD" : "Car Scanner"}
                        {detailed && ` · ${s.sample_count} lecturas · ${s.label}`}
                      </span>
                    </span>
                    <span aria-hidden>{openSession === s.id ? "▴" : "▾"}</span>
                  </button>
                  <button
                    type="button"
                    className="icon-btn icon-btn--danger"
                    aria-label="Eliminar sesión"
                    title="Eliminar sesión"
                    onClick={() => confirmAndRun("¿Eliminar esta sesión y sus lecturas?", () => api.sessions.remove(vehicle.id, s.id), sessions.reload)}
                  >
                    🗑
                  </button>
                </div>
                {openSession === s.id && <SessionView vehicle={vehicle} sessionId={s.id} detailed={detailed} />}
              </li>
            ))}
          </ul>
        )}
      </section>

      {adding && (
        <Modal title="Añadir código de avería" onClose={() => setAdding(false)}>
          <p className="muted small">Útil para apuntar los códigos que lees con Car Scanner (no los incluye en el CSV).</p>
          <RecordForm
            fields={DTC_FIELDS}
            detailed
            initial={{ kind: "stored" }}
            submitLabel="Añadir"
            onSubmit={(d) => api.dtcs.create(vehicle.id, d as { code: string; kind: string; notes: string })}
            onDone={() => {
              setAdding(false);
              dtcs.reload();
            }}
            onCancel={() => setAdding(false)}
          />
        </Modal>
      )}
      {defining && (
        <Modal title={`Diccionario: ${defining.code}`} onClose={() => setDefining(null)}>
          <p className="muted small">
            {defining.generic
              ? "Código genérico: tu descripción se usará en todos los vehículos."
              : `Código del fabricante: se guarda para ${vehicle.make || "esta marca"} (en otras marcas puede significar otra cosa).`}
          </p>
          <RecordForm
            fields={[
              { name: "description", label: "Qué significa", type: "textarea", required: true },
              {
                name: "severity",
                label: "Gravedad",
                type: "select",
                options: [
                  { value: "baja", label: "Baja" },
                  { value: "media", label: "Media" },
                  { value: "alta", label: "Alta (cuenta para el semáforo)" },
                ],
              },
              ...(defining.generic ? [] : [{ name: "all_makes", label: "Usarla para todas las marcas", type: "checkbox" as const }]),
            ]}
            detailed
            initial={{ description: defining.description, severity: defining.severity }}
            onSubmit={(d) =>
              api.dtcs.define(vehicle.id, defining.code, {
                description: String(d.description ?? ""),
                severity: (d.severity as string | null) ?? null,
                all_makes: Boolean(d.all_makes),
              })
            }
            onDone={() => {
              setDefining(null);
              dtcs.reload();
            }}
            onCancel={() => setDefining(null)}
          />
          {defining.learned && (
            <button
              type="button"
              className="link-btn small"
              onClick={() =>
                confirmAndRun(`¿Volver a la descripción del diccionario base para ${defining.code}?`, () => api.dtcs.resetDefinition(vehicle.id, defining.code), () => {
                  setDefining(null);
                  dtcs.reload();
                })
              }
            >
              Restaurar la del diccionario base
            </button>
          )}
        </Modal>
      )}
      {notesFor && (
        <Modal title={`Notas de ${notesFor.code}`} onClose={() => setNotesFor(null)}>
          <RecordForm
            fields={[{ name: "notes", label: "Diagnóstico, piezas cambiadas, taller…", type: "textarea" }]}
            detailed
            initial={{ notes: notesFor.notes }}
            onSubmit={(d) => api.dtcs.setNotes(vehicle.id, notesFor.id, String(d.notes ?? ""))}
            onDone={() => {
              setNotesFor(null);
              dtcs.reload();
            }}
            onCancel={() => setNotesFor(null)}
          />
        </Modal>
      )}
    </div>
  );
}
