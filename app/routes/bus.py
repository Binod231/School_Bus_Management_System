from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.db.session import get_db
from app.core.jwt import get_current_active_user
from app.schemas.bus import BusResponse, BusRouteResponse, BusStopResponse
from app.services.bus import get_buses, get_bus_routes, get_bus_stops
from app.services.trip import get_active_trips_with_locations, get_latest_location_update_for_trips
from app.models import Bus, Trip, BusRoute, BusStop, BusRouteStop, User # Import User model
from sqlalchemy import func, select
from datetime import datetime, date

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])

# --- Security Dependency for ADMIN ONLY ---
async def get_current_admin_user(current_user: User = Depends(get_current_active_user)):
    """Dependency to ensure the user has the 'admin' role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user

# --- NEW: Security Dependency for ADMIN or GUARDIAN ---
async def get_admin_or_guardian_user(current_user: User = Depends(get_current_active_user)):
    """Dependency to ensure the user has either 'admin' or 'guardian' role."""
    if current_user.role not in ["admin", "guardian"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to Admins and Guardians only"
        )
    return current_user

# --- Reusable dependency lists for cleaner routes ---
admin_only = [Depends(get_current_admin_user)]
admin_or_guardian = [Depends(get_admin_or_guardian_user)]


@router.get(
    "/buses", 
    response_model=List[BusResponse],
    summary="[Admin] List all buses for a school",
    dependencies=admin_only
)
async def list_buses(
    school_id: int,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all buses for a school (Admin endpoint)"""
    buses = await get_buses(db, school_id=school_id, skip=skip, limit=limit)
    return buses


@router.get(
    "/bus-routes", 
    response_model=List[BusRouteResponse],
    summary="[Admin] List all bus routes for a school",
    dependencies=admin_only
)
async def list_bus_routes(
    school_id: int,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all bus routes for a school (Admin endpoint)"""
    routes = await get_bus_routes(db, school_id=school_id, skip=skip, limit=limit)
    return routes


@router.get(
    "/bus-stops", 
    response_model=List[BusStopResponse],
    summary="[Admin] List all bus stops for a school",
    dependencies=admin_only
)
async def list_bus_stops(
    school_id: int,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all bus stops for a school (Admin endpoint)"""
    stops = await get_bus_stops(db, school_id=school_id, skip=skip, limit=limit)
    return stops

# --- MODIFIED ROUTE: Now accessible by Admins and Guardians ---
@router.get(
    "/schools/{school_id}/live-locations",
    summary="[Admin/Guardian] Get live bus locations",
    description="Endpoint for Admins and Guardians to get live location updates for active bus trips.",
    dependencies=admin_or_guardian  # <-- Uses the new dependency
)
async def get_live_bus_locations(
    school_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get live bus locations for a school (Admin/Guardian endpoint)"""
    active_trips = await get_active_trips_with_locations(db, school_id)
    trip_ids = [trip.id for trip in active_trips]
    latest_updates = await get_latest_location_update_for_trips(db, trip_ids)
    
    result = []
    for trip in active_trips:
        latest_location = latest_updates.get(trip.id)
        
        result.append({
            "id": trip.bus.id, # Use bus ID for the key
            "trip_id": trip.id,
            "trip_name": trip.name,
            "bus_number": trip.bus.bus_number,
            "driver_name": f"{trip.driver.first_name} {trip.driver.last_name}" if trip.driver else "N/A",
            "driver_phone": trip.driver.phone if trip.driver else "N/A",
            "route_name": trip.route.name,
            "status": trip.status,
            "latest_location": {
                "latitude": float(latest_location.latitude) if latest_location else None,
                "longitude": float(latest_location.longitude) if latest_location else None,
                "timestamp": latest_location.timestamp.isoformat() if latest_location else None,
                "speed": float(latest_location.speed) if latest_location and latest_location.speed else 0,
                "heading": float(latest_location.heading) if latest_location and latest_location.heading else 0
            } if latest_location else None,
            "students_count": len([ts for ts in trip.students if ts.status == "on_bus"])
        })
    
    return result


@router.get(
    "/schools/{school_id}/bus-status",
    summary="[Admin] Get bus status overview",
    dependencies=admin_only
)
async def get_bus_status_overview(
    school_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get bus status overview for a school (Admin endpoint)"""
    total_buses = await db.scalar(
        select(func.count(Bus.id)).where(
            Bus.school_id == school_id,
            Bus.is_active == True
        )
    )
    
    active_trips_query = select(func.count(Trip.id)).join(BusRoute).where(
        BusRoute.school_id == school_id,
        Trip.status == "in_progress"
    )
    active_trips = await db.scalar(active_trips_query)

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())
    
    scheduled_trips = await db.scalar(
        select(func.count(Trip.id)).where(
            Trip.route.has(BusRoute.school_id == school_id),
            Trip.scheduled_start >= today_start,
            Trip.scheduled_start <= today_end,
            Trip.status == "scheduled"
        )
    )
    
    completed_trips = await db.scalar(
        select(func.count(Trip.id)).where(
            Trip.route.has(BusRoute.school_id == school_id),
            Trip.actual_end >= today_start,
            Trip.actual_end <= today_end,
            Trip.status == "completed"
        )
    )
    
    return {
        "total_buses": total_buses or 0,
        "active_trips": active_trips or 0,
        "scheduled_trips_today": scheduled_trips or 0,
        "completed_trips_today": completed_trips or 0
    }