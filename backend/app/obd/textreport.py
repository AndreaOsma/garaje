"""Importador tolerante de ficheros de texto del OBD.

Cada app exporta a su manera, así que se extrae lo que se reconozca:
- Informes de diagnóstico (Car Scanner, OBD Auto Doctor…): códigos P/C/B/U, con su
  tipo según el apartado en el que aparezcan (confirmados / pendientes / permanentes),
  VIN y líneas «Sensor: valor unidad».
- Logs de terminal del ELM327: respuestas en hexadecimal a 01xx / 03 / 07 / 0A / 0902.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .dtc import DTC_RE
from .elm327 import _FRAME_PREFIX, clean_lines, hex_bytes, parse_dtc_response, parse_vin
from .pids import decode_pid, key_for_label, normalize_label

_CODE_RE = re.compile(r"\b([PCBU][0-3][0-9A-F]{3})\b")
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_KV_RE = re.compile(r"^\s*([A-Za-zÁÉÍÓÚÜÑáéíóúüñ][^:=\t]{1,80}?)\s*[:=\t]\s*(-?\d+(?:[.,]\d+)?)\s*([^\d\s][^\s]{0,8})?\s*$")
_HEX_LINE = re.compile(r"^(?:[0-9A-F]:)?\s*(?:[0-9A-F]{2}\s?){2,}$", re.I)

_KIND_WORDS = (
    ("pending", ("pendiente", "pending")),
    ("permanent", ("permanente", "permanent")),
    ("stored", ("confirmad", "almacenad", "stored", "memoriz", "activo", "active", "actuales", "current")),
)
# Líneas «Etiqueta: número» que no son lecturas de sensores (recuentos, metadatos del informe).
_NON_SENSOR = re.compile(r"\b(dtcs?|codigos?|codes?|errore?s?|fallos?|averias?|fecha|date|hora|time|version|protocol\w*|ecus?|vin|numero|count|total|id)\b")
_DESC_SEP = re.compile(r"^[\s\-–—:|=·.)\]]+")
_STATUS_ONLY = re.compile(r"^\(?(confirmad\w*|pendiente|permanente|stored|pending|permanent|activo|active|historic\w*)\)?$", re.I)

_NO_CODES = re.compile(r"no (se )?(han )?(encontr|detect)|sin (c[oó]digos|errores|aver[ií]as)|no (dtc|fault|trouble|errors?)\b|no codes", re.I)


@dataclass
class TextReport:
    dtcs: dict[str, list[str]] = field(default_factory=dict)
    values: dict[str, float] = field(default_factory=dict)
    sensors: dict[str, tuple[str, str]] = field(default_factory=dict)
    # Descripción que trae el propio informe junto al código (para el diccionario propio).
    descriptions: dict[str, str] = field(default_factory=dict)
    vin: Optional[str] = None

    @property
    def empty(self) -> bool:
        return not (self.dtcs or self.values or self.vin)


def _kind_from(line: str) -> Optional[str]:
    low = line.lower()
    for kind, words in _KIND_WORDS:
        if any(w in low for w in words):
            return kind
    return None


def _add_code(report: TextReport, kind: str, code: str) -> None:
    codes = report.dtcs.setdefault(kind, [])
    if code not in codes:
        codes.append(code)


def _parse_elm(lines: list[str], report: TextReport) -> bool:
    """Bloques comando → respuesta de un log de terminal ELM327. True si encontró alguno."""
    found = False
    current: Optional[str] = None
    block: list[str] = []

    def flush() -> None:
        nonlocal found
        if not current or not block:
            return
        cleaned = clean_lines("\r".join(block))
        is_can = any(_FRAME_PREFIX.match(l) for l in cleaned) or None
        if current in ("03", "07", "0A"):
            kind = {"03": "stored", "07": "pending", "0A": "permanent"}[current]
            msgs = [hex_bytes(l) for l in cleaned]
            if is_can is None:
                # Sin tramas "N:": en CAN el byte tras el de respuesta es el nº de códigos → longitud impar.
                is_can = any(len(m) > 1 and (len(m) - 1) % 2 == 1 for m in msgs)
            report.dtcs.setdefault(kind, [])
            for code in parse_dtc_response(cleaned, current, bool(is_can)):
                _add_code(report, kind, code)
            found = True
        elif current == "0902":
            vin = parse_vin(cleaned)
            if vin:
                report.vin, found = vin, True
        elif len(current) == 4 and current.startswith("01"):
            pid = current[2:]
            for line in cleaned:
                data = hex_bytes(line)
                if data[:2] == [0x41, int(pid, 16)]:
                    value = decode_pid(pid, data[2:])
                    if value is not None:
                        report.values[pid], found = value, True
                    break

    for raw in lines:
        line = raw.strip().lstrip(">").strip().upper().replace(" ", "")
        if re.fullmatch(r"0[1-9A]([0-9A-F]{2})?", line) and len(line) in (2, 4):
            flush()
            current, block = line, []
        elif current and (_HEX_LINE.match(raw.strip()) or line in ("NODATA", "SEARCHING...")):
            block.append(raw.strip())
        elif current and line and not line.startswith(("AT", "ELM", "OK")):
            flush()
            current, block = None, []
    flush()
    return found


def parse_text(content: bytes) -> TextReport:
    text = content.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    report = TextReport()
    if _parse_elm(lines, report):
        return report

    section: Optional[str] = None
    for line in lines:
        codes = [c for c in _CODE_RE.findall(line.upper()) if DTC_RE.match(c)]
        kind_here = _kind_from(line)
        if not codes:
            if kind_here:
                section = kind_here  # Cabecera de apartado: «Códigos pendientes», «Permanent DTCs»…
            if _NO_CODES.search(line):
                report.dtcs.setdefault(section or "stored", [])
            m = _KV_RE.match(line)
            if m and not _NON_SENSOR.search(normalize_label(m.group(1))):
                label, raw_value, unit = m.group(1).strip(), m.group(2), (m.group(3) or "").strip()
                key, standard = key_for_label(label)
                value = float(raw_value.replace(",", "."))
                report.values[key] = value
                if not standard:
                    report.sensors[key] = (label[:120], unit[:24])
        for code in codes:
            _add_code(report, kind_here or section or "stored", code)
        if len(codes) == 1:
            # «P0490 - Circuito de control de la EGR…»: lo que sigue al código es su descripción.
            rest = line[line.upper().index(codes[0]) + len(codes[0]):]
            desc = _DESC_SEP.sub("", rest).strip()
            desc = re.sub(r"\s*\((confirmad\w*|pendiente|permanente|stored|pending|permanent)\)\s*$", "", desc, flags=re.I)
            if len(re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúñÑ]", "", desc)) >= 6 and not _STATUS_ONLY.match(desc):
                report.descriptions.setdefault(codes[0], desc[:300])
        if not report.vin:
            vin = _VIN_RE.search(line.upper())
            if vin and re.search(r"\d", vin.group(1)) and re.search(r"[A-Z]", vin.group(1)):
                report.vin = vin.group(1)
    return report
