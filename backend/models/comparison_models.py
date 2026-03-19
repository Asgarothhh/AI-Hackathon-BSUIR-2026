# backend/models/comparison_models.py
from sqlalchemy import Column, Integer, Text, TIMESTAMP, func, JSON, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from backend.models.base import Base

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    filename = Column(Text, nullable=False)
    mime = Column(Text, nullable=False)
    size = Column(BigInteger, nullable=True)
    storage_path = Column(Text, nullable=False)
    uploaded_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    comparison_id = Column(Integer, unique=True)
    status = Column(Text, nullable=False, server_default="pending")
    storage_path = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Comparison(Base):
    __tablename__ = "comparisons"
    id = Column(Integer, primary_key=True)
    title = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(Text, nullable=False, server_default="queued")
    options = Column(JSON, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    finished_at = Column(TIMESTAMP(timezone=True), nullable=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=True)

    files = relationship("Document", secondary="comparison_files", viewonly=True)

class ComparisonFile(Base):
    __tablename__ = "comparison_files"
    comparison_id = Column(Integer, ForeignKey("comparisons.id", ondelete="CASCADE"), primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    role = Column(Text, nullable=True)

class ChangeItem(Base):
    __tablename__ = "change_items"
    id = Column(Integer, primary_key=True)
    comparison_id = Column(Integer, ForeignKey("comparisons.id", ondelete="CASCADE"))
    kind = Column(Text)
    location = Column(JSON)
    before = Column(Text)
    after = Column(Text)
    linked_law = Column(JSON)
    risk_level = Column(Text)
    recommendation = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
