"""Importador de grabaciones CSV de Car Scanner (iOS/Android).

Car Scanner exporta en formato "largo": `"SECONDS";"PID";"VALUE";"UNITS"`, una fila
por lectura, con SECONDS = segundos desde la medianoche (hora local del móvil) y PID =
nombre del sensor en el idioma de la app. También se acepta el formato "ancho"
(columna de tiempo + una columna por sensor) que exportan otras apps.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Optional

from .pids import key_for_label

_TIME_HEADERS = {"seconds", "time", "timestamp", "tiempo", "segundos", "time s", "device time"}


class CsvFormatError(ValueError):
    pass


@dataclass
class ParsedLog:
    samples: list[tuple[datetime, str, float]] = field(default_factory=list)
    # key → (nombre, unidad) de sensores no estándar, para guardarlos en ObdSensor.
    sensors: dict[str, tuple[str, str]] = field(default_factory=dict)
    skipped_rows: int = 0

    @property
    def started_at(self) -> Optional[datetime]:
        return min((s[0] for s in self.samples), default=None)

    @property
    def ended_at(self) -> Optional[datetime]:
        return max((s[0] for s in self.samples), default=None)


def _number(text: str) -> Optional[float]:
    text = text.strip().strip('"')
    if not text:
        return None
    text = text.replace(",", ".") if text.count(",") == 1 and "." not in text else text
    try:
        return float(text)
    except ValueError:
        return None


def _split_label_unit(header: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", header)
    return (match.group(1).strip(), match.group(2).strip()) if match else (header.strip(), "")


class _Clock:
    """Segundos desde medianoche local → datetime UTC, contando los pasos por medianoche."""

    def __init__(self, day: date, tz: tzinfo):
        self.base = datetime(day.year, day.month, day.day, tzinfo=tz)
        self.day_shift = 0
        self.last = None

    def at(self, seconds: float) -> datetime:
        if self.last is not None and seconds < self.last - 43200:
            self.day_shift += 1
        self.last = seconds
        return (self.base + timedelta(days=self.day_shift, seconds=seconds)).astimezone(timezone.utc)


def parse_csv(content: bytes, day: date, tz: tzinfo = timezone.utc) -> ParsedLog:
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise CsvFormatError("El CSV está vacío")

    header = [h.strip().strip('"') for h in rows[0]]
    lower = [h.lower() for h in header]
    clock = _Clock(day, tz)
    log = ParsedLog()

    def register(label: str, unit: str) -> str:
        key, standard = key_for_label(label)
        if not standard and key not in log.sensors:
            log.sensors[key] = (label[:120], unit[:24])
        return key

    if {"seconds", "pid", "value"} <= set(lower):
        i_s, i_p, i_v = lower.index("seconds"), lower.index("pid"), lower.index("value")
        i_u = lower.index("units") if "units" in lower else None
        keys: dict[str, str] = {}
        for row in rows[1:]:
            try:
                seconds, label, value = _number(row[i_s]), row[i_p].strip(), _number(row[i_v])
            except IndexError:
                log.skipped_rows += 1
                continue
            if seconds is None or value is None or not label:
                log.skipped_rows += 1
                continue
            if label not in keys:
                keys[label] = register(label, row[i_u].strip() if i_u is not None and i_u < len(row) else "")
            log.samples.append((clock.at(seconds), keys[label], value))
        return log

    time_idx = next((i for i, h in enumerate(lower) if h in _TIME_HEADERS), None)
    if time_idx is None:
        raise CsvFormatError("No se reconoce el formato: falta la columna de tiempo (SECONDS/Time)")
    columns = {}
    for i, h in enumerate(header):
        if i != time_idx and h:
            label, unit = _split_label_unit(h)
            columns[i] = register(label, unit)
    for row in rows[1:]:
        seconds = _number(row[time_idx]) if time_idx < len(row) else None
        if seconds is None:
            log.skipped_rows += 1
            continue
        ts = clock.at(seconds)
        for i, key in columns.items():
            if i < len(row):
                value = _number(row[i])
                if value is not None:
                    log.samples.append((ts, key, value))
    return log
