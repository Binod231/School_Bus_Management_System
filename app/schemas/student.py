from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date

class StudentBase(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    grade: str
    student_id: str

class StudentCreate(StudentBase):
    school_id: int
    bus_route_id: Optional[int] = None
    bus_stop_id: Optional[int] = None

class StudentUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    grade: Optional[str] = None
    student_id: Optional[str] = None
    bus_route_id: Optional[int] = None
    bus_stop_id: Optional[int] = None
    is_active: Optional[bool] = None

class StudentResponse(StudentBase):
    id: int
    school_id: int
    bus_route_id: Optional[int] = None
    bus_stop_id: Optional[int] = None
    qr_code: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class GuardianBase(BaseModel):
    fcm_token: Optional[str] = None

class GuardianCreate(GuardianBase):
    user_id: int

class GuardianUpdate(GuardianBase):
    pass

class GuardianResponse(GuardianBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class GuardianStudentBase(BaseModel):
    relationship: str
    is_primary: bool = False

class GuardianStudentCreate(GuardianStudentBase):
    guardian_id: int
    student_id: int

class GuardianStudentResponse(GuardianStudentBase):
    id: int
    guardian_id: int
    student_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class StudentWithGuardiansResponse(StudentResponse):
    guardians: List[GuardianStudentResponse] = []


class GuardianWithStudentsResponse(GuardianResponse):
    students: List[GuardianStudentResponse] = []