import { Suspense, lazy, useEffect, useState } from "react";
import { api, type TwinComponent, type Vehicle } from "../api";
import type { TabId } from "../router";
import { AssemblyExplorer } from "./AssemblyExplorer";
import type { Assembly } from "./AssemblyScene";
import { EngineExplorer } from "./EngineExplorer";
import { Modal } from "./Modal";
import { ErrorBox, Loading, useLoad } from "./ui";

const CarScene = lazy(() => import("./CarScene"));

const LEVEL = {
  ok: { icon: "✓", label: "Bien" },
  info: { icon: "ℹ", label: "Aviso" },
  warn: { icon: "!", label: "Atención" },
  danger: { icon: "⛔", label: "Grave" },
} as const;

const RANK = { danger: 0, warn: 1, info: 2, ok: 3 } as const;
// Piezas del modelo general desde las que tiene sentido abrir el motor por dentro.
const ENGINE_IDS = new Set(["engine", "injection", "turbo", "egr", "intake", "exhaust", "cooling", "battery"]);
// Piezas que, al tocarlas en el coche, abren el motor directamente (con esa pieza elegida).
const OPEN_ENGINE: Record<string, string | null> = { engine: null, injection: "fuel_rail", egr: "egr", intake: "intake" };
// Piezas con su propio conjunto en detalle.
const OPEN_ASSEMBLY: Record<string, Assembly> = { brakes: "brake", tyres: "brake", suspension: "suspension", gearbox: "gearbox", turbo: "turbo" };
const ASSEMBLY_SOURCES: Record<Assembly, string[]> = {
  brake: ["brakes", "tyres"],
  suspension: ["suspension"],
  gearbox: ["gearbox"],
  turbo: ["turbo"],
  propeller: [],
  landing_gear: [],
  flight_controls: [],
};
const ASSEMBLY_TITLE: Partial<Record<Assembly, string>> = {
  brake: "Frenos por dentro",
  suspension: "Suspensión por dentro",
  gearbox: "Caja de cambios y embrague por dentro",
  turbo: "Turbo por dentro",
};

type Props = { vehicle: Vehicle; detailed: boolean; dark: boolean; goTab: (tab: TabId) => void };

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(mq.matches);
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return reduced;
}

