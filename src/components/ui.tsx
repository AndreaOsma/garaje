import { useCallback, useEffect, useState, type ReactNode } from "react";
import type { Status } from "../api";

const STATUS: Record<string, { icon: string; label: string }> = {
  ok: { icon: "✓", label: "Al día" },
  soon: { icon: "◔", label: "Pronto" },
  overdue: { icon: "!", label: "Vencido" },
  unknown: { icon: "?", label: "Sin registro" },
  inactive: { icon: "–", label: "Desactivada" },
  done: { icon: "✓", label: "Hecho" },
};

/** Estado con icono + texto (nunca solo color). */
export function StatusBadge({ status, label }: { status: Status; label?: string }) {
  const s = STATUS[status] ?? STATUS.unknown;
  return (
    <span className={`badge badge--${status}`}>
      <span aria-hidden>{s.icon}</span> {label ?? s.label}
    </span>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty-state">
      <p className="empty-state__title">{title}</p>
      {children && <div className="muted">{children}</div>}
    </div>
  );
}

export function Loading({ label = "Cargando…" }: { label?: string }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-box" role="alert">
      <span>⚠️ {message}</span>
      {onRetry && (
        <button type="button" className="btn btn--ghost btn--sm" onClick={onRetry}>
          Reintentar
        </button>
      )}
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="stat">
      <span className="stat__label">{label}</span>
      <span className="stat__value">{value}</span>
      {hint && <span className="stat__hint muted">{hint}</span>}
    </div>
  );
}

/** Carga asíncrona con estados loading/error y recarga manual. */
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(loader, deps);

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await load());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error de red");
    } finally {
      setLoading(false);
    }
  }, [load]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload, setData };
}

/** Confirmación + borrado con feedback de error. */
export async function confirmAndRun(message: string, action: () => Promise<unknown>, after: () => void) {
  if (!window.confirm(message)) return;
  try {
    await action();
    after();
  } catch (err) {
    window.alert(err instanceof Error ? err.message : "No se pudo completar la acción");
  }
}
