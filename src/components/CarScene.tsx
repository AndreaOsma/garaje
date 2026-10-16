import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export type PartStatus = "ok" | "info" | "warn" | "danger";
export type ViewMode = "xray" | "exterior";

type Props = {
  fuelType: string;
  statuses: Record<string, PartStatus>;
  selected: string | null;
  dark: boolean;
  reducedMotion: boolean;
  mode: ViewMode;
  bodyColor: string;
  onSelect: (id: string | null) => void;
  onWebGLUnavailable: () => void;
};

// Solo las piezas con problemas cambian de color; las sanas conservan su material real.
const STATUS_COLOR: Record<Exclude<PartStatus, "ok">, number> = {
  info: 0x3b82f6,
  warn: 0xf59e0b,
  danger: 0xef4444,
};

// Utilitario de 4 m: batalla 2,53 m, vía 1,52 m, rueda de 0,31 m de radio.
const FRONT_X = 1.27;
const REAR_X = -1.26;
const TRACK_Z = 0.76;
const WHEEL_R = 0.31;
const WHEELS: Array<[number, number]> = [
  [FRONT_X, TRACK_Z],
  [FRONT_X, -TRACK_Z],
  [REAR_X, TRACK_Z],
  [REAR_X, -TRACK_Z],
];

type Mat = { color: number; metalness?: number; roughness?: number };
const METAL: Mat = { color: 0x8a9099, metalness: 0.8, roughness: 0.35 };
const DARK_METAL: Mat = { color: 0x3a3f46, metalness: 0.7, roughness: 0.45 };
const PLASTIC: Mat = { color: 0x22262c, metalness: 0.1, roughness: 0.7 };
const RUBBER: Mat = { color: 0x16181b, metalness: 0, roughness: 0.9 };
const FABRIC: Mat = { color: 0x4b5563, metalness: 0, roughness: 0.95 };

type PartDef = { id: string; geom: THREE.BufferGeometry; pos: [number, number, number]; mat: Mat; rot?: [number, number, number] };
type Part = { id: string; mesh: THREE.Mesh; base: Mat };

function box(w: number, h: number, d: number, r = 0.02) {
  // Caja con aristas suavizadas (bisel) para que no parezca un bloque de juguete.
  const shape = new THREE.Shape();
  const x = w / 2 - r;
  const y = h / 2 - r;
  shape.moveTo(-x, -h / 2);
  shape.lineTo(x, -h / 2);
  shape.quadraticCurveTo(w / 2, -h / 2, w / 2, -y);
  shape.lineTo(w / 2, y);
  shape.quadraticCurveTo(w / 2, h / 2, x, h / 2);
  shape.lineTo(-x, h / 2);
  shape.quadraticCurveTo(-w / 2, h / 2, -w / 2, y);
  shape.lineTo(-w / 2, -y);
  shape.quadraticCurveTo(-w / 2, -h / 2, -x, -h / 2);
  const g = new THREE.ExtrudeGeometry(shape, { depth: Math.max(0.001, d - 2 * r), bevelEnabled: true, bevelSize: r, bevelThickness: r, bevelSegments: 2, curveSegments: 4 });
  g.translate(0, 0, -(d - 2 * r) / 2);
  return g;
}

function cylinder(r: number, len: number, axis: "x" | "y" | "z" = "y", segments = 28) {
  const g = new THREE.CylinderGeometry(r, r, len, segments);
  if (axis === "z") g.rotateX(Math.PI / 2);
  if (axis === "x") g.rotateZ(Math.PI / 2);
  return g;
}

// --- Carrocería -------------------------------------------------------------

