/**
 * Visor 3D de conjuntos mecánicos en detalle (frenos, suspensión, caja de cambios,
 * turbo, hélice, tren de aterrizaje, mandos de vuelo): animación de su funcionamiento,
 * despiece, corte en sección y colores por estado.
 *
 * Copia idéntica en dev/apps/garaje y dev/apps/bitacora: si cambias uno, cambia el otro.
 */
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export type Assembly = "brake" | "suspension" | "gearbox" | "turbo" | "propeller" | "landing_gear" | "flight_controls";
export type PartStatus = "ok" | "info" | "warn" | "danger";

type Props = {
  assembly: Assembly;
  statuses: Record<string, PartStatus>;
  selected: string | null;
  playing: boolean;
  speed: number;
  explode: number;
  section: boolean;
  onSelect: (id: string | null) => void;
  /** Texto de estado de la animación (marcha engranada, frenando…), ~4 veces por segundo. */
  onState?: (state: string) => void;
  onWebGLUnavailable: () => void;
};

const STATUS_COLOR: Record<Exclude<PartStatus, "ok">, number> = { info: 0x3b82f6, warn: 0xf59e0b, danger: 0xef4444 };

type Mat = { color: number; metalness: number; roughness: number };
const ALU: Mat = { color: 0xb9bfc7, metalness: 0.8, roughness: 0.35 };
const IRON: Mat = { color: 0x5f656d, metalness: 0.75, roughness: 0.45 };
const STEEL: Mat = { color: 0xd3d8de, metalness: 0.95, roughness: 0.2 };
const BLACK: Mat = { color: 0x22262c, metalness: 0.2, roughness: 0.6 };
const RUBBER: Mat = { color: 0x17191c, metalness: 0, roughness: 0.85 };
const RED: Mat = { color: 0xb91c1c, metalness: 0.3, roughness: 0.45 };
const YELLOW: Mat = { color: 0xeab308, metalness: 0.3, roughness: 0.45 };
const FRICTION: Mat = { color: 0x6b5b4b, metalness: 0.1, roughness: 0.95 };
const PAINT: Mat = { color: 0xf1f5f9, metalness: 0.1, roughness: 0.35 };
const WOOD: Mat = { color: 0x7c4a1e, metalness: 0.05, roughness: 0.55 };
const BLUE: Mat = { color: 0x1d4ed8, metalness: 0.1, roughness: 0.5 };
const BRASS: Mat = { color: 0xc8a24a, metalness: 0.9, roughness: 0.3 };

type Item = {
  obj: THREE.Object3D;
  part: string;
  housing: boolean;
  explode: THREE.Vector3;
  base: THREE.Vector3;
  mats: THREE.MeshStandardMaterial[];
  color: number;
  /** Desplazamiento animado (además de la base y la explosión). */
  offset: THREE.Vector3;
};

type Built = {
  items: Item[];
  animate: (t: number, dt: number, explode: number) => string;
  camera: THREE.Vector3;
  sectionNormal: THREE.Vector3;
};

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

function cyl(r: number, h: number, axis: "x" | "y" | "z" = "y", seg = 32, open = false, rTop?: number) {
  const g = new THREE.CylinderGeometry(rTop ?? r, r, h, seg, 1, open);
  if (axis === "x") g.rotateZ(Math.PI / 2);
  if (axis === "z") g.rotateX(Math.PI / 2);
  return g;
}

function tube(points: THREE.Vector3[], r: number, closed = false, seg = 64) {
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points, closed, "catmullrom", 0.4), seg, r, 10, closed);
}

/** Muelle helicoidal a lo largo de y, de altura h. */
function helix(radius: number, h: number, turns: number, wire: number) {
  const pts: THREE.Vector3[] = [];
  const steps = turns * 24;
  for (let i = 0; i <= steps; i++) {
    const a = (i / 24) * Math.PI * 2;
    pts.push(v(radius * Math.cos(a), (i / steps) * h - h / 2, radius * Math.sin(a)));
  }
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), steps * 2, wire, 8, false);
}

/** Rueda dentada simple: disco + dientes, eje a lo largo de x. */
function gear(r: number, w: number, teeth: number) {
  const g = new THREE.Group();
  g.add(new THREE.Mesh(cyl(r * 0.92, w, "x", 40)));
  for (let i = 0; i < teeth; i++) {
    const a = (i / teeth) * Math.PI * 2;
    const tooth = new THREE.Mesh(new THREE.BoxGeometry(w, r * 0.16, ((2 * Math.PI * r) / teeth) * 0.5));
    tooth.position.set(0, r * Math.cos(a), r * Math.sin(a));
    tooth.rotation.x = -a;
    g.add(tooth);
  }
  return g;
}

function bladeGeom(len: number, chordRoot: number, chordTip: number, twist: number) {
  // Pala de hélice: secciones de perfil a lo largo de y con torsión.
  const g = new THREE.BoxGeometry(0.02, len, 1, 1, 24, 1);
  const pos = g.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < pos.count; i++) {
    const y = pos.getY(i);
    const f = (y + len / 2) / len;
    const chord = chordRoot + (chordTip - chordRoot) * f;
    const z = pos.getZ(i) * chord;
    const x = pos.getX(i) * (1 - 0.6 * f);
    const a = twist * (1 - f);
    pos.setXYZ(i, x * Math.cos(a) - z * Math.sin(a), y + len / 2, x * Math.sin(a) + z * Math.cos(a));
  }
  g.computeVertexNormals();
  return g;
}

