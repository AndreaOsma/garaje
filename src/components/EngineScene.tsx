/**
 * Visor 3D de un motor por dentro: cinemática real de biela-manivela, distribución a
 * media vuelta, válvulas, gas de la cámara por fase, vista explotada y corte en sección.
 *
 * Copia idéntica en dev/apps/garaje y dev/apps/bitacora (cada app usa un tipo de motor):
 * si cambias uno, cambia el otro.
 */
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export type EngineKind = "inline-gasoline" | "inline-diesel" | "rotax912";
export type PartStatus = "ok" | "info" | "warn" | "danger";
export type Stroke = "admisión" | "compresión" | "explosión" | "escape";

type Props = {
  kind: EngineKind;
  /** Cilindros del motor en línea (2-6); se ignora en el Rotax. */
  cylinders?: number;
  statuses: Record<string, PartStatus>;
  selected: string | null;
  playing: boolean;
  rpm: number;
  explode: number;
  section: boolean;
  dark: boolean;
  onSelect: (id: string | null) => void;
  onStrokes: (strokes: Stroke[]) => void;
  onWebGLUnavailable: () => void;
};

const STATUS_COLOR: Record<Exclude<PartStatus, "ok">, number> = { info: 0x3b82f6, warn: 0xf59e0b, danger: 0xef4444 };

type Mat = { color: number; metalness: number; roughness: number };
const ALU: Mat = { color: 0xb9bfc7, metalness: 0.8, roughness: 0.35 };
const IRON: Mat = { color: 0x585e66, metalness: 0.7, roughness: 0.5 };
const STEEL: Mat = { color: 0xd3d8de, metalness: 0.95, roughness: 0.18 };
const BLACK: Mat = { color: 0x1f2328, metalness: 0.2, roughness: 0.6 };
const COPPER: Mat = { color: 0xb87333, metalness: 0.9, roughness: 0.3 };
const RUBBER: Mat = { color: 0x16181b, metalness: 0, roughness: 0.85 };
const BLUE_HOSE: Mat = { color: 0x1d4ed8, metalness: 0, roughness: 0.6 };
const RED: Mat = { color: 0xb91c1c, metalness: 0.3, roughness: 0.5 };
const CERAMIC: Mat = { color: 0xf1f5f9, metalness: 0, roughness: 0.4 };

/** Pieza del motor: malla, a qué pieza lógica pertenece, cilindro (si aplica), si es carcasa
 * (se recorta en sección) y hacia dónde se separa en la vista explotada. */
type Item = {
  obj: THREE.Object3D;
  part: string;
  cyl?: number;
  housing: boolean;
  explode: THREE.Vector3;
  base: THREE.Vector3;
  mats: THREE.MeshStandardMaterial[];
  color: number;
};

function mat(m: Mat) {
  return new THREE.MeshStandardMaterial({ color: m.color, metalness: m.metalness, roughness: m.roughness, transparent: true, side: THREE.DoubleSide });
}

function cyl(r: number, h: number, axis: "x" | "y" | "z" = "y", seg = 28, open = false) {
  const g = new THREE.CylinderGeometry(r, r, h, seg, 1, open);
  if (axis === "x") g.rotateZ(Math.PI / 2);
  if (axis === "z") g.rotateX(Math.PI / 2);
  return g;
}

function tube(points: THREE.Vector3[], r: number, closed = false) {
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points, closed, "catmullrom", 0.3), 48, r, 10, closed);
}

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

/** Fase del ciclo (0-720°) → tiempo. */
function strokeOf(phase: number): Stroke {
  if (phase < 180) return "admisión";
  if (phase < 360) return "compresión";
  if (phase < 540) return "explosión";
  return "escape";
}

const GAS: Record<Stroke, { color: number; opacity: number }> = {
  admisión: { color: 0x60a5fa, opacity: 0.35 },
  compresión: { color: 0x22d3ee, opacity: 0.5 },
  explosión: { color: 0xfb923c, opacity: 0.75 },
  escape: { color: 0x9ca3af, opacity: 0.4 },
};

/** Elevación de válvula (0-1) en una ventana de fase. */
function lift(phase: number, start: number, end: number) {
  if (phase < start || phase > end) return 0;
  return Math.sin((Math.PI * (phase - start)) / (end - start));
}

type Built = {
  items: Item[];
  /** Actualiza las piezas móviles para un ángulo de cigüeñal (grados) y devuelve los tiempos. */
  animate: (crankDeg: number, explode: number) => Stroke[];
  sectionNormal: THREE.Vector3;
  camera: THREE.Vector3;
};

// ---------------------------------------------------------------------------
// Motor en línea de N cilindros (2-6), 4 válvulas por cilindro (gasolina / diésel).
// ---------------------------------------------------------------------------

/** Orden de encendido habitual de cada configuración en línea. */
export const FIRING_ORDER: Record<number, number[]> = {
  2: [1, 2],
  3: [1, 2, 3],
  4: [1, 3, 4, 2],
  5: [1, 2, 4, 5, 3],
  6: [1, 5, 3, 6, 2, 4],
};

