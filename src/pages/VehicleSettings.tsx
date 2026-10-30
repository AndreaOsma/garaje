import { useState } from "react";
import { api, type Vehicle, type VehicleInput } from "../api";
import { RecordForm, type Field } from "../components/RecordForm";
import { SoberanLink } from "../components/SoberanLink";
import { confirmAndRun } from "../components/ui";
import { FUEL_LABELS, KIND_LABELS } from "../format";
import { Bot, Check, Icon, KeyRound, Smartphone, TriangleAlert } from "../vendor/icons";

export const VEHICLE_FIELDS: Field[] = [
  {
    name: "kind",
    label: "Tipo",
    type: "select",
    required: true,
    options: Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label })),
    hint: "Cambia el plan de mantenimiento, las revisiones y el modelo 3D",
  },
  { name: "name", label: "Nombre", required: true, placeholder: "El León", wide: true },
  { name: "make", label: "Marca" },
  { name: "model", label: "Modelo" },
  { name: "year", label: "Año", type: "number", min: 1886, step: "1" },
  {
    name: "fuel_type",
    label: "Combustible",
    type: "select",
    required: true,
    options: Object.entries(FUEL_LABELS).map(([value, label]) => ({ value, label })),
  },
  { name: "plate", label: "Matrícula" },
  { name: "odometer_km", label: "Km actuales", type: "number", min: 0, step: "1", required: true },
  {
    name: "tank_capacity",
    label: "Capacidad del depósito",
    type: "number",
    min: 1,
    step: "0.1",
    hint: "Litros (kWh útiles si es eléctrico). Vacío: la busca Garaje en la ficha técnica",
  },
  { name: "color", label: "Color", type: "color", hint: "Para el modelo 3D en vista exterior" },
  {
    name: "cylinders",
    label: "Cilindros",
    type: "select",
    options: [1, 2, 3, 4, 5, 6].map((n) => ({ value: String(n), label: n === 1 ? "1 (monocilíndrico)" : `${n} en línea` })),
    hint: "Para el motor 3D (vacío = 4)",
  },
  { name: "engine", label: "Motor", placeholder: "1.6 TDI 115 CV", advanced: true },
  { name: "vin", label: "Nº de bastidor (VIN)", hint: "El agente OBD lo rellena solo si la ECU lo expone", advanced: true },
  { name: "purchase_date", label: "Fecha de compra", type: "date", advanced: true },
  { name: "notes", label: "Notas", type: "textarea", advanced: true },
  { name: "archived", label: "Archivado (ya no lo tengo)", type: "checkbox", advanced: true },
];

type Props = { vehicle: Vehicle; detailed: boolean; onVehicleChanged: () => void; onDeleted: () => void };

function CopyBox({ label, value, placeholder = false }: { label: string; value: string; placeholder?: boolean }) {
  const [copied, setCopied] = useState(false);
  if (placeholder) {
    // Sin token recién generado no hay nada real que copiar: copiar el texto de ejemplo
    // acaba pegado tal cual en el Atajo y la subida se rechaza.
    return (
      <div className="copy-box">
        <span className="muted small">{label}</span>
        <div className="copy-box__row">
          <code className="is-placeholder">{value}</code>
        </div>
        <small className="muted">Genera (o regenera) el token arriba para poder copiarlo completo.</small>
      </div>
    );
  }
  return (
    <div className="copy-box">
      <span className="muted small">{label}</span>
      <div className="copy-box__row">
        <code>{value}</code>
        <button
          type="button"
          className="btn btn--sm btn--ghost"
          onClick={() =>
            navigator.clipboard?.writeText(value).then(
              () => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              },
              () => window.prompt("Copia el texto:", value)
            )
          }
        >
          {copied ? <><Icon svg={Check} /> Copiado</> : "Copiar"}
        </button>
      </div>
    </div>
  );
}

