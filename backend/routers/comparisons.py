# backend/routers/comparisons.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from backend.core.database import get_db
from backend.models.comparison_models import Comparison, ComparisonFile, Document, ChangeItem, Report
from backend.schemas.comparison import ComparisonCreateIn, ComparisonOut, PaginatedChangeItems
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/api/v1/comparisons", tags=["comparisons"])

@router.post("", response_model=ComparisonOut, status_code=status.HTTP_202_ACCEPTED)
def create_comparison(payload: ComparisonCreateIn, db: Session = Depends(get_db), authorization: Optional[str] = None):
    """
    Создать задачу сравнения. Доступно без авторизации.
    Если хотите записывать created_by — добавьте проверку токена и извлечение user_id.
    """
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

@router.get("/{comparison_id}/track", response_model=PaginatedChangeItems)
def get_track(comparison_id: int, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=200), db: Session = Depends(get_db)):
    q = db.query(ChangeItem).filter(ChangeItem.comparison_id == comparison_id).order_by(ChangeItem.id.asc())
    total = q.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return PaginatedChangeItems(items=items, page=page, total_pages=total_pages)
