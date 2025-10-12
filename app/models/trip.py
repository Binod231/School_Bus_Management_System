from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Enum, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


class TripStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TripType(str, enum.Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    SPECIAL = "special"

class TripDirection(str, enum.Enum):
    TO_SCHOOL = "to_school"
    FROM_SCHOOL = "from_school"
class StudentStatus(str, enum.Enum):
    AT_HOME = "at_home"
    ON_BUS = "on_bus"
    AT_SCHOOL = "at_school"


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(Enum(TripType), nullable=False)
    direction = Column(Enum(TripDirection), nullable=False)
    status = Column(Enum(TripStatus), default=TripStatus.SCHEDULED)
    scheduled_start = Column(DateTime(timezone=True), nullable=False)
    actual_start = Column(DateTime(timezone=True), nullable=True)
    scheduled_end = Column(DateTime(timezone=True), nullable=False)
    actual_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Bus association
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False)
    bus = relationship("Bus", back_populates="trips")
    
    # Route association
    route_id = Column(Integer, ForeignKey("bus_routes.id"), nullable=False)
    route = relationship("BusRoute", back_populates="trips")
    
    # Driver association
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    driver = relationship("User")
    
    # Relationships
    students = relationship("TripStudent", back_populates="trip")
    location_updates = relationship("LocationUpdate", back_populates="trip")
    incidents = relationship("Incident", back_populates="trip", cascade="all, delete-orphan")


class TripStudent(Base):
    __tablename__ = "trip_students"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    status = Column(Enum(StudentStatus), default=StudentStatus.AT_HOME)
    boarded_at = Column(DateTime(timezone=True), nullable=True)
    disembarked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    trip = relationship("Trip", back_populates="students")
    student = relationship("Student", back_populates="trip_attendances")


class LocationUpdate(Base):
    __tablename__ = "location_updates"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed = Column(Float, nullable=True)
    heading = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    trip = relationship("Trip", back_populates="location_updates")