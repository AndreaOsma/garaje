import { useEffect, useState } from "react";
import { api, type Course, type License, type LicenseProgressInput, type LicenseStatus } from "../api";
import { EmptyState, ErrorBox, Loading, useLoad } from "../components/ui";
import { date } from "../format";
import { linkTo, type Navigate } from "../router";
import { GameBar, Mascot, MixedReviewCard, PathView, play, Quests, Shop, StreakCard, WEEKDAYS_ES, type GameState, type PathUnit } from "../vendor/learn-game";
import { BookOpenCheck, Bus, Car, Check, CircleAlert, CircleCheck, CircleDashed, CircleMinus, ClockAlert, Download, Flame, Icon, Library, Motorcycle, NotebookPen, Repeat, Target, Truck, Upload, Zap } from "../vendor/icons";

const GROUPS: { id: License["group"]; title: string }[] = [
  { id: "moto", title: "Motos" },
  { id: "coche", title: "Coche y remolque" },
  { id: "camion", title: "Camiones" },
  { id: "autobus", title: "Autobuses" },
];

const STATUS: Record<LicenseStatus, { label: string; icon: string }> = {
  none: { label: "Sin empezar", icon: CircleMinus },
  planning: { label: "Lo estoy pensando", icon: CircleDashed },
  studying: { label: "Preparándolo", icon: Library },
  obtained: { label: "Lo tengo", icon: CircleCheck },
};

const QUEST_ICON: Record<string, string> = { xp: Zap, lessons: BookOpenCheck, combo: Flame, perfect: Target, correct: CircleCheck, exam: NotebookPen };
// Icono de cada grupo de carné (el emoji que manda el servidor no se usa).
const GROUP_ICON: Record<string, string> = { moto: Motorcycle, coche: Car, camion: Truck, autobus: Bus };

function StatusBadge({ status }: { status: LicenseStatus }) {
  const cls = { none: "inactive", planning: "soon", studying: "info", obtained: "ok" }[status];
  return (
    <span className={`badge badge--${cls}`}>
      <Icon svg={STATUS[status].icon} /> {STATUS[status].label}
    </span>
  );
}

