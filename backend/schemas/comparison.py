# backend/schemas/comparison.py
from datetime import datetime

from pydantic import BaseModel, Field
from typing import List, Optional, Any

class UploadedFileOut(BaseModel):
    id: int
    filename: str
    size: int
    mime: str

    model_config = {"from_attributes": True}

class UploadResponse(BaseModel):
    files: List[UploadedFileOut]

class ComparisonCreateIn(BaseModel):
    title: Optional[str]
    file_ids: List[int]
    options: Optional[dict] = None

class ComparisonOut(BaseModel):
    id: int
    title: Optional[str]
    status: str
    summary: Optional[str] = None
    risk_counts: Optional[dict] = None
    report_id: Optional[int] = None

    model_config = {"from_attributes": True}

class ChangeItemOut(BaseModel):
    id: int
    kind: str
    location: dict
    before: Optional[str]
    after: Optional[str]
    linked_law: Optional[dict]
    risk_level: Optional[str]
    recommendation: Optional[str]

    model_config = {"from_attributes": True}

class PaginatedChangeItems(BaseModel):
    items: List[ChangeItemOut]
    page: int
    total_pages: int


# backend/schemas/comparison.py  (дополнения)
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class DocumentOut(BaseModel):
    id: int
    filename: str
    mime: Optional[str]
    size: Optional[int]
    storage_path: Optional[str]

    model_config = {"from_attributes": True}

class ComparisonListItem(BaseModel):
    id: int
    title: Optional[str]
    status: str
    created_at: Optional[datetime]
    report_id: Optional[int]

    model_config = {"from_attributes": True}