/** Gemelo digital: el coche en 3D (rayos X) con cada pieza coloreada por su estado. */
export function CarTwin({ vehicle, detailed, dark, goTab }: Props) {
  const twin = useLoad(() => api.twin(vehicle.id), [vehicle.id, vehicle.odometer_km, vehicle.last_obd_at]);
  const [selected, setSelected] = useState<string | null>(null);
  const [noWebGL, setNoWebGL] = useState(false);
  const [engineOpen, setEngineOpen] = useState(false);
  const [enginePart, setEnginePart] = useState<string | null>(null);
  const openEngine = (part: string | null) => {
    setEnginePart(part);
    setEngineOpen(true);
  };
  const [assembly, setAssembly] = useState<Assembly | null>(null);
  const assemblyFor = (id: string): Assembly | null => {
    const a = OPEN_ASSEMBLY[id];
    if (!a) return null;
    if (a === "gearbox" && vehicle.fuel_type === "electric") return null;
    if (a === "turbo" && vehicle.fuel_type !== "diesel") return null;
    return a;
  };
  // Tocar una pieza con vista detallada en el coche la abre directamente: el motor, o su
  // conjunto (frenos, suspensión, caja, turbo).
  const select = (id: string | null) => {
    setSelected(id);
    if (!id) return;
    const a = assemblyFor(id);
    if (a) setAssembly(a);
    else if (id in OPEN_ENGINE && vehicle.fuel_type !== "electric") openEngine(OPEN_ENGINE[id]);
  };
  const [mode, setMode] = useState<"xray" | "exterior">(() => {
    try {
      return localStorage.getItem("garaje-twin-mode") === "exterior" ? "exterior" : "xray";
    } catch {
      return "xray";
    }
  });
  const changeMode = (m: "xray" | "exterior") => {
    setMode(m);
    try {
      localStorage.setItem("garaje-twin-mode", m);
    } catch {
      /* sin almacenamiento: no se recuerda */
    }
  };
  const reducedMotion = useReducedMotion();

  if (twin.loading && !twin.data) return <Loading label="Montando el coche…" />;
  if (twin.error) return <ErrorBox message={twin.error} onRetry={twin.reload} />;
  const data = twin.data!;
  const statuses = Object.fromEntries(data.components.map((c) => [c.id, c.status]));
  const sorted = [...data.components].sort((a, b) => RANK[a.status] - RANK[b.status] || a.name.localeCompare(b.name));
  const withProblems = sorted.filter((c) => c.status !== "ok");
  const listed = detailed ? sorted : withProblems;
  const current: TwinComponent | undefined = data.components.find((c) => c.id === selected);

  return (
    <section className="panel twin" aria-label="Tu coche por dentro">
      <header className="panel__header">
        <h2>Tu coche por dentro</h2>
        {noWebGL ? (
          <span className="muted small">Vista en lista</span>
        ) : (
          <div className="segmented" role="group" aria-label="Vista del coche">
            <button type="button" aria-pressed={mode === "xray"} className={mode === "xray" ? "is-active" : ""} onClick={() => changeMode("xray")}>
              Rayos X
            </button>
            <button type="button" aria-pressed={mode === "exterior"} className={mode === "exterior" ? "is-active" : ""} onClick={() => changeMode("exterior")}>
              Exterior
            </button>
          </div>
        )}
      </header>
      {vehicle.fuel_type !== "electric" && (
        <button type="button" className="btn btn--ghost btn--sm engine-cta" onClick={() => openEngine(null)}>
          🔍 Motor por dentro: pistones, levas, válvulas{vehicle.fuel_type === "diesel" ? ", turbo, EGR, FAP" : ""}…
        </button>
      )}
      {assembly && (
        <Modal title={ASSEMBLY_TITLE[assembly] ?? "Por dentro"} onClose={() => setAssembly(null)} wide>
          <AssemblyExplorer
            assembly={assembly}
            items={data.components.filter((c) => ASSEMBLY_SOURCES[assembly].includes(c.id)).flatMap((c) => c.items)}
            reducedMotion={reducedMotion}
            goTab={(t) => {
              setAssembly(null);
              goTab(t);
            }}
          />
        </Modal>
      )}
      {engineOpen && (
        <Modal title={`Motor de ${vehicle.cylinders ?? 4} cilindros en línea · ${vehicle.fuel_type === "diesel" ? "diésel" : "gasolina"}`} onClose={() => setEngineOpen(false)} wide>
          <EngineExplorer
            vehicle={vehicle}
            dark={dark}
            reducedMotion={reducedMotion}
            initialPart={enginePart}
            goTab={(t) => {
              setEngineOpen(false);
              goTab(t);
            }}
          />
        </Modal>
      )}
      <div className="twin__layout">
        {!noWebGL && (
          <div className="twin__canvas" role="img" aria-label={`Modelo 3D de ${vehicle.name}: ${withProblems.length ? withProblems.map((c) => `${c.name} (${LEVEL[c.status].label})`).join(", ") : "todas las piezas bien"}`}>
            <Suspense fallback={<Loading label="Cargando 3D…" />}>
              <CarScene
                fuelType={vehicle.fuel_type}
                statuses={statuses}
                selected={selected}
                dark={dark}
                reducedMotion={reducedMotion}
                mode={mode}
                bodyColor={vehicle.color || "#8aa2b8"}
                onSelect={select}
                onWebGLUnavailable={() => setNoWebGL(true)}
              />
            </Suspense>
            <ul className="twin__legend" aria-hidden>
              {(["danger", "warn", "info", "ok"] as const).map((l) => (
                <li key={l}>
                  <span className={`twin__dot twin__dot--${l}`} /> {LEVEL[l].label}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="twin__side">
          {current ? (
            <div className="twin__detail" aria-live="polite">
              <div className="twin__detail-head">
                <h3>
                  <span className={`twin__dot twin__dot--${current.status}`} aria-hidden /> {current.name}
                </h3>
                <button type="button" className="icon-btn" aria-label="Cerrar detalle" onClick={() => setSelected(null)}>
                  ✕
                </button>
              </div>
              {assemblyFor(current.id) && (
                <button type="button" className="btn btn--sm btn--primary engine-open" onClick={() => setAssembly(assemblyFor(current.id))}>
                  🔍 Ver por dentro
                </button>
              )}
              {ENGINE_IDS.has(current.id) && !assemblyFor(current.id) && vehicle.fuel_type !== "electric" && (
                <button type="button" className="btn btn--sm btn--primary engine-open" onClick={() => openEngine(OPEN_ENGINE[current.id] ?? null)}>
                  🔍 Ver el motor por dentro
                </button>
              )}
              {current.items.length === 0 ? (
                <p className="muted">Nada pendiente en esta pieza.</p>
              ) : (
                <ul className="twin__items">
                  {current.items.map((it, i) => (
                    <li key={i}>
                      <button type="button" className={`twin__item twin__item--${it.level}`} onClick={() => goTab(it.target as TabId)}>
                        <span aria-hidden>{LEVEL[it.level].icon}</span> {it.text}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : withProblems.length === 0 ? (
            <p className="all-good">✅ Todas las piezas sin problemas conocidos.</p>
          ) : (
            <p className="muted small">Toca una pieza en el coche o en la lista para ver qué le pasa.</p>
          )}

          {listed.length > 0 && (
            <ul className="twin__list" aria-label="Piezas">
              {listed.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className={`twin__part${selected === c.id ? " is-selected" : ""}`}
                    aria-pressed={selected === c.id}
                    onClick={() => select(selected === c.id ? null : c.id)}
                  >
                    <span className={`twin__dot twin__dot--${c.status}`} aria-hidden />
                    <span className="twin__part-name">{c.name}</span>
                    <span className="sr-only">: {LEVEL[c.status].label}</span>
                    {c.items.filter((i) => i.level !== "ok").length > 0 && (
                      <span className="muted small">{c.items.filter((i) => i.level !== "ok").length}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {detailed && data.unassigned.length > 0 && (
            <div className="subsection">
              <p className="small muted">Sin pieza asignada (códigos del fabricante, incidencias genéricas):</p>
              <ul className="twin__items">
                {data.unassigned.map((it, i) => (
                  <li key={i}>
                    <button type="button" className={`twin__item twin__item--${it.level}`} onClick={() => goTab(it.target as TabId)}>
                      <span aria-hidden>{LEVEL[it.level].icon}</span> {it.text}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