function makeBuilder(root: THREE.Group) {
  const items: Item[] = [];
  const add = (obj: THREE.Object3D, part: string, m: Mat, explode: THREE.Vector3, housing = false) => {
    const mats: THREE.MeshStandardMaterial[] = [];
    obj.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) {
        const mm = new THREE.MeshStandardMaterial({ color: m.color, metalness: m.metalness, roughness: m.roughness, transparent: true, side: THREE.DoubleSide });
        mesh.material = mm;
        mats.push(mm);
      }
    });
    root.add(obj);
    items.push({ obj, part, housing, explode, base: obj.position.clone(), mats, color: m.color, offset: v(0, 0, 0) });
    return obj;
  };
  const mesh = (g: THREE.BufferGeometry, pos?: THREE.Vector3, rot?: [number, number, number]) => {
    const m = new THREE.Mesh(g);
    if (pos) m.position.copy(pos);
    if (rot) m.rotation.set(...rot);
    return m;
  };
  const place = (explode: number) => {
    for (const it of items) it.obj.position.copy(it.base).add(it.offset).addScaledVector(it.explode, explode);
  };
  return { items, add, mesh, place };
}

// --- Frenos de disco (rueda delantera) ---------------------------------------
function buildBrake(root: THREE.Group): Built {
  const { items, add, mesh, place } = makeBuilder(root);
  const rot = new THREE.Group(); // lo que gira con la rueda
  const disc = new THREE.Group();
  disc.add(mesh(cyl(0.14, 0.008, "x", 64), v(0.012, 0, 0)));
  disc.add(mesh(cyl(0.14, 0.008, "x", 64), v(-0.012, 0, 0)));
  for (let i = 0; i < 36; i++) {
    const a = (i / 36) * Math.PI * 2;
    disc.add(mesh(new THREE.BoxGeometry(0.016, 0.04, 0.004), v(0, 0.115 * Math.cos(a), 0.115 * Math.sin(a)), [-a, 0, 0]));
  }
  disc.add(mesh(cyl(0.075, 0.045, "x", 48), v(0.03, 0, 0)));
  add(disc, "disc", IRON, v(0.12, 0, 0));
  const hub = new THREE.Group();
  hub.add(mesh(cyl(0.045, 0.06, "x"), v(0.03, 0, 0)));
  for (let i = 0; i < 4; i++) {
    const a = (i / 4) * Math.PI * 2;
    hub.add(mesh(cyl(0.006, 0.05, "x"), v(0.07, 0.05 * Math.cos(a), 0.05 * Math.sin(a))));
  }
  add(hub, "hub", STEEL, v(0.2, 0, 0));
  // Corona dentada del ABS y su sensor.
  const tone = new THREE.Group();
  tone.add(mesh(new THREE.TorusGeometry(0.055, 0.004, 6, 48).rotateY(Math.PI / 2), v(-0.03, 0, 0)));
  for (let i = 0; i < 44; i++) {
    const a = (i / 44) * Math.PI * 2;
    tone.add(mesh(new THREE.BoxGeometry(0.008, 0.006, 0.004), v(-0.03, 0.06 * Math.cos(a), 0.06 * Math.sin(a)), [-a, 0, 0]));
  }
  add(tone, "abs", STEEL, v(-0.08, 0, 0));
  [disc, hub, tone].forEach((o) => rot.add(o));
  root.add(rot);
  add(mesh(cyl(0.008, 0.05, "z"), v(-0.03, 0.075, 0.0), [0.3, 0, 0]), "abs", BLACK, v(-0.12, 0.08, 0));
  add(mesh(tube([v(-0.03, 0.1, 0.01), v(-0.08, 0.16, 0.05), v(-0.15, 0.2, 0.05)], 0.004)), "abs", BLACK, v(-0.12, 0.08, 0));
  // Pinza flotante arriba-detrás del disco: cuerpo, puente, pistón y dos pastillas.
  const cal = new THREE.Group();
  cal.position.set(0, 0.11, -0.06);
  cal.rotation.x = 0.5;
  root.add(cal);
  const caliperBody = mesh(new THREE.BoxGeometry(0.03, 0.06, 0.1), v(-0.035, 0, 0));
  const bridge = mesh(new THREE.BoxGeometry(0.1, 0.02, 0.1), v(0, 0.04, 0));
  const fingers = mesh(new THREE.BoxGeometry(0.018, 0.05, 0.09), v(0.035, 0.01, 0));
  const calGroup = new THREE.Group();
  calGroup.add(caliperBody, bridge, fingers);
  cal.add(calGroup);
  const calItem = add(calGroup, "caliper", RED, v(0, 0.12, 0));
  cal.add(calItem);
  const piston = mesh(cyl(0.02, 0.025, "x"), v(-0.021, 0, 0));
  cal.add(add(piston, "piston", STEEL, v(-0.08, 0.04, 0)));
  const padIn = new THREE.Group();
  padIn.add(mesh(new THREE.BoxGeometry(0.004, 0.045, 0.085), v(-0.006, 0, 0)), mesh(new THREE.BoxGeometry(0.002, 0.05, 0.09), v(-0.01, 0, 0)));
  padIn.position.set(-0.016, 0, 0);
  const padOut = new THREE.Group();
  padOut.add(mesh(new THREE.BoxGeometry(0.004, 0.045, 0.085), v(0.006, 0, 0)), mesh(new THREE.BoxGeometry(0.002, 0.05, 0.09), v(0.01, 0, 0)));
  padOut.position.set(0.016, 0, 0);
  cal.add(add(padIn, "pads", FRICTION, v(-0.06, 0.03, 0)));
  cal.add(add(padOut, "pads", FRICTION, v(0.06, 0.03, 0)));
  // Soporte de la pinza (fijo a la mangueta) y latiguillo hacia el chasis.
  add(mesh(new THREE.BoxGeometry(0.02, 0.03, 0.14), v(-0.05, 0.06, -0.08), [0.5, 0, 0]), "caliper", IRON, v(-0.06, 0, 0));
  add(mesh(tube([v(-0.05, 0.14, -0.1), v(-0.1, 0.2, -0.12), v(-0.18, 0.22, -0.05), v(-0.25, 0.25, 0)], 0.005)), "hydraulics", RUBBER, v(-0.1, 0.06, 0));
  // Neumático y llanta (contexto, semitransparentes en rayos X).
  add(mesh(new THREE.TorusGeometry(0.24, 0.07, 16, 64).rotateY(Math.PI / 2), v(0.07, 0, 0)), "wheel", RUBBER, v(0.35, 0, 0), true);
  add(mesh(cyl(0.19, 0.16, "x", 48, true), v(0.07, 0, 0)), "wheel", ALU, v(0.35, 0, 0), true);
  const discMats = items.find((i) => i.part === "disc")!.mats;
  let angle = 0;
  return {
    items,
    camera: v(-0.55, 0.3, 0.55),
    sectionNormal: v(-1, 0, 0),
    animate: (t, dt, explode) => {
      const cycle = t % 4;
      const pressure = cycle > 2 && cycle < 3.2 ? Math.min(1, (cycle - 2) * 4, (3.2 - cycle) * 4) : 0;
      angle += dt * (6 - 4.5 * pressure);
      rot.rotation.x = angle;
      items.find((i) => i.obj === piston)!.offset.set(0.003 * pressure - 0.003, 0, 0);
      items.find((i) => i.obj === padIn)!.offset.set(0.003 * pressure - 0.003, 0, 0);
      items.find((i) => i.obj === padOut)!.offset.set(-0.003 * pressure + 0.003, 0, 0);
      items.find((i) => i.obj === calGroup)!.offset.set(-0.003 * pressure + 0.003, 0, 0);
      place(explode);
      // El disco se calienta (rojo) mientras frena.
      for (const m of discMats) {
        if (m.emissive.getHex() === 0 || m.userData.heat) {
          m.emissive.setHex(0xff4500);
          m.emissiveIntensity = 0.5 * pressure;
          m.userData.heat = true;
        }
      }
      return pressure > 0.05 ? "Frenando: el pistón empuja la pastilla interior y la pinza flotante tira de la exterior" : "Rueda girando libre";
    },
  };
}

