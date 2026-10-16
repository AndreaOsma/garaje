import { useCallback, useEffect, useState } from "react";

export const TABS = [
  { id: "home", label: "Inicio", short: "Inicio", icon: "🏠" },
  { id: "maintenance", label: "Mecánica", short: "Mecánica", icon: "🔧" },
  { id: "fuel", label: "Repostajes", short: "Repostar", icon: "⛽" },
  { id: "expenses", label: "Gastos", short: "Gastos", icon: "💶" },
  { id: "documents", label: "Documentos", short: "Papeles", icon: "📄" },
  { id: "diagnostics", label: "Diagnóstico", short: "OBD", icon: "🩺" },
  { id: "settings", label: "Vehículo", short: "Coche", icon: "⚙️" },
] as const;

export type TabId = (typeof TABS)[number]["id"];

export type Route = { name: "garage" } | { name: "new" } | { name: "vehicle"; id: number; tab: TabId };

const TAB_IDS = new Set<string>(TABS.map((t) => t.id));

function parsePath(pathname: string): Route {
  if (pathname === "/nuevo") return { name: "new" };
  const match = pathname.match(/^\/v\/(\d+)(?:\/([a-z]+))?\/?$/);
  if (match) {
    const tab = (match[2] && TAB_IDS.has(match[2]) ? match[2] : "home") as TabId;
    return { name: "vehicle", id: Number(match[1]), tab };
  }
  return { name: "garage" };
}

function pathFor(route: Route): string {
  if (route.name === "new") return "/nuevo";
  if (route.name === "vehicle") return route.tab === "home" ? `/v/${route.id}` : `/v/${route.id}/${route.tab}`;
  return "/";
}

export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parsePath(window.location.pathname));

  useEffect(() => {
    const onPopState = () => setRoute(parsePath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = useCallback((next: Route, replace = false) => {
    const path = pathFor(next);
    if (path !== window.location.pathname) {
      if (replace) window.history.replaceState({}, "", path);
      else window.history.pushState({}, "", path);
    }
    setRoute(next);
    window.scrollTo({ top: 0 });
  }, []);

  return { route, navigate };
}
