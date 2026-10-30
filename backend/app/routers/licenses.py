"""Carnés: catálogo de permisos y tu progreso hacia cada uno (pasos, fechas, notas)."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .. import licenses, models
from ..database import get_db

router = APIRouter(prefix="/api/licenses", tags=["licenses"])


class ProgressIn(BaseModel):
    status: Literal["none", "planning", "studying", "obtained"] = "none"
    # {paso: fecha en que lo completaste}; los pasos que no son de este permiso se rechazan.
    steps: dict[str, Optional[date]] = Field(default_factory=dict)
    next_exam_on: Optional[date] = None
    obtained_on: Optional[date] = None
    notes: str = Field(default="", max_length=5000)

    @field_validator("steps")
    @classmethod
    def _known(cls, v: dict[str, Optional[date]]) -> dict[str, Optional[date]]:
        unknown = set(v) - set(licenses.STEPS)
        if unknown:
            raise ValueError(f"Pasos desconocidos: {', '.join(sorted(unknown))}")
        return v


def _entry(code: str) -> dict:
    entry = licenses.BY_CODE.get(code)
    if entry is None:
        raise HTTPException(status_code=404, detail="Permiso no encontrado")
    return entry


@router.get("")
def list_licenses(db: Session = Depends(get_db)):
    return licenses.all_summaries(db)


@router.get("/{code}")
def get_license(code: str, db: Session = Depends(get_db)):
    _entry(code)
    return next(x for x in licenses.all_summaries(db) if x["code"] == code)


@router.put("/{code}")
def put_license(code: str, payload: ProgressIn, db: Session = Depends(get_db)):
    entry = _entry(code)
    extra = set(payload.steps) - set(entry["steps"])
    if extra:
        raise HTTPException(status_code=422, detail=f"El {code} no tiene estos pasos: {', '.join(sorted(extra))}")
    row = licenses.progress(db, code)
    row.status = payload.status
    row.steps = {k: v.isoformat() for k, v in payload.steps.items() if v}
    row.next_exam_on = payload.next_exam_on
    row.obtained_on = payload.obtained_on if payload.status == "obtained" else None
    row.notes = payload.notes
    db.commit()
    return next(x for x in licenses.all_summaries(db) if x["code"] == code)
