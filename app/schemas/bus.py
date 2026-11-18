from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
from app.schemas.user import UserResponse


class BusBase(BaseModel):
    bus_number: str
    capacity: int
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    color: Optional[str] = None
    license_plate: str
    current_odometer: Optional[float] = 0.0
    insurance_expiry: Optional[datetime] = None
    fitness_certificate_expiry: Optional[datetime] = None


class BusCreate(BusBase):
    school_id: int


class BusUpdate(BaseModel):
    bus_number: Optional[str] = None
    capacity: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    color: Optional[str] = None
    license_plate: Optional[str] = None
    current_odometer: Optional[float] = None
    insurance_expiry: Optional[datetime] = None
    fitness_certificate_expiry: Optional[datetime] = None
    is_active: Optional[bool] = None


class BusResponse(BusBase):
    id: int
    school_id: int
    current_odometer: Optional[float] = 0.0
    insurance_expiry: Optional[datetime] = None
    fitness_certificate_expiry: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    assigned_driver: Optional[UserResponse] = None

    class Config:
        from_attributes = True


class BusRouteBase(BaseModel):
    name: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime


class BusRouteCreate(BusRouteBase):
    school_id: int
    bus_id: int


class BusRouteUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_active: Optional[bool] = None


class BusRouteResponse(BusRouteBase):
    id: int
    school_id: int
    bus_id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    bus: Optional[BusResponse] = None

    class Config:
        from_attributes = True


class BusStopBase(BaseModel):
    name: str
    address: str
    latitude: str
    longitude: str
    sequence: int


class BusStopCreate(BusStopBase):
    pass


class BusStopUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    sequence: Optional[int] = None
    is_active: Optional[bool] = None


class BusStopResponse(BusStopBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BusRouteStopBase(BaseModel):
    estimated_arrival_time: datetime
    sequence: int


class BusRouteStopCreate(BusRouteStopBase):
    route_id: int
    stop_id: int


class BusRouteStopMinimal(BaseModel):
    stop_id: int
    sequence: Optional[int] = None

class BusRouteStopsBulkUpdate(BaseModel):
    stop_ids: Optional[List[int]] = None
    bus_stop_ids: Optional[List[int]] = None
    stops: Optional[List[BusRouteStopMinimal]] = None


class BusRouteStopResponse(BusRouteStopBase):
    id: int
    route_id: int
    stop_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class BusDriverBase(BaseModel):
    is_active: bool = True


class BusDriverCreate(BusDriverBase):
    bus_id: int
    driver_id: int


class BusDriverResponse(BusDriverBase):
    id: int
    bus_id: int
    driver_id: int
    assigned_at: datetime
    unassigned_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BusWithDriversResponse(BusResponse):
    drivers: List[BusDriverResponse] = []


class BusRouteWithStopsResponse(BusRouteResponse):
    stops: List[BusRouteStopResponse] = []
    
class LocationState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    latitude: float
    longitude: float
    timestamp: datetime
    speed: Optional[float] = None
    heading: Optional[float] = None

class StudentRosterEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    student_id: int
    first_name: str
    last_name: str
    status: str
    boarded_at: Optional[datetime] = None
    guardian_name: Optional[str] = None
    guardian_phone: Optional[str] = None
    profile_picture_url: Optional[str] = None


class ActiveBusLocation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bus_number: str
    driver_name: str
    driver_phone: Optional[str] = None
    route_name: str
    current_location: Optional[LocationState] = None
    status: str
    trip_id: str
    total_students: int
    boarded_students: int
    dropped_off_students: int
    arrived_students: int
    student_roster: List[StudentRosterEntry] = []


class BusMaintenanceCreate(BaseModel):
    service_type: str  # ROUTINE, REPAIR, INSPECTION, OIL_CHANGE, TIRES
    status: Optional[str] = "COMPLETED"
    cost: Optional[float] = Field(None, description="Maintenance cost in Nepali Rupees (NPR / Rs.)")
    currency: Optional[str] = Field("NPR", description="Currency code (defaults to NPR - Nepali Rupee)")
    odometer_reading: Optional[float] = None
    performed_at: Optional[datetime] = None
    next_service_due_date: Optional[datetime] = None
    next_service_due_odometer: Optional[float] = None
    performed_by: Optional[str] = None
    notes: Optional[str] = None


class BusMaintenanceResponse(BaseModel):
    id: int
    bus_id: int
    school_id: int
    service_type: str
    status: str
    cost: Optional[float] = Field(None, description="Maintenance cost in Nepali Rupees (NPR / Rs.)")
    currency: str = Field("NPR", description="Currency code (defaults to NPR - Nepali Rupee)")
    odometer_reading: Optional[float] = None
    performed_at: datetime
    next_service_due_date: Optional[datetime] = None
    next_service_due_odometer: Optional[float] = None
    performed_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FleetExpiryAlert(BaseModel):
    bus_id: int
    bus_number: str
    license_plate: Optional[str] = None
    alert_type: str  # INSURANCE_EXPIRING, FITNESS_EXPIRING, SERVICE_OVERDUE
    severity: str    # WARNING, CRITICAL
    due_date: Optional[datetime] = None
    days_remaining: Optional[int] = None
    message: str
