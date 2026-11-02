import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct
from app.models.school import School
from app.models.student import Student
from app.models.bus import Bus, BusRoute, BusStop
from app.models.user import User, UserRole
from app.models.trip import Trip, TripStatus, TripStudent, StudentStatus
from app.models.incident import Incident, IncidentStatus
from app.schemas.public import (
    PublicAnalyticsResponse,
    OverviewStats,
    LiveMetrics,
    SafetyMetrics,
    DisplayStats,
)
from app.core.cache import redis_client

CACHE_KEY = "public:landing_analytics"
CACHE_TTL = 60  # Cache for 60 seconds

def _format_stat(value: int) -> str:
    """Formats numbers for landing page display, e.g. 500+, 10K+."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M+".replace(".0M", "M")
    if value >= 1_000:
        return f"{value / 1_000:.1f}K+".replace(".0K", "K")
    if value > 0:
        return f"{value}+"
    return "0"

async def get_public_landing_analytics(db: AsyncSession) -> PublicAnalyticsResponse:
    # Check Redis cache first
    try:
        cached = await redis_client.get(CACHE_KEY)
        if cached:
            data = json.loads(cached)
            return PublicAnalyticsResponse(**data)
    except Exception:
        pass  # If redis is unavailable, proceed directly to DB query

    # 1. Total active schools & geographic reach
    total_schools = (await db.scalar(select(func.count(School.id)).where(School.is_active == True))) or 0
    cities_covered = (await db.scalar(select(func.count(distinct(School.city))).where(School.is_active == True))) or 0

    # 2. Total active students
    total_students = (await db.scalar(select(func.count(Student.id)).where(Student.is_active == True))) or 0

    # 3. Fleet & routes
    total_buses = (await db.scalar(select(func.count(Bus.id)).where(Bus.is_active == True))) or 0
    total_routes = (await db.scalar(select(func.count(BusRoute.id)).where(BusRoute.is_active == True))) or 0
    total_stops = (await db.scalar(select(func.count(BusStop.id)).where(BusStop.is_active == True))) or 0

    # 4. Users (Drivers & Guardians)
    total_drivers = (await db.scalar(
        select(func.count(User.id)).where(User.role == UserRole.DRIVER, User.is_active == True)
    )) or 0
    total_guardians = (await db.scalar(
        select(func.count(User.id)).where(User.role == UserRole.GUARDIAN, User.is_active == True)
    )) or 0

    # 5. Trips
    total_trips = (await db.scalar(select(func.count(Trip.id)))) or 0
    completed_trips = (await db.scalar(
        select(func.count(Trip.id)).where(Trip.status == TripStatus.COMPLETED)
    )) or 0
    active_trips = (await db.scalar(
        select(func.count(Trip.id)).where(Trip.status == TripStatus.IN_PROGRESS)
    )) or 0

    # 6. Live operational metrics
    buses_on_road = (await db.scalar(
        select(func.count(distinct(Trip.bus_id))).where(Trip.status == TripStatus.IN_PROGRESS)
    )) or 0
    students_in_transit = (await db.scalar(
        select(func.count(TripStudent.id))
        .join(Trip, TripStudent.trip_id == Trip.id)
        .where(Trip.status == TripStatus.IN_PROGRESS, TripStudent.status == StudentStatus.ON_BUS)
    )) or 0

    # 7. Incident & Safety metrics
    total_incidents = (await db.scalar(select(func.count(Incident.id)))) or 0
    resolved_incidents = (await db.scalar(
        select(func.count(Incident.id)).where(
            Incident.status.in_([IncidentStatus.RESOLVED, IncidentStatus.CLOSED])
        )
    )) or 0

    incident_trips_count = (await db.scalar(
        select(func.count(distinct(Incident.trip_id))).where(Incident.trip_id.isnot(None))
    )) or 0

    # Calculate safety score (% of completed trips without incidents)
    if completed_trips > 0:
        safe_trips = max(0, completed_trips - incident_trips_count)
        safety_score = round((safe_trips / completed_trips) * 100, 1)
    else:
        safety_score = 99.9

    if total_incidents > 0:
        incident_resolution_rate = round((resolved_incidents / total_incidents) * 100, 1)
    else:
        incident_resolution_rate = 100.0

    uptime_percentage = 99.9

    overview = OverviewStats(
        total_schools=total_schools,
        total_students=total_students,
        total_buses=total_buses,
        total_routes=total_routes,
        total_drivers=total_drivers,
        total_guardians=total_guardians,
        total_trips=total_trips,
        completed_trips=completed_trips,
        total_stops=total_stops,
        cities_covered=cities_covered,
    )

    live_metrics = LiveMetrics(
        active_trips=active_trips,
        buses_on_road=buses_on_road,
        students_in_transit=students_in_transit,
    )

    safety = SafetyMetrics(
        safety_score=safety_score,
        incident_resolution_rate=incident_resolution_rate,
        total_incidents=total_incidents,
        resolved_incidents=resolved_incidents,
        uptime_percentage=uptime_percentage,
    )

    display_stats = DisplayStats(
        schools=_format_stat(total_schools),
        students=_format_stat(total_students),
        buses=_format_stat(total_buses),
        trips=_format_stat(total_trips),
        safety_rate=f"{safety_score}%",
        uptime=f"{uptime_percentage}%",
    )

    response = PublicAnalyticsResponse(
        total_schools=total_schools,
        total_students=total_students,
        total_buses=total_buses,
        total_routes=total_routes,
        total_drivers=total_drivers,
        total_guardians=total_guardians,
        total_trips=total_trips,
        completed_trips=completed_trips,
        active_trips=active_trips,
        cities_covered=cities_covered,
        safety_score=safety_score,
        uptime_percentage=uptime_percentage,
        overview=overview,
        live_metrics=live_metrics,
        safety=safety,
        display_stats=display_stats,
    )

    # Store in Redis cache
    try:
        await redis_client.set(CACHE_KEY, json.dumps(response.dict()), ex=CACHE_TTL)
    except Exception:
        pass

    return response

