# backend/routers/reports.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.core.database import get_db
from backend.models.comparison_models import Report, Comparison
from backend.core.storage import get_file_path
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

@router.post("/comparisons/{comparison_id}/export", status_code=status.HTTP_202_ACCEPTED)
def export_report(comparison_id: int, db: Session = Depends(get_db), authorization: Optional[str] = None):
    """
    Запустить экспорт отчёта. Доступно без проверки ролей.
    В реальной системе: поставить задачу в очередь для генерации .docx.
    """
    comp = db.query(Comparison).filter(Comparison.id == comparison_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Comparison not found")
    report = db.query(Report).filter(Report.comparison_id == comparison_id).first()
    if not report:
        report = Report(comparison_id=comparison_id, status="generating")
        db.add(report)
        db.commit()
        db.refresh(report)
        comp.report_id = report.id
        db.add(comp)
        db.commit()
    else:
        report.status = "generating"
        db.add(report)
        db.commit()
    return {"report_id": report.id, "status": report.status}

@router.get("/{report_id}/download")
def download_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != "ready" or not report.storage_path:
        raise HTTPException(status_code=404, detail="Report not ready")
    path = Path(get_file_path(report.storage_path))
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name)
