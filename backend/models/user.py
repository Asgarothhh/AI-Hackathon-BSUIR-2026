# backend/models/user.py
from sqlalchemy import Column, Integer, String, Boolean, Index, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("ux_users_username_lower", func.lower(username), unique=True),
    )
