"""Códigos de avería (DTC): decodificación de bytes OBD y diccionario en español.

El diccionario cubre los códigos genéricos (SAE J2012) más habituales; para el resto
se deduce al menos el sistema afectado a partir de la estructura del código.
"""
from __future__ import annotations

import re
from typing import Sequence

DTC_RE = re.compile(r"^[PCBU][0-3][0-9A-F]{3}$")

_LETTERS = "PCBU"


def decode_dtc_pair(hi: int, lo: int) -> str | None:
    """Dos bytes de modo 03/07/0A → "P0133". 0x0000 es relleno (sin código)."""
    if hi == 0 and lo == 0:
        return None
    letter = _LETTERS[(hi >> 6) & 0x03]
    return f"{letter}{(hi >> 4) & 0x03}{hi & 0x0F:X}{lo:02X}"


def decode_dtc_bytes(data: Sequence[int]) -> list[str]:
    codes: list[str] = []
    for i in range(0, len(data) - 1, 2):
        code = decode_dtc_pair(data[i], data[i + 1])
        if code and code not in codes:
            codes.append(code)
    return codes


def normalize_code(code: str) -> str | None:
    clean = code.strip().upper().replace(" ", "")
    return clean if DTC_RE.match(clean) else None


# (descripción, severidad: baja | media | alta)
DTC_DICTIONARY: dict[str, tuple[str, str]] = {
    "P0010": ("Circuito del actuador de la distribución variable (árbol de levas A, banco 1)", "media"),
    "P0011": ("Distribución variable árbol de levas A demasiado adelantada (banco 1)", "media"),
    "P0016": ("Correlación cigüeñal/árbol de levas incorrecta (banco 1, sensor A)", "alta"),
    "P0087": ("Presión del rail de combustible demasiado baja", "alta"),
    "P0088": ("Presión del rail de combustible demasiado alta", "alta"),
    "P0093": ("Fuga grande en el sistema de combustible", "alta"),
    "P0100": ("Circuito del caudalímetro (MAF)", "media"),
    "P0101": ("Caudalímetro (MAF) fuera de rango o rendimiento", "media"),
    "P0102": ("Caudalímetro (MAF): señal baja", "media"),
    "P0103": ("Caudalímetro (MAF): señal alta", "media"),
    "P0106": ("Sensor de presión del colector (MAP) fuera de rango o rendimiento", "media"),
    "P0107": ("Sensor MAP: señal baja", "media"),
    "P0108": ("Sensor MAP: señal alta", "media"),
    "P0110": ("Circuito del sensor de temperatura del aire de admisión", "baja"),
    "P0113": ("Sensor de temperatura del aire de admisión: señal alta", "baja"),
    "P0115": ("Circuito del sensor de temperatura del refrigerante", "media"),
    "P0116": ("Sensor de temperatura del refrigerante fuera de rango o rendimiento", "media"),
    "P0117": ("Sensor de temperatura del refrigerante: señal baja", "media"),
    "P0118": ("Sensor de temperatura del refrigerante: señal alta", "media"),
    "P0120": ("Circuito del sensor de posición del acelerador/mariposa A", "media"),
    "P0121": ("Sensor de posición de mariposa A fuera de rango o rendimiento", "media"),
    "P0128": ("Termostato: refrigerante por debajo de la temperatura de regulación", "media"),
    "P0130": ("Circuito de la sonda lambda (banco 1, sensor 1)", "media"),
    "P0131": ("Sonda lambda banco 1 sensor 1: tensión baja", "media"),
    "P0132": ("Sonda lambda banco 1 sensor 1: tensión alta", "media"),
    "P0133": ("Sonda lambda banco 1 sensor 1: respuesta lenta", "media"),
    "P0134": ("Sonda lambda banco 1 sensor 1: sin actividad", "media"),
    "P0135": ("Calefactor de la sonda lambda (banco 1, sensor 1)", "media"),
    "P0136": ("Circuito de la sonda lambda (banco 1, sensor 2)", "baja"),
    "P0137": ("Sonda lambda banco 1 sensor 2: tensión baja", "baja"),
    "P0138": ("Sonda lambda banco 1 sensor 2: tensión alta", "baja"),
    "P0141": ("Calefactor de la sonda lambda (banco 1, sensor 2)", "baja"),
    "P0171": ("Mezcla demasiado pobre (banco 1)", "media"),
    "P0172": ("Mezcla demasiado rica (banco 1)", "media"),
    "P0174": ("Mezcla demasiado pobre (banco 2)", "media"),
    "P0175": ("Mezcla demasiado rica (banco 2)", "media"),
    "P0191": ("Sensor de presión del rail de combustible fuera de rango o rendimiento", "alta"),
    "P0201": ("Circuito del inyector, cilindro 1", "alta"),
    "P0202": ("Circuito del inyector, cilindro 2", "alta"),
    "P0203": ("Circuito del inyector, cilindro 3", "alta"),
    "P0204": ("Circuito del inyector, cilindro 4", "alta"),
    "P0234": ("Sobrepresión del turbo", "alta"),
    "P0299": ("Presión del turbo insuficiente", "media"),
    "P0300": ("Fallo de encendido aleatorio o en varios cilindros", "alta"),
    "P0301": ("Fallo de encendido en el cilindro 1", "alta"),
    "P0302": ("Fallo de encendido en el cilindro 2", "alta"),
    "P0303": ("Fallo de encendido en el cilindro 3", "alta"),
    "P0304": ("Fallo de encendido en el cilindro 4", "alta"),
    "P0305": ("Fallo de encendido en el cilindro 5", "alta"),
    "P0306": ("Fallo de encendido en el cilindro 6", "alta"),
    "P0325": ("Circuito del sensor de picado 1 (banco 1)", "media"),
    "P0335": ("Circuito del sensor de posición del cigüeñal A", "alta"),
    "P0340": ("Circuito del sensor de posición del árbol de levas A (banco 1)", "alta"),
    "P0380": ("Circuito de calentadores (bujías de precalentamiento) A", "media"),
    "P0400": ("Flujo de recirculación de gases de escape (EGR)", "media"),
    "P0401": ("Flujo de EGR insuficiente", "media"),
    "P0402": ("Flujo de EGR excesivo", "media"),
    "P0403": ("Circuito de control de la válvula EGR", "media"),
    "P0420": ("Eficiencia del catalizador por debajo del umbral (banco 1)", "media"),
    "P0430": ("Eficiencia del catalizador por debajo del umbral (banco 2)", "media"),
    "P0440": ("Sistema de control de emisiones evaporativas (EVAP)", "baja"),
    "P0441": ("EVAP: flujo de purga incorrecto", "baja"),
    "P0442": ("EVAP: fuga pequeña detectada", "baja"),
    "P0446": ("EVAP: circuito de control de ventilación", "baja"),
    "P0455": ("EVAP: fuga grande detectada (revisa el tapón del depósito)", "baja"),
    "P0456": ("EVAP: fuga muy pequeña detectada", "baja"),
    "P0470": ("Sensor de presión de escape", "media"),
    "P0480": ("Circuito de control del ventilador de refrigeración 1", "media"),
    "P0500": ("Sensor de velocidad del vehículo A", "media"),
    "P0505": ("Sistema de control de ralentí", "media"),
    "P0506": ("Ralentí más bajo de lo esperado", "baja"),
    "P0507": ("Ralentí más alto de lo esperado", "baja"),
    "P0520": ("Circuito del sensor/interruptor de presión de aceite", "alta"),
    "P0562": ("Tensión del sistema baja", "media"),
    "P0563": ("Tensión del sistema alta", "media"),
    "P0571": ("Circuito del interruptor de freno A (control de crucero)", "baja"),
    "P0600": ("Enlace de comunicación serie (centralita)", "alta"),
    "P0603": ("Error de memoria KAM de la centralita", "media"),
    "P0605": ("Error de memoria ROM de la centralita", "alta"),
    "P0700": ("Sistema de control de la transmisión (consulta la centralita del cambio)", "media"),
    "P0705": ("Circuito del sensor de posición de la palanca de cambio", "media"),
    "P0715": ("Circuito del sensor de velocidad de turbina/entrada del cambio", "media"),
    "P0720": ("Circuito del sensor de velocidad de salida del cambio", "media"),
    "P0730": ("Relación de marcha incorrecta", "alta"),
    "P0741": ("Embrague del convertidor de par: rendimiento o bloqueado en abierto", "media"),
    "P2002": ("Eficiencia del filtro de partículas (DPF) por debajo del umbral (banco 1)", "media"),
    "P2004": ("Mariposas del colector de admisión bloqueadas abiertas (banco 1)", "media"),
    "P2096": ("Ajuste de combustible posterior al catalizador demasiado pobre (banco 1)", "media"),
    "P2097": ("Ajuste de combustible posterior al catalizador demasiado rico (banco 1)", "media"),
    "P2135": ("Correlación de los sensores de posición del acelerador/mariposa A/B", "alta"),
    "P2187": ("Mezcla pobre en ralentí (banco 1)", "media"),
    "P2188": ("Mezcla rica en ralentí (banco 1)", "media"),
    "P2263": ("Rendimiento del sistema de sobrealimentación turbo/compresor", "media"),
    "P242F": ("Restricción del filtro de partículas: acumulación de ceniza", "media"),
    "P2463": ("Restricción del filtro de partículas: acumulación de hollín", "media"),
    "P2BAD": ("NOx excesivo: causa desconocida (sistema SCR/AdBlue)", "media"),
    "P0045": ("Circuito del control de presión del turbo A abierto", "media"),
    "P0046": ("Circuito del control de presión del turbo A fuera de rango o rendimiento", "media"),
    "P0047": ("Circuito del control de presión del turbo A: señal baja", "media"),
    "P0048": ("Circuito del control de presión del turbo A: señal alta", "media"),
    "P0089": ("Rendimiento del regulador de presión de combustible 1", "alta"),
    "P0236": ("Sensor de presión del turbo A fuera de rango o rendimiento", "media"),
    "P0237": ("Sensor de presión del turbo A: señal baja", "media"),
    "P0238": ("Sensor de presión del turbo A: señal alta", "media"),
    "P0251": ("Control de dosificación de la bomba de inyección A", "alta"),
    "P0381": ("Circuito del testigo de calentadores (bujías de precalentamiento)", "baja"),
    "P0382": ("Circuito de calentadores (bujías de precalentamiento) B", "media"),
    "P0404": ("Circuito de la EGR fuera de rango o rendimiento", "media"),
    "P0405": ("Sensor A de la EGR: señal baja", "media"),
    "P0406": ("Sensor A de la EGR: señal alta", "media"),
    "P0409": ("Circuito del sensor A de la EGR", "media"),
    "P0471": ("Sensor de presión de escape A fuera de rango o rendimiento", "media"),
    "P0472": ("Sensor de presión de escape A: señal baja", "media"),
    "P0473": ("Sensor de presión de escape A: señal alta", "media"),
    "P0488": ("Control de posición de la mariposa de la EGR fuera de rango o rendimiento", "media"),
    "P0489": ("Circuito de control de la EGR A: señal baja", "media"),
    "P0490": ("Circuito de control de la EGR A: señal alta", "media"),
    "P0560": ("Tensión del sistema (batería/alimentación)", "media"),
    "P0561": ("Tensión del sistema inestable", "media"),
    "P0606": ("Procesador de la centralita del motor", "alta"),
    "P0627": ("Circuito de control de la bomba de combustible A abierto", "alta"),
    "P0641": ("Tensión de referencia A de los sensores: circuito abierto", "alta"),
    "P0651": ("Tensión de referencia B de los sensores: circuito abierto", "alta"),
    "P0670": ("Circuito del módulo de control de calentadores", "media"),
    "P0671": ("Circuito del calentador del cilindro 1", "media"),
    "P0672": ("Circuito del calentador del cilindro 2", "media"),
    "P0673": ("Circuito del calentador del cilindro 3", "media"),
    "P0674": ("Circuito del calentador del cilindro 4", "media"),
    "P2003": ("Eficiencia del filtro de partículas (DPF) por debajo del umbral (banco 2)", "media"),
    "P2279": ("Fuga en el sistema de admisión de aire", "media"),
    "P2452": ("Circuito del sensor de presión diferencial del filtro de partículas A", "media"),
    "P2453": ("Sensor de presión diferencial del filtro de partículas A fuera de rango o rendimiento", "media"),
    "P2454": ("Sensor de presión diferencial del filtro de partículas A: señal baja", "media"),
    "P2455": ("Sensor de presión diferencial del filtro de partículas A: señal alta", "media"),
    "U0001": ("Bus de comunicación CAN de alta velocidad", "alta"),
    "U0073": ("Bus de comunicación A de las centralitas apagado", "alta"),
    "U0100": ("Pérdida de comunicación con la centralita del motor (ECM/PCM)", "alta"),
    "U0101": ("Pérdida de comunicación con la centralita del cambio (TCM)", "alta"),
    "U0121": ("Pérdida de comunicación con el módulo del ABS", "alta"),
    "U0140": ("Pérdida de comunicación con el módulo de carrocería (BCM)", "media"),
    "U0155": ("Pérdida de comunicación con el cuadro de instrumentos", "media"),
    "C0035": ("Circuito del sensor de velocidad de rueda delantera izquierda", "alta"),
    "C0040": ("Circuito del sensor de velocidad de rueda delantera derecha", "alta"),
    "C0045": ("Circuito del sensor de velocidad de rueda trasera izquierda", "alta"),
    "C0050": ("Circuito del sensor de velocidad de rueda trasera derecha", "alta"),
    "B0001": ("Control de despliegue del airbag frontal del conductor", "alta"),
}

