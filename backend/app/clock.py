"""Fecha de «hoy» en la zona horaria de la instalación (GARAJE_TZ), no la del contenedor (UTC).

La racha de los carnés cambia de día a medianoche en Madrid, no a las 2 de la madrugada.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo(config.DEFAULT_TZ)


def today() -> date:
    return datetime.now(TZ).date()
