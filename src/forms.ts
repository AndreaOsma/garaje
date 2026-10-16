/** Definiciones de formulario compartidas entre páginas y la bandeja de Soberan. */
import type { Service, Task } from "./api";
import type { Field } from "./components/RecordForm";
import { EXPENSE_CATEGORIES, MAINTENANCE_CATEGORIES } from "./format";

export function fuelFields(electric: boolean): Field[] {
  return [
    { name: "date", label: "Fecha", type: "date", required: true },
    { name: "odometer_km", label: "Km", type: "number", required: true, min: 0, step: "1" },
    { name: "quantity", label: electric ? "Energía (kWh)" : "Litros", type: "number", required: true, min: 0, step: "0.01" },
    {
      name: "total_cost",
      label: "Importe pagado (€)",
      type: "number",
      required: true,
      min: 0,
      step: "0.01",
      hint: "Lo que te cobran, ya con el descuento",
    },
    { name: "discount", label: "Descuento (€)", type: "number", min: 0, step: "0.01", hint: "Cupón, club de fidelidad…" },
    {
      name: "discount_cents_per_unit",
      label: electric ? "…o descuento en c€/kWh" : "…o descuento en c€/L",
      type: "number",
      min: 0,
      step: "0.1",
      hint: "Si lo rellenas, calcula el descuento en € solo",
    },
    { name: "full_tank", label: electric ? "Carga completa" : "Depósito lleno", type: "checkbox" },
    { name: "station", label: electric ? "Punto de carga" : "Gasolinera", advanced: true },
    { name: "notes", label: "Notas", type: "textarea", advanced: true },
  ];
}

export const EXPENSE_FIELDS: Field[] = [
  { name: "title", label: "Concepto", required: true, wide: true },
  { name: "date", label: "Fecha", type: "date", required: true },
  { name: "category", label: "Categoría", type: "select", options: EXPENSE_CATEGORIES, required: true },
  { name: "amount", label: "Importe (€)", type: "number", required: true, min: 0, step: "0.01" },
  { name: "notes", label: "Notas", type: "textarea", advanced: true },
];

export function serviceFields(tasks: Task[]): Field[] {
  return [
    { name: "title", label: "Qué se hizo", required: true, wide: true },
    { name: "date", label: "Fecha", type: "date", required: true },
    { name: "odometer_km", label: "Km", type: "number", min: 0, step: "1" },
    {
      name: "task_id",
      label: "Completa la tarea del plan",
      type: "select",
      options: tasks.map((t) => ({ value: String(t.id), label: t.name })),
      hint: "Reinicia su contador de km/meses",
    },
    { name: "category", label: "Categoría", type: "select", options: MAINTENANCE_CATEGORIES, required: true },
    { name: "cost", label: "Coste (€)", type: "number", min: 0, step: "0.01" },
    { name: "workshop", label: "Taller", advanced: true },
    { name: "parts", label: "Piezas / referencias", type: "textarea", advanced: true },
    { name: "description", label: "Detalle", type: "textarea", advanced: true },
  ];
}

export function toServicePayload(data: Record<string, unknown>): Partial<Service> {
  return { ...data, task_id: data.task_id ? Number(data.task_id) : null, cost: Number(data.cost ?? 0) };
}