// --- Suspensión McPherson ------------------------------------------------------
function buildSuspension(root: THREE.Group): Built {
  const { items, add, mesh, place } = makeBuilder(root);
  const damper = new THREE.Group();
  damper.add(mesh(cyl(0.028, 0.3, "y", 32), v(0, 0.05, 0)));
  add(damper, "damper", { color: 0x1f2937, metalness: 0.6, roughness: 0.4 }, v(0, -0.05, 0.15), true);
  const rod = mesh(cyl(0.01, 0.22, "y"), v(0, 0.3, 0));
  add(rod, "damper", STEEL, v(0, 0.12, 0.15));
  const spring = mesh(helix(0.07, 0.24, 6, 0.007), v(0, 0.33, 0));
  add(spring, "spring", YELLOW, v(0, 0.12, -0.18));
  add(mesh(cyl(0.085, 0.008, "y", 40), v(0, 0.205, 0)), "spring", STEEL, v(0, 0.05, -0.12)); // platillo inferior
  const topMount = new THREE.Group();
  topMount.add(mesh(cyl(0.085, 0.02, "y", 40), v(0, 0.46, 0)), mesh(new THREE.TorusGeometry(0.05, 0.015, 10, 32).rotateX(Math.PI / 2), v(0, 0.48, 0)));
  add(topMount, "top_mount", BLACK, v(0, 0.35, 0));
  const knuckle = new THREE.Group();
  knuckle.add(mesh(new THREE.BoxGeometry(0.06, 0.18, 0.08), v(0.02, -0.17, 0)));
  knuckle.add(mesh(cyl(0.05, 0.06, "x"), v(0.07, -0.2, 0)));
  add(knuckle, "knuckle", IRON, v(0.12, -0.05, 0));
  const arm = new THREE.Group();
  arm.add(mesh(tube([v(0.02, -0.3, 0), v(-0.15, -0.3, 0.12), v(-0.33, -0.3, 0.12)], 0.016)));
  arm.add(mesh(tube([v(0.02, -0.3, 0), v(-0.2, -0.3, -0.14), v(-0.33, -0.3, -0.16)], 0.016)));
  add(arm, "arm", IRON, v(-0.08, -0.12, 0));
  const bushings = new THREE.Group();
  bushings.add(mesh(cyl(0.03, 0.05, "z"), v(-0.33, -0.3, 0.12)), mesh(cyl(0.03, 0.05, "x"), v(-0.33, -0.3, -0.16)));
  add(bushings, "bushings", RUBBER, v(-0.16, -0.12, 0));
  add(mesh(new THREE.SphereGeometry(0.025, 20, 14), v(0.02, -0.29, 0)), "ball_joint", STEEL, v(0.04, -0.2, 0));
  add(mesh(cyl(0.008, 0.2, "y"), v(-0.05, -0.08, 0.06)), "sway_link", STEEL, v(-0.1, 0, 0.12));
  add(mesh(tube([v(-0.05, -0.18, 0.06), v(-0.2, -0.2, 0.08), v(-0.45, -0.2, 0.0)], 0.012)), "sway_bar", BLACK, v(-0.16, -0.08, 0.1));
  add(mesh(new THREE.TorusGeometry(0.24, 0.07, 16, 64).rotateY(Math.PI / 2), v(0.16, -0.2, 0)), "wheel", RUBBER, v(0.3, 0, 0), true);
  const movers = [damper, knuckle, arm, bushings].map((o) => items.find((i) => i.obj === o)!);
  const ball = items.find((i) => i.part === "ball_joint")!;
  const wheel = items.filter((i) => i.part === "wheel");
  const link = items.find((i) => i.part === "sway_link")!;
  return {
    items,
    camera: v(0.95, 0.4, 1.3),
    sectionNormal: v(0, 0, -1),
    animate: (t, _dt, explode) => {
      // Baches: la rueda sube y el muelle y el amortiguador se comprimen.
      const bump = Math.max(0, Math.sin(t * 2.2)) ** 3 * 0.07 - 0.01;
      for (const it of movers) it.offset.set(0, bump, 0);
      ball.offset.set(0, bump, 0);
      link.offset.set(0, bump * 0.6, 0);
      wheel.forEach((w) => w.offset.set(0, bump, 0));
      spring.scale.y = 1 - (bump + 0.01) / 0.26;
      spring.position.y = 0.33 + (bump + 0.01) / 2;
      items.find((i) => i.obj === spring)!.base.y = 0.33 + (bump + 0.01) / 2;
      place(explode);
      return bump > 0.02 ? "Bache: el muelle absorbe el golpe y el amortiguador frena el rebote" : "Rodando en llano";
    },
  };
}

