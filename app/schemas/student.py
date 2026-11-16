from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime, date
from pydantic.networks import EmailStr
from app.schemas.user import UserResponse
from app.schemas.bus import BusRouteResponse, BusStopResponse
class StudentBase(BaseModel):
    first_name: str
    last_name: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    date_of_birth: date
    grade: str
    student_id: str
    

class StudentCreate(StudentBase):
    school_id: int
    bus_route_id: Optional[int] = None
    bus_stop_id: Optional[int] = None

    # Add this validator to handle the date string
    @field_validator('date_of_birth', mode='before')
    @classmethod
    def format_date(cls, value):
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value

class StudentUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    date_of_birth: Optional[date] = None
    grade: Optional[str] = None
    student_id: Optional[str] = None
    bus_route_id: Optional[int] = None
    bus_stop_id: Optional[int] = None
    is_active: Optional[bool] = None
    qr_code: Optional[str] = None

class GuardianForStudentResponse(BaseModel):
    id: int
    user: UserResponse

    class Config:
        from_attributes = True
class GuardianBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    # fcm_token: Optional[str] = None

class GuardianCreate(GuardianBase):
    password: str
    student_ids: Optional[List[int]] = None
class GuardianUpdate(GuardianBase):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    fcm_token: Optional[str] = None
    student_ids: Optional[List[int]] = None


class GuardianResponse(GuardianBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: Optional[bool] = True 
    student_count: Optional[int] = 0

    class Config:
        from_attributes = True

class GuardianStudentBase(BaseModel):
    relationship_type: str
    is_primary: bool = False

class GuardianStudentCreate(GuardianStudentBase):
    guardian_id: int
    student_id: int

class GuardianStudentResponse(GuardianStudentBase):
    id: int
    guardian_id: int
    student_id: int
    alert_radius_meters: Optional[float] = 500.0
    notify_on_approaching: Optional[bool] = True
    created_at: datetime
    guardian: GuardianForStudentResponse

    class Config:
        from_attributes = True

class StudentResponse(StudentBase):
    id: int
    school_id: int
    bus_route: Optional[BusRouteResponse] = None
    bus_route_id: Optional[int] = None
    bus_stop: Optional[BusStopResponse] = None
    bus_stop_id: Optional[int] = None
    qr_code: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    guardians: List[GuardianStudentResponse] = []

    class Config:
        from_attributes = True
class StudentWithGuardiansResponse(StudentResponse):
    guardians: List[GuardianStudentResponse] = []


class GuardianWithStudentsResponse(GuardianResponse):
    students: List[GuardianStudentResponse] = []


class AlertPreferenceUpdate(BaseModel):
    alert_radius_meters: float
    notify_on_approaching: bool = True


class AlertPreferenceResponse(BaseModel):
    student_id: int
    alert_radius_meters: float
    notify_on_approaching: bool


class StudentAbsenceCreate(BaseModel):
    date: date
    trip_type: str = "ALL_DAY"  # MORNING, AFTERNOON, ALL_DAY
    reason: Optional[str] = None


class StudentAbsenceResponse(BaseModel):
    id: int
    student_id: int
    school_id: int
    date: date
    trip_type: str
    reason: Optional[str] = None
    reported_by_id: int
    created_at: datetime

    class Config:
        from_attributes = True