_SYSTEMS = {"P": "Motor y transmisión", "C": "Chasis", "B": "Carrocería", "U": "Red de comunicación"}

# Tercer carácter de los códigos P genéricos → subsistema (SAE J2012).
_P_SUBSYSTEMS = {
    "0": "Medición de aire/combustible y emisiones auxiliares",
    "1": "Medición de aire/combustible",
    "2": "Medición de aire/combustible (inyectores)",
    "3": "Encendido y fallos de encendido",
    "4": "Control auxiliar de emisiones",
    "5": "Velocidad, ralentí y entradas auxiliares",
    "6": "Centralita y salidas auxiliares",
    "7": "Transmisión",
    "8": "Transmisión",
    "9": "Transmisión",
    "A": "Propulsión híbrida/eléctrica",
    "B": "Propulsión híbrida/eléctrica",
    "C": "Propulsión híbrida/eléctrica",
}


def describe_dtc(code: str) -> dict:
    """{code, description, system, severity, generic}. Nunca falla con códigos raros."""
    code = code.upper()
    letter = code[:1]
    # P0/P2 genéricos (P1/P3 fabricante); en C/B/U solo el 0 es genérico.
    generic = code[1:2] in (("0", "2") if letter == "P" else ("0",))
    entry = DTC_DICTIONARY.get(code)
    system = _SYSTEMS.get(letter, "Desconocido")
    if letter == "P" and len(code) == 5:
        system = f"{system} — {_P_SUBSYSTEMS.get(code[2], 'otros')}"
    if entry:
        description, severity = entry
    elif not generic:
        description = "Código del fabricante, aún sin descripción (se busca automáticamente)"
        severity = "media"
    else:
        description = "Código genérico no incluido en el diccionario"
        severity = "media"
    return {"code": code, "description": description, "system": system, "severity": severity, "generic": generic}