// --- Caja de cambios manual de 5 marchas con embrague ---------------------------
function buildGearbox(root: THREE.Group): Built {
  const { items, add, mesh, place } = makeBuilder(root);
  const xs = [-0.16, -0.08, 0, 0.08, 0.16];
  const ratios = [3.6, 2.0, 1.35, 1.0, 0.8];
  const rIn = [0.022, 0.034, 0.042, 0.048, 0.054];
  const input = new THREE.Group();
  input.add(mesh(cyl(0.012, 0.5, "x"), v(-0.02, 0, 0)));
  xs.forEach((x, i) => {
    const g = gear(rIn[i], 0.022, Math.round(rIn[i] * 400));
    g.position.set(x, 0, 0);
    input.add(g);
  });
  add(input, "shafts", STEEL, v(0, 0.12, 0));
  const output = new THREE.Group();
  output.position.set(0, -0.14, 0);
  output.add(mesh(cyl(0.014, 0.46, "x"), v(0, 0, 0)));
  const driven: THREE.Group[] = [];
  xs.forEach((x, i) => {
    const r = 0.14 - rIn[i] * 0.96;
    const g = gear(r, 0.022, Math.round(r * 400));
    g.position.set(x, 0, 0);
    output.add(g);
    driven.push(g);
  });
  const pinion = gear(0.026, 0.03, 11); // piñón de ataque hacia la corona del diferencial
  pinion.position.set(0.25, 0, 0);
  output.add(pinion);
  add(output, "shafts", STEEL, v(0, -0.12, 0));
  // Sincronizadores (1-2, 3-4, 5) entre piñones y horquillas que los desplazan.
  const synchroX = [-0.12, 0.04, 0.2];
  const synchros = synchroX.map((x) => {
    const s = new THREE.Group();
    s.add(mesh(cyl(0.05, 0.022, "x", 36, true)), mesh(new THREE.TorusGeometry(0.05, 0.004, 6, 36).rotateY(Math.PI / 2)));
    s.position.set(x, -0.14, 0);
    return add(s, "synchros", BRASS, v(0, -0.05, 0.1));
  });
  const forks = synchroX.map((x) => {
    const f = new THREE.Group();
    f.add(mesh(new THREE.TorusGeometry(0.055, 0.006, 6, 24, Math.PI).rotateY(Math.PI / 2).rotateX(Math.PI / 2), v(0, 0, 0)));
    f.add(mesh(new THREE.BoxGeometry(0.008, 0.11, 0.01), v(0, 0.07, 0.05)));
    f.position.set(x, -0.14, 0);
    return add(f, "forks", ALU, v(0, 0.05, 0.12));
  });
  add(mesh(cyl(0.007, 0.48, "x"), v(0, -0.07, 0.05)), "forks", STEEL, v(0, 0.05, 0.12));
  // Diferencial: corona y caja de satélites.
  const diff = new THREE.Group();
  diff.position.set(0.25, -0.26, 0);
  const crown = gear(0.1, 0.03, 44);
  diff.add(crown, mesh(new THREE.SphereGeometry(0.045, 20, 14)));
  add(diff, "differential", IRON, v(0.1, -0.15, 0));
  // Embrague: volante, disco y maza; cojinete de empuje.
  add(mesh(cyl(0.12, 0.02, "x", 48), v(-0.33, 0, 0)), "clutch", IRON, v(-0.2, 0, 0));
  const clutchDisc = mesh(cyl(0.1, 0.01, "x", 48), v(-0.305, 0, 0));
  add(clutchDisc, "clutch", FRICTION, v(-0.14, 0, 0));
  add(mesh(cyl(0.11, 0.03, "x", 48), v(-0.28, 0, 0)), "clutch", STEEL, v(-0.08, 0, 0));
  const bearing = mesh(cyl(0.03, 0.02, "x"), v(-0.25, 0, 0));
  add(bearing, "clutch", BLACK, v(-0.02, 0, 0));
  add(mesh(new THREE.BoxGeometry(0.62, 0.42, 0.3), v(-0.01, -0.07, 0)), "housing", ALU, v(0, 0, 0), true);
  const syncItems = synchros.map((s) => items.find((i) => i.obj === s)!);
  const forkItems = forks.map((f) => items.find((i) => i.obj === f)!);
  const bearingItem = items.find((i) => i.obj === bearing)!;
  const discItem = items.find((i) => i.obj === clutchDisc)!;
  // A qué sincronizador y hacia qué lado engrana cada marcha.
  const engage = [
    { s: 0, dir: -1 },
    { s: 0, dir: 1 },
    { s: 1, dir: -1 },
    { s: 1, dir: 1 },
    { s: 2, dir: -1 },
  ];
  let inAngle = 0;
  let outAngle = 0;
  return {
    items,
    camera: v(0.35, 0.45, 0.85),
    sectionNormal: v(0, 0, -1),
    animate: (t, dt, explode) => {
      const slot = Math.floor(t / 3) % 5;
      const local = t % 3;
      const shifting = local < 0.6;
      const gearIdx = slot;
      const k = shifting ? Math.min(1, local / 0.3) : 1; // la corona se desplaza al engranar
      syncItems.forEach((it, i) => it.offset.set(engage[gearIdx].s === i ? engage[gearIdx].dir * 0.025 * k : 0, 0, 0));
      forkItems.forEach((it, i) => it.offset.set(engage[gearIdx].s === i ? engage[gearIdx].dir * 0.025 * k : 0, 0, 0));
      bearingItem.offset.set(shifting ? 0.02 : 0, 0, 0);
      discItem.offset.set(shifting ? 0.006 : 0, 0, 0);
      inAngle += dt * 8;
      if (!shifting) outAngle += (dt * 8) / ratios[gearIdx];
      input.rotation.x = inAngle;
      output.rotation.x = -outAngle;
      driven.forEach((d, i) => (d.rotation.x = i === gearIdx ? 0 : -(inAngle * rIn[i]) / (0.14 - rIn[i] * 0.96) + outAngle));
      diff.rotation.x = outAngle * 0.26; // la corona gira más despacio que el piñón (reducción final)
      place(explode);
      return shifting ? `Pisando el embrague y metiendo ${gearIdx + 1}ª…` : `${gearIdx + 1}ª engranada (relación ${ratios[gearIdx].toFixed(2).replace(".", ",")}:1)`;
    },
  };
}