function lowerBodyShape() {
  const s = new THREE.Shape();
  const archR = 0.4;
  s.moveTo(-2.0, 0.32);
  s.lineTo(REAR_X - archR, 0.32);
  s.absarc(REAR_X, WHEEL_R, archR, Math.PI, 0, true);
  s.lineTo(FRONT_X - archR, 0.32);
  s.absarc(FRONT_X, WHEEL_R, archR, Math.PI, 0, true);
  s.lineTo(2.02, 0.32);
  s.quadraticCurveTo(2.11, 0.45, 2.07, 0.63);
  s.quadraticCurveTo(2.0, 0.8, 1.78, 0.85);
  s.quadraticCurveTo(1.3, 0.92, 0.86, 0.97);
  s.lineTo(-1.8, 1.0);
  s.quadraticCurveTo(-2.04, 0.99, -2.06, 0.72);
  s.quadraticCurveTo(-2.07, 0.45, -2.0, 0.32);
  return s;
}

function greenhouseShape() {
  const s = new THREE.Shape();
  s.moveTo(0.86, 0.96);
  s.quadraticCurveTo(0.45, 1.25, 0.06, 1.39);
  s.quadraticCurveTo(-0.6, 1.45, -1.32, 1.42);
  s.quadraticCurveTo(-1.7, 1.25, -1.82, 0.99);
  s.lineTo(0.86, 0.96);
  return s;
}

function roofShape() {
  const s = new THREE.Shape();
  s.moveTo(0.1, 1.37);
  s.quadraticCurveTo(-0.6, 1.47, -1.34, 1.43);
  s.lineTo(-1.36, 1.39);
  s.quadraticCurveTo(-0.6, 1.42, 0.08, 1.34);
  s.lineTo(0.1, 1.37);
  return s;
}

function extrude(shape: THREE.Shape, width: number, bevel: number) {
  const g = new THREE.ExtrudeGeometry(shape, { depth: width - 2 * bevel, bevelEnabled: true, bevelSize: bevel, bevelThickness: bevel, bevelSegments: 6, curveSegments: 28 });
  g.translate(0, 0, -(width - 2 * bevel) / 2);
  g.computeVertexNormals();
  return g;
}

type Body = {
  group: THREE.Group;
  paint: THREE.MeshPhysicalMaterial;
  glass: THREE.MeshPhysicalMaterial;
  edges: THREE.LineSegments[];
};

function buildBody(): Body {
  const group = new THREE.Group();
  const paint = new THREE.MeshPhysicalMaterial({ color: 0x8aa2b8, metalness: 0.55, roughness: 0.32, clearcoat: 1, clearcoatRoughness: 0.08, transparent: true });
  const glass = new THREE.MeshPhysicalMaterial({ color: 0x1e293b, metalness: 0.4, roughness: 0.04, clearcoat: 1, transparent: true, opacity: 0.85, depthWrite: false });
  const lower = extrude(lowerBodyShape(), 1.72, 0.14);
  const house = extrude(greenhouseShape(), 1.42, 0.07);
  const roof = extrude(roofShape(), 1.44, 0.04);
  const edges: THREE.LineSegments[] = [];
  for (const [geom, mat] of [[lower, paint], [roof, paint], [house, glass]] as const) {
    const mesh = new THREE.Mesh(geom, mat);
    mesh.castShadow = true;
    group.add(mesh);
    const e = new THREE.LineSegments(new THREE.EdgesGeometry(geom, 28), new THREE.LineBasicMaterial({ transparent: true }));
    group.add(e);
    edges.push(e);
  }
  // Montantes A, B y C (pintados): unen techo y carrocería como en un coche real.
  const beam = (x1: number, y1: number, x2: number, y2: number, z: number, t: number) => {
    const len = Math.hypot(x2 - x1, y2 - y1);
    const m = new THREE.Mesh(box(len + 0.04, t, 0.05, 0.015), paint);
    m.position.set((x1 + x2) / 2, (y1 + y2) / 2, z);
    m.rotation.z = Math.atan2(y2 - y1, x2 - x1);
    m.castShadow = true;
    return m;
  };
  for (const z of [0.7, -0.7]) {
    group.add(beam(0.86, 0.97, 0.06, 1.39, z, 0.07), beam(-0.55, 1.0, -0.58, 1.44, z, 0.09), beam(-1.34, 1.42, -1.82, 0.99, z, 0.14));
  }
  // Detalles: faros, pilotos, calandra y retrovisores.
  const lamp = new THREE.MeshStandardMaterial({ color: 0xf1f5f9, emissive: 0xfff7d6, emissiveIntensity: 0.6, roughness: 0.1 });
  const tail = new THREE.MeshStandardMaterial({ color: 0x7f1d1d, emissive: 0xdc2626, emissiveIntensity: 0.5, roughness: 0.2 });
  const trim = new THREE.MeshStandardMaterial({ color: 0x111418, roughness: 0.6 });
  for (const z of [0.56, -0.56]) {
    const h = new THREE.Mesh(box(0.08, 0.1, 0.32, 0.03), lamp);
    h.position.set(2.03, 0.7, z);
    h.rotation.z = -0.35;
    const t = new THREE.Mesh(box(0.05, 0.16, 0.24, 0.02), tail);
    t.position.set(-2.05, 0.85, z * 1.08);
    const m = new THREE.Mesh(box(0.14, 0.09, 0.16, 0.03), trim);
    m.position.set(0.72, 1.02, z > 0 ? 0.93 : -0.93);
    group.add(h, t, m);
  }
  const grille = new THREE.Mesh(box(0.03, 0.14, 0.78, 0.02), trim);
  grille.position.set(2.09, 0.5, 0);
  group.add(grille);
  return { group, paint, glass, edges };
}

