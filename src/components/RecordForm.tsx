import { useId, useState, type FormEvent } from "react";
import { capitalize } from "../format";

export type FieldType = "text" | "number" | "date" | "select" | "textarea" | "checkbox" | "color";

export type Field = {
  name: string;
  label: string;
  type?: FieldType;
  required?: boolean;
  options?: Array<string | { value: string; label: string }>;
  step?: string;
  min?: number;
  placeholder?: string;
  hint?: string;
  /** Solo se muestra en modo "detailed" (salvo que ya tenga valor). */
  advanced?: boolean;
  /** Ocupa toda la fila en la rejilla del formulario. */
  wide?: boolean;
};

type Values = Record<string, string | boolean>;

type Props = {
  fields: Field[];
  initial?: Record<string, unknown>;
  submitLabel?: string;
  detailed: boolean;
  onSubmit: (data: Record<string, unknown>) => Promise<unknown>;
  onDone?: () => void;
  onCancel?: () => void;
};

function toFormValues(fields: Field[], initial: Record<string, unknown> = {}): Values {
  const values: Values = {};
  for (const f of fields) {
    const v = initial[f.name];
    // Un <input type="color"> vacío enviaría #000000: se parte del color por defecto del 3D.
    values[f.name] = f.type === "checkbox" ? Boolean(v) : v == null ? (f.type === "color" ? "#8aa2b8" : "") : String(v);
  }
  return values;
}

function toPayload(fields: Field[], values: Values): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const v = values[f.name];
    if (f.type === "checkbox") out[f.name] = Boolean(v);
    else if (f.type === "number") out[f.name] = v === "" ? null : Number(String(v).replace(",", "."));
    else if (f.type === "date" || f.type === "color" || (f.type === "select" && !f.required)) out[f.name] = v === "" ? null : v;
    else out[f.name] = String(v).trim();
  }
  return out;
}

/** Formulario declarativo con estados loading / success / error (baseline UX del repo). */
export function RecordForm({ fields, initial, submitLabel = "Guardar", detailed, onSubmit, onDone, onCancel }: Props) {
  const id = useId();
  const [values, setValues] = useState<Values>(() => toFormValues(fields, initial));
  const [state, setState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState("");

  const visible = fields.filter((f) => detailed || !f.advanced || (values[f.name] !== "" && values[f.name] !== false));

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setState("loading");
    setError("");
    try {
      // Los campos ocultos en modo minimal conservan su valor inicial.
      await onSubmit(toPayload(fields, values));
      setState("success");
      setTimeout(() => {
        // Formularios que siguen montados tras guardar (p.ej. Vehículo) vuelven a ser editables.
        setState("idle");
        onDone?.();
      }, 900);
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "No se pudo guardar");
    }
  }

  return (
    <form className="record-form" onSubmit={handleSubmit} noValidate={false}>
      <div className="record-form__grid">
        {visible.map((f) => {
          const fid = `${id}-${f.name}`;
          const common = {
            id: fid,
            name: f.name,
            required: f.required,
            disabled: state === "loading",
            "aria-describedby": f.hint ? `${fid}-hint` : undefined,
          };
          if (f.type === "checkbox") {
            return (
              <label key={f.name} className={`check${f.wide ? " is-wide" : ""}`} htmlFor={fid}>
                <input
                  {...common}
                  type="checkbox"
                  checked={Boolean(values[f.name])}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.checked }))}
                />
                <span>{f.label}</span>
              </label>
            );
          }
          const value = String(values[f.name]);
          const set = (v: string) => setValues((prev) => ({ ...prev, [f.name]: v }));
          return (
            <div key={f.name} className={`field${f.wide || f.type === "textarea" ? " is-wide" : ""}`}>
              <label htmlFor={fid}>
                {f.label}
                {f.required && <span aria-hidden> *</span>}
              </label>
              {f.type === "select" ? (
                <select {...common} value={value} onChange={(e) => set(e.target.value)}>
                  {!f.required && <option value="">—</option>}
                  {f.options?.map((o) => {
                    const opt = typeof o === "string" ? { value: o, label: capitalize(o) } : o;
                    return (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    );
                  })}
                </select>
              ) : f.type === "textarea" ? (
                <textarea {...common} rows={3} value={value} placeholder={f.placeholder} onChange={(e) => set(e.target.value)} />
              ) : (
                <input
                  {...common}
                  type={f.type ?? "text"}
                  inputMode={f.type === "number" ? "decimal" : undefined}
                  step={f.step}
                  min={f.min}
                  value={value}
                  placeholder={f.placeholder}
                  onChange={(e) => set(e.target.value)}
                />
              )}
              {f.hint && (
                <small id={`${fid}-hint`} className="muted">
                  {f.hint}
                </small>
              )}
            </div>
          );
        })}
      </div>
      <div className="form-status" role="status" aria-live="polite">
        {state === "error" && <p className="form-error">⚠️ {error}</p>}
        {state === "success" && <p className="form-success">✓ Guardado</p>}
      </div>
      <div className="form-actions">
        {onCancel && (
          <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={state === "loading"}>
            Cancelar
          </button>
        )}
        <button type="submit" className="btn btn--primary" disabled={state === "loading" || state === "success"}>
          {state === "loading" ? "Guardando…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
