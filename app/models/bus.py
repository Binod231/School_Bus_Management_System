# app/models/bus.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base import Base


class Bus(Base):
    __tablename__ = "buses"

    id = Column(Integer, primary_key=True, index=True)
    bus_number = Column(String, nullable=False)
    capacity = Column(Integer, nullable=False)
    make = Column(String, nullable=True)
    model = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    color = Column(String, nullable=True)
    license_plate = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # School association
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    school = relationship("School", back_populates="buses")

    # Relationships
    drivers = relationship("BusDriver", back_populates="bus")
    routes = relationship("BusRoute", back_populates="bus")
    trips = relationship("Trip", back_populates="bus")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class BusRoute(Base):
    __tablename__ = "bus_routes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # School association
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    school = relationship("School", back_populates="bus_routes")

    # Bus association
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False)
    bus = relationship("Bus", back_populates="routes")

    # Relationships
    stops = relationship("BusRouteStop", back_populates="route")
    students = relationship("Student", back_populates="bus_route")
    trips = relationship("Trip", back_populates="route")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class BusStop(Base):
    __tablename__ = "bus_stops"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    address = Column(Text, nullable=False)
    latitude = Column(String, nullable=False)
    longitude = Column(String, nullable=False)
    sequence = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    route_stops = relationship("BusRouteStop", back_populates="stop")
    students = relationship("Student", back_populates="bus_stop")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class BusRouteStop(Base):
    __tablename__ = "bus_route_stops"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("bus_routes.id"), nullable=False)
    stop_id = Column(Integer, ForeignKey("bus_stops.id"), nullable=False)
    estimated_arrival_time = Column(DateTime(timezone=True), nullable=False)
    sequence = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    route = relationship("BusRoute", back_populates="stops")
    stop = relationship("BusStop", back_populates="route_stops")


class BusDriver(Base):
    __tablename__ = "bus_drivers"

    id = Column(Integer, primary_key=True, index=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    unassigned_at = Column(DateTime(timezone=True), nullable=True)

    bus = relationship("Bus", back_populates="drivers")
    driver = relationship("User", back_populates="driver_buses")