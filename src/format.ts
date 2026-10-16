const nf0 = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 });
const eur = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" });

export const km = (value: number | null | undefined) => (value == null ? "—" : `${nf0.format(value)} km`);
const price3 = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
/** Precio por litro/kWh como en el surtidor: siempre tres decimales. */
export const unitPrice = (value: number | null | undefined) => (value == null ? "—" : `${price3.format(value)} €`);
export const money = (value: number | null | undefined) => (value == null ? "—" : eur.format(value));
export const num = (value: number | null | undefined, digits = 1) =>
  value == null ? "—" : new Intl.NumberFormat("es-ES", { maximumFractionDigits: digits }).format(value);
/** Lecturas de sensores: menos decimales cuanto mayor es el valor (1495 rpm, 14,1 V, 0,85 bar). */
export const reading = (value: number) => num(value, Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2);

export function date(value: string | null | undefined): string {
  if (!value) return "—";
  // Fechas "YYYY-MM-DD" del backend: se pintan tal cual, sin pasar por UTC (evita el día anterior).
  const [y, m, d] = value.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" });
}

export function relative(value: string | null | undefined): string {
  if (!value) return "nunca";
  const minutes = Math.round((Date.now() - new Date(value).getTime()) / 60000);
  if (minutes < 1) return "ahora mismo";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `hace ${hours} h`;
  return `hace ${Math.round(hours / 24)} días`;
}

export function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const FUEL_LABELS: Record<string, string> = {
  gasoline: "Gasolina",
  diesel: "Diésel",
  hybrid: "Híbrido",
  phev: "Híbrido enchufable",
  electric: "Eléctrico",
  lpg: "GLP",
};

export const MAINTENANCE_CATEGORIES = [
  "aceite", "filtros", "frenos", "neumáticos", "distribución", "encendido", "refrigeración",
  "eléctrico", "suspensión", "transmisión", "climatización", "carrocería", "otros",
];
export const EXPENSE_CATEGORIES = ["seguro", "impuesto", "itv", "parking", "peaje", "lavado", "multa", "financiación", "otros"];
export const DEADLINE_KINDS = ["itv", "seguro", "impuesto", "garantía", "carnet", "revisión", "otro"];

export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