// --- Turbo de geometría variable --------------------------------------------------
function buildTurbo(root: THREE.Group): Built {
  const { items, add, mesh, place } = makeBuilder(root);
  const wheel = (blades: number, r: number, color: Mat, x: number, part: string, explodeX: number) => {
    const g = new THREE.Group();
    g.position.set(x, 0, 0);
    g.add(mesh(cyl(0.012, 0.04, "x", 24, false, 0.02)));
    for (let i = 0; i < blades; i++) {
      const a = (i / blades) * Math.PI * 2;
      const b = mesh(new THREE.BoxGeometry(0.035, r, 0.003), v(0, (r / 2) * Math.cos(a), (r / 2) * Math.sin(a)), [-a, 0.4, 0]);
      g.add(b);
    }
    return add(g, part, color, v(explodeX, 0, 0)) as THREE.Group;
  };
  const turbine = wheel(11, 0.04, IRON, -0.06, "turbine", -0.12);
  const compressor = wheel(12, 0.045, ALU, 0.06, "compressor", 0.12);
  const shaft = mesh(cyl(0.006, 0.14, "x"));
  add(shaft, "bearings", STEEL, v(0, 0.06, 0));
  add(mesh(cyl(0.03, 0.06, "x", 32)), "bearings", { color: 0x8b8f96, metalness: 0.7, roughness: 0.4 }, v(0, 0.06, 0), true);
  add(mesh(tube([v(0, 0.03, 0), v(0, 0.09, 0.02), v(0.02, 0.15, 0.04)], 0.005)), "oil_lines", STEEL, v(0, 0.12, 0));
  add(mesh(tube([v(0, -0.03, 0), v(0, -0.09, 0.01), v(-0.01, -0.14, 0.03)], 0.007)), "oil_lines", RUBBER, v(0, -0.12, 0));
  add(mesh(new THREE.TorusGeometry(0.065, 0.032, 16, 40).rotateY(Math.PI / 2), v(-0.075, 0, 0)), "turbine_housing", IRON, v(-0.18, 0, 0), true);
  add(mesh(new THREE.TorusGeometry(0.07, 0.03, 16, 40).rotateY(Math.PI / 2), v(0.075, 0, 0)), "compressor_housing", ALU, v(0.18, 0, 0), true);
  add(mesh(cyl(0.03, 0.06, "x", 32, true), v(0.13, 0, 0)), "compressor_housing", ALU, v(0.22, 0, 0), true);
  // Álabes de geometría variable alrededor de la turbina y actuador que los gira.
  const vanes = new THREE.Group();
  vanes.position.set(-0.075, 0, 0);
  const vaneMeshes: THREE.Mesh[] = [];
  for (let i = 0; i < 11; i++) {
    const a = (i / 11) * Math.PI * 2;
    const m = mesh(new THREE.BoxGeometry(0.01, 0.02, 0.003), v(0, 0.052 * Math.cos(a), 0.052 * Math.sin(a)));
    m.rotation.x = -a;
    vanes.add(m);
    vaneMeshes.push(m);
  }
  add(vanes, "vgt", STEEL, v(-0.13, 0.06, 0));
  const actuator = new THREE.Group();
  actuator.add(mesh(cyl(0.025, 0.05, "y"), v(-0.08, 0.13, 0.06)), mesh(cyl(0.004, 0.06, "y"), v(-0.08, 0.08, 0.06)));
  add(actuator, "actuator", BLACK, v(-0.12, 0.12, 0.06));
  let angle = 0;
  return {
    items,
    camera: v(0.25, 0.22, 0.42),
    sectionNormal: v(0, 0, -1),
    animate: (t, dt, explode) => {
      const load = 0.5 + 0.5 * Math.sin(t * 0.8);
      angle += dt * (25 + 40 * load);
      turbine.rotation.x = angle;
      compressor.rotation.x = angle;
      shaft.rotation.x = angle;
      vaneMeshes.forEach((m) => (m.rotation.z = 0.2 + 0.6 * (1 - load)));
      place(explode);
      return load > 0.6 ? "Mucha carga: álabes cerrados, más presión de soplado" : "Poca carga: álabes abiertos, menos contrapresión";
    },
  };
}

