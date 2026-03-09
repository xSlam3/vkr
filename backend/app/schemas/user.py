from pydantic import BaseModel
from pydantic import ConfigDict
from typing import Literal
from datetime import datetime


class UserCreate(BaseModel):
    username: str
    password: str
    role: Literal["admin", "employee"] = "employee"


class UserUpdate(BaseModel):
    username: str | None = None
    password: str | None = None
    role: Literal["admin", "employee"] | None = None


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: str
    username: str
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
