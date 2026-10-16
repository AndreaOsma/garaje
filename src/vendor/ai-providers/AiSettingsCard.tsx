/* GENERADO desde dev/lib/ai-providers (Homelab): no lo edites aquí, edita la librería y ejecuta su sync.mjs */
import { useEffect, useId, useState } from "react";
import "./ai-settings.css";

type ProviderMeta = { label: string; needs_key: boolean; needs_url: boolean; url: string; help: string; model: string };
export type AiPublic = {
  provider: string | null;
  base_url: string;
  model: string;
  has_key: boolean;
  kind: "text" | "vision";
  status: { enabled: boolean; reason: string; source: "settings" | "server" | "none"; provider: string | null; model: string };
  providers: Record<string, ProviderMeta>;
};

type Msg = { kind: "ok" | "error" | "loading"; text: string } | null;

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { credentials: "same-origin", ...init });
  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* cuerpo no JSON */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

/** Ajustes de IA: cada persona pone su proveedor (Claude, Gemini, OpenRouter u Ollama) y su clave.
 * La clave se envía una vez y el servidor la guarda cifrada; nunca vuelve al navegador. */
export function AiSettingsCard({ apiBase = "/api", purpose }: { apiBase?: string; purpose?: string }) {
  const [data, setData] = useState<AiPublic | null>(null);
  const [provider, setProvider] = useState<string>("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState<Msg>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const ids = { provider: useId(), url: useId(), model: useId(), key: useId() };

  const apply = (d: AiPublic) => {
    setData(d);
    setProvider(d.provider ?? "");
    setBaseUrl(d.base_url);
    setModel(d.model);
    setKey("");
  };

  useEffect(() => {
    call<AiPublic>(`${apiBase}/ai`).then(apply).catch((e: Error) => setLoadError(e.message));
  }, [apiBase]);

  if (loadError) return <section className="ai-card"><p className="ai-card__msg is-error" role="alert">⚠ {loadError}</p></section>;
  if (!data) return <section className="ai-card"><p className="ai-card__muted" role="status">Cargando…</p></section>;

  const meta = provider ? data.providers[provider] : null;
  const st = data.status;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg({ kind: "loading", text: "Guardando…" });
    try {
      const body: Record<string, unknown> = { provider: provider || null, base_url: baseUrl, model };
      if (key.trim()) body.key = key.trim();
      apply(await call<AiPublic>(`${apiBase}/ai`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }));
      setMsg({ kind: "ok", text: "Guardado" });
    } catch (err) {
      setMsg({ kind: "error", text: (err as Error).message });
    }
  };

  const removeKey = async () => {
    setMsg({ kind: "loading", text: "Borrando la clave…" });
    try {
      apply(await call<AiPublic>(`${apiBase}/ai`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: data.provider, base_url: data.base_url, model: data.model, key: "" }),
      }));
      setMsg({ kind: "ok", text: "Clave borrada" });
    } catch (err) {
      setMsg({ kind: "error", text: (err as Error).message });
    }
  };

  const test = async () => {
    setMsg({ kind: "loading", text: "Probando la conexión…" });
    try {
      const r = await call<{ message: string }>(`${apiBase}/ai/test`, { method: "POST" });
      setMsg({ kind: "ok", text: r.message });
    } catch (err) {
      setMsg({ kind: "error", text: (err as Error).message });
    }
  };

  return (
    <section className="ai-card" aria-labelledby={`${ids.provider}-title`}>
      <h2 className="ai-card__title" id={`${ids.provider}-title`}>Inteligencia artificial</h2>
      {purpose && <p className="ai-card__muted">{purpose}</p>}

      <p className={`ai-card__status ${st.enabled ? "is-on" : "is-off"}`} role="status">
        {st.enabled
          ? st.source === "server"
            ? `Activa con la configuración del servidor (${data.providers[st.provider ?? ""]?.label ?? st.provider} · ${st.model}). Pon la tuya abajo para usar tu propia cuenta.`
            : `Activa: ${data.providers[st.provider ?? ""]?.label ?? st.provider} · ${st.model}`
          : `Desactivada: ${st.reason}.`}
      </p>

      <form className="ai-card__form" onSubmit={(e) => void save(e)}>
        <div className="ai-card__field">
          <label htmlFor={ids.provider}>Proveedor</label>
          <select id={ids.provider} value={provider} onChange={(e) => { setProvider(e.target.value); setModel(""); setBaseUrl(""); }}>
            <option value="">Ninguno (usar lo del servidor, si hay)</option>
            {Object.entries(data.providers).map(([k, p]) => (
              <option key={k} value={k}>{p.label}</option>
            ))}
          </select>
          {meta && <small className="ai-card__muted">{meta.help}</small>}
        </div>

        {meta && (
          <>
            {(meta.needs_key || provider === "ollama") && (
              <div className="ai-card__field">
                <label htmlFor={ids.key}>{meta.needs_key ? "Clave de API" : "Token (opcional)"}</label>
                <input id={ids.key} type="password" autoComplete="off" spellCheck={false} value={key}
                  placeholder={data.has_key ? "Guardada · escribe otra para cambiarla" : meta.needs_key ? "Pega aquí tu clave" : "Solo si tu servidor lo pide"}
                  onChange={(e) => setKey(e.target.value)} />
                <small className="ai-card__muted">Se guarda cifrada en el servidor y no se vuelve a mostrar.</small>
              </div>
            )}
            {meta.needs_url && (
              <div className="ai-card__field">
                <label htmlFor={ids.url}>URL del servidor</label>
                <input id={ids.url} type="url" inputMode="url" value={baseUrl} placeholder={meta.url} onChange={(e) => setBaseUrl(e.target.value)} />
              </div>
            )}
            <div className="ai-card__field">
              <label htmlFor={ids.model}>Modelo{data.kind === "vision" ? " (con visión)" : ""}</label>
              <input id={ids.model} value={model} spellCheck={false} placeholder={meta.model} onChange={(e) => setModel(e.target.value)} />
              <small className="ai-card__muted">Vacío = {meta.model}</small>
            </div>
          </>
        )}

        <div className="ai-card__actions">
          <button type="submit" className="ai-card__btn ai-card__btn--primary" disabled={msg?.kind === "loading"}>Guardar</button>
          <button type="button" className="ai-card__btn" disabled={msg?.kind === "loading" || !st.enabled} onClick={() => void test()}>Probar conexión</button>
          {data.has_key && (
            <button type="button" className="ai-card__btn ai-card__btn--danger" disabled={msg?.kind === "loading"} onClick={() => void removeKey()}>Borrar clave</button>
          )}
        </div>
        {msg && (
          <p className={`ai-card__msg ${msg.kind === "error" ? "is-error" : msg.kind === "ok" ? "is-ok" : ""}`} role={msg.kind === "error" ? "alert" : "status"}>
            {msg.kind === "ok" ? "✓ " : msg.kind === "error" ? "⚠ " : ""}{msg.text}
          </p>
        )}
      </form>
    </section>
  );
}