function buildInline(root: THREE.Group, diesel: boolean, n: number): Built {
  const items: Item[] = [];
  const add = (obj: THREE.Object3D, part: string, m: Mat, explode: THREE.Vector3, opts: { housing?: boolean; cyl?: number } = {}) => {
    const mats: THREE.MeshStandardMaterial[] = [];
    obj.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) {
        const mm = mat(m);
        mesh.material = mm;
        mesh.castShadow = true;
        mats.push(mm);
      }
    });
    root.add(obj);
    items.push({ obj, part, cyl: opts.cyl, housing: Boolean(opts.housing), explode, base: obj.position.clone(), mats, color: m.color });
    return obj;
  };
  const mesh = (g: THREE.BufferGeometry, pos?: THREE.Vector3) => {
    const m = new THREE.Mesh(g);
    if (pos) m.position.copy(pos);
    return m;
  };

  const PITCH = 0.09;
  const N = FIRING_ORDER[n] ? n : 4;
  const H = (N * PITCH) / 2; // media longitud del bloque
  const X = Array.from({ length: N }, (_, i) => (i - (N - 1) / 2) * PITCH);
  const BORE = 0.08;
  const R = 0.044; // radio de manivela (carrera 88 mm)
  const L = 0.14; // biela
  const DECK = 0.215;
  // Fase de cada cilindro en el ciclo de 720° según su posición en el orden de encendido;
  // su muñequilla está donde ese cilindro llega al PMS (ángulo opuesto a la fase).
  const order = FIRING_ORDER[N];
  const cycleOffset = X.map((_, i) => (order.indexOf(i + 1) * 720) / N);
  const throwOffset = cycleOffset.map((o) => (((-o % 360) + 360) % 360));

  // Carcasas: bloque, culata, tapa, cárter.
  add(mesh(new THREE.BoxGeometry(2 * H + 0.04, 0.24, 0.17), v(0, 0.1, 0)), "block", IRON, v(0, 0, 0), { housing: true });
  add(mesh(new THREE.BoxGeometry(2 * H + 0.04, 0.1, 0.19), v(0, 0.27, 0)), "head", ALU, v(0, 0.22, 0), { housing: true });
  add(mesh(new THREE.BoxGeometry(2 * H + 0.02, 0.04, 0.17), v(0, 0.345, 0)), "head", BLACK, v(0, 0.42, 0), { housing: true });
  add(mesh(new THREE.BoxGeometry(2 * H + 0.02, 0.1, 0.15), v(0, -0.07, 0)), "oil", BLACK, v(0, -0.22, 0), { housing: true });
  add(mesh(cyl(0.035, 0.08, "z"), v(H - 0.1, -0.03, -0.12)), "oil", { color: 0x1d4ed8, metalness: 0.3, roughness: 0.5 }, v(0, -0.1, -0.15));

  // Camisas de los cilindros (dentro del bloque).
  X.forEach((x, i) => add(mesh(cyl(BORE / 2 + 0.004, DECK - 0.07, "y", 32, true), v(x, (DECK + 0.07) / 2, 0)), "block", STEEL, v(0, 0, 0), { housing: true, cyl: i + 1 }));

  // Cigüeñal: apoyos, muñequillas y contrapesos; gira entero.
  const crank = new THREE.Group();
  const crankParts: THREE.Mesh[] = [];
  const journal = cyl(0.022, 0.03, "x");
  for (let i = 0; i <= N; i++) crankParts.push(mesh(journal, v(-H + i * PITCH, 0, 0)));
  X.forEach((x, i) => {
    const a = (throwOffset[i] * Math.PI) / 180;
    const pin = mesh(cyl(0.018, 0.028, "x"), v(x, R * Math.cos(a), R * Math.sin(a)));
    crankParts.push(pin);
    for (const dx of [-0.022, 0.022]) {
      const web = mesh(new THREE.BoxGeometry(0.012, R + 0.03, 0.05), v(x + dx, (R / 2) * Math.cos(a), (R / 2) * Math.sin(a)));
      web.rotation.x = a;
      const cw = mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.012, 24, 1, false, 0, Math.PI).rotateZ(Math.PI / 2), v(x + dx, -0.01 * Math.cos(a), -0.01 * Math.sin(a)));
      cw.rotation.x = a + Math.PI;
      crankParts.push(web, cw);
    }
  });
  crankParts.forEach((p) => crank.add(p));
  add(crank, "crank", STEEL, v(0, -0.12, 0));

  // Volante motor y distribución (correa) en los extremos.
  add(mesh(cyl(0.13, 0.025, "x", 48), v(-H - 0.045, 0, 0)), "flywheel", IRON, v(-0.18, 0, 0));
  const camY = 0.3;
  const camZ = [-0.035, 0.035];
  const TX = H + 0.045; // plano de la distribución
  add(mesh(cyl(0.03, 0.03, "x"), v(TX, 0, 0)), "timing", STEEL, v(0.16, 0, 0));
  camZ.forEach((z) => add(mesh(cyl(0.045, 0.025, "x"), v(TX, camY, z)), "timing", STEEL, v(0.16, 0.2, 0)));
  add(mesh(cyl(0.028, 0.025, "x"), v(TX, 0.12, -0.075)), "cooling", ALU, v(0.16, 0, -0.1)); // bomba de agua
  add(
    mesh(tube([v(TX + 0.01, -0.03, 0.0), v(TX + 0.01, 0.0, 0.035), v(TX + 0.01, camY, 0.08), v(TX + 0.01, camY + 0.05, 0), v(TX + 0.01, camY, -0.08), v(TX + 0.01, 0.12, -0.11), v(TX + 0.01, -0.01, -0.03)], 0.006, true)),
    "timing", RUBBER, v(0.16, 0.1, 0)
  );
  // Alternador (correa auxiliar).
  add(mesh(cyl(0.05, 0.09, "x"), v(H - 0.02, 0.06, 0.15)), "alternator", ALU, v(0.1, 0, 0.18));

  // Árboles de levas (admisión z−, escape z+), giran a media vuelta.
  const cams = camZ.map((z, side) => {
    const g = new THREE.Group();
    g.position.set(0, camY, z);
    g.add(mesh(cyl(0.012, 2 * H + 0.06, "x")));
    X.forEach((x, i) => {
      // Lóbulo orientado para abrir en su ventana: admisión 0-180°, escape 540-720° de cada cilindro.
      const open = side === 0 ? 90 : 630;
      const camAngle = (((cycleOffset[i] + open) / 2) * Math.PI) / 180;
      for (const dx of [-0.015, 0.015]) {
        const lobe = mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.01, 20).rotateZ(Math.PI / 2).scale(1, 1.35, 1), v(x + dx, 0, 0));
        lobe.rotation.x = -camAngle;
        lobe.geometry.translate(0, 0.006, 0);
        g.add(lobe);
      }
    });
    return add(g, "camshaft", STEEL, v(0, 0.3, side === 0 ? -0.06 : 0.06));
  });

  // Por cilindro: pistón con segmentos, biela, válvulas, gas, bujía/inyector.
  type Cyl = { piston: THREE.Object3D; rod: THREE.Object3D; valves: { obj: THREE.Object3D; dir: THREE.Vector3; base: THREE.Vector3; intake: boolean }[]; gas: THREE.Mesh; spark: THREE.Mesh };
  const cylinders: Cyl[] = X.map((x, i) => {
    const p = new THREE.Group();
    p.add(mesh(cyl(BORE / 2 - 0.001, 0.05)));
    for (const dy of [0.016, 0.008, 0]) p.add(mesh(new THREE.TorusGeometry(BORE / 2 - 0.0005, 0.0012, 6, 32).rotateX(Math.PI / 2), v(0, dy, 0)));
    const piston = add(p, "pistons", ALU, v(0, 0.12, 0), { cyl: i + 1 });
    const rod = add(mesh(new THREE.BoxGeometry(0.014, L, 0.026)), "conrods", STEEL, v(0, 0.06, 0), { cyl: i + 1 });
    const valves = [-1, 1].flatMap((side) =>
      [-0.016, 0.016].map((dx) => {
        const g = new THREE.Group();
        g.add(mesh(cyl(0.0035, 0.085)));
        g.add(mesh(cyl(0.014, 0.004), v(0, -0.0425, 0)));
        g.add(mesh(new THREE.CylinderGeometry(0.011, 0.011, 0.025, 12, 1, true), v(0, 0.03, 0))); // muelle
        const tilt = side * 0.22;
        g.rotation.x = tilt;
        const base = v(x + dx, DECK + 0.045, side * 0.022);
        g.position.copy(base);
        const dir = v(0, -Math.cos(tilt), -Math.sin(tilt)); // hacia la cámara, a lo largo del vástago
        add(g, "valves", STEEL, v(0, 0.2, side * 0.03), { cyl: i + 1 });
        return { obj: g, dir, base, intake: side < 0 };
      })
    );
    const gasMat = new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false });
    const gas = new THREE.Mesh(cyl(BORE / 2 - 0.003, 1), gasMat);
    root.add(gas);
    // Bujía (gasolina) con su bobina, o inyector (diésel) en el centro de la cámara.
    const top = new THREE.Group();
    if (diesel) {
      top.add(mesh(cyl(0.006, 0.09), v(0, 0, 0)));
      top.add(mesh(cyl(0.011, 0.03), v(0, 0.04, 0)));
      add(top, "injectors", STEEL, v(0, 0.32, 0), { cyl: i + 1 });
      // Calentador (bujía de precalentamiento) al lado.
      const glow = mesh(cyl(0.004, 0.07), v(x + 0.022, DECK + 0.05, 0.01));
      glow.rotation.z = 0.3;
      add(glow, "glow", COPPER, v(0.02, 0.3, 0), { cyl: i + 1 });
    } else {
      top.add(mesh(cyl(0.007, 0.05), v(0, 0, 0)));
      top.add(mesh(cyl(0.01, 0.02), v(0, 0.035, 0)));
      add(top, "ignition", CERAMIC, v(0, 0.32, 0), { cyl: i + 1 });
      add(mesh(new THREE.BoxGeometry(0.035, 0.06, 0.04), v(x, 0.395, 0)), "ignition", BLACK, v(0, 0.5, 0), { cyl: i + 1 });
    }
    top.position.set(x, DECK + 0.07, 0);
    items.find((it) => it.obj === top)!.base.copy(top.position);
    const spark = new THREE.Mesh(new THREE.SphereGeometry(0.012, 12, 8), new THREE.MeshBasicMaterial({ color: diesel ? 0xfef08a : 0xfde68a, transparent: true }));
    spark.position.set(x, DECK + 0.005, 0);
    root.add(spark);
    return { piston, rod, valves, gas, spark };
  });

  // Admisión (z−): colector con 4 tubos, cuerpo de mariposa / caudalímetro.
  const intake = new THREE.Group();
  intake.add(mesh(new THREE.BoxGeometry(2 * H, 0.07, 0.07), v(0, 0.2, -0.2)));
  X.forEach((x) => intake.add(mesh(tube([v(x, 0.22, -0.17), v(x, 0.27, -0.13), v(x, 0.29, -0.095)], 0.017))));
  intake.add(mesh(cyl(0.035, 0.07, "x"), v(H + 0.04, 0.2, -0.2)));
  add(intake, "intake", diesel ? BLACK : ALU, v(0, 0, -0.2));

  // Escape (z+): colector 4-1 hacia catalizador (gasolina) o turbo + FAP (diésel).
  const exhaust = new THREE.Group();
  X.forEach((x) => exhaust.add(mesh(tube([v(x, 0.28, 0.095), v(x, 0.25, 0.14), v(x * 0.4, 0.17, 0.19), v(0, 0.12, 0.2)], 0.016))));
  add(exhaust, "exhaust", IRON, v(0, 0, 0.2));
  if (diesel) {
    const turbo = new THREE.Group();
    turbo.add(mesh(new THREE.TorusGeometry(0.038, 0.022, 14, 28).rotateY(Math.PI / 2), v(-0.05, 0.12, 0.24)));
    turbo.add(mesh(new THREE.TorusGeometry(0.034, 0.019, 14, 28).rotateY(Math.PI / 2), v(-0.15, 0.12, 0.24)));
    turbo.add(mesh(cyl(0.025, 0.1, "x"), v(-0.1, 0.12, 0.25)));
    add(turbo, "turbo", STEEL, v(0, 0.05, 0.3));
    add(mesh(cyl(0.045, 0.26, "x"), v(-0.08, -0.1, 0.3)), "dpf", STEEL, v(0, -0.12, 0.3));
    // EGR: válvula y tubo del colector de escape al de admisión.
    add(mesh(new THREE.BoxGeometry(0.06, 0.05, 0.05), v(H + 0.02, 0.33, 0)), "egr", ALU, v(0.12, 0.3, 0));
    add(mesh(tube([v(H - 0.06, 0.17, 0.19), v(H + 0.02, 0.3, 0.1), v(H + 0.02, 0.33, 0), v(H + 0.02, 0.25, -0.15), v(H - 0.03, 0.2, -0.2)], 0.012)), "egr", STEEL, v(0.12, 0.3, 0));
    add(mesh(new THREE.BoxGeometry(0.06, 0.16, 0.3), v(H + 0.18, 0.05, 0)), "intercooler", ALU, v(0.25, 0, 0));
    // Common rail y bomba de alta presión.
    const rail = new THREE.Group();
    rail.add(mesh(cyl(0.012, 2 * H, "x"), v(0, DECK + 0.13, 0.045)));
    X.forEach((x) => rail.add(mesh(tube([v(x, DECK + 0.13, 0.045), v(x, DECK + 0.12, 0.02), v(x, DECK + 0.11, 0)], 0.004))));
    rail.add(mesh(cyl(0.03, 0.07, "x"), v(H + 0.02, 0.2, 0.11)));
    add(rail, "fuel_rail", STEEL, v(0, 0.42, 0.05));
  } else {
    add(mesh(cyl(0.06, 0.2, "x"), v(-0.02, 0.0, 0.26)), "exhaust", STEEL, v(0, -0.08, 0.3));
    const rail = new THREE.Group();
    rail.add(mesh(cyl(0.01, 2 * H, "x"), v(0, 0.255, -0.08)));
    X.forEach((x) => rail.add(mesh(cyl(0.006, 0.05, "z"), v(x, 0.255, -0.06))));
    add(rail, "fuel_rail", STEEL, v(0, 0.1, -0.15));
  }
  // Sensores: posición de cigüeñal (junto al volante) y de árbol de levas.
  add(mesh(cyl(0.01, 0.04, "z"), v(-H - 0.02, -0.1, 0.06)), "sensors", BLACK, v(-0.1, -0.1, 0.1));
  add(mesh(cyl(0.01, 0.04, "x"), v(H + 0.03, camY + 0.03, -0.06)), "sensors", BLACK, v(0.15, 0.25, 0));
  // Termostato y manguitos.
  add(mesh(tube([v(H, 0.28, -0.095), v(H + 0.07, 0.3, -0.15), v(H + 0.15, 0.2, -0.12), v(H + 0.18, 0.1, -0.08)], 0.013)), "cooling", BLUE_HOSE, v(0.15, 0, -0.1));

  const setPos = (it: Item, p: THREE.Vector3, explode: number) => it.obj.position.copy(p).addScaledVector(it.explode, explode);
  const itemOf = (o: THREE.Object3D) => items.find((it) => it.obj === o)!;

  return {
    items,
    sectionNormal: v(0, 0, -1),
    camera: v(0.72, 0.7, 1.0).multiplyScalar(Math.max(0.85, (N + 1) / 5)),
    animate: (crankDeg, explode) => {
      const crankRad = (crankDeg * Math.PI) / 180;
      const crankItem = itemOf(crank);
      crank.rotation.x = crankRad;
      setPos(crankItem, crankItem.base, explode);
      cams.forEach((c) => {
        c.rotation.x = crankRad / 2;
        const it = itemOf(c);
        setPos(it, it.base, explode);
      });
      for (const it of items) if (!it.cyl && it.obj !== crank && !cams.includes(it.obj as THREE.Group)) setPos(it, it.base, explode);
      return cylinders.map((c, i) => {
        const a = ((crankDeg + throwOffset[i]) * Math.PI) / 180;
        const pinY = R * Math.cos(a);
        const pinZ = R * Math.sin(a);
        const pistonY = pinY + Math.sqrt(L * L - pinZ * pinZ);
        const pItem = itemOf(c.piston);
        setPos(pItem, v(X[i], pistonY - 0.005, 0), explode); // bulón 5 mm bajo el centro del pistón
        const rItem = itemOf(c.rod);
        setPos(rItem, v(X[i], (pinY + pistonY) / 2, pinZ / 2), explode);
        c.rod.rotation.x = Math.atan2(-pinZ, pistonY - pinY);
        const phase = (((crankDeg - cycleOffset[i]) % 720) + 720) % 720;
        for (const valve of c.valves) {
          const l = valve.intake ? lift(phase, 0, 200) : lift(phase, 520, 720);
          const it = itemOf(valve.obj);
          setPos(it, valve.base.clone().addScaledVector(valve.dir, 0.009 * l), explode);
        }
        for (const it of items) if (it.cyl === i + 1 && it.part !== "pistons" && it.part !== "conrods" && it.part !== "valves") setPos(it, it.base, explode);
        const stroke = strokeOf(phase);
        const gasTop = DECK;
        const gasBottom = pistonY + 0.02;
        c.gas.scale.y = Math.max(0.001, gasTop - gasBottom);
        c.gas.position.set(X[i], (gasTop + gasBottom) / 2 + explode * 0.06, 0);
        const g = c.gas.material as THREE.MeshBasicMaterial;
        g.color.setHex(GAS[stroke].color);
        g.opacity = explode > 0.3 ? 0 : GAS[stroke].opacity;
        // Chispa / inyección justo en el PMS de explosión.
        const fire = phase > 355 && phase < 395 ? 1 - Math.abs(phase - 370) / 25 : 0;
        (c.spark.material as THREE.MeshBasicMaterial).opacity = explode > 0.3 ? 0 : fire;
        c.spark.scale.setScalar(0.5 + fire);
        return stroke;
      });
    },
  };
}

