from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
from app.schemas.student import StudentResponse
from app.models.trip import TripDirection
from app.schemas.bus import BusResponse, BusRouteResponse


class TripStatusEnum(str, Enum):
    scheduled = "SCHEDULED"
    in_progress = "IN_PROGRESS"
    completed = "COMPLETED"
    cancelled = "CANCELLED"


class TripTypeEnum(str, Enum):
    morning = "MORNING"
    afternoon = "AFTERNOON"
    evening = "EVENING"
    special = "SPECIAL"


class StudentStatusEnum(str, Enum):
    at_home = "AT_HOME"
    on_bus = "ON_BUS"
    dropped_off = "DROPPED_OFF"
    at_school = "AT_SCHOOL"


class TripBase(BaseModel):
    name: str
    type: TripTypeEnum
    direction: TripDirection
    status: TripStatusEnum = TripStatusEnum.scheduled
    scheduled_start: datetime
    scheduled_end: datetime
    
    @field_validator('type', 'direction', 'status', mode='before')
    @classmethod
    def uppercase_enums(cls, v):
        if isinstance(v, str):
            return v.upper()
        return v
    


class TripCreate(TripBase):
    bus_id: Optional[int] = None
    route_id: Optional[int] = None
    driver_id: Optional[int] = None


class TripUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[TripTypeEnum] = None
    status: Optional[TripStatusEnum] = None
    direction: Optional[TripDirection] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None

class TripStudentBase(BaseModel):
    status: StudentStatusEnum = StudentStatusEnum.at_home
class TripStudentResponse(TripStudentBase):
    id: int
    trip_id: int
    student_id: int
    boarded_at: Optional[datetime] = None
    disembarked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    student: StudentResponse

    class Config:
        from_attributes = True
class LocationUpdateBase(BaseModel):
    latitude: float
    longitude: float
    speed: Optional[float] = None
    heading: Optional[float] = None


class LocationUpdateCreate(LocationUpdateBase):
    trip_id: int


class LocationUpdateResponse(LocationUpdateBase):
    id: int
    trip_id: int
    timestamp: datetime

    class Config:
        from_attributes = True
class TripResponse(TripBase):
    id: int
    bus_id: int
    route_id: int
    driver_id: int
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    latest_location: Optional[LocationUpdateResponse] = None
    students: List[TripStudentResponse] = []
    bus: Optional[BusResponse] = None
    route: Optional[BusRouteResponse] = None
    student_trip_status: Optional[str] = None

    class Config:
        from_attributes = True





class TripStudentCreate(TripStudentBase):
    trip_id: int
    student_id: int


class TripStudentUpdate(BaseModel):
    status: Optional[StudentStatusEnum] = None
    boarded_at: Optional[datetime] = None
    disembarked_at: Optional[datetime] = None








class TripWithStudentsResponse(TripResponse):
    students: List[TripStudentResponse] = []


class TripWithLocationUpdatesResponse(TripResponse):
    location_updates: List[LocationUpdateResponse] = []
    
class MarkStudentsBoardedRequest(BaseModel):
    student_ids: List[int]