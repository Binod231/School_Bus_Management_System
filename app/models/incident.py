from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


class IncidentType(str, enum.Enum):
    ACCIDENT = "accident"
    EMERGENCY = "emergency"
    ABSENCE = "absence"
    BEHAVIOR = "behavior"
    OTHER = "other"


class IncidentStatus(str, enum.Enum):
    REPORTED = "reported"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(Enum(IncidentType), nullable=False)
    status = Column(Enum(IncidentStatus), default=IncidentStatus.REPORTED)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    reported_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # School association
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    school = relationship("School", back_populates="incidents")
    
    # Student association (if applicable)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=True)
    student = relationship("Student", back_populates="incidents")
    
    # Reporter association
    reported_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reported_by = relationship("User", back_populates="incidents_reported", foreign_keys=[reported_by_id])
    
    # Resolver association (if applicable)
    resolved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_by = relationship("User", back_populates="incidents_resolved", foreign_keys=[resolved_by_id])
    
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=True)
    trip = relationship("Trip", back_populates="incidents")
    