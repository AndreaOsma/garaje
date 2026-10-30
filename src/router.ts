import { useCallback, useEffect, useState, type MouseEvent } from "react";
import type { VehicleKind } from "./api";
import { Euro, FileText, Fuel, House, Settings, Stethoscope, Wrench } from "./vendor/icons";

export const TABS = [
  { id: "home", label: "Inicio", short: "Inicio", icon: House },
  { id: "maintenance", label: "Mecánica", short: "Mecánica", icon: Wrench },
  { id: "fuel", label: "Repostajes", short: "Repostar", icon: Fuel },
  { id: "expenses", label: "Gastos", short: "Gastos", icon: Euro },
  { id: "documents", label: "Documentos", short: "Papeles", icon: FileText },
  { id: "diagnostics", label: "Diagnóstico", short: "OBD", icon: Stethoscope },
  { id: "settings", label: "Vehículo", short: "Coche", icon: Settings },
] as const;

export type TabId = (typeof TABS)[number]["id"];

/** Las pestañas con el texto corto adaptado al vehículo («Coche» / «Moto»). */
export function tabsFor(kind: VehicleKind) {
  return TABS.map((t) => (t.id === "settings" ? { ...t, short: kind === "motorcycle" ? "Moto" : "Coche" } : t));
}

export type Route =
  | { name: "garage" }
  | { name: "new" }
  | { name: "vehicle"; id: number; tab: TabId }
  // Carnés: catálogo, un permiso y el reproductor de su teórico.
  | { name: "licenses" }
  | { name: "license"; code: string }
  | { name: "lesson"; id: number }
  | { name: "review" }
  | { name: "mixed"; courses: number[] }
  | { name: "practice"; courseId: number; concept: string }
  | { name: "exam"; courseId: number };

export type Navigate = (next: Route, replace?: boolean) => void;

const TAB_IDS = new Set<string>(TABS.map((t) => t.id));

function parsePath(pathname: string, search: string): Route {
  if (pathname === "/nuevo") return { name: "new" };
  const match = pathname.match(/^\/v\/(\d+)(?:\/([a-z]+))?\/?$/);
  if (match) {
    const tab = (match[2] && TAB_IDS.has(match[2]) ? match[2] : "home") as TabId;
    return { name: "vehicle", id: Number(match[1]), tab };
  }
  if (/^\/carnes\/?$/.test(pathname)) return { name: "licenses" };
  if (pathname === "/carnes/repaso") return { name: "review" };
  let m = pathname.match(/^\/carnes\/repaso-mixto(?:\/([\d-]+))?\/?$/);
  if (m) return { name: "mixed", courses: m[1] ? m[1].split("-").map(Number).filter(Boolean) : [] };
  m = pathname.match(/^\/carnes\/leccion\/(\d+)\/?$/);
  if (m) return { name: "lesson", id: Number(m[1]) };
  m = pathname.match(/^\/carnes\/practica\/(\d+)\/?$/);
  if (m) return { name: "practice", courseId: Number(m[1]), concept: new URLSearchParams(search).get("concepto") ?? "" };
  m = pathname.match(/^\/carnes\/simulacro\/(\d+)\/?$/);
  if (m) return { name: "exam", courseId: Number(m[1]) };
  m = pathname.match(/^\/carnes\/([A-Z0-9]{1,4})\/?$/);
  if (m) return { name: "license", code: m[1] };
  return { name: "garage" };
}

export function pathFor(route: Route): string {
  switch (route.name) {
    case "new":
      return "/nuevo";
    case "vehicle":
      return route.tab === "home" ? `/v/${route.id}` : `/v/${route.id}/${route.tab}`;
    case "licenses":
      return "/carnes";
    case "license":
      return `/carnes/${route.code}`;
    case "lesson":
      return `/carnes/leccion/${route.id}`;
    case "review":
      return "/carnes/repaso";
    case "mixed":
      return `/carnes/repaso-mixto${route.courses.length ? `/${route.courses.join("-")}` : ""}`;
    case "practice":
      return `/carnes/practica/${route.courseId}${route.concept ? `?concepto=${encodeURIComponent(route.concept)}` : ""}`;
    case "exam":
      return `/carnes/simulacro/${route.courseId}`;
    default:
      return "/";
  }
}

/** onClick de un <a href>: navega sin recargar, pero deja abrir en otra pestaña con ⌘/Ctrl. */
export function linkTo(navigate: Navigate, route: Route) {
  return (e: MouseEvent) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(route);
  };
}

export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parsePath(window.location.pathname, window.location.search));

  useEffect(() => {
    const onPopState = () => setRoute(parsePath(window.location.pathname, window.location.search));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = useCallback<Navigate>((next, replace = false) => {
    const path = pathFor(next);
    if (path !== window.location.pathname + window.location.search) {
      if (replace) window.history.replaceState({}, "", path);
      else window.history.pushState({}, "", path);
    }
    setRoute(next);
    window.scrollTo({ top: 0 });
  }, []);

  return { route, navigate };
}