function ObdConnection({ vehicle, onVehicleChanged }: { vehicle: Vehicle; onVehicleChanged: () => void }) {
  const [token, setToken] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");
  const origin = window.location.origin;
  const shownToken = token ?? "<tu token>";

  async function rotate() {
    if (vehicle.has_ingest_token && !window.confirm("Se invalidará el token actual (Atajo y agente dejarán de funcionar hasta actualizarlos). ¿Continuar?")) return;
    setState("loading");
    try {
      setToken((await api.vehicles.rotateToken(vehicle.id)).token);
      setState("idle");
      onVehicleChanged();
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "No se pudo generar el token");
    }
  }

  return (
    <section className="panel" aria-label="Conexión OBD">
      <header className="panel__header">
        <h2>Conexión OBD</h2>
      </header>

      <div className="token-row">
        <p>
          {vehicle.has_ingest_token ? <><Icon svg={KeyRound} /> Token de ingesta activo.</> : "Sin token: genera uno para automatizar la subida de datos."}
        </p>
        <div className="panel__actions">
          <button type="button" className="btn btn--primary btn--sm" onClick={rotate} disabled={state === "loading"}>
            {state === "loading" ? "Generando…" : vehicle.has_ingest_token ? "Regenerar token" : "Generar token"}
          </button>
          {vehicle.has_ingest_token && (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() =>
                confirmAndRun("¿Revocar el token? Nada podrá subir datos hasta generar otro.", () => api.vehicles.revokeToken(vehicle.id), () => {
                  setToken(null);
                  onVehicleChanged();
                })
              }
            >
              Revocar
            </button>
          )}
        </div>
      </div>
      {state === "error" && (
        <p className="form-error" role="alert">
          <Icon svg={TriangleAlert} /> {error}
        </p>
      )}
      {token && (
        <div className="token-reveal" role="status">
          <p>
            <strong>Cópialo ahora:</strong> no se vuelve a mostrar (solo se guarda su huella).
          </p>
          <CopyBox label="Token" value={token} />
        </div>
      )}

      <details className="howto" open>
        <summary><Icon svg={Smartphone} /> iPhone + Car Scanner (Atajo de iOS): CSV o TXT</summary>
        <ol>
          <li>
            Abre <strong>Atajos</strong> → nuevo atajo → activa <em>Mostrar en hoja para compartir</em> y que acepte <em>Archivos</em>.
          </li>
          <li>
            Añade <strong>Obtener contenido de URL</strong> con método <code>POST</code> y esta URL:
            <CopyBox label="URL" value={`${origin}/api/ingest/file`} />
          </li>
          <li>
            En <em>Encabezados</em> añade <code>Authorization</code> con el valor:
            <CopyBox label="Valor del encabezado" value={`Bearer ${shownToken}`} placeholder={!token} />
          </li>
          <li>
            En <em>Cuerpo de la solicitud</em> elige <em>Formulario</em> y añade: <code>file</code> (tipo Archivo) = <em>Entrada del atajo</em>;{" "}
            <code>date</code> = <em>Fecha actual</em> con formato personalizado <code>yyyy-MM-dd</code>; <code>tz</code> ={" "}
            <code>{Intl.DateTimeFormat().resolvedOptions().timeZone}</code>.
          </li>
          <li>Termina con <strong>Mostrar notificación</strong> del <em>Contenido de URL</em> para ver cuántas lecturas entraron.</li>
          <li>
            En Car Scanner: graba el viaje, luego en la grabación desliza → <em>Compartir</em> → <em>CSV</em> → tu atajo. Subir el mismo
            CSV dos veces no duplica nada.
          </li>
        </ol>
        <p className="muted small">
          <Icon svg={TriangleAlert} /> Garaje es privado: el iPhone necesita <strong>Tailscale activo</strong> (si no, la subida ni siquiera llega). Sirve el CSV
          de una grabación o el TXT de un informe de diagnóstico (con sus códigos de avería). También puedes subirlos a mano en
          Diagnóstico.
        </p>
      </details>

      <details className="howto">
        <summary><Icon svg={Bot} /> Agente automático (Raspberry Pi / portátil + ELM327)</summary>
        <p>
          Lee sensores, códigos de avería (confirmados, pendientes y permanentes), monitores de la ITV, VIN, tensión de batería y odómetro
          (si el coche lo expone), y los sube solo. Sin conexión, guarda los lotes y los envía al volver a casa.
        </p>
        <ol>
          <li>
            En la máquina del coche, con el código de <code>garaje/backend</code>:{" "}
            <code>pip install -r requirements-agent.txt</code>
          </li>
          <li>
            Arráncalo (adaptadores BLE como los de iPhone: <code>--ble auto</code>; WiFi: <code>--tcp 192.168.0.10:35000</code>; USB o
            Bluetooth clásico: <code>--serial /dev/rfcomm0</code>):
            <CopyBox label="Comando" value={`GARAJE_TOKEN=${shownToken} python -m app.obd.agent --server ${origin} --ble auto`} placeholder={!token} />
          </li>
          <li>
            Para un servicio que arranque con el coche, usa <code>--duration</code> o <code>--once</code> desde systemd/cron. Borrar códigos de
            la centralita solo ocurre con <code>--clear-dtc</code> explícito.
          </li>
        </ol>
      </details>
    </section>
  );
}

