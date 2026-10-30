"""Importa al arrancar los packs de teórico versionados en content/*.json.

El import hace upsert por `ref` (learn.import_course), así que reimportar el mismo pack no
duplica nada ni pisa el progreso. Para no revalidar cada JSON en todos los arranques se
guarda el sha256 de cada pack importado (clave interna `_content_hashes` en app_settings).
"""
from __future__ import annotations

import hashlib
import logging

from sqlalchemy.orm import Session

from . import config, learn, licenses, models

logger = logging.getLogger("garaje.content")

STATE_KEY = "_content_hashes"


def import_packs(db: Session) -> None:
    content_dir = config.CONTENT_DIR
    if not content_dir.is_dir():
        return
    row = db.get(models.AppSetting, STATE_KEY)
    hashes: dict[str, str] = dict(row.value or {}) if row else {}
    changed = False
    for path in sorted(content_dir.glob("*.json")):
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if hashes.get(path.name) == digest:
            continue
        try:
            course_in = learn.load_course(data)
            entry = licenses.BY_CODE.get(course_in.subject_code)
            if entry is None:
                raise ValueError(f"«subject_code» {course_in.subject_code!r} no es un permiso del catálogo")
            learn.import_course(db, course_in, entry["code"], course_in.title)
        except ValueError as exc:
            # Un pack roto no debe tumbar el arranque: se avisa y se sigue.
            db.rollback()
            logger.error("No se pudo importar %s: %s", path.name, exc)
            continue
        logger.info("Pack importado: %s (%s unidades)", path.name, len(course_in.units))
        hashes[path.name] = digest
        changed = True
    if changed:
        row = db.get(models.AppSetting, STATE_KEY)
        if row is None:
            db.add(models.AppSetting(key=STATE_KEY, value=hashes))
        else:
            row.value = hashes
        db.commit()
