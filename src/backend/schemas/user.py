from pydantic import BaseModel, Field

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=1024)

    model_config = {
        "from_attributes": True
    }

class UserOut(BaseModel):
    id: int
    username: str

    model_config = {
        "from_attributes": True
    }
