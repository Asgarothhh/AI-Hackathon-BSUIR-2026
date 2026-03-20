from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from backend.core.database import get_db
from backend.models.comparison_models import Document, ComparisonFile, Comparison, ChangeItem
from backend.schemas.comparison import DocumentOut, ChangeItemOut

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/documents/search", response_model=List[DocumentOut])
def search_documents(q: str = Query(..., min_length=1), limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    like = f"%{q}%"
    docs_q = db.query(Document).distinct().join(
        ComparisonFile, ComparisonFile.document_id == Document.id, isouter=True
    ).join(
        Comparison, Comparison.id == ComparisonFile.comparison_id, isouter=True
    ).join(
        ChangeItem, ChangeItem.comparison_id == Comparison.id, isouter=True
    ).filter(
        (Document.filename.ilike(like)) |
        (ChangeItem.before.ilike(like)) |
        (ChangeItem.after.ilike(like))
    ).limit(limit)
    return docs_q.all()


@router.get("/change_items/search", response_model=List[ChangeItemOut])
def search_change_items(q: str = Query(..., min_length=1), limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    like = f"%{q}%"
    items = db.query(ChangeItem).filter(
        (ChangeItem.before.ilike(like)) |
        (ChangeItem.after.ilike(like)) |
        (ChangeItem.risk_level.ilike(like))
    ).order_by(ChangeItem.created_at.desc()).limit(limit).all()
    return items
