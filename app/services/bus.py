from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload, Session
from app.models.bus import Bus, BusRoute, BusStop, BusRouteStop, BusDriver
from app.schemas.bus import BusCreate, BusUpdate, BusRouteCreate, BusRouteUpdate
from app.core.exceptions import NotFoundException
from typing import Optional, List
from app.core.cache import redis_client
import json
from datetime import datetime
from app import models
# Helper to serialize Bus objects, handling datetime
def bus_serializer(bus: Bus) -> dict:
    bus_dict = {c.name: getattr(bus, c.name) for c in bus.__table__.columns}
    for key, value in bus_dict.items():
        if isinstance(value, datetime):
            bus_dict[key] = value.isoformat()
    return bus_dict

async def get_bus_by_id(db: AsyncSession, bus_id: int) -> Bus:
    """Get bus by ID"""
    cache_key = f"bus:{bus_id}"
    cached_bus = await redis_client.get(cache_key)
    if cached_bus:
        bus_data = json.loads(cached_bus)
        # Convert isoformat strings back to datetime objects
        for key in ['created_at', 'updated_at']:
            if bus_data.get(key):
                bus_data[key] = datetime.fromisoformat(bus_data[key])
        return Bus(**bus_data)

    result = await db.execute(select(Bus).where(Bus.id == bus_id))
    bus = result.scalar_one_or_none()
    if not bus:
        raise NotFoundException("Bus", bus_id)
    
    await redis_client.set(cache_key, json.dumps(bus_serializer(bus)), ex=3600)
    return bus


async def get_buses(
    db: AsyncSession,
    school_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Bus]:
    """Get buses with optional school filter and assigned driver"""
    query = (
        select(Bus)
        .options(
            selectinload(Bus.drivers)
            .selectinload(BusDriver.driver)
        )
    )
    if school_id is not None:
        query = query.where(Bus.school_id == school_id)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    buses = result.scalars().unique().all()

    for bus in buses:
        active_driver = next((d.driver for d in bus.drivers if d.is_active), None)
        if active_driver:
            bus.assigned_driver = active_driver
        else:
            bus.assigned_driver = None

    return buses


async def create_bus(db: AsyncSession, bus_data: dict) -> Bus:
    """Create a new bus"""
    db_bus = Bus(**bus_data)
    db.add(db_bus)
    await db.commit()
    await db.refresh(db_bus)
    return db_bus


async def update_bus(db: AsyncSession, bus_id: int, bus_data: dict) -> Bus:
    """Update a bus"""
    result = await db.execute(
        update(Bus)
        .where(Bus.id == bus_id)
        .values(**bus_data)
        .returning(Bus)
    )
    await db.commit()
    updated_bus = result.scalar_one_or_none()
    if not updated_bus:
        raise NotFoundException("Bus", bus_id)
    
    await redis_client.delete(f"bus:{bus_id}")
    return updated_bus


async def delete_bus(db: AsyncSession, bus_id: int) -> bool:
    """Delete a bus"""
    result = await db.execute(delete(Bus).where(Bus.id == bus_id))
    await db.commit()
    if result.rowcount == 0:
        raise NotFoundException("Bus", bus_id)
    
    await redis_client.delete(f"bus:{bus_id}")
    return True


async def get_bus_route_by_id(db: AsyncSession, route_id: int) -> BusRoute:
    """Get bus route by ID"""
    result = await db.execute(select(BusRoute).where(BusRoute.id == route_id))
    route = result.scalar_one_or_none()
    if not route:
        raise NotFoundException("BusRoute", route_id)
    return route


