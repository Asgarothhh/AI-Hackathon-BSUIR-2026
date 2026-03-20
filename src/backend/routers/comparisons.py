# backend/routers/comparisons.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from src.backend.core.database import get_db
from src.backend.models.comparison_models import Comparison, ComparisonFile, Document, ChangeItem, Report
from src.backend.schemas.comparison import (
    ComparisonCreateIn,
    ComparisonOut,
    PaginatedChangeItems,
    ChangeItemOut,
    ComparisonListItem,
)

router = APIRouter(prefix="/api/v1/comparisons", tags=["comparisons"])


@router.get("", response_model=List[ComparisonListItem])
def list_comparisons(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    q = db.query(Comparison).order_by(Comparison.created_at.desc()).limit(limit)
    items = q.all()
    return items


@router.post("", response_model=ComparisonOut, status_code=202)
def create_comparison(payload: ComparisonCreateIn, db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.id.in_(payload.file_ids)).all()
    if len(docs) != len(payload.file_ids):
        raise HTTPException(status_code=400, detail="One or more files not found")
    comp = Comparison(title=payload.title, created_by=None, status="queued", options=payload.options)
    db.add(comp)
    db.commit()
    db.refresh(comp)
    for fid in payload.file_ids:
        db.add(ComparisonFile(comparison_id=comp.id, document_id=fid, role=None))
    db.commit()
    report = Report(comparison_id=comp.id, status="pending")
    db.add(report)
    db.commit()
    db.refresh(report)
    comp.report_id = report.id
    db.add(comp)
    db.commit()
    return ComparisonOut(id=comp.id, title=comp.title, status=comp.status, summary=None, risk_counts=None, report_id=comp.report_id)


@router.get("/track", response_model=PaginatedChangeItems)
def get_track_all(
    comparison_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=1000),
    q: Optional[str] = Query(None, description="Поиск по before/after/linked_law"),
    db: Session = Depends(get_db),
):
    """
    Если comparison_id указан — возвращает change_items для этого сравнения.
    Если comparison_id не указан — возвращает все change_items по всем сравнениям, новые сверху.
    Поддерживает поиск по тексту (q).
    """
    base = db.query(ChangeItem)
    if comparison_id:
        base = base.filter(ChangeItem.comparison_id == comparison_id)
    if q:
        like = f"%{q}%"
        base = base.filter(
            (ChangeItem.before.ilike(like)) |
            (ChangeItem.after.ilike(like)) |
            (ChangeItem.linked_law.cast(db.bind.dialect.type_descriptor(ChangeItem.linked_law.type)).ilike(like))
        )
    total = base.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    items = base.order_by(ChangeItem.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return PaginatedChangeItems(items=items, page=page, total_pages=total_pages)


@router.get("/{comparison_id}", response_model=ComparisonOut)
def get_comparison(comparison_id: int, db: Session = Depends(get_db)):
    comp = db.query(Comparison).filter(Comparison.id == comparison_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Comparison not found")
    total = db.query(ChangeItem).filter(ChangeItem.comparison_id == comp.id).count()
    red = db.query(ChangeItem).filter(ChangeItem.comparison_id == comp.id, ChangeItem.risk_level == "red").count()
    yellow = db.query(ChangeItem).filter(ChangeItem.comparison_id == comp.id, ChangeItem.risk_level == "yellow").count()
    green = db.query(ChangeItem).filter(ChangeItem.comparison_id == comp.id, ChangeItem.risk_level == "green").count()
    summary = f"Найдено {total} изменений: {red} критических, {yellow} требующих проверки, {green} безопасных"
    return ComparisonOut(id=comp.id, title=comp.title, status=comp.status, summary=summary, risk_counts={"green": green, "yellow": yellow, "red": red}, report_id=comp.report_id)
