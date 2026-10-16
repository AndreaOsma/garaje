"""Registro de PIDs OBD-II (modo 01, SAE J1979) y decodificación de sus bytes.

Sin dependencias del resto de la app: lo importan tanto el backend como el agente
(`python -m app.obd.agent`), que corre en una Raspberry/portátil sin base de datos.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional, Sequence


@dataclass(frozen=True)
class PidDef:
    key: str
    name: str
    unit: str
    nbytes: int
    decode: Callable[[Sequence[int]], float]
    # Agrupación para la UI de diagnóstico.
    group: str = "motor"


def _u16(b: Sequence[int]) -> int:
    return b[0] * 256 + b[1]


def _pct(b: Sequence[int]) -> float:
    return round(b[0] * 100 / 255, 1)


def _trim(b: Sequence[int]) -> float:
    return round((b[0] - 128) * 100 / 128, 1)


PIDS: dict[str, PidDef] = {
    p.key: p
    for p in (
        PidDef("04", "Carga calculada del motor", "%", 1, _pct),
        PidDef("05", "Temperatura del refrigerante", "°C", 1, lambda b: b[0] - 40),
        PidDef("06", "Ajuste combustible corto B1", "%", 1, _trim, "mezcla"),
        PidDef("07", "Ajuste combustible largo B1", "%", 1, _trim, "mezcla"),
        PidDef("08", "Ajuste combustible corto B2", "%", 1, _trim, "mezcla"),
        PidDef("09", "Ajuste combustible largo B2", "%", 1, _trim, "mezcla"),
        PidDef("0A", "Presión de combustible", "kPa", 1, lambda b: b[0] * 3, "mezcla"),
        PidDef("0B", "Presión del colector (MAP)", "kPa", 1, lambda b: b[0], "admisión"),
        PidDef("0C", "Revoluciones", "rpm", 2, lambda b: _u16(b) / 4),
        PidDef("0D", "Velocidad", "km/h", 1, lambda b: b[0], "marcha"),
        PidDef("0E", "Avance de encendido", "°", 1, lambda b: b[0] / 2 - 64),
        PidDef("0F", "Temperatura del aire de admisión", "°C", 1, lambda b: b[0] - 40, "admisión"),
        PidDef("10", "Caudal de aire (MAF)", "g/s", 2, lambda b: _u16(b) / 100, "admisión"),
        PidDef("11", "Posición del acelerador", "%", 1, _pct, "admisión"),
        PidDef("1F", "Tiempo desde el arranque", "s", 2, _u16, "marcha"),
        PidDef("21", "Distancia con testigo MIL encendido", "km", 2, _u16, "diagnóstico"),
        PidDef("2F", "Nivel de combustible", "%", 1, _pct, "marcha"),
        PidDef("31", "Distancia desde borrado de códigos", "km", 2, _u16, "diagnóstico"),
        PidDef("33", "Presión barométrica", "kPa", 1, lambda b: b[0], "admisión"),
        PidDef("42", "Tensión del módulo de control", "V", 2, lambda b: round(_u16(b) / 1000, 2), "eléctrico"),
        PidDef("46", "Temperatura ambiente", "°C", 1, lambda b: b[0] - 40, "marcha"),
        PidDef("5C", "Temperatura del aceite", "°C", 1, lambda b: b[0] - 40),
        PidDef("5E", "Consumo instantáneo", "L/h", 2, lambda b: _u16(b) / 20, "mezcla"),
        PidDef(
            "A6", "Odómetro", "km", 4,
            lambda b: ((b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]) / 10, "marcha",
        ),
    )
}

# Claves especiales que no son PIDs de modo 01.
SPECIAL_KEYS: dict[str, tuple[str, str, str]] = {
    # ATRV del ELM327: tensión en el pin 16 del conector = batería.
    "BATT": ("Tensión de batería", "V", "eléctrico"),
}

# PIDs que el agente sondea en cada ciclo si la ECU los soporta (orden = prioridad).
DEFAULT_POLL_PIDS = (
    "0C", "0D", "05", "04", "0F", "10", "0B", "11", "06", "07",
    "0E", "2F", "42", "46", "5C", "5E", "33", "1F", "21", "31", "A6",
)


def decode_pid(key: str, data: Sequence[int]) -> Optional[float]:
    pid = PIDS.get(key.upper())
    if pid is None or len(data) < pid.nbytes:
        return None
    return float(pid.decode(data[: pid.nbytes]))


def describe_key(key: str) -> tuple[str, str, str]:
    """(nombre, unidad, grupo) para cualquier clave de muestra conocida."""
    pid = PIDS.get(key.upper())
    if pid:
        return pid.name, pid.unit, pid.group
    if key in SPECIAL_KEYS:
        return SPECIAL_KEYS[key]
    return key, "", "otros"


# ---------------------------------------------------------------------------
# Monitores de preparación (PID 01) — lo que mira la ITV en la prueba OBD.
# ---------------------------------------------------------------------------

_COMMON_MONITORS = ("Fallos de encendido", "Sistema de combustible", "Componentes")
_SPARK_MONITORS = (
    "Catalizador", "Catalizador calefactado", "Sistema EVAP", "Aire secundario",
    "Refrigerante A/C", "Sonda lambda", "Calefactor sonda lambda", "EGR",
)
_DIESEL_MONITORS = (
    "Catalizador NMHC", "NOx / SCR", None, "Presión de sobrealimentación",
    None, "Sensor de gases de escape", "Filtro de partículas", "EGR / VVT",
)


def decode_monitor_status(data: Sequence[int]) -> dict:
    """PID 01 → {mil_on, dtc_count, ignition, monitors: [{name, complete}], ready}.

    Solo se listan los monitores que la ECU declara disponibles. `ready` es True
    cuando todos los disponibles están completos (criterio práctico de la ITV;
    algunas normativas toleran uno incompleto, por eso se devuelve el detalle).
    """
    a, b, c, d = (list(data) + [0, 0, 0, 0])[:4]
    compression = bool(b & 0x08)
    monitors: list[dict] = []
    for bit, name in enumerate(_COMMON_MONITORS):
        if b & (1 << bit):
            monitors.append({"name": name, "complete": not (b & (1 << (bit + 4)))})
    names = _DIESEL_MONITORS if compression else _SPARK_MONITORS
    for bit, name in enumerate(names):
        if name and c & (1 << bit):
            monitors.append({"name": name, "complete": not (d & (1 << bit))})
    return {
        "mil_on": bool(a & 0x80),
        "dtc_count": a & 0x7F,
        "ignition": "compresión" if compression else "chispa",
        "monitors": monitors,
        "ready": all(m["complete"] for m in monitors),
    }


# ---------------------------------------------------------------------------
# Nombres de sensores en apps de terceros (Car Scanner, en inglés y español).
# ---------------------------------------------------------------------------

def normalize_label(label: str) -> str:
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\(.*?\)", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


_ALIASES: dict[str, tuple[str, ...]] = {
    "04": ("calculated engine load", "calculated engine load value", "engine load", "carga del motor", "carga calculada del motor"),
    "05": ("engine coolant temperature", "coolant temperature", "temperatura del refrigerante", "temperatura del refrigerante del motor"),
    "06": ("short term fuel trim bank 1", "short term fuel trim bank1", "ajuste de combustible a corto plazo banco 1"),
    "07": ("long term fuel trim bank 1", "long term fuel trim bank1", "ajuste de combustible a largo plazo banco 1"),
    "0B": ("intake manifold absolute pressure", "intake manifold pressure", "presion absoluta del colector de admision"),
    "0C": ("engine rpm", "rpm", "revoluciones del motor", "rpm del motor"),
    "0D": ("vehicle speed", "speed", "velocidad del vehiculo", "velocidad"),
    "0E": ("timing advance", "avance del encendido", "avance de encendido"),
    "0F": ("intake air temperature", "temperatura del aire de admision"),
    "10": ("maf air flow rate", "mass air flow rate", "maf", "caudal de aire maf", "flujo de aire maf"),
    "11": ("throttle position", "posicion del acelerador", "posicion de la mariposa"),
    "2F": ("fuel level input", "fuel tank level input", "fuel level", "nivel de combustible"),
    "31": ("distance traveled since codes cleared", "distancia recorrida desde que se borraron los codigos"),
    "33": ("absolute barometric pressure", "barometric pressure", "presion barometrica"),
    "42": ("control module voltage", "tension del modulo de control", "voltaje del modulo de control"),
    "46": ("ambient air temperature", "temperatura del aire ambiente", "temperatura ambiente"),
    "5C": ("engine oil temperature", "oil temperature", "temperatura del aceite del motor", "temperatura del aceite"),
    "5E": ("engine fuel rate", "fuel rate", "consumo de combustible del motor"),
    "A6": ("odometer", "odometro", "cuentakilometros"),
    "BATT": ("obd module voltage", "adapter voltage", "battery voltage", "tension de la bateria", "voltaje de la bateria"),
}
_ALIAS_INDEX = {alias: key for key, aliases in _ALIASES.items() for alias in aliases}


def key_for_label(label: str) -> tuple[str, bool]:
    """Nombre libre de sensor → (clave, es_estándar). Desconocidos → "cs:<slug>"."""
    norm = normalize_label(label)
    if norm in _ALIAS_INDEX:
        return _ALIAS_INDEX[norm], True
    return "cs:" + norm.replace(" ", "-")[:58], False
