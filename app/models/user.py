import enum
from sqlalchemy import Column, Integer, String, Boolean, Enum, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

class UserRole(str, enum.Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    DRIVER = "driver"
    GUARDIAN = "guardian"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # School association (except for superadmin)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=True)
    school = relationship("School", back_populates="users")
    
    # Driver specific fields
    license_number = Column(String, nullable=True)
    license_expiry = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    driver_buses = relationship("BusDriver", back_populates="driver")
    guardian_students = relationship("Guardian", back_populates="user")
    incidents_reported = relationship("Incident", back_populates="reported_by", foreign_keys="Incident.reported_by_id")
    incidents_resolved = relationship("Incident", back_populates="resolved_by", foreign_keys="Incident.resolved_by_id")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="refresh_tokens")