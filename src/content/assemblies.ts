/** Conjuntos mecánicos en detalle (frenos, suspensión, caja de cambios, turbo):
 * fichas de cada pieza y palabras clave para asignarle las averías e incidencias. */
import type { Assembly } from "../components/AssemblyScene";

export type PartInfo = { name: string; what: string; fails: string; care: string; keywords?: string[] };

export type AssemblyInfo = {
  title: string;
  /** Pieza a la que va lo que no encaje con ninguna palabra clave. */
  fallback: string;
  parts: Record<string, PartInfo>;
};

export const ASSEMBLIES: Partial<Record<Assembly, AssemblyInfo>> = {
  brake: {
    title: "Frenos de disco",
    fallback: "pads",
    parts: {
      disc: {
        name: "Disco ventilado",
        what: "Gira con la rueda; las pastillas lo aprietan para frenar. Los delanteros suelen ser ventilados (dos caras con aletas en medio) para disipar el calor.",
        fails: "Desgaste por debajo del espesor mínimo, alabeo (vibración en el volante al frenar) o cristalización tras calentones.",
        care: "Medir el espesor en cada cambio de pastillas; se cambian por parejas en el mismo eje.",
        keywords: ["disco"],
      },
      pads: {
        name: "Pastillas",
        what: "Material de fricción pegado a una placa de acero que roza contra el disco.",
        fails: "Desgaste: chirrido del testigo metálico, testigo en el cuadro o frenada larga. Si se acaban, el metal raya el disco.",
        care: "Revisar el grosor en cada revisión (por debajo de unos 3 mm, cambiar).",
        keywords: ["pastilla"],
      },
      caliper: {
        name: "Pinza y soporte",
        what: "Pinza flotante: un pistón empuja la pastilla interior y el cuerpo, al deslizar sobre sus guías, arrastra la exterior.",
        fails: "Guías agarrotadas o pistón que no retrocede: el coche tira hacia un lado, una rueda se calienta o la pastilla se gasta en cuña.",
        care: "Limpiar y engrasar las guías al cambiar pastillas.",
        keywords: ["pinza", "guia", "guía"],
      },
      piston: {
        name: "Pistón",
        what: "La presión del líquido de frenos lo empuja contra la pastilla; un retén lo hace retroceder un poco al soltar.",
        fails: "Corrosión o retén dañado: fuga de líquido o pistón agarrotado.",
        care: "Cambiar el líquido de frenos según el plan: la humedad oxida el pistón por dentro.",
        keywords: ["piston", "pistón", "retén", "reten"],
      },
      hydraulics: {
        name: "Latiguillo y líquido de frenos",
        what: "El latiguillo flexible lleva el líquido desde el circuito del coche hasta la pinza; el líquido transmite la fuerza del pedal.",
        fails: "Líquido viejo (absorbe agua, hierve con frenadas fuertes): pedal esponjoso. Latiguillo agrietado o hinchado.",
        care: "Cambio de líquido cada pocos años (según el manual) y revisión visual de latiguillos.",
        keywords: ["latiguillo", "líquido de frenos", "liquido de frenos", "pedal"],
      },
      abs: {
        name: "Sensor ABS y corona",
        what: "El sensor lee los dientes de la corona para saber a qué velocidad gira cada rueda; el ABS lo usa para evitar el bloqueo.",
        fails: "Sensor sucio o cable roto: testigo de ABS/ESP y códigos C0035-C0050 (cada rueda tiene el suyo).",
        care: "Limpiar el sensor y la corona y revisar el cable antes de cambiar el sensor.",
        keywords: ["abs", "esp", "velocidad de rueda", "c00"],
      },
      hub: {
        name: "Buje y rodamiento",
        what: "Sujeta la rueda y la deja girar sobre el rodamiento.",
        fails: "Rodamiento gastado: zumbido que aumenta con la velocidad y cambia al girar.",
        care: "Atender pronto un zumbido nuevo de rueda.",
        keywords: ["rodamiento", "buje"],
      },
      wheel: {
        name: "Rueda",
        what: "Llanta y neumático: lo que realmente apoya en el suelo.",
        fails: "Desgaste, presión baja, cortes o bultos en el flanco.",
        care: "Presión en frío según la etiqueta de la puerta y profundidad mínima de 1,6 mm.",
        keywords: ["neumático", "neumatico", "rueda", "llanta", "presión"],
      },
    },
  },
  suspension: {
    title: "Suspensión McPherson",
    fallback: "damper",
    parts: {
      damper: {
        name: "Amortiguador",
        what: "Frena el movimiento del muelle (aceite que pasa por válvulas) para que la rueda no rebote.",
        fails: "Fugas de aceite, rebotes tras un bache, frenada más larga y peor estabilidad.",
        care: "Revisión visual de fugas; se cambian por parejas en el mismo eje.",
        keywords: ["amortiguador", "rebote"],
      },
      spring: {
        name: "Muelle",
        what: "Sostiene el peso del coche y absorbe los golpes.",
        fails: "Muelle roto (golpe seco, el coche más bajo de un lado), normalmente en la última espira.",
        care: "Revisar si el coche está más bajo de un lado.",
        keywords: ["muelle"],
      },
      top_mount: {
        name: "Copela",
        what: "Une la parte superior del amortiguador a la carrocería, con un cojinete que deja girar la dirección.",
        fails: "Golpeteo arriba al pasar baches o crujido al girar el volante en parado.",
        care: "Cambiarla a la vez que los amortiguadores.",
        keywords: ["copela"],
      },
      knuckle: {
        name: "Mangueta",
        what: "Pieza que une el amortiguador, el trapecio, la dirección y el buje de la rueda.",
        fails: "Daños tras un golpe fuerte contra un bordillo.",
        care: "Revisar la alineación tras un golpe.",
        keywords: ["mangueta"],
      },
      arm: {
        name: "Trapecio (brazo inferior)",
        what: "Une la parte de abajo de la mangueta al chasis y deja que la rueda suba y baje.",
        fails: "Doblado tras un golpe: el coche tira o desgasta el neumático por un lado.",
        care: "Alineación tras sustituirlo.",
        keywords: ["trapecio", "brazo"],
      },
      bushings: {
        name: "Silentblocks",
        what: "Gomas en las uniones del trapecio con el chasis: absorben vibraciones.",
        fails: "Gomas agrietadas: golpeteo, holguras y dirección imprecisa.",
        care: "Revisión visual en la ITV y en las revisiones.",
        keywords: ["silentblock", "goma"],
      },
      ball_joint: {
        name: "Rótula",
        what: "Articulación esférica entre el trapecio y la mangueta.",
        fails: "Holgura: golpeteo y dirección imprecisa; es un defecto grave en la ITV.",
        care: "Revisar holguras y el guardapolvos.",
        keywords: ["rótula", "rotula"],
      },
      sway_link: {
        name: "Bieleta de la estabilizadora",
        what: "Une la barra estabilizadora con el amortiguador.",
        fails: "Rótulas de la bieleta gastadas: «cloc-cloc» en baches pequeños.",
        care: "Es de las piezas que antes se gastan; barata de cambiar.",
        keywords: ["bieleta"],
      },
      sway_bar: {
        name: "Barra estabilizadora",
        what: "Barra de torsión que une las dos ruedas del eje para reducir el balanceo en curva.",
        fails: "Gomas de la barra gastadas: ruidos.",
        care: "Revisar las gomas de sujeción.",
        keywords: ["estabilizadora"],
      },
      wheel: {
        name: "Rueda",
        what: "Apoya en el suelo y transmite los baches a la suspensión.",
        fails: "Desequilibrio: vibración a cierta velocidad.",
        care: "Equilibrado al cambiar neumáticos.",
        keywords: ["neumático", "rueda", "equilibr"],
      },
    },
  },
  gearbox: {
    title: "Caja de cambios manual y embrague",
    fallback: "shafts",
    parts: {
      clutch: {
        name: "Embrague",
        what: "Volante, disco y maza: al pisar el pedal, el cojinete de empuje separa el disco y el motor deja de mover la caja.",
        fails: "Patina (el motor sube de vueltas sin acelerar el coche), pedal duro o que «muerde» muy arriba.",
        care: "No llevar el pie apoyado en el pedal ni sujetar el coche en cuesta con el embrague.",
        keywords: ["embrague", "volante", "bimasa"],
      },
      shafts: {
        name: "Ejes y piñones",
        what: "El eje primario recibe el giro del motor y el secundario lo entrega; cada pareja de piñones es una marcha con su relación.",
        fails: "Ruido en una marcha concreta o zumbido constante (rodamientos).",
        care: "Cambiar el aceite de la caja si el fabricante lo indica.",
        keywords: ["caja", "marcha", "piñón", "pinon", "rodamiento"],
      },
      synchros: {
        name: "Sincronizadores",
        what: "Igualan la velocidad de piñón y eje antes de engranar para que la marcha entre sin rascar.",
        fails: "Rasca al meter una marcha (a menudo 2ª): sincronizador gastado.",
        care: "Pisar el embrague a fondo y no forzar la palanca.",
        keywords: ["sincroniz", "rasca"],
      },
      forks: {
        name: "Horquillas",
        what: "Mueven los manguitos de los sincronizadores cuando mueves la palanca.",
        fails: "Holgura en la timonería: palanca imprecisa o marchas que saltan.",
        care: "Revisar la timonería y sus casquillos.",
        keywords: ["horquilla", "palanca", "timonería"],
      },
      differential: {
        name: "Diferencial",
        what: "La corona recibe el giro del piñón de ataque y deja que cada rueda gire a distinta velocidad en las curvas.",
        fails: "Ruido o golpe al girar a fondo, fugas por los retenes de los palieres.",
        care: "Revisar fugas de los retenes de los palieres.",
        keywords: ["diferencial", "palier"],
      },
      housing: {
        name: "Cárter de la caja",
        what: "Carcasa de aluminio con el aceite de la caja.",
        fails: "Fugas de aceite por juntas o retenes.",
        care: "Revisar manchas de aceite bajo la caja.",
        keywords: ["aceite de la caja", "fuga"],
      },
    },
  },
  turbo: {
    title: "Turbo de geometría variable",
    fallback: "turbine",
    parts: {
      turbine: {
        name: "Turbina",
        what: "Los gases de escape la hacen girar a muchísimas vueltas.",
        fails: "Daños por objetos o carbonilla; soporta temperaturas muy altas.",
        care: "Dejar el motor al ralentí unos segundos antes de pararlo tras un uso exigente.",
        keywords: ["turbina"],
      },
      compressor: {
        name: "Compresor",
        what: "En el mismo eje que la turbina: comprime el aire que entra al motor.",
        fails: "Silbido fuerte o pérdida de potencia si se dañan los álabes.",
        care: "Filtro de aire en buen estado (cualquier partícula daña el compresor).",
        keywords: ["compresor", "silbido"],
      },
      bearings: {
        name: "Eje y cojinetes",
        what: "Une turbina y compresor y gira sobre cojinetes lubricados por el aceite del motor.",
        fails: "Holgura del eje: humo azul y consumo de aceite.",
        care: "Aceite de calidad cambiado a tiempo; no acelerar a fondo en frío.",
        keywords: ["eje", "cojinete", "holgura", "humo azul"],
      },
      oil_lines: {
        name: "Tubos de aceite",
        what: "Llevan aceite a presión a los cojinetes y lo devuelven al cárter.",
        fails: "Obstrucción: el turbo se queda sin lubricar y se rompe.",
        care: "Cambiar los tubos si se cambia el turbo.",
        keywords: ["tubo de aceite"],
      },
      vgt: {
        name: "Geometría variable",
        what: "Álabes móviles alrededor de la turbina: se cierran a bajas vueltas para dar presión antes y se abren arriba.",
        fails: "Se agarrotan por la carbonilla: falta de presión (P0299) o sobrepresión (P0234) y modo de emergencia.",
        care: "Trayectos a buen ritmo de vez en cuando; existen limpiezas de geometría.",
        keywords: ["geometría", "geometria", "álabe", "alabe", "p0299", "p0234", "presión del turbo"],
      },
      actuator: {
        name: "Actuador",
        what: "Mueve la geometría variable, por vacío o eléctrico, siguiendo a la centralita.",
        fails: "Actuador o su sensor de posición averiado: códigos de control del turbo (P0045-P0048).",
        care: "Revisar los tubos de vacío si es neumático.",
        keywords: ["actuador", "p004"],
      },
      turbine_housing: {
        name: "Carcasa de la turbina",
        what: "Caracol de hierro que dirige los gases de escape hacia la turbina.",
        fails: "Grietas por calor o fugas en la junta con el colector.",
        care: "Revisar fugas de escape (ruido de «soplido»).",
      },
      compressor_housing: {
        name: "Carcasa del compresor",
        what: "Caracol de aluminio que recoge el aire comprimido y lo envía al intercooler.",
        fails: "Fugas en los manguitos de salida: pérdida de presión.",
        care: "Revisar abrazaderas y manguitos.",
        keywords: ["manguito"],
      },
    },
  },
};

/** Asigna cada aviso a la pieza cuyo nombre o palabras clave aparezcan en su texto. */
export function partForText(info: AssemblyInfo, text: string): string {
  const t = text.toLowerCase();
  for (const [id, p] of Object.entries(info.parts)) {
    if (p.keywords?.some((k) => t.includes(k.toLowerCase()))) return id;
  }
  return info.fallback;
}
