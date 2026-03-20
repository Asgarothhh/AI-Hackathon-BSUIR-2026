from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, Index
from sqlalchemy.orm import relationship
from src.backend.models.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Отношение к ролям через таблицу user_roles
    roles = relationship("Role", secondary="user_roles", back_populates="users")

    __table_args__ = (
        Index("ux_users_username_lower", func.lower(username), unique=True),
    )