function wheel(x: number, z: number): THREE.Group {
  const g = new THREE.Group();
  // Neumático: perfil de sección redondeada girado (no un donut).
  const pts: THREE.Vector2[] = [];
  const w = 0.2;
  const inner = 0.21;
  for (let i = 0; i <= 16; i++) {
    const a = (i / 16) * Math.PI;
    pts.push(new THREE.Vector2(inner + 0.1 * Math.sin(a) + 0.0, (w / 2) * Math.cos(a)));
  }
  const tyreGeom = new THREE.LatheGeometry(pts, 48);
  tyreGeom.rotateX(Math.PI / 2);
  const tyre = new THREE.Mesh(tyreGeom, new THREE.MeshStandardMaterial({ color: RUBBER.color, roughness: 0.9 }));
  tyre.castShadow = true;
  const rimMat = new THREE.MeshStandardMaterial({ color: 0xc0c6cf, metalness: 0.9, roughness: 0.25 });
  const rim = new THREE.Mesh(cylinder(0.2, 0.16, "z", 40), rimMat);
  const outer = z > 0 ? 1 : -1;
  const hub = new THREE.Group();
  for (let i = 0; i < 5; i++) {
    const spoke = new THREE.Mesh(box(0.035, 0.17, 0.03, 0.008), rimMat);
    spoke.position.set(0, 0.085, 0);
    const holder = new THREE.Group();
    holder.rotation.z = (i / 5) * Math.PI * 2;
    holder.add(spoke);
    hub.add(holder);
  }
  hub.position.z = outer * 0.09;
  const cap = new THREE.Mesh(cylinder(0.045, 0.04, "z"), rimMat);
  cap.position.z = outer * 0.1;
  const dish = new THREE.Mesh(cylinder(0.205, 0.02, "z", 40), new THREE.MeshStandardMaterial({ color: 0x1f2329, roughness: 0.6 }));
  dish.position.z = -outer * 0.03;
  g.add(tyre, rim, hub, cap, dish);
  g.position.set(x, WHEEL_R, z);
  g.name = "tyres";
  return g;
}

// --- Piezas -----------------------------------------------------------------

