import { Suspense, lazy, useEffect, useState } from "react";
import type { TwinItem } from "../api";
import { ASSEMBLIES, partForText } from "../content/assemblies";
import type { TabId } from "../router";
import type { Assembly, PartStatus } from "./AssemblyScene";
import { Loading } from "./ui";

const AssemblyScene = lazy(() => import("./AssemblyScene"));

const LEVEL_ICON = { ok: "✓", info: "ℹ", warn: "!", danger: "⛔" } as const;
const RANK = { danger: 0, warn: 1, info: 2, ok: 3 } as const;

type Props = { assembly: Assembly; items: TwinItem[]; reducedMotion: boolean; goTab: (tab: TabId) => void; initialPart?: string | null };

/** Conjunto mecánico en detalle (frenos, suspensión, caja, turbo): animación, despiece, corte y fichas. */
export function AssemblyExplorer({ assembly, items, reducedMotion, goTab, initialPart = null }: Props) {
  const info = ASSEMBLIES[assembly]!;
  const [playing, setPlaying] = useState(!reducedMotion);
  const [speed, setSpeed] = useState(1);
  const [explode, setExplode] = useState(0);
  const [section, setSection] = useState(false);
  const [selected, setSelected] = useState<string | null>(initialPart);
  const [state, setState] = useState("");
  const [noWebGL, setNoWebGL] = useState(false);
  useEffect(() => setPlaying(!reducedMotion), [reducedMotion]);

  // Avisos del modelo general repartidos por pieza.
  const byPart: Record<string, TwinItem[]> = {};
  for (const it of items.filter((i) => i.level !== "ok")) (byPart[partForText(info, it.text)] ??= []).push(it);
  const statuses: Record<string, PartStatus> = Object.fromEntries(
    Object.entries(byPart).map(([k, list]) => [k, [...list].sort((a, b) => RANK[a.level] - RANK[b.level])[0].level])
  );
  const problems = Object.entries(byPart)
    .flatMap(([k, list]) => list.map((it) => ({ key: k, it })))
    .sort((a, b) => RANK[a.it.level] - RANK[b.it.level]);
  const part = selected ? info.parts[selected] : null;

  return (
    <div className="engine">
      <div className="engine__stage">
        {noWebGL ? (
          <p className="muted">Tu navegador no puede mostrar 3D; usa la lista de piezas.</p>
        ) : (
          <div className="engine__canvas" role="img" aria-label={info.title}>
            <Suspense fallback={<Loading label="Cargando…" />}>
              <AssemblyScene
                assembly={assembly}
                statuses={statuses}
                selected={selected}
                playing={playing}
                speed={speed}
                explode={explode}
                section={section}
                onSelect={setSelected}
                onState={setState}
                onWebGLUnavailable={() => setNoWebGL(true)}
              />
            </Suspense>
            {state && <p className="engine__state">{state}</p>}
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
                <p className="engine__legend-ok">✅ Nada raro en este conjunto</p>
              ) : (
                <ul aria-label="Piezas con algo raro">
                  {problems.map(({ key, it }, i) => (
                    <li key={i}>
                      <button type="button" className={`engine__problem engine__problem--${it.level}`} onClick={() => setSelected(key)}>
                        <span aria-hidden>{LEVEL_ICON[it.level]}</span> <strong>{info.parts[key]?.name ?? key}:</strong> {it.text}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
        <div className="engine__controls">
          <button type="button" className="btn btn--sm btn--primary" onClick={() => setPlaying((p) => !p)} aria-pressed={playing}>
            {playing ? "⏸ Pausa" : "▶ En marcha"}
          </button>
          <label className="range">
            <span>Velocidad</span>
            <input type="range" min={0.1} max={3} step={0.1} value={speed} onChange={(e) => setSpeed(Number(e.target.value))} />
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
        {part ? (
          <article className="engine__info" aria-live="polite">
            <div className="engine__info-head">
              <h3>{part.name}</h3>
              <button type="button" className="icon-btn" aria-label="Cerrar ficha" onClick={() => setSelected(null)}>
                ✕
              </button>
            </div>
            {(byPart[selected!] ?? []).length > 0 && (
              <ul className="engine__live">
                {byPart[selected!].map((it, i) => (
                  <li key={i}>
                    <button type="button" className={`twin__item twin__item--${it.level}`} onClick={() => goTab(it.target as TabId)}>
                      <span aria-hidden>{LEVEL_ICON[it.level]}</span> {it.text}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p>
              <strong>Qué es.</strong> {part.what}
            </p>
            <p>
              <strong>Cómo falla.</strong> {part.fails}
            </p>
            <p>
              <strong>Cuidados.</strong> {part.care}
            </p>
          </article>
        ) : (
          <p className="muted small">Toca una pieza o elígela abajo. Las de color tienen averías, incidencias o mantenimiento pendiente.</p>
        )}
        <ul className="twin__list" aria-label="Piezas">
          {Object.entries(info.parts).map(([id, p]) => (
            <li key={id}>
              <button type="button" className={`twin__part${selected === id ? " is-selected" : ""}`} aria-pressed={selected === id} onClick={() => setSelected(selected === id ? null : id)}>
                <span className={`twin__dot twin__dot--${statuses[id] ?? "ok"}`} aria-hidden />
                {p.name}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
