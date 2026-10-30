import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type AnswerResult, type CompleteResult, type GameState, type LessonFull, type PublicStep } from "../api";
import { ErrorBox, Loading } from "../components/ui";
import { InlineRich, RichText } from "../lib/rich";
import { linkTo, type Navigate, type Route } from "../router";
import { ComboFlash, EndScreen, PlayerFoot, PlayerTop, play, PRAISE, QuestionBubble, StreakScreen, vibrate, WEEKDAYS_ES } from "../vendor/learn-game";
import { BadgeCheck, BookOpen, Check, CircleHelp, Icon, Lightbulb, X } from "../vendor/icons";

export type PlayerMode =
  | { kind: "lesson"; lessonId: number }
  | { kind: "review" }
  | { kind: "mixed"; courses: number[] }
  | { kind: "practice"; courseId: number; concept: string }
  | { kind: "exam"; courseId: number };

type Queued = { step: PublicStep; firstTry: boolean };
type Draft = { choice: number[]; tf: boolean | null; order: string[]; match: (string | null)[] };
type ExamRow = { step: PublicStep; result: AnswerResult | null; skipped: boolean };

const emptyDraft = (step?: PublicStep): Draft => ({ choice: [], tf: null, order: [], match: (step?.left ?? []).map(() => null) });

function instruction(step: PublicStep): string {
  if (step.kind === "choice") return step.prompt.includes("___") ? "Completa la frase" : step.multiple ? "Selecciona todas las correctas" : "Selecciona la respuesta correcta";
  if (step.kind === "truefalse") return "¿Verdadero o falso?";
  if (step.kind === "order") return "Ordena los pasos";
  if (step.kind === "match") return "Empareja cada par";
  return "Lee con atención";
}

function responseOf(step: PublicStep, d: Draft): unknown {
  if (step.kind === "choice") return d.choice;
  if (step.kind === "truefalse") return d.tf;
  if (step.kind === "order") return d.order;
  if (step.kind === "match") return d.match;
  return null;
}

function ready(step: PublicStep, d: Draft): boolean {
  if (step.kind === "choice") return d.choice.length > 0;
  if (step.kind === "truefalse") return d.tf !== null;
  if (step.kind === "order") return d.order.length === (step.items ?? []).length;
  if (step.kind === "match") return d.match.every((m) => m !== null);
  return true;
}

/** El enunciado; en frases con hueco, el hueco muestra la opción elegida. */
function Prompt({ step, draft }: { step: PublicStep; draft: Draft }) {
  if (step.kind === "choice" && step.prompt.includes("___")) {
    const chosen = draft.choice.length ? step.options?.[draft.choice[0]] : null;
    const [before, after] = step.prompt.split("___", 2);
    return (
      <p className="lp-prompt">
        <InlineRich text={before} />
        <span className={`lp-blank${chosen ? " is-filled" : ""}`}>{chosen ? <InlineRich text={chosen} /> : "      "}</span>
        <InlineRich text={after ?? ""} />
      </p>
    );
  }
  return <RichText text={step.prompt} className="lp-prompt" />;
}

