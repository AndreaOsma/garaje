const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export type FuelType = "gasoline" | "diesel" | "hybrid" | "phev" | "electric" | "lpg";

export type Monitor = { name: string; complete: boolean };

export type Vehicle = {
  id: number;
  name: string;
  make: string;
  model: string;
  year: number | null;
  vin: string;
  plate: string;
  fuel_type: FuelType;
  engine: string;
  color: string | null;
  cylinders: number | null;
  purchase_date: string | null;
  odometer_km: number;
  odometer_updated_at: string | null;
  notes: string;
  archived: boolean;
  has_ingest_token: boolean;
  mil_on: boolean | null;
  ecu_dtc_count: number | null;
  monitors: { ignition: string; monitors: Monitor[]; ready: boolean } | null;
  last_obd_at: string | null;
  soberan_property_id: number | null;
  soberan_debt_id: number | null;
  market_value: number | null;
  market_value_at: string | null;
  market_value_confidence: string | null;
  debt_pending: number | null;
  debt_monthly: number | null;
};

export type VehicleInput = Omit<
  Vehicle,
  | "id"
  | "odometer_updated_at"
  | "has_ingest_token"
  | "mil_on"
  | "ecu_dtc_count"
  | "monitors"
  | "last_obd_at"
  | "soberan_property_id"
  | "soberan_debt_id"
  | "market_value"
  | "market_value_at"
  | "market_value_confidence"
  | "debt_pending"
  | "debt_monthly"
>;

export type Status = "ok" | "soon" | "overdue" | "unknown" | "inactive" | "done";

export type Task = {
  id: number;
  name: string;
  category: string;
  interval_km: number | null;
  interval_months: number | null;
  last_done_date: string | null;
  last_done_km: number | null;
  notes: string;
  active: boolean;
  next_due_km: number | null;
  next_due_date: string | null;
  remaining_km: number | null;
  remaining_days: number | null;
  status: Status;
};

export type Service = {
  id: number;
  task_id: number | null;
  date: string;
  odometer_km: number | null;
  category: string;
  title: string;
  description: string;
  parts: string;
  workshop: string;
  cost: number;
};

export type FuelEntry = {
  id: number;
  date: string;
  odometer_km: number;
  quantity: number;
  total_cost: number;
  discount: number;
  full_tank: boolean;
  station: string;
  notes: string;
  price_per_unit: number | null;
  pump_price_per_unit: number | null;
  consumption: number | null;
};

export type Expense = { id: number; date: string; category: string; title: string; amount: number; notes: string };

export type Deadline = {
  id: number;
  kind: string;
  title: string;
  due_date: string;
  notes: string;
  done: boolean;
  status: Status;
  days_left: number;
};

export type Dtc = {
  id: number;
  code: string;
  kind: "stored" | "pending" | "permanent";
  source: string;
  first_seen: string;
  last_seen: string;
  occurrences: number;
  cleared_at: string | null;
  notes: string;
  description: string;
  system: string;
  severity: "baja" | "media" | "alta";
  generic: boolean;
  learned: "import" | "manual" | "web" | "ia" | null;
  details: {
    system: string;
    causes: string[];
    advice: string;
    sources: string[];
    confidence: "alta" | "media" | "baja";
    provider: string;
  } | null;
};

export type LiveValue = { key: string; name: string; unit: string; group: string; value: number; ts: string };

export type ObdSession = {
  id: number;
  source: string;
  label: string;
  started_at: string;
  ended_at: string;
  sample_count: number;
};

export type SensorSeries = {
  key: string;
  name: string;
  unit: string;
  group: string;
  count: number;
  min: number;
  max: number;
  avg: number;
  points: [number, number][];
};

export type Alert = {
  level: "danger" | "warning" | "info";
  kind: string;
  title: string;
  detail: string;
  target: string;
};

export type Dashboard = {
  vehicle: Vehicle;
  alerts: Alert[];
  costs: {
    total: number;
    last_12_months: number;
    by_category: Record<string, number>;
    cost_per_km: number | null;
    km_tracked: number;
  };
  avg_consumption: number | null;
  consumption_unit: string;
  active_dtcs: number;
  live: LiveValue[];
  next_tasks: Task[];
  inbox_pending: number;
  readiness: Readiness | null;
};

export type SoberanProperty = {
  id: number;
  nombre: string;
  marca: string | null;
  modelo: string | null;
  anio: number | null;
  matricula: string | null;
  bastidor: string | null;
  km: number | null;
  valor_estimado: number | null;
  confianza: string | null;
};

export type SoberanDebt = { id: number; nombre: string; acreedor: string; pendiente: number; cuota_mensual: number | null };

export type SoberanState = {
  last_sync_at: string | null;
  properties: SoberanProperty[];
  debts: SoberanDebt[];
  categories: string[];
  selected_categories: string[];
};