function partsFor(fuelType: string): PartDef[] {
  const combustion = fuelType !== "electric";
  const electrified = ["electric", "hybrid", "phev"].includes(fuelType);
  const list: PartDef[] = [
    { id: "cooling", geom: box(0.05, 0.42, 1.18, 0.02), pos: [1.95, 0.56, 0], mat: { color: 0x9ca3af, metalness: 0.6, roughness: 0.5 } },
    { id: "battery", geom: box(0.26, 0.19, 0.17, 0.015), pos: [1.5, 0.76, -0.55], mat: PLASTIC },
    { id: "ecu", geom: box(0.18, 0.05, 0.15, 0.01), pos: [1.0, 0.9, -0.5], mat: { color: 0x9ca3af, metalness: 0.7, roughness: 0.4 } },
    // Habitáculo: salpicadero, volante y asientos.
    { id: "cabin", geom: box(0.28, 0.24, 1.42, 0.06), pos: [0.66, 0.86, 0], mat: PLASTIC },
    { id: "cabin", geom: new THREE.TorusGeometry(0.17, 0.02, 10, 32), pos: [0.42, 0.98, 0.36], mat: PLASTIC, rot: [0, Math.PI / 2, -0.35] },
    ...[0.36, -0.36].flatMap<PartDef>((z) => [
      { id: "cabin", geom: box(0.5, 0.12, 0.5, 0.05), pos: [-0.05, 0.52, z], mat: FABRIC },
      { id: "cabin", geom: box(0.12, 0.6, 0.5, 0.05), pos: [-0.33, 0.85, z], mat: FABRIC, rot: [0, 0, 0.18] },
    ]),
    { id: "cabin", geom: box(0.5, 0.12, 1.3, 0.05), pos: [-1.05, 0.55, 0], mat: FABRIC },
    { id: "cabin", geom: box(0.12, 0.55, 1.3, 0.05), pos: [-1.32, 0.86, 0], mat: FABRIC, rot: [0, 0, 0.12] },
  ];
  if (combustion) {
    list.push(
      // Motor transversal: bloque, culata, tapa de balancines y correa.
      { id: "engine", geom: box(0.5, 0.36, 0.62, 0.04), pos: [1.36, 0.56, 0], mat: DARK_METAL },
      { id: "engine", geom: box(0.4, 0.12, 0.6, 0.03), pos: [1.33, 0.8, 0], mat: METAL },
      { id: "engine", geom: box(0.3, 0.05, 0.52, 0.02), pos: [1.33, 0.88, 0], mat: PLASTIC },
      { id: "engine", geom: new THREE.TorusGeometry(0.12, 0.012, 8, 28), pos: [1.42, 0.6, 0.33], mat: RUBBER },
      { id: "injection", geom: cylinder(0.022, 0.5, "z"), pos: [1.2, 0.86, 0], mat: METAL },
      { id: "intake", geom: box(0.3, 0.14, 0.32, 0.04), pos: [1.58, 0.87, 0.52], mat: PLASTIC },
      { id: "intake", geom: cylinder(0.05, 0.3, "x"), pos: [1.4, 0.88, 0.42], mat: PLASTIC },
      { id: "gearbox", geom: box(0.34, 0.3, 0.3, 0.05), pos: [1.3, 0.48, 0.5], mat: { color: 0xa3a3a3, metalness: 0.7, roughness: 0.45 } },
      // Escape: colector, catalizador/FAP, tubo y silencioso.
      { id: "exhaust", geom: cylinder(0.045, 2.75, "x"), pos: [-0.45, 0.22, 0.22], mat: METAL },
      { id: "exhaust", geom: cylinder(0.1, 0.42, "x"), pos: [0.78, 0.22, 0.22], mat: METAL },
      { id: "exhaust", geom: cylinder(0.12, 0.42, "x"), pos: [-1.68, 0.24, 0.24], mat: METAL },
      { id: "fuel_tank", geom: box(0.55, 0.2, 0.95, 0.06), pos: [-0.8, 0.3, -0.1], mat: PLASTIC }
    );
  }
  if (fuelType === "diesel") {
    list.push(
      { id: "turbo", geom: new THREE.TorusGeometry(0.075, 0.04, 12, 24), pos: [1.16, 0.62, -0.42], mat: METAL },
      { id: "turbo", geom: cylinder(0.05, 0.12, "z"), pos: [1.16, 0.62, -0.42], mat: METAL },
      { id: "egr", geom: box(0.13, 0.1, 0.13, 0.02), pos: [1.08, 0.86, 0.26], mat: METAL }
    );
  }
  if (electrified) {
    list.push(
      { id: "hv_battery", geom: box(fuelType === "electric" ? 2.2 : 0.8, 0.12, 1.3, 0.03), pos: fuelType === "electric" ? [0, 0.2, 0] : [-0.9, 0.45, 0], mat: { color: 0x334155, metalness: 0.5, roughness: 0.5 } },
      { id: "emotor", geom: cylinder(0.17, 0.32, "z"), pos: fuelType === "electric" ? [REAR_X, 0.34, 0] : [1.0, 0.45, -0.1], mat: METAL }
    );
    if (fuelType === "electric") list.push({ id: "gearbox", geom: box(0.3, 0.26, 0.3, 0.04), pos: [REAR_X, 0.34, 0.3], mat: METAL });
  }
  for (const [x, z] of WHEELS) {
    const inner = z > 0 ? z - 0.16 : z + 0.16;
    list.push(
      { id: "brakes", geom: cylinder(0.17, 0.025, "z", 36), pos: [x, WHEEL_R, inner], mat: { color: 0x9aa1aa, metalness: 0.85, roughness: 0.35 } },
      { id: "brakes", geom: box(0.09, 0.12, 0.07, 0.015), pos: [x - 0.1, WHEEL_R + 0.12, inner + (z > 0 ? -0.02 : 0.02)], mat: { color: 0xb91c1c, metalness: 0.3, roughness: 0.5 } },
      { id: "suspension", geom: cylinder(0.035, 0.46, "y"), pos: [x, 0.66, z > 0 ? z - 0.26 : z + 0.26], mat: METAL },
      { id: "suspension", geom: new THREE.TorusGeometry(0.06, 0.012, 6, 18), pos: [x, 0.74, z > 0 ? z - 0.26 : z + 0.26], mat: METAL, rot: [Math.PI / 2, 0, 0] }
    );
  }
  return list;
}

