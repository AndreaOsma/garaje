import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Vehicle } from "./api";
import { AppearanceToggle, type DayNightMode } from "./components/AppearanceToggle";
import { DensityToggle } from "./components/DensityToggle";
import { ErrorBox, Loading } from "./components/ui";
import { Diagnostics } from "./pages/Diagnostics";
import { Garage, NewVehicle } from "./pages/Garage";
import { Home } from "./pages/Home";
import { LessonPlayer } from "./pages/LessonPlayer";
import { LicenseDetail, Licenses } from "./pages/Licenses";
import { Maintenance } from "./pages/Maintenance";
import { Documents, Expenses, Fuel } from "./pages/Records";
import { VehicleSettings } from "./pages/VehicleSettings";
import { linkTo, tabsFor, useRoute, type Route, type TabId } from "./router";
import { Car, Icon, IdCard, Motorcycle } from "./vendor/icons";

type UiDensity = "minimal" | "detailed";

function readPref<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = localStorage.getItem(key) as T | null;
    return value && allowed.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

function writePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* modo privado: la preferencia no persiste, sin más */
  }
}

export default function App() {
  const { route, navigate } = useRoute();
  const [dayNightMode, setDayNightMode] = useState<DayNightMode>(() => readPref("garaje-daynight", ["day", "night", "auto"], "auto"));
  const [density, setDensity] = useState<UiDensity>(() => readPref("garaje-density", ["minimal", "detailed"], "minimal"));
  const [systemDark, setSystemDark] = useState(() => window.matchMedia("(prefers-color-scheme: dark)").matches);

  const [vehicles, setVehicles] = useState<Vehicle[] | null>(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => writePref("garaje-daynight", dayNightMode), [dayNightMode]);
  useEffect(() => writePref("garaje-density", density), [density]);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => setSystemDark(mq.matches);
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  const effectiveDark = dayNightMode === "night" ? true : dayNightMode === "day" ? false : systemDark;

  useEffect(() => {
    document.documentElement.style.colorScheme = effectiveDark ? "dark" : "light";
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", effectiveDark ? "#0b1220" : "#eef3f8");
  }, [effectiveDark]);

  const loadVehicles = useCallback(async () => {
    setLoadError("");
    try {
      setVehicles(await api.vehicles.list());
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "No se pudo conectar con el servidor");
    }
  }, []);

  useEffect(() => {
    void loadVehicles();
  }, [loadVehicles]);

  // Con un solo vehículo, la portada es directamente su Inicio (solo al abrir la app:
  // pulsar la marca después sí lleva al garaje, para poder añadir otro).
  const initialRedirect = useRef(false);
  useEffect(() => {
    if (!vehicles || initialRedirect.current) return;
    initialRedirect.current = true;
    if (route.name === "garage" && vehicles.filter((v) => !v.archived).length === 1) {
      const only = vehicles.find((v) => !v.archived)!;
      navigate({ name: "vehicle", id: only.id, tab: "home" }, true);
    }
  }, [route.name, vehicles, navigate]);

  const detailed = density === "detailed";
  const vehicle = route.name === "vehicle" ? vehicles?.find((v) => v.id === route.id) : undefined;
  const goTab = (tab: TabId) => vehicle && navigate({ name: "vehicle", id: vehicle.id, tab });
  const inLicenses = ["licenses", "license", "lesson", "review", "mixed", "practice", "exam"].includes(route.name);
  const isPlayer = ["lesson", "review", "mixed", "practice", "exam"].includes(route.name);
  // Al salir del reproductor se vuelve al permiso de donde se vino (si se sabe).
  const [lastLicense, setLastLicense] = useState<string | null>(null);
  useEffect(() => {
    if (route.name === "license") setLastLicense(route.code);
  }, [route]);
  const playerBack: Route = lastLicense ? { name: "license", code: lastLicense } : { name: "licenses" };

  let content;
  if (route.name === "licenses") content = <Licenses navigate={navigate} detailed={detailed} />;
  else if (route.name === "license") content = <LicenseDetail code={route.code} navigate={navigate} detailed={detailed} />;
  else if (route.name === "lesson") content = <LessonPlayer navigate={navigate} back={playerBack} mode={{ kind: "lesson", lessonId: route.id }} />;
  else if (route.name === "review") content = <LessonPlayer navigate={navigate} back={playerBack} mode={{ kind: "review" }} />;
  else if (route.name === "mixed") content = <LessonPlayer navigate={navigate} back={playerBack} mode={{ kind: "mixed", courses: route.courses }} />;
  else if (route.name === "practice")
    content = <LessonPlayer navigate={navigate} back={playerBack} mode={{ kind: "practice", courseId: route.courseId, concept: route.concept }} />;
  else if (route.name === "exam") content = <LessonPlayer navigate={navigate} back={playerBack} mode={{ kind: "exam", courseId: route.courseId }} />;
  else if (loadError) content = <ErrorBox message={loadError} onRetry={loadVehicles} />;
  else if (!vehicles) content = <Loading />;
  else if (route.name === "new")
    content = (
      <NewVehicle
        detailed={detailed}
        onCreated={async (v) => {
          await loadVehicles();
          navigate({ name: "vehicle", id: v.id, tab: "home" });
        }}
        onCancel={() => navigate({ name: "garage" })}
      />
    );
  else if (route.name === "garage" || !vehicle)
    content = (
      <Garage
        vehicles={vehicles}
        detailed={detailed}
        onOpen={(id) => navigate({ name: "vehicle", id, tab: "home" })}
        onNew={() => navigate({ name: "new" })}
      />
    );
  else {
    const common = { vehicle, detailed, onVehicleChanged: loadVehicles };
    content = {
      home: <Home {...common} goTab={goTab} dark={effectiveDark} />,
      maintenance: <Maintenance {...common} goTab={goTab} />,
      fuel: <Fuel {...common} />,
      expenses: <Expenses {...common} />,
      documents: <Documents {...common} />,
      diagnostics: <Diagnostics {...common} goTab={goTab} />,
      settings: (
        <VehicleSettings
          {...common}
          onDeleted={async () => {
            await loadVehicles();
            navigate({ name: "garage" });
          }}
        />
      ),
    }[route.tab];
  }

  const otherVehicles = (vehicles ?? []).filter((v) => !v.archived || v.id === vehicle?.id);

  return (
    <div className={`app-shell ${effectiveDark ? "theme-dark" : "theme-light"} density-${density}${isPlayer ? " is-player" : ""}`}>
      <a href="#main" className="skip-link">
        Saltar al contenido
      </a>
      {!isPlayer && (
      <header className="app-header">
        {/* El nombre de la app es el <h1> de cada vista (el reproductor de lecciones, sin cabecera, lleva el suyo). */}
        <h1 className="app-header__title">
          <button type="button" className="app-header__brand ds-display" onClick={() => navigate({ name: "garage" })}>
            <Icon svg={vehicle?.kind === "motorcycle" ? Motorcycle : Car} /> Garaje
          </button>
        </h1>
        {vehicle && otherVehicles.length > 1 && (
          <label className="vehicle-switch">
            <span className="sr-only">Vehículo</span>
            <select
              value={vehicle.id}
              onChange={(e) => navigate({ name: "vehicle", id: Number(e.target.value), tab: route.name === "vehicle" ? route.tab : "home" })}
            >
              {otherVehicles.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {vehicle && otherVehicles.length <= 1 && <span className="app-header__vehicle">{vehicle.name}</span>}
        <div className="app-header__controls">
          <a href="/carnes" className={`app-header__nav${inLicenses ? " is-active" : ""}`} aria-current={inLicenses ? "page" : undefined} onClick={linkTo(navigate, { name: "licenses" })}>
            <span aria-hidden><Icon svg={IdCard} /></span> Carnés
          </a>
          <DensityToggle value={density} onChange={setDensity} />
          <AppearanceToggle value={dayNightMode} onChange={setDayNightMode} />
        </div>
      </header>
      )}

      {vehicle && route.name === "vehicle" && (
        <nav className="tabs" aria-label="Secciones del vehículo">
          {tabsFor(vehicle.kind).map((t) => (
            <button
              key={t.id}
              type="button"
              className={`tabs__item${route.tab === t.id ? " is-active" : ""}`}
              aria-current={route.tab === t.id ? "page" : undefined}
              aria-label={t.label}
              onClick={() => goTab(t.id)}
            >
              <span aria-hidden className="tabs__icon">
                <Icon svg={t.icon} />
              </span>
              <span className="tabs__label tabs__label--long">{t.label}</span>
              <span className="tabs__label tabs__label--short" aria-hidden>
                {t.short}
              </span>
            </button>
          ))}
        </nav>
      )}

      <main id="main" className="app-main">
        {content}
      </main>

      {!isPlayer && (
      <footer className="app-footer">
        © {new Date().getFullYear()}{" "}
        <a href="https://andreaosma.com" target="_blank" rel="noopener noreferrer">
          Andrea Osma Rafael
        </a>
      </footer>
      )}
    </div>
  );
}