export type InboxItem = {
  id: number;
  vehicle_id: number | null;
  date: string;
  amount: number;
  description: string;
  category: string;
  suggested_kind: "fuel" | "service" | "expense";
  suggested_category: string;
  status: string;
};

export type IssueSeverity = "info" | "limiting" | "grounding";

export type Issue = {
  id: number;
  reported_on: string;
  odometer_km: number | null;
  title: string;
  description: string;
  severity: IssueSeverity;
  category: string;
  dtc_code: string | null;
  resolved_on: string | null;
  resolution: string;
  service_id: number | null;
};

export type ChecklistSection = { title: string; items: { label: string; check: string }[] };

export type Checklist = {
  id: number;
  vehicle_id: number | null;
  name: string;
  interval_days: number | null;
  sections: ChecklistSection[];
  last_run_on: string | null;
  last_run_failed: number | null;
  due: boolean;
};

export type RunResult = {
  section: string;
  label: string;
  check: string;
  ok: boolean | null;
  note: string;
  severity?: IssueSeverity;
  create_issue?: boolean;
};

export type ChecklistRun = {
  id: number;
  checklist_id: number | null;
  checklist_name: string;
  date: string;
  odometer_km: number | null;
  results: RunResult[];
  failed: number;
  issues_created: number;
};

export type Readiness = {
  status: "go" | "caution" | "nogo";
  reasons: { level: "nogo" | "caution"; text: string; target: string }[];
};

export type Mechanics = {
  readiness: Readiness;
  issues: Issue[];
  checklists: Checklist[];
  runs: ChecklistRun[];
  suggestions: { name: string; category: string; interval_km: number | null; interval_months: number | null; notes: string }[];
};

export type TwinItem = { kind: "dtc" | "issue" | "task" | "reading"; level: "ok" | "info" | "warn" | "danger"; text: string; target: string };
export type TwinComponent = { id: string; name: string; status: "ok" | "info" | "warn" | "danger"; items: TwinItem[] };
export type Twin = { fuel_type: string; components: TwinComponent[]; unassigned: TwinItem[] };

export type IngestResult = {
  session_id: number | null;
  samples: number;
  skipped_rows: number;
  kind: "log" | "report";
  dtcs: Partial<Record<"stored" | "pending" | "permanent", string[]>>;
  vin: string | null;
  learned: number;
  reprocessed: boolean;
};

