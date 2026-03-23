from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SchoolBase(BaseModel):
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone: str
    email: str
    website: Optional[str] = None
    logo_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class SchoolCreate(SchoolBase):
    pass


class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: Optional[bool] = None


class SchoolResponse(SchoolBase):
    id: int
    is_active: bool
    admin_assigned: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True