// --- Hélice (3 palas) ---------------------------------------------------------------
function buildPropeller(root: THREE.Group): Built {
  const { items, add, mesh, place } = makeBuilder(root);
  const rotor = new THREE.Group();
  root.add(rotor);
  const blades: THREE.Object3D[] = [];
  for (let i = 0; i < 3; i++) {
    const a = (i / 3) * Math.PI * 2;
    const holder = new THREE.Group();
    holder.rotation.x = a;
    const b = mesh(bladeGeom(0.8, 0.13, 0.07, 0.7), v(0, 0.08, 0));
    holder.add(b);
    rotor.add(holder);
    blades.push(add(holder, "blades", WOOD, v(0.0, 0, 0)));
  }
  blades.forEach((b) => rotor.add(b));
  const hub = new THREE.Group();
  hub.add(mesh(cyl(0.09, 0.03, "x", 40), v(0.02, 0, 0)), mesh(cyl(0.09, 0.03, "x", 40), v(-0.03, 0, 0)));
  rotor.add(add(hub, "hub", ALU, v(-0.1, 0, 0)));
  const bolts = new THREE.Group();
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    bolts.add(mesh(cyl(0.006, 0.09, "x"), v(0, 0.06 * Math.cos(a), 0.06 * Math.sin(a))));
  }
  rotor.add(add(bolts, "bolts", STEEL, v(-0.18, 0, 0)));
  rotor.add(add(mesh(new THREE.ConeGeometry(0.1, 0.22, 32).rotateZ(-Math.PI / 2), v(0.14, 0, 0)), "spinner", PAINT, v(0.25, 0, 0), true));
  add(mesh(cyl(0.07, 0.04, "x", 32), v(-0.08, 0, 0)), "flange", STEEL, v(-0.25, 0, 0));
  let angle = 0;
  return {
    items,
    camera: v(2.3, 0.8, 2.0),
    sectionNormal: v(0, 0, -1),
    animate: (_t, dt, explode) => {
      angle += dt * 4;
      rotor.rotation.x = explode > 0.05 ? 0 : angle;
      place(explode);
      // En despiece, las palas se separan radialmente desde el buje.
      blades.forEach((b) => {
        const child = b.children[0];
        child.position.y = 0.08 + explode * 0.25;
      });
      return "Girando: cada pala es un ala que «tira» hacia delante";
    },
  };
}

