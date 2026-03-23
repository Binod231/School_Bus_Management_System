from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum
from typing import List
from app.schemas.bus import BusResponse
from app.schemas.trip import TripResponse
from app.schemas.user import UserResponse


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
    driver_id: Optional[int] = None
    bus_id: Optional[int] = None


class IncidentCreate(IncidentBase):
    school_id: int
    student_id: Optional[int] = None
    reported_by_id: int
class IncidentCreateForDriver(IncidentBase):
    trip_id: Optional[int] = None
    title: str
    description: str
    type: IncidentTypeEnum
    occurred_at: datetime
    student_id: Optional[int] = None
    trip_id: Optional[int] = None
    
class IncidentUpdateForDriver(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[IncidentStatusEnum] = None
    type: Optional[IncidentTypeEnum] = None
    occurred_at: Optional[datetime] = None
    student_id: Optional[int] = None
    resolution: Optional[str] = None

    class Config:
        form_attributes = True

class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[IncidentStatusEnum] = None
    type: Optional[IncidentTypeEnum] = None
    occurred_at: Optional[datetime] = None
    resolution: Optional[str] = None
    student_id: Optional[int] = []
    bus_id: Optional[int] = None
    driver_id: Optional[int] = None

    class Config:
        from_attributes = True


class IncidentResponse(BaseModel):
    id: int
    type: IncidentTypeEnum
    title: str
    description: str
    occurred_at: datetime
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
    trip_id: Optional[int] = None
    bus_id: Optional[int] = None
    driver_id: Optional[int] = None
    reported_by: Optional[UserResponse] = None 

    class Config:
        from_attributes = True
        