function CourseBar({ course }: { course: License["course"] }) {
  if (!course || !course.lessons_total) return null;
  const pct = Math.round((course.lessons_done / course.lessons_total) * 100);
  return (
    <span className="license-card__progress">
      <span className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label="Teórico">
        <span className={`progress__fill${pct === 100 ? " is-done" : ""}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="muted small">
        Teórico {course.lessons_done}/{course.lessons_total}
      </span>
    </span>
  );
}

/** Lo que falta para poder ir a por el permiso, en una línea. */
function readiness(l: License): string | null {
  if (l.status === "obtained") return l.obtained_on ? `Desde el ${date(l.obtained_on)}` : null;
  if (l.covered_by) return l.covered_by;
  const blocking = l.requirements.find((r) => r.state !== "ok");
  if (blocking) return blocking.state === "wait" && blocking.until ? `${blocking.label}: podrás a partir del ${date(blocking.until)}` : `Requisito: ${blocking.label.charAt(0).toLowerCase()}${blocking.label.slice(1)}`;
  if (l.next_exam_on) return `Próximo examen: ${date(l.next_exam_on)}`;
  return null;
}

export function Licenses({ navigate, detailed }: { navigate: Navigate; detailed: boolean }) {
  const q = useLoad(() => api.licenses.list(), []);
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox message={q.error} onRetry={q.reload} />;
  const rows = q.data ?? [];
  const held = rows.filter((l) => l.status === "obtained");
  const active = rows.filter((l) => l.status === "studying" || l.status === "planning");

  return (
    <div className="licenses">
      <section className="panel" aria-labelledby="licenses-title">
        <header className="panel__header">
          <h2 id="licenses-title">Carnés</h2>
        </header>
        <p className="muted">
          Tus permisos de conducir, lo que te falta para el siguiente y su teórico en lecciones cortas, con racha y simulacros.
        </p>
        <div className="license-held" aria-label="Permisos que tienes">
          {held.length ? (
            held.map((l) => (
              <a key={l.code} className="license-chip is-held" href={`/carnes/${l.code}`} onClick={linkTo(navigate, { name: "license", code: l.code })}>
                <Icon svg={GROUP_ICON[l.group] ?? Car} /> {l.code}
              </a>
            ))
          ) : (
            <p className="small">
              ¿Qué permisos tienes ya? Abre el tuyo (por ejemplo el <strong>B</strong>) y márcalo como «Lo tengo» con su fecha: así se calculan los requisitos del resto.
            </p>
          )}
        </div>
      </section>

      {active.length > 0 && (
        <section className="panel" aria-labelledby="licenses-active">
          <header className="panel__header">
            <h2 id="licenses-active">Preparando</h2>
          </header>
          <ul className="license-grid">
            {active.map((l) => (
              <LicenseCard key={l.code} l={l} navigate={navigate} detailed={detailed} />
            ))}
          </ul>
        </section>
      )}

      {GROUPS.map((g) => {
        // En «mínimo», solo motos y coche: camión y autobús quedan para «detallado».
        if (!detailed && (g.id === "camion" || g.id === "autobus")) return null;
        const list = rows.filter((l) => l.group === g.id && l.status === "none");
        if (!list.length) return null;
        return (
          <section key={g.id} className="panel" aria-labelledby={`licenses-${g.id}`}>
            <header className="panel__header">
              <h2 id={`licenses-${g.id}`}>{g.title}</h2>
            </header>
            <ul className="license-grid">
              {list.map((l) => (
                <LicenseCard key={l.code} l={l} navigate={navigate} detailed={detailed} />
              ))}
            </ul>
          </section>
        );
      })}
      <p className="muted small licenses__disclaimer">
        Resumen orientativo del Reglamento General de Conductores para quien ya tiene el B. Tasas, formato de los exámenes y cursos cambian:
        confírmalo en la{" "}
        <a href={rows[0]?.dgt_url ?? "https://www.dgt.es"} target="_blank" rel="noopener noreferrer">
          web de la DGT
        </a>
        .
      </p>
    </div>
  );
}

function LicenseCard({ l, navigate, detailed }: { l: License; navigate: Navigate; detailed: boolean }) {
  const hint = readiness(l);
  return (
    <li>
      <a className={`license-card${l.status === "obtained" ? " is-held" : ""}`} href={`/carnes/${l.code}`} onClick={linkTo(navigate, { name: "license", code: l.code })}>
        <span className="license-card__head">
          <span className="license-card__code">
            <Icon svg={GROUP_ICON[l.group] ?? Car} /> {l.code}
          </span>
          {l.status !== "none" && <StatusBadge status={l.status} />}
        </span>
        <span className="license-card__name">{l.name}</span>
        {detailed && <span className="muted small">{l.allows}</span>}
        {hint && <span className="small license-card__hint">{hint}</span>}
        <CourseBar course={l.course} />
      </a>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Un permiso
// ---------------------------------------------------------------------------

/** El curso en el formato del camino compartido. */
function toPath(course: Course): PathUnit[] {
  return course.units.map((u) => ({
    id: u.id,
    title: u.extra ? `${u.title} (opcional)` : u.title,
    done: u.done,
    badgeClaimed: u.chest_claimed,
    lessons: u.lessons.map((l) => ({
      id: l.id,
      title: l.title,
      done: l.done,
      locked: l.locked,
      current: l.id === course.next_lesson_id,
      level: l.level,
      href: `/carnes/leccion/${l.id}`,
      detail: `${l.steps} preguntas${l.done ? ` · nivel ${l.level}/5` : ""}` + (l.best_ratio !== null ? ` · mejor ${Math.round(l.best_ratio * 100)} %` : ""),
    })),
  }));
}

type SaveState = { kind: "idle" | "saving" | "saved" | "error"; message?: string };

function ProgressForm({ l, onSaved, detailed }: { l: License; onSaved: (l: License) => void; detailed: boolean }) {
  const initial = (): LicenseProgressInput => ({
    status: l.status,
    steps: Object.fromEntries(l.steps.map((s) => [s.key, s.done_on])),
    next_exam_on: l.next_exam_on,
    obtained_on: l.obtained_on,
    notes: l.user_notes,
  });
  const [form, setForm] = useState<LicenseProgressInput>(initial);
  const [state, setState] = useState<SaveState>({ kind: "idle" });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setForm(initial()), [l.code]);

  const save = async (next: LicenseProgressInput) => {
    setState({ kind: "saving" });
    try {
      onSaved(await api.licenses.save(l.code, next));
      setState({ kind: "saved", message: "Guardado" });
    } catch (err) {
      setState({ kind: "error", message: err instanceof Error ? err.message : "No se pudo guardar" });
    }
  };
  const today = new Date().toISOString().slice(0, 10);

  return (
    <form
      className="license-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save(form);
      }}
    >
      <fieldset className="segmented-field">
        <legend className="small muted">Tu situación</legend>
        <div className="segmented" role="radiogroup" aria-label="Tu situación con este permiso">
          {(Object.keys(STATUS) as LicenseStatus[]).map((s) => (
            <button key={s} type="button" role="radio" aria-checked={form.status === s} className={form.status === s ? "is-active" : ""}
              onClick={() => setForm({ ...form, status: s, obtained_on: s === "obtained" ? form.obtained_on ?? today : form.obtained_on })}>
              {STATUS[s].label}
            </button>
          ))}
        </div>
      </fieldset>

      {form.status === "obtained" ? (
        <label className="field">
          <span>Fecha de expedición</span>
          <input type="date" value={form.obtained_on ?? ""} max={today} onChange={(e) => setForm({ ...form, obtained_on: e.target.value || null })} />
          <small className="muted">Cuenta para la antigüedad que piden otros permisos (p. ej. 2 años de A2 para el A).</small>
        </label>
      ) : (
        <>
          <ol className="license-steps" aria-label="Pasos">
            {l.steps.map((s) => {
              const done = form.steps[s.key] ?? null;
              const id = `step-${l.code}-${s.key}`;
              return (
                <li key={s.key} className={done ? "is-done" : ""}>
                  <input id={id} type="checkbox" checked={Boolean(done)} onChange={(e) => setForm({ ...form, steps: { ...form.steps, [s.key]: e.target.checked ? today : null } })} />
                  <label htmlFor={id}>{s.label}</label>
                  {done && detailed && (
                    <input type="date" aria-label={`Fecha: ${s.label}`} value={done} max={today}
                      onChange={(e) => setForm({ ...form, steps: { ...form.steps, [s.key]: e.target.value || today } })} />
                  )}
                  {done && !detailed && <span className="muted small">{date(done)}</span>}
                </li>
              );
            })}
          </ol>
          <label className="field">
            <span>Próximo examen</span>
            <input type="date" value={form.next_exam_on ?? ""} min={today} onChange={(e) => setForm({ ...form, next_exam_on: e.target.value || null })} />
          </label>
        </>
      )}
      {detailed && (
        <label className="field">
          <span>Notas</span>
          <textarea rows={3} value={form.notes} maxLength={5000} placeholder="Autoescuela, profesor, fallos del último examen…" onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </label>
      )}
      <div className="form-actions">
        <button type="submit" className="btn btn--primary btn--sm" disabled={state.kind === "saving"}>
          {state.kind === "saving" ? "Guardando…" : "Guardar"}
        </button>
        <span role="status" aria-live="polite" className={`small ${state.kind === "error" ? "text-crit" : "muted"}`}>
          {state.kind === "saved" || state.kind === "error" ? state.message : ""}
        </span>
      </div>
    </form>
  );
}

function Mastery({ courseId, navigate }: { courseId: number; navigate: Navigate }) {
  const { data } = useLoad(() => api.learn.concepts(courseId), [courseId]);
  const rows = (data ?? []).filter((c) => c.mastery !== null).slice(0, 8);
  if (!rows.length) return null;
  return (
    <section className="card">
      <div className="card__head">
        <h2 className="card__title">Dominio por tema</h2>
      </div>
      <ul className="mastery">
        {rows.map((c) => (
          <li key={c.concept}>
            <a href={`/carnes/practica/${courseId}?concepto=${encodeURIComponent(c.concept)}`} onClick={linkTo(navigate, { name: "practice", courseId, concept: c.concept })}>
              {c.concept}
            </a>
            <span className={`mastery__pct${(c.mastery ?? 0) < 0.6 ? " text-crit" : ""}`}>{Math.round((c.mastery ?? 0) * 100)} %</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function CourseSection({ license, navigate, detailed, onChanged }: { license: License; navigate: Navigate; detailed: boolean; onChanged: () => void }) {
  const courseId = license.course?.id ?? null;
  const course = useLoad(() => (courseId ? api.learn.course(courseId) : Promise.resolve(null)), [courseId]);
  const gameQ = useLoad(() => api.learn.game(), []);
  const mixedGroups = useLoad(() => api.learn.mixedGroups(), []);
  const settings = useLoad(() => api.learn.settings(), []);
  const sounds = settings.data?.sounds !== false;
  const [reward, setReward] = useState<string | null>(null);
  const [importState, setImportState] = useState<SaveState>({ kind: "idle" });

  useEffect(() => {
    if (!reward) return;
    const t = window.setTimeout(() => setReward(null), 2600);
    return () => window.clearTimeout(t);
  }, [reward]);

  const rewarded = (game: GameState, text: string) => {
    play("chest", sounds);
    gameQ.setData(game);
    setReward(text);
  };
  const onImport = async (file: File | undefined) => {
    if (!file) return;
    setImportState({ kind: "saving" });
    try {
      await api.learn.importCourse(license.code, file);
      setImportState({ kind: "saved", message: "Lecciones añadidas" });
      onChanged();
      void course.reload();
    } catch (err) {
      setImportState({ kind: "error", message: err instanceof Error ? err.message : "No se pudo importar" });
    }
  };

  const c = course.data;
  const game = gameQ.data;
  const exam = license.exam;

  return (
    <div className="learn-page">
      <GameBar game={game ?? null}>
        <span className="learn-bar__course">Teórico {license.code}</span>
      </GameBar>
      {reward && (
        <div className="toast toast--reward" role="status">
          {reward}
        </div>
      )}
      {course.loading && courseId ? <Loading /> : course.error ? <ErrorBox message={course.error} onRetry={course.reload} /> : null}
      {!courseId && (
        <section className="panel">
          <div className="learn-empty">
            <Mascot kind="oso" mood="think" size={96} />
            <EmptyState title={`Aún no hay lecciones del ${license.code}`}>
              Garaje trae de serie el teórico del A2. Para este permiso puedes importar un pack de lecciones en .json (formato campus-pilot-course).
            </EmptyState>
          </div>
        </section>
      )}

      <div className="learn-layout">
        <div className="learn-main">
          {c && (
            <>
              <div className="learn-hello">
                <Mascot kind="oso" mood={c.next_lesson_id ? "happy" : "cheer"} size={64} />
                <p>
                  {c.next_lesson_id ? "¡Vamos con la siguiente!" : "¡Temario completado! Repasa para subir de nivel y haz simulacros."}
                  <span className="muted small">
                    {" "}
                    · {c.lessons_done}/{c.lessons_total} lecciones
                  </span>
                </p>
              </div>
              <PathView
                units={toPath(c)}
                onGo={(l, e) => linkTo(navigate, { name: "lesson", id: Number(l.id) })(e)}
                onBadge={(id) =>
                  void api.learn
                    .openChest(Number(id))
                    .then((r) => {
                      rewarded(r.game, `¡Insignia de unidad! +${r.gems} chispas`);
                      void course.reload();
                    })
                    .catch(() => undefined)
                }
              />
            </>
          )}
        </div>

        <aside className="learn-side">
          {game && <StreakCard game={game} weekdays={WEEKDAYS_ES} />}
          {mixedGroups.data && (
            <MixedReviewCard
              groups={mixedGroups.data}
              storageKey="garaje:mixed-off"
              groupLabel="carnés"
              onStart={(ids) => navigate({ name: "mixed", courses: ids.length === mixedGroups.data!.filter((g) => g.count).length ? [] : ids })}
            />
          )}
          {c && (
            <section className="card">
              <div className="card__head">
                <h2 className="card__title">Practicar</h2>
              </div>
              <div className="practice-grid">
                <a className="practice-btn" href="/carnes/repaso" onClick={linkTo(navigate, { name: "review" })}>
                  <span aria-hidden><Icon svg={Repeat} /></span> Repasar fallos
                </a>
                <a className="practice-btn" href={`/carnes/practica/${c.id}`} onClick={linkTo(navigate, { name: "practice", courseId: c.id, concept: "" })}>
                  <span aria-hidden><Icon svg={Target} /></span> Lo más flojo
                </a>
                <a className="practice-btn" href={`/carnes/simulacro/${c.id}`} onClick={linkTo(navigate, { name: "exam", courseId: c.id })}>
                  <span aria-hidden><Icon svg={NotebookPen} /></span> Simulacro
                </a>
              </div>
              <p className="muted small">
                Simulacro: {exam.questions} preguntas, {exam.minutes} min, aprobado con {exam.max_errors} fallos como mucho
                {exam.official ? " (el formato del examen de la DGT)" : " (formato orientativo)"}.
              </p>
            </section>
          )}
          {game && <Quests game={game} icons={QUEST_ICON} onClaim={(id) => void api.learn.claimQuest(id).then((r) => rewarded(r.game, `+${r.gems} chispas`)).catch(() => undefined)} />}
          {game && <Shop game={game} onBuy={() => void api.learn.buy("freeze").then((g) => rewarded(g, "Día libre guardado")).catch(() => undefined)} />}
          {c && <Mastery courseId={c.id} navigate={navigate} />}
        </aside>
      </div>

      {detailed && (
        <section className="panel">
          <header className="panel__header">
            <h2>Lecciones en .json</h2>
          </header>
          <p className="muted small">
            Formato campus-pilot-course (el mismo de Campus Pilot, Bitácora e Insignia), con <code>subject_code</code> «{license.code}». Reimportar actualiza por «ref» sin
            perder el progreso.
          </p>
          <div className="form-actions">
            {c && (
              <a className="btn btn--ghost btn--sm" href={api.learn.exportUrl(c.id)} download={`${c.slug}.json`}>
                <Icon svg={Download} /> Exportar
              </a>
            )}
            <label className="btn btn--ghost btn--sm file-btn">
              <Icon svg={Upload} /> Añadir lecciones (.json)
              <input type="file" accept="application/json,.json" className="sr-only" onChange={(e) => void onImport(e.target.files?.[0])} />
            </label>
            <span role="status" aria-live="polite" className={`small ${importState.kind === "error" ? "text-crit" : "muted"}`}>
              {importState.kind === "saving" ? "Importando…" : importState.message ?? ""}
            </span>
          </div>
        </section>
      )}
    </div>
  );
}

export function LicenseDetail({ code, navigate, detailed }: { code: string; navigate: Navigate; detailed: boolean }) {
  const q = useLoad(() => api.licenses.list(), [code]);
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox message={q.error} onRetry={q.reload} />;
  const rows = q.data ?? [];
  const l = rows.find((x) => x.code === code);
  if (!l) return <ErrorBox message="Permiso no encontrado" />;
  const replace = (next: License) => q.setData(rows.map((x) => (x.code === next.code ? next : x)));

  return (
    <div className="licenses">
      <a className="back-link" href="/carnes" onClick={linkTo(navigate, { name: "licenses" })}>
        ← Carnés
      </a>
      <section className="panel license-detail" aria-labelledby="license-title">
        <header className="panel__header">
          <h2 id="license-title">
            <Icon svg={GROUP_ICON[l.group] ?? Car} /> Permiso {l.code} · {l.name}
          </h2>
          <StatusBadge status={l.status} />
        </header>
        <p>{l.allows}</p>
        <ul className="license-facts">
          <li>Edad mínima: {l.age} años</li>
          {l.requirements.map((r) => (
            <li key={r.label} className={`req req--${r.state}`}>
              <Icon svg={r.state === "ok" ? CircleCheck : r.state === "wait" ? ClockAlert : CircleAlert} /> {r.label}
              {r.state === "wait" && r.until && <span className="muted"> · a partir del {date(r.until)}</span>}
              {r.state === "unknown" && <span className="muted"> · añade la fecha en que lo obtuviste</span>}
              {r.state === "missing" && <span className="muted"> · aún no lo tienes marcado</span>}
            </li>
          ))}
          {l.covered_by && (
            <li className="req req--ok">
              <span aria-hidden><Icon svg={Check} /></span> {l.covered_by}
            </li>
          )}
        </ul>
        {l.notes && <p className="muted small">{l.notes}</p>}
        <ProgressForm l={l} detailed={detailed} onSaved={replace} />
        <p className="muted small">
          Orientativo:{" "}
          <a href={l.dgt_url} target="_blank" rel="noopener noreferrer">
            confirma los requisitos en la DGT
          </a>
          .
        </p>
      </section>

      {l.status !== "obtained" && <CourseSection license={l} navigate={navigate} detailed={detailed} onChanged={q.reload} />}
    </div>
  );
}