// --- Tren de aterrizaje (pata principal + delantera) ------------------------------
function buildLandingGear(root: THREE.Group): Built {
  const { items, add, mesh, place } = makeBuilder(root);
  const leg = mesh(tube([v(0, 0.35, 0), v(0.0, 0.2, 0.15), v(0, 0.02, 0.32)], 0.02));
  add(leg, "leg", STEEL, v(0, 0.08, -0.1));
  const wheelGroup = new THREE.Group();
  wheelGroup.position.set(0, -0.02, 0.38);
  root.add(wheelGroup);
  const tyre = mesh(new THREE.TorusGeometry(0.14, 0.055, 16, 48).rotateY(Math.PI / 2));
  const rim = mesh(cyl(0.11, 0.08, "x", 40));
  wheelGroup.add(add(tyre, "tyre", RUBBER, v(0, 0, 0.25)), add(rim, "wheel", ALU, v(0, 0, 0.2)));
  wheelGroup.add(add(mesh(cyl(0.012, 0.16, "x"), v(0, 0, 0)), "axle", STEEL, v(0, 0, 0.12)));
  wheelGroup.add(add(mesh(cyl(0.085, 0.006, "x", 40), v(-0.045, 0, 0)), "brake_disc", IRON, v(-0.08, 0, 0.18)));
  wheelGroup.add(add(mesh(new THREE.BoxGeometry(0.03, 0.04, 0.05), v(-0.05, 0.08, -0.02)), "brake_caliper", RED, v(-0.1, 0.06, 0.18)));
  add(mesh(tube([v(-0.05, 0.08, 0.36), v(-0.04, 0.2, 0.25), v(-0.02, 0.33, 0.05)], 0.004)), "brake_line", BLACK, v(-0.08, 0.06, 0.1));
  add(mesh(new THREE.SphereGeometry(0.19, 24, 16).scale(0.55, 0.75, 1.3), v(0, 0.0, 0.38)), "fairing", PAINT, v(0.3, 0, 0.3), true);
  // Pata delantera con amortiguador (muelle) y rueda.
  const noseSpring = mesh(helix(0.03, 0.15, 7, 0.005), v(0.75, 0.2, 0));
  add(noseSpring, "nose_leg", YELLOW, v(0, 0.1, 0));
  add(mesh(cyl(0.02, 0.32, "y"), v(0.75, 0.12, 0)), "nose_leg", STEEL, v(0, 0.05, 0));
  add(mesh(new THREE.TorusGeometry(0.11, 0.045, 14, 40).rotateY(Math.PI / 2), v(0.75, -0.06, 0)), "nose_leg", RUBBER, v(0, -0.05, 0));
  let angle = 0;
  return {
    items,
    camera: v(1.2, 0.5, 1.3),
    sectionNormal: v(0, 0, -1),
    animate: (t, dt, explode) => {
      const cycle = t % 4;
      const touchdown = cycle > 1 && cycle < 1.6 ? Math.sin(((cycle - 1) / 0.6) * Math.PI) : 0;
      angle += dt * (cycle > 1 ? 8 : 0);
      wheelGroup.rotation.x = angle;
      noseSpring.scale.y = 1 - 0.3 * touchdown;
      items.find((i) => i.part === "tyre")!.offset.set(0, 0, 0);
      leg.scale.set(1, 1 - 0.08 * touchdown, 1);
      place(explode);
      return touchdown > 0.1 ? "Toma: la ballesta y el amortiguador absorben el impacto" : cycle > 1 ? "Rodando" : "En el aire";
    },
  };
}

