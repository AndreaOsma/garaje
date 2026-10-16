import { Suspense, lazy, useEffect, useState } from "react";
import { api, type Vehicle } from "../api";
import { ENGINE_PARTS } from "../content/engineParts";
import type { TabId } from "../router";
import type { Stroke } from "./EngineScene";
import { ErrorBox, Loading, useLoad } from "./ui";

const EngineScene = lazy(() => import("./EngineScene"));

const STROKE_ICON: Record<Stroke, string> = { admisión: "⬇️", compresión: "⏫", explosión: "💥", escape: "💨" };
const LEVEL_ICON = { ok: "✓", info: "ℹ", warn: "!", danger: "⛔" } as const;

type Props = { vehicle: Vehicle; dark: boolean; reducedMotion: boolean; goTab: (tab: TabId) => void; initialPart?: string | null };

/** Motor por dentro: animación del ciclo, despiece, corte y ficha de cada pieza. */
export function EngineExplorer({ vehicle, dark, reducedMotion, goTab, initialPart = null }: Props) {
  const data = useLoad(() => api.engineTwin(vehicle.id), [vehicle.id, vehicle.last_obd_at]);
  const [playing, setPlaying] = useState(!reducedMotion);
  const [rpm, setRpm] = useState(40);
  const [explode, setExplode] = useState(0);
  const [section, setSection] = useState(false);
  const [selected, setSelected] = useState<string | null>(initialPart);
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [noWebGL, setNoWebGL] = useState(false);

  useEffect(() => setPlaying(!reducedMotion), [reducedMotion]);

  if (data.loading && !data.data) return <Loading label="Abriendo el motor…" />;
  if (data.error || !data.data) return <ErrorBox message={data.error ?? "Sin datos"} onRetry={data.reload} />;
  const { kind, parts, cylinders } = data.data;
  const diesel = kind === "inline-diesel";
  const statuses = Object.fromEntries(Object.entries(parts).map(([k, p]) => [k, p.status]));
  const available = Object.entries(ENGINE_PARTS).filter(([, info]) => !(diesel ? info.gasolineOnly : info.dieselOnly));
  // En gasolina los códigos de inyectores se ven por cilindro; no hay pieza «injectors» separada.
  const cylItems = Array.from({ length: cylinders }, (_, i) => i + 1).flatMap((n) => (parts[`cyl${n}`]?.items ?? []).map((it) => ({ ...it, cyl: n })));
  const info = selected ? ENGINE_PARTS[selected] : null;
  // Leyenda: todo lo que tiene algo raro, por pieza y por cilindro (lo más grave primero).
  const RANKS = { danger: 0, warn: 1, info: 2, ok: 3 } as const;
  const problems = [
    ...Object.entries(parts)
      .filter(([k]) => !k.startsWith("cyl") && ENGINE_PARTS[k])
      .map(([k, p]) => ({ key: k, select: k, name: ENGINE_PARTS[k].name, level: p.status, text: p.items[0]?.text ?? "" })),
    ...Object.entries(parts)
      .filter(([k]) => k.startsWith("cyl"))
      .map(([k, p]) => ({ key: k, select: "pistons", name: `Cilindro ${k.slice(3)}`, level: p.status, text: p.items[0]?.text ?? "" })),
  ].sort((a, b) => RANKS[a.level] - RANKS[b.level]);
  const live = selected ? parts[selected]?.items ?? [] : [];

  return (
    <div className="engine">
      <div className="engine__stage">
        {noWebGL ? (
          <p className="muted">Tu navegador no puede mostrar 3D; usa la lista de piezas.</p>
        ) : (
          <div className="engine__canvas" role="img" aria-label={`Motor ${diesel ? "diésel" : "de gasolina"} de ${cylinders} cilindros en línea`}>
            <Suspense fallback={<Loading label="Cargando motor…" />}>
              <EngineScene
                kind={kind}
                cylinders={cylinders}
                statuses={statuses}
                selected={selected}
                playing={playing}
                rpm={rpm}
                explode={explode}
                section={section}
                dark={dark}
                onSelect={setSelected}
                onStrokes={setStrokes}
                onWebGLUnavailable={() => setNoWebGL(true)}
              />
            </Suspense>
            <div className="engine__legend">
              <div className="engine__legend-keys" aria-hidden>
                <span>
                  <i className="twin__dot twin__dot--danger" /> Grave
                </span>
                <span>
                  <i className="twin__dot twin__dot--warn" /> Atención
                </span>
                <span>
                  <i className="twin__dot twin__dot--info" /> Aviso
                </span>
              </div>
              {problems.length === 0 ? (
                <p className="engine__legend-ok">✅ Sin nada raro en el motor</p>
              ) : (
                <ul aria-label="Piezas con algo raro">
                  {problems.map((p) => (
                    <li key={p.key}>
                      <button type="button" className={`engine__problem engine__problem--${p.level}`} onClick={() => setSelected(p.select)}>
                        <span aria-hidden>{LEVEL_ICON[p.level]}</span> <strong>{p.name}:</strong> {p.text}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {strokes.length > 0 && (
              <ol className="engine__strokes" aria-label="Tiempo de cada cilindro">
                {strokes.map((s, i) => (
                  <li key={i} className={`stroke stroke--${s === "explosión" ? "power" : "other"}`}>
                    <span aria-hidden>{STROKE_ICON[s]}</span> Cil. {i + 1}: {s}
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
        <div className="engine__controls">
          <button type="button" className="btn btn--sm btn--primary" onClick={() => setPlaying((p) => !p)} aria-pressed={playing}>
            {playing ? "⏸ Pausa" : "▶ Arrancar"}
          </button>
          <label className="range">
            <span>Velocidad</span>
            <input type="range" min={5} max={600} value={rpm} onChange={(e) => setRpm(Number(e.target.value))} aria-valuetext={`${rpm} vueltas por minuto (a cámara lenta)`} />
          </label>
          <label className="range">
            <span>Despiece</span>
            <input type="range" min={0} max={1} step={0.01} value={explode} onChange={(e) => setExplode(Number(e.target.value))} />
          </label>
          <label className="check">
            <input type="checkbox" checked={section} onChange={(e) => setSection(e.target.checked)} />
            <span>Corte en sección</span>
          </label>
        </div>
      </div>

      <div className="engine__side">
        {info ? (
          <article className="engine__info" aria-live="polite">
            <div className="engine__info-head">
              <h3>{info.name}</h3>
              <button type="button" className="icon-btn" aria-label="Cerrar ficha" onClick={() => setSelected(null)}>
                ✕
              </button>
            </div>
            {live.length > 0 && (
              <ul className="engine__live">
                {live.map((it, i) => (
                  <li key={i}>
                    <button type="button" className={`twin__item twin__item--${it.level}`} onClick={() => goTab(it.target as TabId)}>
                      <span aria-hidden>{LEVEL_ICON[it.level]}</span> {it.text}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p>
              <strong>Qué es.</strong> {info.what}
            </p>
            <p>
              <strong>Cómo falla.</strong> {info.fails}
            </p>
            <p>
              <strong>Cuidados.</strong> {info.care}
            </p>
          </article>
        ) : (
          <p className="muted small">
            Toca una pieza del motor o elígela abajo. Las de color tienen averías, incidencias o mantenimiento pendiente.
          </p>
        )}
        {cylItems.length > 0 && !selected && (
          <ul className="engine__live">
            {cylItems.map((it, i) => (
              <li key={i} className={`twin__item twin__item--${it.level}`}>
                <span aria-hidden>{LEVEL_ICON[it.level]}</span> Cilindro {it.cyl}: {it.text}
              </li>
            ))}
          </ul>
        )}
        <ul className="twin__list" aria-label="Piezas del motor">
          {available.map(([id, p]) => {
            const st = parts[id]?.status ?? "ok";
            return (
              <li key={id}>
                <button type="button" className={`twin__part${selected === id ? " is-selected" : ""}`} aria-pressed={selected === id} onClick={() => setSelected(selected === id ? null : id)}>
                  <span className={`twin__dot twin__dot--${st}`} aria-hidden />
                  {p.name}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
