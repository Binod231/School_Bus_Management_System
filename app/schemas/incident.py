from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class IncidentTypeEnum(str, Enum):
    accident = "accident"
    emergency = "emergency"
    absence = "absence"
    behavior = "behavior"
    other = "other"


class IncidentStatusEnum(str, Enum):
    reported = "reported"
    under_review = "under_review"
    resolved = "resolved"
    closed = "closed"


class IncidentBase(BaseModel):
    type: IncidentTypeEnum
    title: str
    description: str
    occurred_at: datetime


class IncidentCreate(IncidentBase):
    school_id: int
    student_id: Optional[int] = None
    reported_by_id: int


class IncidentUpdate(BaseModel):
    type: Optional[IncidentTypeEnum] = None
    status: Optional[IncidentStatusEnum] = None
    title: Optional[str] = None
    description: Optional[str] = None
    occurred_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None
    resolved_by_id: Optional[int] = None


class IncidentResponse(IncidentBase):
    id: int
    school_id: int
    student_id: Optional[int] = None
    status: IncidentStatusEnum
    reported_by_id: int
    resolved_by_id: Optional[int] = None
    reported_at: datetime
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True