// --- Mandos de vuelo ------------------------------------------------------------------
function buildFlightControls(root: THREE.Group): Built {
  const { items, add, mesh, place } = makeBuilder(root);
  const stick = new THREE.Group();
  stick.position.set(0, 0, 0);
  stick.add(mesh(cyl(0.012, 0.5, "y"), v(0, 0.25, 0)), mesh(cyl(0.022, 0.1, "y"), v(0, 0.5, 0)));
  add(stick, "stick", BLACK, v(0, 0.1, 0));
  const pedals = [-0.18, 0.18].map((z) => {
    const p = mesh(new THREE.BoxGeometry(0.06, 0.12, 0.08), v(0.45, 0.05, z));
    return add(p, "pedals", ALU, v(0.1, 0, 0));
  });
  // Cables y poleas hacia alerones (alas) y hacia la cola.
  for (const s of [1, -1]) add(mesh(tube([v(0, 0.02, 0), v(-0.2, 0.05, s * 0.3), v(-0.25, 0.6, s * 0.5), v(-0.3, 0.75, s * 1.6)], 0.004)), "cables", STEEL, v(0, 0.05, s * 0.1));
  add(mesh(tube([v(0, 0.02, 0), v(-0.6, 0.05, 0.02), v(-2.2, 0.1, 0.0)], 0.004)), "cables", STEEL, v(0, -0.05, 0));
  add(mesh(tube([v(0.45, 0.05, 0.18), v(-0.6, 0.05, 0.1), v(-2.3, 0.3, 0.02)], 0.004)), "cables", STEEL, v(0, -0.05, 0.05));
  const pulleys = new THREE.Group();
  [v(-0.2, 0.05, 0.3), v(-0.2, 0.05, -0.3), v(-0.6, 0.05, 0.02)].forEach((p) => pulleys.add(mesh(cyl(0.03, 0.012, "z"), p)));
  add(pulleys, "pulleys", ALU, v(0, -0.08, 0));
  // Superficies: alerones (en el borde de salida de cada ala), profundidad y timón.
  const surface = (w: number, l: number, pos: THREE.Vector3, vertical = false) => {
    const g = new THREE.Group();
    g.position.copy(pos);
    const m = mesh(new THREE.BoxGeometry(w, 0.012, l), v(-w / 2, 0, 0));
    if (vertical) {
      g.rotation.x = Math.PI / 2;
    }
    g.add(m);
    return g;
  };
  const ailerons = [1, -1].map((s) => add(surface(0.22, 1.1, v(-0.3, 0.75, s * 2.1)), "ailerons", PAINT, v(0, 0.15, s * 0.2)));
  for (const s of [1, -1]) add(mesh(new THREE.BoxGeometry(0.7, 0.04, 2.0), v(0.05, 0.75, s * 1.6)), "wing", PAINT, v(0, 0.1, s * 0.1), true);
  const elevator = add(surface(0.25, 1.4, v(-2.35, 0.3, 0)), "elevator", PAINT, v(-0.15, 0.05, 0));
  add(mesh(new THREE.BoxGeometry(0.4, 0.03, 1.4), v(-2.0, 0.3, 0)), "tail", PAINT, v(0, 0, 0), true);
  const rudder = add(surface(0.25, 0.6, v(-2.4, 0.6, 0), true), "rudder", PAINT, v(-0.15, 0.1, 0));
  add(mesh(new THREE.BoxGeometry(0.45, 0.6, 0.03), v(-2.05, 0.6, 0)), "tail", PAINT, v(0, 0, 0), true);
  const trim = add(mesh(new THREE.BoxGeometry(0.06, 0.008, 0.3), v(-2.5, 0.3, 0.4)), "trim", BLUE, v(-0.1, 0, 0));
  return {
    items,
    camera: v(2.3, 2.1, 3.8),
    sectionNormal: v(0, -1, 0),
    animate: (t, _dt, explode) => {
      const roll = Math.sin(t * 1.1) * 0.35; // palanca a izquierda/derecha
      const pitch = Math.sin(t * 0.7) * 0.25; // palanca adelante/atrás
      const yaw = Math.sin(t * 0.9 + 1) * 0.35; // pedales
      stick.rotation.set(roll, 0, -pitch);
      ailerons[0].rotation.z = roll * 0.8;
      ailerons[1].rotation.z = -roll * 0.8;
      elevator.rotation.z = -pitch * 1.2;
      rudder.rotation.y = yaw;
      (rudder as THREE.Group).rotation.x = Math.PI / 2;
      pedals[0].position.x = 0.45 + yaw * 0.06;
      pedals[1].position.x = 0.45 - yaw * 0.06;
      items.find((i) => i.obj === pedals[0])!.base.x = 0.45 + yaw * 0.06;
      items.find((i) => i.obj === pedals[1])!.base.x = 0.45 - yaw * 0.06;
      trim.rotation.z = -pitch * 0.5;
      place(explode);
      const dir = roll > 0.1 ? "alabeo a la izquierda" : roll < -0.1 ? "alabeo a la derecha" : "alas niveladas";
      return `Palanca: ${dir}; ${pitch > 0.05 ? "morro abajo" : pitch < -0.05 ? "morro arriba" : "profundidad neutra"}`;
    },
  };
}

const BUILDERS: Record<Assembly, (root: THREE.Group) => Built> = {
  brake: buildBrake,
  suspension: buildSuspension,
  gearbox: buildGearbox,
  turbo: buildTurbo,
  propeller: buildPropeller,
  landing_gear: buildLandingGear,
  flight_controls: buildFlightControls,
};

export default function AssemblyScene({ assembly, statuses, selected, playing, speed, explode, section, onSelect, onState, onWebGLUnavailable }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef({ statuses, selected, playing, speed, explode, section });
  stateRef.current = { statuses, selected, playing, speed, explode, section };
  const cbRef = useRef({ onSelect, onState });
  cbRef.current = { onSelect, onState };

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
    const built = BUILDERS[assembly](root);
    const center = new THREE.Box3().setFromObject(root).getCenter(new THREE.Vector3());
    root.position.sub(center);
    const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 50);
    camera.position.copy(built.camera);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.minDistance = built.camera.length() * 0.35;
    controls.maxDistance = built.camera.length() * 3;
    const plane = new THREE.Plane(built.sectionNormal.clone(), 0);

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
    const meshes: { o: THREE.Object3D; it: Item }[] = [];
    for (const it of built.items) it.obj.traverse((o) => (o as THREE.Mesh).isMesh && meshes.push({ o, it }));
    let downAt: { x: number; y: number } | null = null;
    const pick = (ev: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(meshes.map((m) => m.o));
      for (const hit of hits) {
        const entry = meshes.find((m) => m.o === hit.object)!;
        if (entry.it.housing && hits.length > 1) continue;
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

    let simTime = 0;
    let last = performance.now();
    let lastReport = 0;
    let lastText = "";
    renderer.setAnimationLoop((now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (!visible) return;
      const st = stateRef.current;
      const step = st.playing ? dt * st.speed : 0;
      simTime += step;
      const text = built.animate(simTime, step, st.explode);
      const pulse = 0.3 + 0.25 * Math.sin(now / 200);
      for (const it of built.items) {
        const status = st.statuses[it.part] ?? "ok";
        const isSel = st.selected === it.part;
        for (const m of it.mats) {
          if (m.userData.heat && status === "ok") continue; // el disco gestiona su propio brillo
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
          m.opacity = it.housing ? (dim ? 0.08 : st.section ? 0.9 : 0.25) : dim ? 0.2 : 1;
          m.depthWrite = !it.housing;
          m.clippingPlanes = it.housing && st.section ? [plane] : [];
        }
      }
      if (now - lastReport > 250 && text !== lastText) {
        cbRef.current.onState?.(text);
        lastText = text;
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
  }, [assembly]);

  return <div ref={mountRef} className="engine-scene" />;
}
