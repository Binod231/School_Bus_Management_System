from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Date
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from typing import Optional
from datetime import datetime
from app.db.base import Base


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=False)
    grade = Column(String, nullable=False)
    student_id = Column(String, unique=True, nullable=False)
    qr_code = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # School association
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    school = relationship("School", back_populates="students")
    
    # Bus route association
    bus_route_id = Column(Integer, ForeignKey("bus_routes.id"), nullable=True)
    bus_route = relationship("BusRoute", back_populates="students")
    
    # Bus stop association
    bus_stop_id = Column(Integer, ForeignKey("bus_stops.id"), nullable=True)
    bus_stop = relationship("BusStop", back_populates="students")
    
    # Relationships
    guardians = relationship("GuardianStudent", back_populates="student")
    trip_attendances = relationship("TripStudent", back_populates="student")
    incidents = relationship("Incident", back_populates="student")


class Guardian(Base):
    __tablename__ = "guardians"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    fcm_token = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="guardian_students")
    students = relationship("GuardianStudent", back_populates="guardian", cascade="all, delete-orphan")


class GuardianStudent(Base):
    __tablename__ = "guardian_students"

    id = Column(Integer, primary_key=True, index=True)
    guardian_id = Column(Integer, ForeignKey("guardians.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    relationship_type = Column(String, nullable=False)  # Mother, Father, Grandparent, etc.
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    guardian = relationship("Guardian", back_populates="students")
    student = relationship("Student", back_populates="guardians")
    