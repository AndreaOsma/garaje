/** Fichas de las piezas del motor de combustión (visor «Motor por dentro»).
 * Información general: los valores e intervalos concretos los marca el manual de cada coche. */

export type EnginePartInfo = {
  name: string;
  what: string;
  fails: string;
  care: string;
  dieselOnly?: boolean;
  gasolineOnly?: boolean;
};

export const ENGINE_PARTS: Record<string, EnginePartInfo> = {
  block: {
    name: "Bloque y cilindros",
    what: "La pieza base del motor: aloja los cilindros por los que suben y bajan los pistones y los conductos de aceite y refrigerante. Lleva el sensor de picado.",
    fails: "Rara vez falla por sí mismo; sus problemas suelen venir de un sobrecalentamiento (deformaciones) o de falta de aceite (rayado de cilindros).",
    care: "Aceite y refrigerante en buen estado y a su nivel; no forzar el motor en frío.",
  },
  head: {
    name: "Culata",
    what: "Cierra los cilindros por arriba y forma la cámara de combustión. Aloja las válvulas, los árboles de levas y las bujías o inyectores.",
    fails: "Junta de culata quemada tras un sobrecalentamiento: humo blanco, pérdida de refrigerante, burbujas en el vaso de expansión, aceite «mayonesa».",
    care: "Vigilar la temperatura y el nivel de refrigerante; ante un calentón, parar el motor cuanto antes.",
  },
  pistons: {
    name: "Pistones y segmentos",
    what: "Reciben la presión de la combustión y la transmiten a la biela. Los segmentos (aros) sellan la cámara y rascan el aceite de la pared del cilindro.",
    fails: "Segmentos gastados: consumo de aceite, humo azulado, pérdida de compresión. Un fallo de encendido continuado puede dañar el pistón y el catalizador.",
    care: "Cambios de aceite a tiempo con el aceite correcto; no dejar sin atender un fallo de encendido.",
  },
  conrods: {
    name: "Bielas",
    what: "Unen cada pistón con el cigüeñal y convierten el movimiento de subida y bajada en giro.",
    fails: "Cojinetes de biela desgastados por falta de aceite: golpeteo metálico que aumenta con las revoluciones. Es una avería grave.",
    care: "Presión y nivel de aceite correctos; atender de inmediato el testigo de presión de aceite.",
  },
  crank: {
    name: "Cigüeñal",
    what: "Eje que recibe el empuje de las cuatro bielas y lo convierte en giro; sus contrapesos equilibran el motor. En un 4 en línea los cilindros 1 y 4 suben a la vez, y el 2 y el 3 también.",
    fails: "Desgaste de apoyos por mala lubricación; retenes que pierden aceite.",
    care: "El mismo cuidado que las bielas: aceite correcto y a tiempo.",
  },
  camshaft: {
    name: "Árboles de levas",
    what: "Giran a la mitad de vueltas que el cigüeñal y abren las válvulas en el momento justo. Este motor es de 16 válvulas, con un árbol para la admisión y otro para el escape.",
    fails: "Desgaste de levas por aceite viejo; fallos del sistema de distribución variable (códigos P0010-P0015).",
    care: "Aceite de la especificación correcta (los sistemas de distribución variable son sensibles a la viscosidad).",
  },
  valves: {
    name: "Válvulas",
    what: "Dos de admisión dejan entrar el aire (o la mezcla) y dos de escape dejan salir los gases en cada cilindro. Sus muelles las cierran.",
    fails: "Válvulas quemadas o que no cierran bien: pérdida de compresión y fallos de encendido en un cilindro. Si se rompe la distribución pueden chocar con los pistones.",
    care: "Respetar el cambio de la correa o cadena de distribución.",
  },
  timing: {
    name: "Distribución (correa)",
    what: "Sincroniza el cigüeñal con los árboles de levas: por cada dos vueltas del cigüeñal, una vuelta de las levas. Suele mover también la bomba de agua.",
    fails: "Si la correa se rompe o salta un diente, el motor se para y en la mayoría de motores las válvulas chocan con los pistones (avería muy cara).",
    care: "Cambiar el kit (correa, tensor, rodillos y normalmente la bomba de agua) en el intervalo del fabricante, por km o por años, lo que llegue antes.",
  },
  flywheel: {
    name: "Volante motor",
    what: "Disco pesado que suaviza el giro del cigüeñal y sobre el que trabaja el embrague. Su corona sirve para el motor de arranque.",
    fails: "Los volantes bimasa (habituales en diésel) se desgastan: vibraciones y ruido al arrancar o parar, sobre todo a bajas vueltas.",
    care: "No circular a muy pocas revoluciones en marchas largas; revisarlo al cambiar el embrague.",
  },
  oil: {
    name: "Lubricación (cárter, bomba y filtro)",
    what: "El cárter guarda el aceite; la bomba lo envía a presión a cojinetes, levas y turbo; el filtro retiene las impurezas.",
    fails: "Nivel bajo o aceite degradado: desgaste acelerado. El testigo de presión de aceite encendido significa parar el motor ya.",
    care: "Cambio de aceite y filtro según el plan; comprobar el nivel con la varilla cada pocas semanas.",
  },
  cooling: {
    name: "Refrigeración (bomba de agua, termostato y manguitos)",
    what: "La bomba hace circular el refrigerante por bloque y culata hacia el radiador; el termostato lo deja pasar cuando el motor está caliente.",
    fails: "Termostato abierto: el motor tarda en calentar (P0128) y gasta más. Termostato cerrado o fuga: sobrecalentamiento.",
    care: "Nivel en el vaso de expansión con el motor frío; cambio de refrigerante según el manual.",
  },
  intake: {
    name: "Admisión",
    what: "Colector, caudalímetro (MAF) y sensores de presión y temperatura que miden el aire que entra; en gasolina, también la mariposa.",
    fails: "Caudalímetro sucio o tomas de aire: tirones, ralentí inestable, mezcla pobre (P0171) o códigos P0100-P0113.",
    care: "Filtro de aire al día; no aceitar en exceso los filtros deportivos (ensucia el caudalímetro).",
  },
  exhaust: {
    name: "Escape y catalizador",
    what: "Colector 4-1 que recoge los gases, sondas lambda que vigilan la mezcla y catalizador que reduce los contaminantes.",
    fails: "Catalizador agotado (P0420), sondas lambda lentas (P0133), fugas en el colector (ruido y olor).",
    care: "Corregir rápido los fallos de encendido: la gasolina sin quemar destruye el catalizador.",
  },
  ignition: {
    name: "Encendido (bujías y bobinas)",
    what: "Cada bobina genera la alta tensión y la bujía hace saltar la chispa al final de la compresión de su cilindro. Orden de encendido de este motor: 1-3-4-2.",
    fails: "Bujía gastada o bobina averiada: fallo de encendido en un cilindro (P0301-P0304), tirones, testigo de avería parpadeando.",
    care: "Cambio de bujías según el plan; si falla un cilindro, intercambiar su bobina con otra ayuda a localizar la avería.",
    gasolineOnly: true,
  },
  injectors: {
    name: "Inyectores",
    what: "Pulverizan el combustible a alta presión dentro de cada cilindro, varias veces por ciclo en un diésel moderno.",
    fails: "Inyector que gotea o pulveriza mal: humo negro, ralentí irregular, golpeteo, fallo en un cilindro (P0201-P0204).",
    care: "Combustible de calidad y filtro de combustible al día (el agua en el gasóleo los daña).",
  },
  fuel_rail: {
    name: "Rail y bomba de alta presión",
    what: "La bomba de alta presión llena el rail común, que reparte el combustible a todos los inyectores a la misma presión.",
    fails: "Presión del rail baja o alta (P0087, P0088): pérdida de potencia o modo de emergencia. La contaminación del combustible daña la bomba.",
    care: "Cambiar el filtro de combustible a tiempo y purgarle el agua en los diésel que lo permiten.",
  },
  turbo: {
    name: "Turbo",
    what: "Los gases de escape mueven una turbina que, por el mismo eje, mueve un compresor que mete más aire en el motor.",
    fails: "Falta de presión (P0299) por fugas o geometría variable agarrotada; humo azul y silbido si fallan sus rodamientos.",
    care: "No acelerar a fondo en frío y dejar el motor al ralentí unos segundos antes de pararlo tras un uso exigente; aceite al día.",
    dieselOnly: true,
  },
  intercooler: {
    name: "Intercooler",
    what: "Radiador que enfría el aire comprimido por el turbo antes de que entre en el motor, porque el aire frío es más denso.",
    fails: "Fugas en el intercooler o en sus manguitos: pérdida de potencia y falta de presión de turbo.",
    care: "Revisar manguitos y abrazaderas si el coche pierde fuerza.",
    dieselOnly: true,
  },
  egr: {
    name: "Válvula EGR",
    what: "Recircula parte de los gases de escape hacia la admisión para bajar la temperatura de combustión y las emisiones de NOx.",
    fails: "Se ensucia de carbonilla y se queda abierta o cerrada: tirones, humo negro, pérdida de potencia, códigos P0400-P0409 y P0488-P0490.",
    care: "Hacer trayectos a ritmo constante de vez en cuando; limpiarla o sustituirla si da códigos repetidos.",
    dieselOnly: true,
  },
  dpf: {
    name: "Filtro de partículas (FAP / DPF)",
    what: "Atrapa el hollín del escape y lo quema periódicamente (regeneración) cuando el motor va caliente y a velocidad constante.",
    fails: "Si no puede regenerar (solo trayectos cortos) se colmata: testigo, pérdida de potencia, códigos P2002 o P2463.",
    care: "Un trayecto por autovía de vez en cuando; no interrumpir una regeneración en curso.",
    dieselOnly: true,
  },
  glow: {
    name: "Calentadores",
    what: "Bujías de precalentamiento que calientan la cámara para que el diésel arranque en frío.",
    fails: "Calentador fundido: arranque difícil en frío, humo blanco al arrancar, códigos P0380 o P0671-P0674.",
    care: "Esperar a que se apague el testigo del precalentamiento antes de arrancar en frío.",
    dieselOnly: true,
  },
  sensors: {
    name: "Sensores de cigüeñal y levas",
    what: "Dicen a la centralita la posición exacta del cigüeñal y de los árboles de levas para inyectar y encender en el momento justo.",
    fails: "Si falla el del cigüeñal (P0335), el motor no arranca o se para; el de levas (P0340) causa arranques largos.",
    care: "Revisar conectores y cableado si aparecen estos códigos antes de cambiar el sensor.",
  },
  alternator: {
    name: "Alternador",
    what: "Movido por la correa auxiliar, genera electricidad y recarga la batería con el motor en marcha.",
    fails: "Tensión baja en marcha (por debajo de unos 13 V) o testigo de batería encendido.",
    care: "Revisar la correa auxiliar; Garaje vigila la tensión en marcha si hay lecturas OBD.",
  },
};