async def get_bus_routes(
    db: AsyncSession,
    school_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> List[BusRoute]:
    """Get bus routes with optional school filter"""
    # FIX: Eagerly load the related 'bus' and 'stops' to prevent validation errors
    query = (
        select(BusRoute)
        .options(selectinload(BusRoute.bus), selectinload(BusRoute.stops))
    )

    if school_id is not None:
        query = query.where(BusRoute.school_id == school_id)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    # Use .unique() to handle potential duplicates from the joins
    return result.scalars().unique().all()


async def create_bus_route(db: AsyncSession, route_data: dict) -> BusRoute:
    """Create a new bus route"""
    db_route = BusRoute(**route_data)
    db.add(db_route)
    await db.commit()
    await db.refresh(db_route)
    return db_route


async def update_bus_route(db: AsyncSession, route_id: int, route_data: dict) -> BusRoute:
    """Update a bus route"""
    result = await db.execute(
        update(BusRoute)
        .where(BusRoute.id == route_id)
        .values(**route_data)
        .returning(BusRoute)
    )
    await db.commit()
    updated_route = result.scalar_one_or_none()
    if not updated_route:
        raise NotFoundException("BusRoute", route_id)
    return updated_route


async def delete_bus_route(db: AsyncSession, route_id: int) -> bool:
    """Delete a bus route"""
    result = await db.execute(delete(BusRoute).where(BusRoute.id == route_id))
    await db.commit()
    if result.rowcount == 0:
        raise NotFoundException("BusRoute", route_id)
    return True


async def get_bus_stop_by_id(db: AsyncSession, stop_id: int) -> BusStop:
    """Get bus stop by ID"""
    result = await db.execute(select(BusStop).where(BusStop.id == stop_id))
    stop = result.scalar_one_or_none()
    if not stop:
        raise NotFoundException("BusStop", stop_id)
    return stop


async def get_bus_stops(
    db: AsyncSession,
    school_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> List[BusStop]:
    """Get bus stops with optional school filter"""
    query = select(BusStop)
    if school_id is not None:
        query = query.join(BusRouteStop).join(BusRoute).where(BusRoute.school_id == school_id)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


async def create_bus_stop(db: AsyncSession, stop_data: dict) -> BusStop:
    """Create a new bus stop"""
    db_stop = BusStop(**stop_data)
    db.add(db_stop)
    await db.commit()
    await db.refresh(db_stop)
    return db_stop


async def update_bus_stop(db: AsyncSession, stop_id: int, stop_data: dict) -> BusStop:
    """Update a bus stop"""
    result = await db.execute(
        update(BusStop)
        .where(BusStop.id == stop_id)
        .values(**stop_data)
        .returning(BusStop)
    )
    await db.commit()
    updated_stop = result.scalar_one_or_none()
    if not updated_stop:
        raise NotFoundException("BusStop", stop_id)
    return updated_stop


async def delete_bus_stop(db: AsyncSession, stop_id: int) -> bool:
    """Delete a bus stop"""
    result = await db.execute(delete(BusStop).where(BusStop.id == stop_id))
    await db.commit()
    if result.rowcount == 0:
        raise NotFoundException("BusStop", stop_id)
    return True


async def get_bus_drivers(db: AsyncSession, bus_id: int) -> List[BusDriver]:
    """Get all drivers for a bus"""
    result = await db.execute(select(BusDriver).where(BusDriver.bus_id == bus_id))
    return result.scalars().all()


async def assign_driver_to_bus(db: AsyncSession, assignment_data: dict) -> BusDriver:
    """Assign a driver to a bus"""
    # First, deactivate any existing assignments for this driver
    await db.execute(
        update(BusDriver)
        .where(BusDriver.driver_id == assignment_data['driver_id'])
        .values(is_active=False, unassigned_at=func.now())
    )

    # Create new assignment
    db_assignment = BusDriver(**assignment_data)
    db.add(db_assignment)
    await db.commit()
    await db.refresh(db_assignment)
    return db_assignment


async def get_bus_route_stops(db: AsyncSession, route_id: int) -> List[BusRouteStop]:
    """Get all stops for a bus route"""
    result = await db.execute(
        select(BusRouteStop)
        .where(BusRouteStop.route_id == route_id)
        .order_by(BusRouteStop.sequence)
    )
    return result.scalars().all()


async def add_stop_to_route(db: AsyncSession, route_stop_data: dict) -> BusRouteStop:
    """Add a stop to a bus route"""
    db_route_stop = BusRouteStop(**route_stop_data)
    db.add(db_route_stop)
    await db.commit()
    await db.refresh(db_route_stop)
    return db_route_stop


async def delete_route_stop(db: AsyncSession, route_id: int, stop_id: int) -> bool:
    """Remove a specific stop from a route"""
    result = await db.execute(
        delete(BusRouteStop).where(
            BusRouteStop.route_id == route_id,
            BusRouteStop.stop_id == stop_id
        )
    )
    await db.commit()
    return result.rowcount > 0


async def update_route_stops_bulk(db: AsyncSession, route_id: int, stop_ids: List[int]) -> List[BusRouteStop]:
    """Replace all stops for a route with a new list in order"""
    # 1. Remove all existing stops for this route
    await db.execute(delete(BusRouteStop).where(BusRouteStop.route_id == route_id))
    
    # 2. Add new stops in the specified sequence
    new_stops = []
    base_time = datetime.now() # Minimal placeholder for required time field
    
    for idx, stop_id in enumerate(stop_ids):
        new_stop = BusRouteStop(
            route_id=route_id,
            stop_id=stop_id,
            sequence=idx + 1,
            estimated_arrival_time=base_time # You might want to pass real times later
        )
        db.add(new_stop)
        new_stops.append(new_stop)
    
    await db.commit()
    return new_stops