function errorMessage(body: unknown, status: number, path: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  // Errores de validación de FastAPI: [{loc, msg}, ...]
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d: { msg?: string }) => d.msg?.replace(/^Value error, /, "")).filter(Boolean).join(" · ");
  }
  return `Error ${status} al llamar a ${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(errorMessage(body, response.status, path));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** CRUD genérico de colecciones colgadas de un vehículo. */
function collection<T, I = Partial<T>>(name: string) {
  return {
    list: (vid: number) => request<T[]>(`/vehicles/${vid}/${name}`),
    create: (vid: number, data: I) => request<T>(`/vehicles/${vid}/${name}`, json("POST", data)),
    update: (vid: number, id: number, data: I) => request<T>(`/vehicles/${vid}/${name}/${id}`, json("PUT", data)),
    remove: (vid: number, id: number) => request<void>(`/vehicles/${vid}/${name}/${id}`, { method: "DELETE" }),
  };
}

export const api = {
  vehicles: {
    list: () => request<Vehicle[]>("/vehicles"),
    get: (id: number) => request<Vehicle>(`/vehicles/${id}`),
    create: (data: Partial<VehicleInput> & { with_default_plan?: boolean }) => request<Vehicle>("/vehicles", json("POST", data)),
    update: (id: number, data: VehicleInput) => request<Vehicle>(`/vehicles/${id}`, json("PUT", data)),
    remove: (id: number) => request<void>(`/vehicles/${id}`, { method: "DELETE" }),
    setOdometer: (id: number, odometer_km: number) => request<Vehicle>(`/vehicles/${id}/odometer`, json("POST", { odometer_km })),
    dashboard: (id: number) => request<Dashboard>(`/vehicles/${id}/dashboard`),
    rotateToken: (id: number) => request<{ token: string }>(`/vehicles/${id}/ingest-token`, { method: "POST" }),
    revokeToken: (id: number) => request<void>(`/vehicles/${id}/ingest-token`, { method: "DELETE" }),
  },
  tasks: collection<Task>("tasks"),
  services: collection<Service>("services"),
  fuel: {
    ...collection<FuelEntry>("fuel"),
    list: (vid: number) =>
      request<{ entries: FuelEntry[]; avg_consumption: number | null; unit: string; total_discount: number }>(
        `/vehicles/${vid}/fuel`
      ),
  },
  expenses: collection<Expense>("expenses"),
  deadlines: collection<Deadline>("deadlines"),
  dtcs: {
    list: (vid: number) => request<Dtc[]>(`/vehicles/${vid}/dtcs`),
    create: (vid: number, data: { code: string; kind: string; notes: string }) =>
      request<Dtc>(`/vehicles/${vid}/dtcs`, json("POST", data)),
    setNotes: (vid: number, id: number, notes: string) => request<Dtc>(`/vehicles/${vid}/dtcs/${id}`, json("PUT", { notes })),
    clear: (vid: number, id: number) => request<Dtc>(`/vehicles/${vid}/dtcs/${id}/clear`, { method: "POST" }),
    remove: (vid: number, id: number) => request<void>(`/vehicles/${vid}/dtcs/${id}`, { method: "DELETE" }),
    define: (vid: number, code: string, body: { description: string; severity: string | null; all_makes: boolean }) =>
      request<unknown>(`/vehicles/${vid}/dtc-definitions/${code}`, json("PUT", body)),
    resetDefinition: (vid: number, code: string) => request<unknown>(`/vehicles/${vid}/dtc-definitions/${code}`, { method: "DELETE" }),
    research: (vid: number, id: number) => request<Dtc>(`/vehicles/${vid}/dtcs/${id}/research`, { method: "POST" }),
  },
  live: (vid: number) => request<LiveValue[]>(`/vehicles/${vid}/live`),
  sessions: {
    list: (vid: number) => request<ObdSession[]>(`/vehicles/${vid}/sessions`),
    get: (vid: number, id: number) =>
      request<{ session: ObdSession; series: SensorSeries[] }>(`/vehicles/${vid}/sessions/${id}`),
    remove: (vid: number, id: number) => request<void>(`/vehicles/${vid}/sessions/${id}`, { method: "DELETE" }),
  },
  mechanics: (vid: number) => request<Mechanics>(`/vehicles/${vid}/mechanics`),
  twin: (vid: number) => request<Twin>(`/vehicles/${vid}/twin`),
  engineTwin: (vid: number) =>
    request<{
      kind: "inline-gasoline" | "inline-diesel";
      cylinders: number;
      parts: Record<string, { status: TwinItem["level"]; items: TwinItem[] }>;
    }>(
      `/vehicles/${vid}/twin/engine`
    ),
  researchStatus: () => request<{ providers: string[] }>("/research/status"),
  issues: {
    ...collection<Issue>("issues"),
    resolve: (vid: number, id: number, body: { resolved_on: string; resolution: string; service_id: number | null }) =>
      request<Issue>(`/vehicles/${vid}/issues/${id}/resolve`, json("POST", body)),
    reopen: (vid: number, id: number) => request<Issue>(`/vehicles/${vid}/issues/${id}/reopen`, { method: "POST" }),
  },
  checklists: {
    create: (vid: number, data: { name: string; interval_days: number | null; sections: ChecklistSection[] }) =>
      request<Checklist>(`/vehicles/${vid}/checklists`, json("POST", data)),
    update: (vid: number, id: number, data: { name: string; interval_days: number | null; sections: ChecklistSection[] }) =>
      request<Checklist>(`/vehicles/${vid}/checklists/${id}`, json("PUT", data)),
    remove: (vid: number, id: number) => request<void>(`/vehicles/${vid}/checklists/${id}`, { method: "DELETE" }),
    run: (vid: number, data: { checklist_id: number; date: string; odometer_km: number | null; results: RunResult[] }) =>
      request<ChecklistRun>(`/vehicles/${vid}/checklist-runs`, json("POST", data)),
    removeRun: (vid: number, id: number) => request<void>(`/vehicles/${vid}/checklist-runs/${id}`, { method: "DELETE" }),
  },
  addSuggestedTasks: (vid: number, names: string[]) =>
    request<Task[]>(`/vehicles/${vid}/tasks/from-suggestions`, json("POST", { names })),
  soberan: {
    state: () => request<SoberanState>("/integrations/soberan"),
    setCategories: (categories: string[]) =>
      request<SoberanState>("/integrations/soberan/settings", json("PUT", { categories })),
    link: (vid: number, property_id: number | null, debt_id: number | null) =>
      request<Vehicle>(`/vehicles/${vid}/soberan-link`, json("PUT", { property_id, debt_id })),
    inbox: (vid: number) => request<InboxItem[]>(`/vehicles/${vid}/inbox`),
    resolve: (
      id: number,
      body: { status: "accepted" | "dismissed"; record_type?: "fuel" | "service" | "expense"; record_id?: number; vehicle_id?: number }
    ) => request<InboxItem>(`/inbox/${id}/resolve`, json("POST", body)),
  },
  importObdFile: (vid: number, file: File, date: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("date", date);
    form.append("tz", Intl.DateTimeFormat().resolvedOptions().timeZone);
    return request<IngestResult>(`/vehicles/${vid}/import/obd-file`, { method: "POST", body: form });
  },
};