// ---------------------------------------------------------------------------
// Rotax 912: bóxer de 4 cilindros, cilindros con aletas (aire), culatas refrigeradas
// por líquido, levas centrales con varillas, 2 carburadores, reductora a la hélice,
// doble encendido, cárter seco. Orden de encendido 1-4-2-3.
// ---------------------------------------------------------------------------
function buildRotax(root: THREE.Group): Built {
  const items: Item[] = [];
  const add = (obj: THREE.Object3D, part: string, m: Mat, explode: THREE.Vector3, opts: { housing?: boolean; cyl?: number } = {}) => {
    const mats: THREE.MeshStandardMaterial[] = [];
    obj.traverse((o) => {
      const meshO = o as THREE.Mesh;
      if (meshO.isMesh) {
        const mm = mat(m);
        meshO.material = mm;
        meshO.castShadow = true;
        mats.push(mm);
      }
    });
    root.add(obj);
    items.push({ obj, part, cyl: opts.cyl, housing: Boolean(opts.housing), explode, base: obj.position.clone(), mats, color: m.color });
    return obj;
  };
  const mesh = (g: THREE.BufferGeometry, pos?: THREE.Vector3) => {
    const m = new THREE.Mesh(g);
    if (pos) m.position.copy(pos);
    return m;
  };

  const R = 0.0305; // carrera 61 mm
  const L = 0.103;
  const BORE = 0.0795;
  // Cilindro → [x a lo largo del cigüeñal, lado (+1 derecha, −1 izquierda)]. 1 y 2 delante.
  const CYLS: Array<[number, number]> = [
    [0.07, 1],
    [0.07, -1],
    [-0.07, 1],
    [-0.07, -1],
  ];
  const throwOffset = [0, 0, 180, 180];
  const cycleOffset = [0, 360, 540, 180]; // orden 1-4-2-3
  const DECK = 0.17;

  add(mesh(new THREE.BoxGeometry(0.28, 0.17, 0.14), v(0, 0, 0)), "crankcase", ALU, v(0, 0, 0), { housing: true });
  // Cigüeñal y árbol de levas central.
  const crank = new THREE.Group();
  crank.add(mesh(cyl(0.018, 0.32, "x")));
  // En un bóxer, los cilindros opuestos tienen la muñequilla a 180°: sus pistones salen a la vez.
  CYLS.forEach(([x, side], i) => {
    const a = ((throwOffset[i] + (side < 0 ? 180 : 0)) * Math.PI) / 180;
    crank.add(mesh(cyl(0.015, 0.03, "x"), v(x + side * 0.012, R * Math.sin(a), R * Math.cos(a))));
    const web = mesh(new THREE.BoxGeometry(0.008, 0.03, R + 0.03), v(x + side * 0.03, (R / 2) * Math.sin(a), (R / 2) * Math.cos(a)));
    web.rotation.x = -a;
    crank.add(web);
  });
  add(crank, "crank", STEEL, v(0, -0.1, 0));
  const cam = new THREE.Group();
  cam.position.set(0, -0.045, 0);
  cam.add(mesh(cyl(0.01, 0.26, "x")));
  CYLS.forEach(([x]) => cam.add(mesh(new THREE.CylinderGeometry(0.014, 0.014, 0.01, 16).rotateZ(Math.PI / 2).scale(1, 1.4, 1), v(x, 0, 0))));
  add(cam, "valvetrain", STEEL, v(0, -0.12, 0));

  type Cyl = { piston: THREE.Object3D; rod: THREE.Object3D; side: number; x: number; gas: THREE.Mesh; spark: THREE.Mesh; valves: { obj: THREE.Object3D; base: THREE.Vector3; intake: boolean }[] };
  const cylinders: Cyl[] = CYLS.map(([x, side], i) => {
    // Cilindro de aletas (refrigerado por aire).
    const barrel = new THREE.Group();
    barrel.add(mesh(cyl(BORE / 2 + 0.006, 0.09, "z", 32, true)));
    for (let k = 0; k < 9; k++) barrel.add(mesh(cyl(0.058, 0.003, "z", 32), v(0, 0, -0.04 + k * 0.01)));
    barrel.position.set(x, 0, side * (0.07 + 0.045));
    add(barrel, "cylinders", ALU, v(0, 0, side * 0.12), { housing: true, cyl: i + 1 });
    // Culata (líquido) con su manguito de refrigerante.
    const head = mesh(new THREE.BoxGeometry(0.1, 0.11, 0.05), v(x, 0, side * (DECK + 0.02)));
    add(head, "heads", ALU, v(0, 0, side * 0.22), { housing: true, cyl: i + 1 });
    add(mesh(tube([v(x, 0.05, side * (DECK + 0.02)), v(x, 0.1, side * (DECK + 0.01)), v(x * 0.4, 0.13, side * 0.12), v(0, 0.12, side * 0.05)], 0.008)), "cooling", BLUE_HOSE, v(0, 0.1, side * 0.15), { cyl: i + 1 });
    // Pistón y biela (horizontales).
    const p = new THREE.Group();
    p.add(mesh(cyl(BORE / 2 - 0.001, 0.04, "z")));
    for (const dz of [0.012, 0.005]) p.add(mesh(new THREE.TorusGeometry(BORE / 2 - 0.0005, 0.0011, 6, 32), v(0, 0, side * dz)));
    const piston = add(p, "pistons", ALU, v(0, 0, side * 0.08), { cyl: i + 1 });
    const rod = add(mesh(new THREE.BoxGeometry(0.012, 0.022, L)), "crank", STEEL, v(0, 0, side * 0.04), { cyl: i + 1 });
    // Dos bujías por cilindro (doble encendido): arriba y abajo de la culata.
    for (const dy of [0.04, -0.04]) {
      const plug = mesh(cyl(0.006, 0.04, "z"), v(x, dy, side * (DECK + 0.055)));
      add(plug, "ignition", CERAMIC, v(0, dy * 2, side * 0.3), { cyl: i + 1 });
    }
    // Válvulas (admisión arriba, escape abajo) con varillas desde las levas.
    const valves = [1, -1].map((dir) => {
      const g = new THREE.Group();
      g.add(mesh(cyl(0.003, 0.06, "z")));
      g.add(mesh(cyl(0.012, 0.003, "z"), v(0, 0, -side * 0.03)));
      const base = v(x + dir * 0.015, dir * 0.022, side * (DECK + 0.03));
      g.position.copy(base);
      add(g, "valvetrain", STEEL, v(0, dir * 0.05, side * 0.24), { cyl: i + 1 });
      return { obj: g, base, intake: dir > 0 };
    });
    add(mesh(tube([v(x + 0.015, -0.04, side * 0.06), v(x + 0.015, -0.035, side * 0.12), v(x + 0.015, 0.03, side * DECK)], 0.003)), "valvetrain", STEEL, v(0, 0, side * 0.12), { cyl: i + 1 });
    const gas = new THREE.Mesh(cyl(BORE / 2 - 0.003, 1, "z"), new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false }));
    root.add(gas);
    const spark = new THREE.Mesh(new THREE.SphereGeometry(0.011, 12, 8), new THREE.MeshBasicMaterial({ color: 0xfde68a, transparent: true }));
    spark.position.set(x, 0, side * (DECK - 0.005));
    root.add(spark);
    return { piston, rod, side, x, gas, spark, valves };
  });

  // Carburadores (uno por lado) sobre los colectores, unidos por el tubo de equilibrio.
  for (const side of [1, -1]) {
    const carb = new THREE.Group();
    carb.add(mesh(cyl(0.035, 0.07, "y"), v(0, 0.2, side * 0.14)));
    carb.add(mesh(cyl(0.022, 0.06, "x"), v(0.045, 0.2, side * 0.14)));
    carb.add(mesh(new THREE.BoxGeometry(0.06, 0.04, 0.05), v(0, 0.14, side * 0.14))); // cuba
    add(carb, "carbs", ALU, v(0, 0.2, side * 0.06));
    add(mesh(tube([v(0, 0.16, side * 0.14), v(0.07, 0.1, side * 0.16), v(0.07, 0.06, side * DECK)], 0.013)), "carbs", BLACK, v(0, 0.12, side * 0.06));
    add(mesh(tube([v(0, 0.16, side * 0.14), v(-0.07, 0.1, side * 0.16), v(-0.07, 0.06, side * DECK)], 0.013)), "carbs", BLACK, v(0, 0.12, side * 0.06));
    // Escapes: de cada culata hacia el silenciador inferior.
    for (const x of [0.07, -0.07]) add(mesh(tube([v(x, -0.05, side * (DECK + 0.02)), v(x, -0.12, side * 0.17), v(x * 0.5, -0.19, side * 0.08), v(0, -0.21, 0)], 0.012)), "exhaust", STEEL, v(0, -0.12, side * 0.08));
  }
  add(mesh(tube([v(0, 0.22, 0.14), v(0, 0.26, 0), v(0, 0.22, -0.14)], 0.006)), "carbs", STEEL, v(0, 0.28, 0));
  add(mesh(cyl(0.05, 0.22, "x"), v(0, -0.23, 0)), "exhaust", STEEL, v(0, -0.2, 0));

  // Reductora delantera y brida de la hélice (gira más despacio que el cigüeñal).
  add(mesh(new THREE.BoxGeometry(0.1, 0.16, 0.12), v(0.19, 0.05, 0)), "gearbox", ALU, v(0.18, 0, 0), { housing: true });
  const flange = new THREE.Group();
  flange.position.set(0.255, 0.09, 0);
  flange.add(mesh(cyl(0.055, 0.015, "x", 32)));
  for (let k = 0; k < 6; k++) {
    const a = (k / 6) * Math.PI * 2;
    flange.add(mesh(cyl(0.005, 0.02, "x"), v(0.004, 0.04 * Math.cos(a), 0.04 * Math.sin(a))));
  }
  add(flange, "gearbox", STEEL, v(0.28, 0, 0));

  // Encendido: módulos (A y B) y alternador/generador atrás; motor de arranque abajo.
  add(mesh(new THREE.BoxGeometry(0.05, 0.06, 0.04), v(-0.17, 0.06, 0.05)), "ignition", BLACK, v(-0.16, 0.08, 0.05));
  add(mesh(new THREE.BoxGeometry(0.05, 0.06, 0.04), v(-0.17, 0.06, -0.05)), "ignition", BLACK, v(-0.16, 0.08, -0.05));
  add(mesh(cyl(0.06, 0.05, "x", 32), v(-0.17, -0.02, 0)), "electrical", ALU, v(-0.18, 0, 0));
  add(mesh(cyl(0.03, 0.12, "x"), v(0.02, -0.11, 0.08)), "electrical", BLACK, v(0, -0.12, 0.12));
  // Lubricación por cárter seco: depósito de aceite separado, radiador de aceite y bomba.
  add(mesh(cyl(0.05, 0.16, "y"), v(-0.05, 0.05, 0.3)), "oil", { color: 0x9ca3af, metalness: 0.6, roughness: 0.4 }, v(0, 0, 0.18));
  add(mesh(new THREE.BoxGeometry(0.02, 0.08, 0.12), v(-0.22, -0.05, 0.25)), "oil", ALU, v(-0.1, 0, 0.12));
  add(mesh(tube([v(-0.05, -0.03, 0.27), v(-0.12, -0.08, 0.15), v(-0.14, -0.06, 0.05)], 0.006)), "oil", RUBBER, v(0, 0, 0.12));
  // Bomba mecánica de combustible.
  add(mesh(new THREE.BoxGeometry(0.04, 0.04, 0.04), v(-0.15, -0.08, -0.06)), "fuel", RED, v(-0.12, -0.08, -0.08));

  const itemOf = (o: THREE.Object3D) => items.find((it) => it.obj === o)!;
  const setPos = (it: Item, p: THREE.Vector3, explode: number) => it.obj.position.copy(p).addScaledVector(it.explode, explode);

  return {
    items,
    sectionNormal: v(0, -1, 0),
    camera: v(0.62, 0.6, 0.78),
    animate: (crankDeg, explode) => {
      const rad = (crankDeg * Math.PI) / 180;
      crank.rotation.x = -rad;
      cam.rotation.x = -rad / 2;
      flange.rotation.x = -rad / 2.43;
      for (const it of items) if (!it.cyl || it.part === "cylinders" || it.part === "heads" || it.part === "cooling" || it.part === "ignition") setPos(it, it.base, explode);
      return cylinders.map((c, i) => {
        const a = ((crankDeg + throwOffset[i] + (c.side < 0 ? 180 : 0)) * Math.PI) / 180;
        const pinY = R * Math.sin(a);
        const pinAlong = c.side * R * Math.cos(a); // distancia de la muñequilla a lo largo de su cilindro
        const dist = pinAlong + Math.sqrt(L * L - pinY * pinY);
        const pItem = itemOf(c.piston);
        setPos(pItem, v(c.x, 0, c.side * (dist + 0.005)), explode);
        const rItem = itemOf(c.rod);
        setPos(rItem, v(c.x, pinY / 2, c.side * ((pinAlong + dist) / 2)), explode);
        c.rod.rotation.x = c.side * Math.atan2(pinY, dist - pinAlong);
        const phase = (((crankDeg - cycleOffset[i]) % 720) + 720) % 720;
        for (const valve of c.valves) {
          const l = valve.intake ? lift(phase, 0, 200) : lift(phase, 520, 720);
          setPos(itemOf(valve.obj), valve.base.clone().add(v(0, 0, -c.side * 0.008 * l)), explode);
        }
        for (const it of items) if (it.cyl === i + 1 && it.part === "valvetrain" && !c.valves.some((vv) => vv.obj === it.obj)) setPos(it, it.base, explode);
        const stroke = strokeOf(phase);
        const top = DECK;
        const bottom = dist + 0.025;
        c.gas.scale.z = Math.max(0.001, top - bottom); // el cilindro de gas va a lo largo de z
        c.gas.position.set(c.x, 0, c.side * ((top + bottom) / 2 + explode * 0.05));
        const g = c.gas.material as THREE.MeshBasicMaterial;
        g.color.setHex(GAS[stroke].color);
        g.opacity = explode > 0.3 ? 0 : GAS[stroke].opacity;
        const fire = phase > 355 && phase < 395 ? 1 - Math.abs(phase - 370) / 25 : 0;
        (c.spark.material as THREE.MeshBasicMaterial).opacity = explode > 0.3 ? 0 : fire;
        c.spark.scale.setScalar(0.5 + fire);
        return stroke;
      });
    },
  };
}