function StepInput({ step, draft, setDraft, locked }: { step: PublicStep; draft: Draft; setDraft: (d: Draft) => void; locked: boolean }) {
  const [leftPick, setLeftPick] = useState<number | null>(0);

  if (step.kind === "choice")
    return (
      <div className="lp-choices" role={step.multiple ? "group" : "radiogroup"} aria-label="Opciones">
        {(step.options ?? []).map((opt, i) => {
          const on = draft.choice.includes(i);
          return (
            <button key={i} type="button" disabled={locked} role={step.multiple ? "checkbox" : "radio"} aria-checked={on}
              className={`lp-tile${on ? " is-on" : ""}`}
              onClick={() => {
                play("tap");
                setDraft({ ...draft, choice: step.multiple ? (on ? draft.choice.filter((x) => x !== i) : [...draft.choice, i]) : [i] });
              }}>
              <span className="lp-tile__key" aria-hidden>
                {i + 1}
              </span>
              <span className="lp-tile__text">
                <InlineRich text={opt} />
              </span>
            </button>
          );
        })}
      </div>
    );
  if (step.kind === "truefalse")
    return (
      <div className="lp-choices lp-choices--two" role="radiogroup" aria-label="Verdadero o falso">
        {[true, false].map((v, i) => (
          <button key={String(v)} type="button" disabled={locked} role="radio" aria-checked={draft.tf === v}
            className={`lp-tile lp-tile--center${draft.tf === v ? " is-on" : ""}`}
            onClick={() => {
              play("tap");
              setDraft({ ...draft, tf: v });
            }}>
            <span className="lp-tile__key" aria-hidden>
              {i + 1}
            </span>
            {v ? "Verdadero" : "Falso"}
          </button>
        ))}
      </div>
    );
  if (step.kind === "order") {
    const bank = (step.items ?? []).filter((it) => !draft.order.includes(it));
    return (
      <div className="lp-order">
        <ol className="lp-order__line" aria-label="Tu orden">
          {draft.order.length === 0 && <li className="lp-order__placeholder muted small">Toca los pasos en orden</li>}
          {draft.order.map((it, i) => (
            <li key={it}>
              <button type="button" className="lp-chip is-placed" disabled={locked} aria-label={`Quitar «${it}»`}
                onClick={() => setDraft({ ...draft, order: draft.order.filter((x) => x !== it) })}>
                <span className="lp-chip__n">{i + 1}</span>
                <InlineRich text={it} />
              </button>
            </li>
          ))}
        </ol>
        <div className="lp-order__bank" aria-label="Pasos disponibles">
          {bank.map((it) => (
            <button key={it} type="button" className="lp-chip" disabled={locked}
              onClick={() => {
                play("tap");
                setDraft({ ...draft, order: [...draft.order, it] });
              }}>
              <InlineRich text={it} />
            </button>
          ))}
        </div>
      </div>
    );
  }
  if (step.kind === "match") {
    const used = new Set(draft.match.filter((m): m is string => m !== null));
    return (
      <div className="lp-match">
        <div className="lp-match__col" aria-label="Columna izquierda">
          {(step.left ?? []).map((l, i) => (
            <button key={l} type="button" disabled={locked}
              className={`lp-tile lp-tile--small${leftPick === i ? " is-on" : ""}${draft.match[i] ? " is-paired" : ""}`}
              aria-pressed={leftPick === i}
              onClick={() => {
                play("tap");
                if (draft.match[i]) {
                  const next = [...draft.match];
                  next[i] = null;
                  setDraft({ ...draft, match: next });
                  setLeftPick(i);
                } else setLeftPick(leftPick === i ? null : i);
              }}>
              <InlineRich text={l} />
              {draft.match[i] && (
                <span className="lp-match__pair">
                  → <InlineRich text={draft.match[i]!} />
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="lp-match__col" aria-label="Columna derecha">
          {(step.right ?? []).map((r) => (
            <button key={r} type="button" disabled={locked || used.has(r) || leftPick === null}
              className={`lp-tile lp-tile--small${used.has(r) ? " is-used" : ""}`}
              onClick={() => {
                if (leftPick === null) return;
                play("tap");
                const next = [...draft.match];
                next[leftPick] = r;
                setDraft({ ...draft, match: next });
                const free = next.findIndex((m) => m === null);
                setLeftPick(free === -1 ? null : free);
              }}>
              <InlineRich text={r} />
            </button>
          ))}
        </div>
        <p className="muted small lp-match__help">Toca un elemento de la izquierda y luego su pareja.</p>
      </div>
    );
  }
  return step.explanation ? <RichText text={step.explanation} className="lp-info" /> : null;
}

/** Desglose del simulacro por unidad del temario. */
function examByUnit(rows: ExamRow[]): { unit: string; correct: number; total: number }[] {
  const agg = new Map<string, { correct: number; total: number }>();
  for (const r of rows) {
    const unit = r.step.unit_title ?? "—";
    const cur = agg.get(unit) ?? { correct: 0, total: 0 };
    cur.total += 1;
    if (r.result?.correct) cur.correct += 1;
    agg.set(unit, cur);
  }
  return [...agg.entries()].map(([unit, v]) => ({ unit, ...v }));
}

export function LessonPlayer({ navigate, mode, back }: { navigate: Navigate; mode: PlayerMode; back: Route }) {
  const [sounds, setSounds] = useState(true);
  const [lesson, setLesson] = useState<LessonFull | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<"loading" | "steps" | "done" | "streak">("loading");
  const [queue, setQueue] = useState<Queued[]>([]);
  const [total, setTotal] = useState(0);
  const [doneCount, setDoneCount] = useState(0);
  const [firstTryOk, setFirstTryOk] = useState(0);
  const [xp, setXp] = useState(0);
  const [combo, setCombo] = useState(0);
  const [comboFlash, setComboFlash] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft());
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [hintsShown, setHintsShown] = useState(0);
  const [confidence, setConfidence] = useState<"high" | "low" | null>(null);
  const [showWhy, setShowWhy] = useState(false);
  const [examRows, setExamRows] = useState<ExamRow[]>([]);
  const [maxErrors, setMaxErrors] = useState<number | null>(null);
  const [examPassed, setExamPassed] = useState<boolean | null>(null);
  const [deadline, setDeadline] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const [completion, setCompletion] = useState<CompleteResult | null>(null);
  const [gameAfter, setGameAfter] = useState<GameState | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef(Date.now());
  // ¿Ya había XP hoy antes de esta sesión? Si no, al acabar se celebra la racha.
  const hadXpToday = useRef<boolean | null>(null);
  const isExam = mode.kind === "exam";
  const modeKey = JSON.stringify(mode);
  const backHref = back.name === "license" ? `/carnes/${back.code}` : "/carnes";

  useEffect(() => {
    void api.learn
      .settings()
      .then((s) => setSounds(s.sounds !== false))
      .catch(() => undefined);
  }, []);

  function resetStepUi(next?: PublicStep) {
    setResult(null);
    setHintsShown(0);
    setConfidence(null);
    setShowWhy(false);
    setDraft(emptyDraft(next));
  }

  useEffect(() => {
    let cancelled = false;
    setPhase("loading");
    setError(null);
    void api.learn
      .game()
      .then((g) => (hadXpToday.current = g.today_xp > 0))
      .catch(() => undefined);
    const load: Promise<{ steps: PublicStep[]; lesson: LessonFull | null; title: string; minutes?: number; maxErrors?: number }> =
      mode.kind === "lesson"
        ? api.learn.lesson(mode.lessonId).then((l) => ({ steps: l.steps, lesson: l, title: l.title }))
        : mode.kind === "review"
          ? api.learn.review().then((r) => ({ steps: r.steps, lesson: null, title: "Repaso de fallos" }))
          : mode.kind === "mixed"
            ? api.learn.mixed(mode.courses).then((r) => ({ steps: r.steps, lesson: null, title: "Repaso mixto" }))
          : mode.kind === "practice"
            ? api.learn.practice(mode.courseId, mode.concept).then((r) => ({ steps: r.steps, lesson: null, title: r.title }))
            : api.learn.exam(mode.courseId).then((r) => ({ steps: r.steps, lesson: null, title: r.title, minutes: r.minutes, maxErrors: r.max_errors }));
    load
      .then(({ steps, lesson: l, title: loadedTitle, minutes, maxErrors: me }) => {
        if (cancelled) return;
        setLesson(l);
        setTitle(loadedTitle);
        const q = steps.map((step) => ({ step, firstTry: true }));
        setQueue(q);
        setTotal(steps.filter((x) => x.kind !== "info").length);
        setDoneCount(0);
        setFirstTryOk(0);
        setXp(0);
        setCombo(0);
        setExamRows([]);
        setMaxErrors(me ?? null);
        setExamPassed(null);
        setCompletion(null);
        setGameAfter(null);
        setDeadline(minutes ? Date.now() + minutes * 60_000 : null);
        startedAt.current = Date.now();
        resetStepUi(q[0]?.step);
        setPhase(q.length ? "steps" : "done");
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeKey]);

  useEffect(() => {
    if (!deadline || phase !== "steps") return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [deadline, phase]);

  useEffect(() => {
    if (comboFlash === null) return;
    const t = window.setTimeout(() => setComboFlash(null), 1600);
    return () => window.clearTimeout(t);
  }, [comboFlash]);

  const current = queue[0];
  const remainingSec = deadline ? Math.max(0, Math.round((deadline - now) / 1000)) : null;

  const finish = useCallback(
    async (rows?: ExamRow[]) => {
      play("complete", sounds);
      vibrate([30, 40, 30]);
      setElapsed(Math.round((Date.now() - startedAt.current) / 1000));
      setPhase("done");
      if (lesson) {
        const r = await api.learn.complete(lesson.id, firstTryOk, total, Math.round((Date.now() - startedAt.current) / 1000)).catch(() => null);
        if (r) {
          setXp((x) => x + r.xp);
          setCompletion(r);
          setGameAfter(r.game);
        }
      } else if (mode.kind === "exam") {
        const all = rows ?? examRows;
        const r = await api.learn.completeExam(mode.courseId, all.filter((x) => x.result?.correct).length, Math.max(1, all.length)).catch(() => null);
        if (r) {
          setXp((x) => x + r.xp);
          setExamPassed(r.passed);
          setGameAfter(r.game);
        }
      } else {
        const g = await api.learn.game().catch(() => null);
        if (g) setGameAfter(g);
      }
    },
    [lesson, firstTryOk, total, sounds, mode, examRows]
  );

  useEffect(() => {
    if (isExam && remainingSec === 0 && phase === "steps") {
      const rows = [...examRows, ...queue.map((q) => ({ step: q.step, result: null, skipped: true }))];
      setExamRows(rows);
      setQueue([]);
      void finish(rows);
    }
  }, [isExam, remainingSec, phase, queue, examRows, finish]);

  const advance = (correct: boolean, rowsForFinish?: ExamRow[]) => {
    const [head, ...rest] = queue;
    // Lo fallado vuelve al final una vez (no en simulacro ni en el repaso de fallos).
    const retry = !correct && head && !isExam && mode.kind !== "review" && head.firstTry;
    const next = retry ? [...rest, { step: head.step, firstTry: false }] : rest;
    if ((correct || !retry) && head && head.step.kind !== "info") setDoneCount((n) => n + 1);
    setQueue(next);
    resetStepUi(next[0]?.step);
    if (!next.length) void finish(rowsForFinish);
  };

  const submit = async (skip = false) => {
    if (!current || checking) return;
    if (current.step.kind === "info") {
      advance(true);
      return;
    }
    setChecking(true);
    try {
      const r = await api.learn.answer(current.step.id, skip ? null : responseOf(current.step, draft), {
        firstTry: current.firstTry,
        confidence,
        usedHint: hintsShown > 0,
        combo: combo + 1,
      });
      setXp((x) => x + r.xp);
      if (r.correct) {
        const c = combo + 1;
        setCombo(c);
        if (current.firstTry) setFirstTryOk((n) => n + 1);
        if (!isExam) {
          if (c === 3 || (c >= 5 && c % 5 === 0)) {
            setComboFlash(c);
            play("combo", sounds);
          } else play("correct", sounds);
          vibrate(25);
        }
      } else {
        setCombo(0);
        if (!isExam) {
          play("wrong", sounds);
          vibrate([60, 40, 60]);
        }
      }
      if (isExam) {
        const rows = [...examRows, { step: current.step, result: r, skipped: skip }];
        setExamRows(rows);
        advance(true, rows);
      } else setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setChecking(false);
    }
  };

  // Teclado: Enter = comprobar/continuar; 1–9 = elegir opción.
  useEffect(() => {
    if (phase !== "steps" || !current) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (e.key === "Enter" && !e.shiftKey && tag !== "TEXTAREA" && tag !== "BUTTON") {
        e.preventDefault();
        if (result) advance(result.correct);
        else if (ready(current.step, draft)) void submit();
        return;
      }
      if (result || tag === "INPUT" || tag === "TEXTAREA") return;
      const n = Number(e.key);
      if (n >= 1 && current.step.kind === "choice" && n <= (current.step.options?.length ?? 0)) setDraft({ ...draft, choice: [n - 1] });
      if (n >= 1 && n <= 2 && current.step.kind === "truefalse") setDraft({ ...draft, tf: n === 1 });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const progress = total ? doneCount / total : phase === "done" ? 1 : 0;
  const byUnit = useMemo(() => (isExam ? examByUnit(examRows) : []), [isExam, examRows]);

  if (error) return <ErrorBox message={error} />;
  if (phase === "loading") return <Loading />;

  const examCorrect = examRows.filter((r) => r.result?.correct).length;
  const accuracy = total ? Math.round(((isExam ? examCorrect : firstTryOk) / total) * 100) : 100;
  const praise = PRAISE[(doneCount + xp) % PRAISE.length];
  const celebrateStreak = Boolean(gameAfter && hadXpToday.current === false && gameAfter.today_xp > 0 && gameAfter.streak > 0);
  const goBack = () => navigate(back);

  return (
    <div className={`lp${result ? (result.correct ? " is-ok" : " is-ko") : ""}`}>
      {phase === "steps" && current && (
        <>
          <PlayerTop
            exitHref={backHref}
            onExit={linkTo(navigate, back)}
            progress={progress}
            hot={combo >= 3}
            xp={xp}
            remainingSec={remainingSec}
            sounds={sounds}
            onToggleSounds={() => setSounds((v) => !v)}
          />
          <p className="lp-title muted small">{title}</p>

          <ComboFlash n={comboFlash} />

          <main className="lp-body">
            <section className="lp-card">
              {!current.firstTry && <p className="lp-kicker lp-kicker--again">Otra vez: esta se te resistió</p>}
              {mode.kind !== "lesson" && current.step.lesson_title && (
                <p className="lp-kicker">{[current.step.course_title, current.step.lesson_title].filter(Boolean).join(" · ")}</p>
              )}
              <h1 className="lp-instruction">{instruction(current.step)}</h1>
              <QuestionBubble mascot="oso" mood={result ? (result.correct ? "cheer" : "sad") : "think"}>
                <Prompt step={current.step} draft={draft} />
              </QuestionBubble>
              <StepInput key={current.step.id + (current.firstTry ? "a" : "b")} step={current.step} draft={draft} setDraft={setDraft} locked={!!result || checking} />
              {!result && !isExam && (current.step.hints ?? []).length > 0 && (
                <div className="lp-hints">
                  {(current.step.hints ?? []).slice(0, hintsShown).map((h, i) => (
                    <p key={i} className="hint">
                      <Icon svg={Lightbulb} /> <InlineRich text={h} />
                    </p>
                  ))}
                  {hintsShown < (current.step.hints ?? []).length && (
                    <button type="button" className="btn btn--ghost btn--sm" onClick={() => setHintsShown((n) => n + 1)}>
                      <Icon svg={Lightbulb} /> {hintsShown ? "Otra pista" : "Pista"}
                    </button>
                  )}
                </div>
              )}
              {current.step.source && !isExam && <p className="lp-source"><Icon svg={BookOpen} /> {current.step.source}</p>}
            </section>
          </main>

          <PlayerFoot result={result ? (result.correct ? "ok" : "ko") : null}>
            {result ? (
              <>
                <div className="lp-verdict" role="status" aria-live="polite">
                  <p className="lp-verdict__title">
                    <Icon svg={result.correct ? Check : X} />{" "}
                    {result.correct ? praise : result.confident_wrong ? "Lo tenías claro… pero no" : "Respuesta correcta:"}
                  </p>
                  {!result.correct && result.solution && (
                    <p className="lp-verdict__solution">
                      <InlineRich text={result.solution} />
                    </p>
                  )}
                  {result.option_feedback.map((f, i) => (
                    <p key={i} className="lp-verdict__fb">
                      <InlineRich text={f} />
                    </p>
                  ))}
                  {(result.explanation || result.source) && (
                    <button type="button" className="lp-why" aria-expanded={showWhy} onClick={() => setShowWhy((v) => !v)}>
                      {showWhy ? "Ocultar explicación" : "¿Por qué?"}
                    </button>
                  )}
                  {showWhy && (
                    <div className="lp-verdict__expl">
                      {result.explanation && <RichText text={result.explanation} />}
                      {result.source && <p className="small"><Icon svg={BookOpen} /> {result.source}</p>}
                    </div>
                  )}
                </div>
                <button type="button" className={`lp-btn ${result.correct ? "lp-btn--go" : "lp-btn--bad"}`} autoFocus onClick={() => advance(result.correct)}>
                  Seguir
                </button>
              </>
            ) : (
              <>
                <div className="lp-foot__left">
                  {current.step.kind !== "info" && (
                    <button type="button" className="lp-btn lp-btn--ghost" disabled={checking} onClick={() => void submit(true)}>
                      Saltar
                    </button>
                  )}
                  {current.step.kind !== "info" && !isExam && (
                    <span className="lp-conf" role="group" aria-label="¿Lo tienes claro?">
                      <button type="button" aria-pressed={confidence === "high"} className={confidence === "high" ? "is-on" : ""} title="Lo tengo claro" aria-label="Lo tengo claro"
                        onClick={() => setConfidence(confidence === "high" ? null : "high")}>
                        <Icon svg={BadgeCheck} />
                      </button>
                      <button type="button" aria-pressed={confidence === "low"} className={confidence === "low" ? "is-on" : ""} title="Tengo dudas" aria-label="Tengo dudas"
                        onClick={() => setConfidence(confidence === "low" ? null : "low")}>
                        <Icon svg={CircleHelp} />
                      </button>
                    </span>
                  )}
                </div>
                <button type="button" className="lp-btn lp-btn--go" disabled={checking || !ready(current.step, draft)} onClick={() => void submit()}>
                  {current.step.kind === "info" ? "Seguir" : checking ? "…" : isExam ? "Responder" : "Comprobar"}
                </button>
              </>
            )}
          </PlayerFoot>
        </>
      )}

      {phase === "done" && (
        <EndScreen
          mascot="oso"
          title={
            isExam
              ? examPassed
                ? "¡Simulacro aprobado!"
                : "Simulacro terminado"
              : mode.kind === "lesson"
                ? completion?.perfect
                  ? "¡Lección perfecta!"
                  : "¡Lección completada!"
                : total
                  ? "¡Práctica completada!"
                  : "Nada que repasar hoy"
          }
          stats={total > 0 ? { xp, accuracy, seconds: elapsed } : null}
          note={
            isExam && maxErrors !== null
              ? `${examRows.length - examCorrect} fallos (se admiten ${maxErrors}).`
              : completion?.chest_available
                ? "¡Unidad terminada! Recoge su insignia en el camino."
                : null
          }
          actions={
            <>
              <button type="button" className="lp-btn lp-btn--go" autoFocus onClick={() => (celebrateStreak ? setPhase("streak") : goBack())}>
                Seguir
              </button>
              {lesson?.next_lesson_id && !celebrateStreak && (
                <a className="lp-btn lp-btn--ghost" href={`/carnes/leccion/${lesson.next_lesson_id}`} onClick={linkTo(navigate, { name: "lesson", id: lesson.next_lesson_id })}>
                  Siguiente lección
                </a>
              )}
            </>
          }
        >
          {isExam && byUnit.length > 1 && (
            <ul className="exam-units">
              {byUnit.map((u) => (
                <li key={u.unit} className={u.total && u.correct === u.total ? "is-ok" : "is-ko"}>
                  <span className="exam-units__name">{u.unit}</span>
                  <span className="exam-units__score">
                    {u.correct}/{u.total}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {isExam && examRows.length > 0 && (
            <ol className="exam-results">
              {examRows.map((r, i) => (
                <li key={i} className={r.result?.correct ? "is-ok" : "is-ko"}>
                  <div className="exam-results__q">
                    {r.skipped ? <span aria-hidden>—</span> : <Icon svg={r.result?.correct ? Check : X} />} <RichText text={r.step.prompt} />
                  </div>
                  {!r.result?.correct && r.result?.solution && (
                    <div className="small">
                      Solución: <strong><InlineRich text={r.result.solution} /></strong>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
        </EndScreen>
      )}

      {phase === "streak" && gameAfter && (
        <StreakScreen game={gameAfter} weekdays={WEEKDAYS_ES} message="¡Has estudiado hoy! Vuelve mañana para que siga creciendo." onContinue={goBack} />
      )}
    </div>
  );
}