/** Escena three.js del gemelo digital. Se carga bajo demanda (chunk aparte). */
export default function CarScene({ fuelType, statuses, selected, dark, reducedMotion, mode, bodyColor, onSelect, onWebGLUnavailable }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef({ statuses, selected, dark, reducedMotion, mode, bodyColor });
  stateRef.current = { statuses, selected, dark, reducedMotion, mode, bodyColor };
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

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
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(renderer);
    const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envTex;

    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 60);
    camera.position.set(4.6, 2.2, 4.6);
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(3, 6, 2.5);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    sun.shadow.camera.left = -3;
    sun.shadow.camera.right = 3;
    sun.shadow.camera.top = 3;
    sun.shadow.camera.bottom = -3;
    sun.shadow.radius = 6;
    scene.add(sun, new THREE.HemisphereLight(0xffffff, 0x334455, 0.35));

    const car = new THREE.Group();
    car.position.y = -0.7;
    scene.add(car);
    const body = buildBody();
    car.add(body.group);

    const parts: Part[] = [];
    const tyres: THREE.Mesh[] = [];
    for (const [x, z] of WHEELS) {
      const w = wheel(x, z);
      car.add(w);
      w.traverse((o) => {
        if ((o as THREE.Mesh).isMesh && (o as THREE.Mesh).geometry.type === "LatheGeometry") tyres.push(o as THREE.Mesh);
      });
    }
    tyres.forEach((t) => parts.push({ id: "tyres", mesh: t, base: RUBBER }));
    for (const def of partsFor(fuelType)) {
      const mesh = new THREE.Mesh(def.geom, new THREE.MeshStandardMaterial({ color: def.mat.color, metalness: def.mat.metalness ?? 0.2, roughness: def.mat.roughness ?? 0.5, transparent: true }));
      mesh.position.set(...def.pos);
      if (def.rot) mesh.rotation.set(...def.rot);
      mesh.castShadow = true;
      car.add(mesh);
      parts.push({ id: def.id, mesh, base: def.mat });
    }
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(14, 14), new THREE.ShadowMaterial({ opacity: 0.22 }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.7;
    ground.receiveShadow = true;
    scene.add(ground);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.minDistance = 3.4;
    controls.maxDistance = 10;
    controls.minPolarAngle = 0.25;
    controls.maxPolarAngle = Math.PI / 2 - 0.04;
    controls.target.set(0, -0.05, 0);
    controls.autoRotateSpeed = 0.5;

    const resize = () => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(mount);
    resize();

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let downAt: { x: number; y: number } | null = null;
    const pick = (ev: PointerEvent) => {
      // Solo las piezas visibles (en «Exterior», ruedas, frenos y suspensión).
      const visibleParts = parts.filter((p) => p.mesh.visible);
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(visibleParts.map((p) => p.mesh))[0];
      return hit ? visibleParts.find((p) => p.mesh === hit.object)?.id ?? null : null;
    };
    const onDown = (ev: PointerEvent) => (downAt = { x: ev.clientX, y: ev.clientY });
    const onUp = (ev: PointerEvent) => {
      if (downAt && Math.hypot(ev.clientX - downAt.x, ev.clientY - downAt.y) < 6) onSelectRef.current(pick(ev));
      downAt = null;
    };
    const onMove = (ev: PointerEvent) => {
      renderer.domElement.style.cursor = pick(ev) ? "pointer" : "grab";
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);

    let visible = true;
    const io = new IntersectionObserver(([entry]) => (visible = entry.isIntersecting));
    io.observe(mount);

    const clock = new THREE.Clock();
    renderer.setAnimationLoop(() => {
      if (!visible) return;
      const { statuses: st, selected: sel, dark: dk, reducedMotion: rm, mode: md, bodyColor: bc } = stateRef.current;
      const t = clock.getElapsedTime();
      const xray = md === "xray";
      controls.autoRotate = !rm && !sel;

      // Carrocería: pintada en exterior, cristal en rayos X.
      body.paint.color.set(xray ? (dk ? 0x9fdcff : 0x0e7490) : bc);
      body.paint.opacity = xray ? 0.07 : 1;
      body.paint.depthWrite = !xray;
      body.glass.opacity = xray ? 0.05 : 0.85;
      const bodyStatus = st.body ?? "ok";
      for (const e of body.edges) {
        const m = e.material as THREE.LineBasicMaterial;
        m.color.setHex(bodyStatus === "ok" ? (dk ? 0x67e8f9 : 0x0e7490) : STATUS_COLOR[bodyStatus]);
        m.opacity = xray ? (sel === "body" ? 0.95 : 0.45) : 0;
      }

      for (const { id, mesh, base } of parts) {
        const status = st[id] ?? "ok";
        const mat = mesh.material as THREE.MeshStandardMaterial;
        const always = id === "tyres" || id === "brakes" || id === "suspension";
        mesh.visible = xray || always;
        if (status === "ok") {
          mat.color.setHex(base.color);
          mat.emissive.setHex(0x000000);
          mat.emissiveIntensity = 0;
        } else {
          const c = STATUS_COLOR[status];
          mat.color.setHex(c);
          mat.emissive.setHex(c);
          mat.emissiveIntensity = status === "info" ? 0.25 : rm ? 0.45 : 0.3 + 0.25 * Math.sin(t * (status === "danger" ? 5 : 3));
        }
        const isSel = sel === id;
        if (isSel) {
          mat.emissive.setHex(status === "ok" ? 0x22d3ee : STATUS_COLOR[status]);
          mat.emissiveIntensity = 0.6;
        }
        mat.opacity = sel && !isSel ? 0.22 : 1;
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
      renderer.domElement.removeEventListener("pointermove", onMove);
      scene.traverse((obj) => {
        const m = obj as THREE.Mesh;
        m.geometry?.dispose();
        const mat = m.material as THREE.Material | THREE.Material[] | undefined;
        (Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((x) => x.dispose());
      });
      envTex.dispose();
      pmrem.dispose();
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    };
    // La escena se reconstruye solo si cambia el tipo de motor; el resto se lee en cada frame.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fuelType]);

  return <div ref={mountRef} className="car-scene" />;
}
