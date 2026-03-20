from pydantic import BaseModel, Field
from typing import List, Optional

class UserCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=1024)

class UserOut(BaseModel):
    id: int
    email: str
    is_active: bool

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    expires_in: int

class TokenPayload(BaseModel):
    sub: int
    exp: int
    type: str

class RoleAssignIn(BaseModel):
    user_id: int
    role_name: str