export default function EngineScene({ kind, cylinders = 4, statuses, selected, playing, rpm, explode, section, dark, onSelect, onStrokes, onWebGLUnavailable }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef({ statuses, selected, playing, rpm, explode, section, dark });
  stateRef.current = { statuses, selected, playing, rpm, explode, section, dark };
  const cbRef = useRef({ onSelect, onStrokes });
  cbRef.current = { onSelect, onStrokes };

  useEffect(() => {
    const mount = mountRef.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      onWebGLUnavailable();
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.localClippingEnabled = true;
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(renderer);
    const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envTex;
    const key = new THREE.DirectionalLight(0xffffff, 1.2);
    key.position.set(2, 3, 2);
    scene.add(key, new THREE.HemisphereLight(0xffffff, 0x334455, 0.4));

    const root = new THREE.Group();
    scene.add(root);
    const built = kind === "rotax912" ? buildRotax(root) : buildInline(root, kind === "inline-diesel", cylinders);
    const box = new THREE.Box3().setFromObject(root);
    const center = box.getCenter(new THREE.Vector3());
    root.position.sub(center);

    const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 20);
    camera.position.copy(built.camera);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.minDistance = 0.4;
    controls.maxDistance = 3;
    controls.target.set(0, 0, 0);

    const sectionPlane = new THREE.Plane(built.sectionNormal.clone(), 0);

    const resize = () => {
      renderer.setSize(mount.clientWidth, mount.clientHeight, false);
      camera.aspect = mount.clientWidth / mount.clientHeight;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(mount);
    resize();

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const meshes = () => built.items.flatMap((it) => {
      const out: THREE.Object3D[] = [];
      it.obj.traverse((o) => (o as THREE.Mesh).isMesh && out.push(o));
      return out.map((o) => ({ o, it }));
    });
    const all = meshes();
    let downAt: { x: number; y: number } | null = null;
    const pick = (ev: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const { section: sec } = stateRef.current;
      // Con la carcasa semitransparente (o recortada) se puede tocar lo de dentro.
      const hits = raycaster.intersectObjects(all.map((x) => x.o));
      for (const hit of hits) {
        const entry = all.find((x) => x.o === hit.object)!;
        if (entry.it.housing && !sec && hits.length > 1) continue;
        if (sec && entry.it.housing && sectionPlane.distanceToPoint(hit.point.clone().sub(root.position)) < 0) continue;
        return entry.it.part;
      }
      return null;
    };
    const onDown = (ev: PointerEvent) => (downAt = { x: ev.clientX, y: ev.clientY });
    const onUp = (ev: PointerEvent) => {
      if (downAt && Math.hypot(ev.clientX - downAt.x, ev.clientY - downAt.y) < 6) cbRef.current.onSelect(pick(ev));
      downAt = null;
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    let visible = true;
    const io = new IntersectionObserver(([entry]) => (visible = entry.isIntersecting));
    io.observe(mount);

    let crankDeg = 0;
    let last = performance.now();
    let lastReport = 0;
    let lastStrokes = "";
    renderer.setAnimationLoop((now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (!visible) return;
      const st = stateRef.current;
      // rpm «visuales»: a 60 rpm se ve una vuelta por segundo.
      if (st.playing) crankDeg = (crankDeg + st.rpm * 6 * dt) % 1440;
      const strokes = built.animate(crankDeg, st.explode);
      const pulse = 0.3 + 0.25 * Math.sin(now / 200);
      for (const it of built.items) {
        const own = st.statuses[it.part] ?? "ok";
        const cylStatus = it.cyl ? st.statuses[`cyl${it.cyl}`] ?? "ok" : "ok";
        const rank = { ok: 0, info: 1, warn: 2, danger: 3 } as const;
        const status = rank[cylStatus] > rank[own] ? cylStatus : own;
        const isSel = st.selected === it.part;
        for (const m of it.mats) {
          if (status === "ok") {
            m.color.setHex(it.color);
            m.emissive.setHex(isSel ? 0x22d3ee : 0x000000);
            m.emissiveIntensity = isSel ? 0.45 : 0;
          } else {
            const c = STATUS_COLOR[status];
            m.color.setHex(c);
            m.emissive.setHex(c);
            m.emissiveIntensity = isSel ? 0.7 : status === "info" ? 0.2 : pulse;
          }
          const dim = st.selected && !isSel;
          m.opacity = it.housing ? (st.section ? (dim ? 0.25 : 1) : dim ? 0.08 : 0.22) : dim ? 0.18 : 1;
          m.depthWrite = !(it.housing && !st.section);
          m.clippingPlanes = it.housing && st.section ? [sectionPlane] : [];
        }
      }
      if (now - lastReport > 250) {
        const key = strokes.join(",");
        if (key !== lastStrokes) {
          cbRef.current.onStrokes(strokes);
          lastStrokes = key;
        }
        lastReport = now;
      }
      controls.update();
      renderer.render(scene, camera);
    });

    return () => {
      renderer.setAnimationLoop(null);
      ro.disconnect();
      io.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      scene.traverse((obj) => {
        const m = obj as THREE.Mesh;
        m.geometry?.dispose();
        const material = m.material as THREE.Material | THREE.Material[] | undefined;
        (Array.isArray(material) ? material : material ? [material] : []).forEach((x) => x.dispose());
      });
      envTex.dispose();
      pmrem.dispose();
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, cylinders]);

  return <div ref={mountRef} className="engine-scene" />;
}
