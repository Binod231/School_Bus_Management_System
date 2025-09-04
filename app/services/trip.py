from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, func
from app.models.trip import Trip, TripStudent, LocationUpdate, TripStatus
from app.models.bus import Bus, BusRoute
from app.models.user import User
from app.models.student import Student
from app.core.exceptions import NotFoundException
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import selectinload, joinedload


async def get_trip_by_id(db: AsyncSession, trip_id: int) -> Trip:
    """Get trip by ID with bus relationship eagerly loaded"""
    result = await db.execute(
        select(Trip)
        .options(selectinload(Trip.bus))
        .options(selectinload(Trip.route))
        .where(Trip.id == trip_id)
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise NotFoundException(f"Trip with id {trip_id} not found")

    return trip

async def get_trips(
    db: AsyncSession,
    school_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Trip]:
    """Get trips with optional school filter"""
    query = select(Trip)

    if school_id is not None:
        query = query.where(Trip.school_id == school_id)

    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


async def get_driver_trips(db: AsyncSession, driver_id: int, skip: int = 0, limit: int = 100) -> List[Trip]:
    """Get trips for a specific driver"""
    result = await db.execute(
        select(Trip)
        .where(Trip.driver_id == driver_id)
        .offset(skip)
        .limit(limit)
        .order_by(Trip.scheduled_start.desc())
    )
    return result.scalars().all()


async def get_student_trips(db: AsyncSession, student_id: int, skip: int = 0, limit: int = 100) -> List[Trip]:
    """Get trips for a specific student"""
    result = await db.execute(
        select(Trip)
        .join(TripStudent, TripStudent.trip_id == Trip.id)
        .where(TripStudent.student_id == student_id)
        .offset(skip)
        .limit(limit)
        .order_by(Trip.scheduled_start.desc())
    )
    return result.scalars().all()


async def get_active_trips(db: AsyncSession, school_id: Optional[int] = None) -> List[Trip]:
    """Get active trips (in progress)"""
    query = select(Trip).where(Trip.status == TripStatus.IN_PROGRESS)

    if school_id is not None:
        query = query.where(Trip.school_id == school_id)

    result = await db.execute(query)
    return result.scalars().all()


async def get_active_trips_with_locations(db: AsyncSession, school_id: Optional[int] = None) -> List[Trip]:
    """Get active trips with their location updates and other details"""
    query = select(Trip).where(Trip.status == TripStatus.IN_PROGRESS)

    if school_id is not None:
        query = query.join(Bus, Trip.bus_id == Bus.id).where(Bus.school_id == school_id)

    query = query.options(
        joinedload(Trip.bus),
        joinedload(Trip.driver),
        joinedload(Trip.route),
        selectinload(Trip.students)
    )

    result = await db.execute(query)
    return result.scalars().unique().all()


async def get_latest_location_update_for_trips(db: AsyncSession, trip_ids: List[int]) -> dict:
    """Get the latest location update for a list of trips using a single query"""
    if not trip_ids:
        return {}

    latest_updates_subq = select(
        LocationUpdate.trip_id,
        func.max(LocationUpdate.timestamp).label("max_timestamp")
    ).where(
        LocationUpdate.trip_id.in_(trip_ids)
    ).group_by(LocationUpdate.trip_id).subquery()

    result = await db.execute(
        select(LocationUpdate).join(
            latest_updates_subq,
            and_(
                LocationUpdate.trip_id == latest_updates_subq.c.trip_id,
                LocationUpdate.timestamp == latest_updates_subq.c.max_timestamp
            )
        )
    )

    latest_updates = {update.trip_id: update for update in result.scalars().all()}
    return latest_updates


async def get_active_student_trip(db: AsyncSession, student_id: int) -> Trip:
    """Get active trip for a student"""
    result = await db.execute(
        select(Trip)
        .join(TripStudent, TripStudent.trip_id == Trip.id)
        .where(
            and_(
                TripStudent.student_id == student_id,
                Trip.status == TripStatus.IN_PROGRESS
            )
        )
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise NotFoundException("Active Trip for Student", student_id)
    return trip


async def create_trip(db: AsyncSession, trip_data: dict) -> Trip:
    """Create a new trip"""
    db_trip = Trip(**trip_data)
    db.add(db_trip)
    await db.commit()
    await db.refresh(db_trip)
    return db_trip


async def update_trip(db: AsyncSession, trip_id: int, trip_data: dict) -> Trip:
    """Update a trip"""
    result = await db.execute(
        update(Trip)
        .where(Trip.id == trip_id)
        .values(**trip_data)
        .returning(Trip)
    )
    await db.commit()
    updated_trip = result.scalar_one_or_none()
    if not updated_trip:
        raise NotFoundException("Trip", trip_id)
    return updated_trip


async def delete_trip(db: AsyncSession, trip_id: int) -> bool:
    """Delete a trip"""
    result = await db.execute(delete(Trip).where(Trip.id == trip_id))
    await db.commit()
    if result.rowcount == 0:
        raise NotFoundException("Trip", trip_id)
    return True


async def get_trip_students(db: AsyncSession, trip_id: int) -> List[TripStudent]:
    """Get all students for a trip"""
    result = await db.execute(
        select(TripStudent).where(TripStudent.trip_id == trip_id)
    )
    return result.scalars().all()


async def get_trip_student(db: AsyncSession, trip_id: int, student_id: int) -> TripStudent:
    """Get a specific student on a trip"""
    result = await db.execute(
        select(TripStudent)
        .where(
            and_(
                TripStudent.trip_id == trip_id,
                TripStudent.student_id == student_id
            )
        )
    )
    trip_student = result.scalar_one_or_none()
    if not trip_student:
        raise NotFoundException("TripStudent", f"trip_id: {trip_id}, student_id: {student_id}")
    return trip_student


async def update_trip_student(db: AsyncSession, trip_id: int, student_id: int, student_data: dict) -> TripStudent:
    """Update a student's status on a trip"""
    result = await db.execute(
        update(TripStudent)
        .where(
            and_(
                TripStudent.trip_id == trip_id,
                TripStudent.student_id == student_id
            )
        )
        .values(**student_data)
        .returning(TripStudent)
    )
    await db.commit()
    updated_student = result.scalar_one_or_none()
    if not updated_student:
        raise NotFoundException("TripStudent", f"trip_id: {trip_id}, student_id: {student_id}")
    return updated_student


async def mark_all_students_boarded(db: AsyncSession, trip_id: int):
    """Mark all students as boarded for a trip"""
    from datetime import datetime

    trip = await get_trip_by_id(db, trip_id)

    from app.services.student import get_students_by_bus_route
    students = await get_students_by_bus_route(db, trip.route_id)

    for student in students:
        try:
            trip_student = await get_trip_student(db, trip_id, student.id)
            await update_trip_student(
                db, trip_id, student.id,
                {"status": "on_bus", "boarded_at": datetime.now()}
            )
        except NotFoundException:
            db_trip_student = TripStudent(
                trip_id=trip_id,
                student_id=student.id,
                status="on_bus",
                boarded_at=datetime.now()
            )
            db.add(db_trip_student)

    await db.commit()

async def get_trip_location_updates(db: AsyncSession, trip_id: int, skip: int = 0, limit: int = 100) -> List[LocationUpdate]:
    """Get location updates for a trip"""
    result = await db.execute(
        select(LocationUpdate)
        .where(LocationUpdate.trip_id == trip_id)
        .order_by(LocationUpdate.timestamp.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def create_location_update(db: AsyncSession, location_data: dict) -> LocationUpdate:
    """Create a new location update"""
    db_location = LocationUpdate(**location_data)
    db.add(db_location)
    await db.commit()
    await db.refresh(db_location)
    return db_location


async def get_latest_location_update(db: AsyncSession, trip_id: int) -> Optional[LocationUpdate]:
    """Get the latest location update for a trip"""
    result = await db.execute(
        select(LocationUpdate)
        .where(LocationUpdate.trip_id == trip_id)
        .order_by(LocationUpdate.timestamp.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()