export function VehicleSettings({ vehicle, detailed, onVehicleChanged, onDeleted }: Props) {
  return (
    <div className="stack">
      <section className="panel" aria-label="Datos del vehículo">
        <header className="panel__header">
          <h2>Datos del vehículo</h2>
        </header>
        <RecordForm
          key={vehicle.id}
          fields={VEHICLE_FIELDS}
          detailed={detailed}
          initial={vehicle}
          onSubmit={(d) => api.vehicles.update(vehicle.id, d as VehicleInput)}
          onDone={onVehicleChanged}
        />
      </section>

      <TankCapacity vehicle={vehicle} onVehicleChanged={onVehicleChanged} />

      <ObdConnection vehicle={vehicle} onVehicleChanged={onVehicleChanged} />

      <SoberanLink vehicle={vehicle} onVehicleChanged={onVehicleChanged} />

      <section className="panel panel--danger" aria-label="Zona peligrosa">
        <header className="panel__header">
          <h2>Eliminar vehículo</h2>
        </header>
        <p className="muted">Borra el vehículo y todo su historial: mantenimiento, repostajes, gastos, documentos y datos OBD.</p>
        <button
          type="button"
          className="btn btn--danger"
          onClick={() =>
            confirmAndRun(
              `¿Eliminar «${vehicle.name}» y TODO su historial? No se puede deshacer.`,
              () => api.vehicles.remove(vehicle.id),
              onDeleted
            )
          }
        >
          Eliminar «{vehicle.name}»
        </button>
      </section>
    </div>
  );
}

const TANK_SOURCE: Record<string, string> = {
  manual: "La escribiste tú",
  web: "Buscada en la ficha técnica (con fuentes)",
  ia: "Orientativa: calculada por la IA sin consultar internet",
};

/** De dónde sale la capacidad del depósito y botón para buscarla (si no la escribiste tú). */
function TankCapacity({ vehicle, onVehicleChanged }: { vehicle: Vehicle; onVehicleChanged: () => void }) {
  const [state, setState] = useState<"idle" | "loading" | "error" | "done">("idle");
  const [error, setError] = useState("");
  const unit = vehicle.fuel_type === "electric" ? "kWh" : "L";
  async function confirm() {
    setState("loading");
    setError("");
    try {
      await api.vehicles.confirmTank(vehicle.id);
      setState("done");
      onVehicleChanged();
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "No se pudo confirmar");
    }
  }
  async function search() {
    setState("loading");
    setError("");
    try {
      await api.vehicles.researchTank(vehicle.id);
      setState("done");
      onVehicleChanged();
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "No se pudo buscar");
    }
  }
  return (
    <section className="panel" aria-labelledby="tank-title">
      <h2 id="tank-title">Depósito</h2>
      {vehicle.tank_capacity ? (
        <p>
          <strong>{vehicle.tank_capacity} {unit}</strong>
          {vehicle.tank_capacity_source && <span className="muted"> · {TANK_SOURCE[vehicle.tank_capacity_source] ?? vehicle.tank_capacity_source}</span>}
          {vehicle.tank_capacity_note && <><br /><span className="muted small">{vehicle.tank_capacity_note}</span></>}
        </p>
      ) : (
        <p className="muted">Sin capacidad todavía. Con ella, Garaje calcula cuánto queda y para cuántos km cuando le dices el % (en la portada o a ágora).</p>
      )}
      {vehicle.tank_capacity_source !== "manual" && (
        <div className="form-actions">
          {vehicle.tank_capacity && (vehicle.tank_capacity_source === "ia" || vehicle.tank_capacity_source === "web") && (
            // Lo que propone la IA se revisa: si cuadra con tu manual, pasa a ser tuyo y no se vuelve a tocar.
            <button type="button" className="btn btn--sm btn--primary" onClick={confirm} disabled={state === "loading"}>
              Es correcta
            </button>
          )}
          <button type="button" className="btn btn--sm" onClick={search} disabled={state === "loading" || !vehicle.make}>
            {state === "loading" ? "Buscando… (hasta un minuto)" : vehicle.tank_capacity ? "Volver a buscar" : "Buscar en la ficha técnica"}
          </button>
        </div>
      )}
      {!vehicle.make && <p className="muted small">Pon antes la marca y el modelo.</p>}
      {state === "done" && <p className="muted small" role="status">Capacidad actualizada.</p>}
      {state === "error" && <p className="form-error" role="alert">{error}</p>}
    </section>
  );
}
