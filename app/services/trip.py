# school_bus_management/app/services/trip.py

import math
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, func
from app.models.trip import Trip, TripStudent, LocationUpdate, TripStatus, StudentStatus, TripType, TripDirection
from app.models.bus import Bus, BusRoute, BusRouteStop, BusStop
from app.models.user import User, UserRole
from app.models.student import Student
from app.core.exceptions import NotFoundException
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import selectinload, joinedload
from app.models.student import GuardianStudent, Guardian, Student
from app.services.student import get_students_by_bus_route, get_students_by_guardian_id



async def get_trip_by_id(db: AsyncSession, trip_id: int) -> Trip:
    """Get trip by ID with bus relationship eagerly loaded"""
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id)
        .options(
            joinedload(Trip.bus),
            joinedload(Trip.route),
            selectinload(Trip.students).options(
                joinedload(TripStudent.student).options(
                    joinedload(Student.bus_route),
                    joinedload(Student.bus_stop),
                    selectinload(Student.guardians).options(
                        joinedload(GuardianStudent.guardian).options(
                            joinedload(Guardian.user)
                        )
                    )
                )
            )
        )
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise NotFoundException(f"Trip with id {trip_id} not found")

    return trip

async def get_trips(
    db: AsyncSession,
    school_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    driver_id: Optional[int] = None,
    status: Optional[str] = None,
    sort_by: str = "scheduled_start",
    sort_order: str = "desc"
) -> List[Trip]:
    """Get all trips with optional filters and sorting"""
    query = select(Trip).options(
        joinedload(Trip.bus),
        joinedload(Trip.route),
        selectinload(Trip.students).options(
            joinedload(TripStudent.student).options(
                joinedload(Student.bus_route),
                joinedload(Student.bus_stop),
                selectinload(Student.guardians).options(
                    joinedload(GuardianStudent.guardian).options(
                        joinedload(Guardian.user)
                    )
                )
            )
        )
    )
    
    if school_id:
        query = query.where(Trip.school_id == school_id)

    if driver_id:
        query = query.where(Trip.driver_id == driver_id)

    if status:
        query = query.where(Trip.status == status)

    # Sorting logic
    if hasattr(Trip, sort_by):
        column_to_sort = getattr(Trip, sort_by)
        if sort_order == "desc":
            query = query.order_by(column_to_sort.desc())
        else:
            query = query.order_by(column_to_sort.asc())

    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().unique().all()


async def get_driver_trips(db: AsyncSession, driver_id: int, skip: int = 0, limit: int = 100) -> List[Trip]:
    """Get trips for a specific driver with all nested student details eagerly loaded."""
    result = await db.execute(
        select(Trip)
        .where(Trip.driver_id == driver_id)
        .options(
            joinedload(Trip.bus),
            joinedload(Trip.route),
            selectinload(Trip.students)
            .selectinload(TripStudent.student)
            .options(
                selectinload(Student.bus_route).selectinload(BusRoute.bus),
                selectinload(Student.bus_stop),
                selectinload(Student.guardians)
                .selectinload(GuardianStudent.guardian)
                .selectinload(Guardian.user)
            )
        )
        .offset(skip)
        .limit(limit)
        .order_by(Trip.scheduled_start.desc())
    )
    return result.scalars().unique().all()


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

    # This subquery finds the latest timestamp for each trip_id
    latest_updates_subq = select(
        LocationUpdate.trip_id,
        func.max(LocationUpdate.timestamp).label("max_timestamp")
    ).where(
        LocationUpdate.trip_id.in_(trip_ids)
    ).group_by(LocationUpdate.trip_id).subquery()

    # This main query joins the full LocationUpdate table with the subquery
    # to fetch only the rows that match the latest timestamp for each trip.
    result = await db.execute(
        select(LocationUpdate).join(
            latest_updates_subq,
            and_(
                LocationUpdate.trip_id == latest_updates_subq.c.trip_id,
                LocationUpdate.timestamp == latest_updates_subq.c.max_timestamp
            )
        )
    )

    # Return a dictionary mapping trip_id to the latest LocationUpdate object
    latest_updates = {update.trip_id: update for update in result.scalars().all()}
    return latest_updates


async def get_active_student_trip(db: AsyncSession, student_id: int) -> Trip:
    """Get active trip for a student, with all relationships eagerly loaded."""
    result = await db.execute(
        select(Trip)
        .join(TripStudent, TripStudent.trip_id == Trip.id)
        .where(
            and_(
                TripStudent.student_id == student_id,
                Trip.status == TripStatus.IN_PROGRESS
            )
        )
        # This section now loads the nested 'guardians' and 'bus_stop' relationships as well
        .options(
            selectinload(Trip.students)
            .selectinload(TripStudent.student)
            .options(
                selectinload(Student.guardians)
                .selectinload(GuardianStudent.guardian)
                .selectinload(Guardian.user),
                selectinload(Student.bus_stop)
            ),
            selectinload(Trip.bus),
            selectinload(Trip.driver),
            selectinload(Trip.route)
            .selectinload(BusRoute.stops)
            .selectinload(BusRouteStop.stop)
        )
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise NotFoundException(f"Active Trip for Student {student_id} not found")
    latest_location = await get_latest_location_update(db, trip.id)
    trip.latest_location = latest_location
    return trip


async def create_trip(db: AsyncSession, trip_data: dict) -> Trip:
    """Create a new trip AND associate students from the route."""
    # Create the initial trip record
    db_trip = Trip(**trip_data)
    db.add(db_trip)
    await db.commit()
    await db.refresh(db_trip)

    # Get students from the route and create TripStudent entries
    if db_trip.route_id:
        students_on_route = await get_students_by_bus_route(db, db_trip.route_id)
        for student in students_on_route:
            trip_student_entry = TripStudent(
                trip_id=db_trip.id,
                student_id=student.id,
                status=StudentStatus.AT_HOME 
            )
            db.add(trip_student_entry)
        await db.commit()
    
    # Re-fetch the trip with all relationships correctly loaded
    result = await db.execute(
        select(Trip)
        .where(Trip.id == db_trip.id)
        .options(
            selectinload(Trip.students)
            .selectinload(TripStudent.student)
            .options(
                selectinload(Student.bus_route),
                selectinload(Student.bus_stop),
                selectinload(Student.guardians)
                .selectinload(GuardianStudent.guardian)
                .selectinload(Guardian.user)
            ),
            selectinload(Trip.bus),
            selectinload(Trip.route)
        )
    )
    return result.scalar_one()


async def update_trip(db: AsyncSession, trip_id: int, trip_data: dict) -> Trip:
    """Update a trip's status and handle student status changes accordingly."""
    result = await db.execute(
        update(Trip)
        .where(Trip.id == trip_id)
        .values(**trip_data)
    )
    await db.commit()
    
    if result.rowcount == 0:
        raise NotFoundException("Trip", trip_id)

    # If the trip is being marked as completed, check its direction.
    if trip_data.get("status") == TripStatus.COMPLETED.value:
        trip_to_update = await get_trip_by_id(db, trip_id)
        
        # Only auto-update status for trips TO school.
        # For trips FROM school, status remains ON_BUS until guardian confirms.
        # Auto-update status based on trip direction
        # Trip TO SCHOOL -> AT_SCHOOL
        if trip_to_update.direction == TripDirection.TO_SCHOOL:
            stmt = select(TripStudent).where(
                and_(
                    TripStudent.trip_id == trip_id,
                    TripStudent.status == StudentStatus.ON_BUS
                )
            ).options(selectinload(TripStudent.student))
            res = await db.execute(stmt)
            students_arrived = res.scalars().all()

            if students_arrived:
                await db.execute(
                    update(TripStudent)
                    .where(
                        and_(
                            TripStudent.trip_id == trip_id,
                            TripStudent.status == StudentStatus.ON_BUS
                        )
                    )
                    .values(status=StudentStatus.AT_SCHOOL, disembarked_at=datetime.now())
                )
                from app.services.notification import notify_guardians_arrival
                for ts in students_arrived:
                    await notify_guardians_arrival(
                        db,
                        student_id=ts.student_id,
                        location="School",
                        time=datetime.now().strftime("%H:%M")
                    )

        
        # Trip FROM SCHOOL -> DROPPED_OFF (Waiting for Guardian Confirmation)
        elif trip_to_update.direction == TripDirection.FROM_SCHOOL:
            # 1. Fetch relevant students first (so we know who to notify)
            stmt = select(TripStudent).where(
                and_(
                    TripStudent.trip_id == trip_id,
                    TripStudent.status == StudentStatus.ON_BUS
                )
            ).options(selectinload(TripStudent.student))
            
            result = await db.execute(stmt)
            students_on_bus = result.scalars().all()
            
            if students_on_bus:
                # 2. Update them to DROPPED_OFF
                await db.execute(
                    update(TripStudent)
                    .where(
                        and_(
                            TripStudent.trip_id == trip_id,
                            TripStudent.status == StudentStatus.ON_BUS
                        )
                    )
                    .values(status=StudentStatus.DROPPED_OFF, disembarked_at=datetime.now())
                )
                
                # 3. Trigger Notifications
                from app.services.notification import notify_dropoff_pending_confirmation
                for ts in students_on_bus:
                    await notify_dropoff_pending_confirmation(db, ts.student, trip_to_update)
            
        await db.commit()
    
    # Re-fetch the updated trip with all relationships eagerly loaded
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id)
        .options(
            selectinload(Trip.bus),
            selectinload(Trip.route),
            selectinload(Trip.students)
            .selectinload(TripStudent.student)
            .options(
                 selectinload(Student.bus_route).selectinload(BusRoute.bus),
                 selectinload(Student.bus_stop),
                 selectinload(Student.guardians)
                .selectinload(GuardianStudent.guardian)
                .selectinload(Guardian.user)
            )
        )
    )
    updated_trip = result.scalars().unique().one_or_none()
    
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
    """Update a student's status on a trip, creating the record if it doesn't exist."""
    # First, try to find an existing record for this student on this trip.
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
        # If no record exists, create a new one. This handles the first time
        # a student is marked as boarded on a trip.
        trip_student = TripStudent(trip_id=trip_id, student_id=student_id, **student_data)
        db.add(trip_student)
    else:
        # If the record already exists, update its values.
        for key, value in student_data.items():
            setattr(trip_student, key, value)

    await db.commit()
    await db.refresh(trip_student)

    result = await db.execute(
        select(TripStudent)
        .where(TripStudent.id == trip_student.id)
        .options(selectinload(TripStudent.student))
    )
    updated_trip_student = result.scalar_one_or_none()

    if not updated_trip_student:
        raise NotFoundException("TripStudent", f"trip_id: {trip_id}, student_id: {student_id}")

    return updated_trip_student


async def mark_students_boarded(db: AsyncSession, trip_id: int, student_ids: List[int]):
    """
    Marks a specific list of students as boarded for a trip.
    """
    from datetime import datetime

    for student_id in student_ids:
        try:
            # Check if a TripStudent entry already exists and update it
            trip_student = await get_trip_student(db, trip_id, student_id)
            await update_trip_student(
                db, trip_id, student_id,
                {"status": StudentStatus.ON_BUS, "boarded_at": datetime.now()}
            )
        except NotFoundException:
            # If no entry exists, create one
            db_trip_student = TripStudent(
                trip_id=trip_id,
                student_id=student_id,
                status=StudentStatus.ON_BUS,
                boarded_at=datetime.now()
            )
            db.add(db_trip_student)

    await db.commit()


async def mark_students_dropped_off(
    db: AsyncSession,
    trip_id: int,
    student_ids: List[int],
    stop_id: Optional[int] = None
) -> List[TripStudent]:
    """
    Marks a specific list of students as dropped off / unboarded for a trip.
    Preserves boarded_at and records disembarked_at.
    """
    trip = await get_trip_by_id(db, trip_id)
    target_status = StudentStatus.AT_SCHOOL if trip.direction == TripDirection.TO_SCHOOL else StudentStatus.DROPPED_OFF
    now = datetime.now()
    results = []

    for student_id in student_ids:
        try:
            trip_student = await get_trip_student(db, trip_id, student_id)
            updated = await update_trip_student(
                db, trip_id, student_id,
                {"status": target_status, "disembarked_at": now}
            )
            results.append(updated)
        except NotFoundException:
            db_trip_student = TripStudent(
                trip_id=trip_id,
                student_id=student_id,
                status=target_status,
                disembarked_at=now
            )
            db.add(db_trip_student)
            await db.commit()
            await db.refresh(db_trip_student)
            results.append(db_trip_student)

    await db.commit()
    return results


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

async def get_all_active_trips_for_driver(db: AsyncSession, driver_id: int) -> List[Trip]:
    """Get all currently active trips for a specific driver."""
    result = await db.execute(
        select(Trip)
        .where(
            and_(
                Trip.driver_id == driver_id,
                Trip.status == TripStatus.IN_PROGRESS
            )
        )
        .options(
            selectinload(Trip.bus),
            selectinload(Trip.route),
            selectinload(Trip.students)
            .selectinload(TripStudent.student)
            .options(
                 selectinload(Student.bus_route).selectinload(BusRoute.bus),
                 selectinload(Student.bus_stop),
                 selectinload(Student.guardians)
                .selectinload(GuardianStudent.guardian)
                .selectinload(Guardian.user)
            )
        )
    )
    return result.scalars().unique().all()

async def update_student_status_on_trip(db: AsyncSession, trip_id: int, student_id: int, status: StudentStatus) -> Optional[TripStudent]:
    """Update the status of a single student on a specific trip, preserving boarding records."""
    now = datetime.now()

    # Check if a TripStudent entry already exists
    res = await db.execute(
        select(TripStudent).where(
            and_(
                TripStudent.trip_id == trip_id,
                TripStudent.student_id == student_id
            )
        )
    )
    trip_student = res.scalar_one_or_none()

    if not trip_student:
        trip_student = TripStudent(
            trip_id=trip_id,
            student_id=student_id,
            status=status,
            boarded_at=now if status == StudentStatus.ON_BUS else None,
            disembarked_at=now if status in (StudentStatus.DROPPED_OFF, StudentStatus.AT_SCHOOL, StudentStatus.AT_HOME) else None
        )
        db.add(trip_student)
    else:
        trip_student.status = status
        if status == StudentStatus.ON_BUS:
            if not trip_student.boarded_at:
                trip_student.boarded_at = now
        elif status in (StudentStatus.DROPPED_OFF, StudentStatus.AT_SCHOOL, StudentStatus.AT_HOME):
            trip_student.disembarked_at = now
            # CRITICAL: Preserve existing boarded_at!

    await db.commit()
    await db.refresh(trip_student)
    return trip_student


async def verify_student_qr_code(db: AsyncSession, qr_data: str, school_id: int) -> Optional[Student]:
    """
    Verifies QR code data and returns the student if valid and belongs to the school.
    Expected format: "STUDENT:{student.id}:{student.student_id}:{student.school_id}"
    """
    if not qr_data or not qr_data.startswith("STUDENT:"):
        return None

    parts = qr_data.split(":")
    if len(parts) != 4:
        return None

    try:
        student_id = int(parts[1])
        qr_school_id = int(parts[3])
    except (ValueError, IndexError):
        return None

    if qr_school_id != school_id:
        return None

    student = await db.get(Student, student_id)
    return student

async def get_student_trips(db: AsyncSession, student_id: int, skip: int = 0, limit: int = 100) -> List[Trip]:
    """
    Get trips for a specific student, eagerly loading ALL related data for the guardian view.
    """
    result = await db.execute(
        select(Trip)
        .join(TripStudent, TripStudent.trip_id == Trip.id)
        .where(TripStudent.student_id == student_id)
        .options(
            # ✅ THE FIX: This ensures the driver's full details are included in the query.
            selectinload(Trip.driver), 
            selectinload(Trip.bus),
            selectinload(Trip.route),
            selectinload(Trip.students).options(
                selectinload(TripStudent.student).options(
                    selectinload(Student.bus_route),
                    selectinload(Student.bus_stop),
                    selectinload(Student.guardians).options(
                        selectinload(GuardianStudent.guardian).options(
                            selectinload(Guardian.user)
                        )
                    )
                )
            )
        )
        .offset(skip)
        .limit(limit)
        .order_by(Trip.scheduled_start.desc())
    )
    return result.scalars().unique().all()


async def authorize_trip_access(db: AsyncSession, user: User, trip_id: int) -> bool:
    """
    Checks if a user is authorized to receive location updates for a specific trip,
    now with correct role checking and school validation.
    """
    try:
        # Eagerly load necessary relationships for authorization checks
        result = await db.execute(
            select(Trip)
            .where(Trip.id == trip_id)
            .options(
                selectinload(Trip.bus).selectinload(Bus.school),
                selectinload(Trip.students)
            )
        )
        trip = result.scalar_one_or_none()

        if not trip:
            return False

    except Exception:
        return False

    # Check for Admin/Superadmin roles
    if user.role in [UserRole.ADMIN, UserRole.SUPERADMIN]:
        # Security Check: Ensure the trip belongs to the admin's school
        if trip.bus and trip.bus.school_id == user.school_id:
            return True

    # Check for the Driver role
    if user.role == UserRole.DRIVER and trip.driver_id == user.id:
        return True

    # Check for the Guardian role
    if user.role == UserRole.GUARDIAN:
        # Explicitly query for the guardian profile using the user's ID
        query = select(Guardian).where(Guardian.user_id == user.id)
        result = await db.execute(query)
        guardian = result.scalar_one_or_none()

        if not guardian:
            return False

        # Get the IDs of the students associated with this guardian
        guardian_students = await get_students_by_guardian_id(db, guardian.id)
        guardian_student_ids = {student.id for student in guardian_students}

        # Check if any of the guardian's students are on this trip
        for trip_student in trip.students:
            if trip_student.student_id in guardian_student_ids:
                return True

    return False


async def get_active_trips_with_locations(db: AsyncSession, school_id: Optional[int] = None) -> List[Trip]:
    """
    Get active trips with their location updates and other details,
    specifically designed for the admin live tracking view.
    """
    query = select(Trip).where(Trip.status == TripStatus.IN_PROGRESS)

    if school_id is not None:
        # Ensure we only get trips for the given school by joining through the Bus model
        query = query.join(Bus, Trip.bus_id == Bus.id).where(Bus.school_id == school_id)

    query = query.options(
        # Eagerly load all the required relationships in a single query
        selectinload(Trip.bus),
        selectinload(Trip.driver), # This directly loads the driver (User) from the Trip
        selectinload(Trip.route),
        selectinload(Trip.students)
        .selectinload(TripStudent.student)
        .options(
            selectinload(Student.bus_route),
            selectinload(Student.bus_stop),
            selectinload(Student.guardians)
            .selectinload(GuardianStudent.guardian)
            .selectinload(Guardian.user)
        ),
        selectinload(Trip.location_updates) # Load all location updates
    ).order_by(Trip.scheduled_start.desc())

    result = await db.execute(query)
    active_trips = result.scalars().unique().all()
    
    return active_trips


def calculate_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance in meters between two GPS coordinates using Haversine formula."""
    R = 6371000.0  # Earth's radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


async def get_student_live_tracking(db: AsyncSession, student_id: int) -> dict:
    """
    Retrieves real-time live tracking data for a student's bus trip.
    Computes current bus location, distance to student's stop, arrival status, ETA,
    and route stops with coordinates.
    """
    from app.services.student import get_student_by_id
    from app.models.bus import BusStop, BusRouteStop

    student = await get_student_by_id(db, student_id)
    if not student:
        raise NotFoundException("Student", student_id)

    # Format assigned stop info
    assigned_stop_data = None
    stop_lat = None
    stop_lon = None
    if student.bus_stop:
        try:
            stop_lat = float(student.bus_stop.latitude)
            stop_lon = float(student.bus_stop.longitude)
        except (ValueError, TypeError):
            pass

        assigned_stop_data = {
            "id": student.bus_stop.id,
            "name": student.bus_stop.name,
            "address": student.bus_stop.address,
            "latitude": stop_lat if stop_lat is not None else 0.0,
            "longitude": stop_lon if stop_lon is not None else 0.0,
            "sequence": student.bus_stop.sequence,
            "estimated_arrival_time": None
        }

    # Find the active trip for this student
    active_trip = None
    try:
        active_trip = await get_active_student_trip(db, student_id)
    except NotFoundException:
        # Fallback 1: check if there is an in-progress trip on the student's route
        if student.bus_route_id:
            stmt = (
                select(Trip)
                .where(
                    and_(
                        Trip.route_id == student.bus_route_id,
                        Trip.status == TripStatus.IN_PROGRESS
                    )
                )
                .options(
                    selectinload(Trip.bus),
                    selectinload(Trip.driver),
                    selectinload(Trip.route)
                    .selectinload(BusRoute.stops)
                    .selectinload(BusRouteStop.stop),
                    selectinload(Trip.students)
                    .selectinload(TripStudent.student)
                )
                .order_by(Trip.scheduled_start.desc())
                .limit(1)
            )
            res = await db.execute(stmt)
            active_trip = res.scalar_one_or_none()

    # Fallback 2: check if recently completed trip where student was dropped off
    if not active_trip:
        stmt = (
            select(Trip)
            .join(TripStudent, TripStudent.trip_id == Trip.id)
            .options(
                selectinload(Trip.bus),
                selectinload(Trip.driver),
                selectinload(Trip.route)
                .selectinload(BusRoute.stops)
                .selectinload(BusRouteStop.stop),
                selectinload(Trip.students)
                .selectinload(TripStudent.student)
            )
            .where(
                and_(
                    TripStudent.student_id == student_id,
                    TripStudent.status == StudentStatus.DROPPED_OFF
                )
            )
            .order_by(Trip.actual_end.desc())
            .limit(1)
        )
        res = await db.execute(stmt)
        active_trip = res.scalar_one_or_none()

    if not active_trip:
        return {
            "student": {
                "id": student.id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "grade": student.grade,
                "student_id": student.student_id,
                "is_onboard": False,
                "status": "NO_ACTIVE_TRIP",
                "boarded_at": None,
                "disembarked_at": None,
                "assigned_stop": assigned_stop_data
            },
            "trip": None,
            "bus": None,
            "driver": None,
            "route": None,
            "current_location": None,
            "arrival_status": {
                "has_arrived_at_student_stop": False,
                "distance_to_student_stop_meters": None,
                "distance_to_student_stop_km": None,
                "estimated_minutes_to_stop": None,
                "nearest_stop_name": None,
                "status_summary": "No active trip in progress for this student."
            },
            "websocket_endpoint": None,
            "is_trip_active": False
        }

    # Eagerly load route stops if needed
    if active_trip.route and not hasattr(active_trip.route, 'stops'):
        route_stmt = (
            select(BusRoute)
            .where(BusRoute.id == active_trip.route_id)
            .options(
                selectinload(BusRoute.stops)
                .selectinload(BusRouteStop.stop)
            )
        )
        route_res = await db.execute(route_stmt)
        active_trip.route = route_res.scalar_one_or_none()

    # Find trip student record
    trip_student_record = None
    for ts in active_trip.students:
        if ts.student_id == student_id:
            trip_student_record = ts
            break

    is_onboard = (trip_student_record.status == StudentStatus.ON_BUS) if trip_student_record else False
    current_student_status = trip_student_record.status.value if trip_student_record else "SCHEDULED"
    boarded_at = trip_student_record.boarded_at if trip_student_record else None
    disembarked_at = trip_student_record.disembarked_at if trip_student_record else None

    # Latest bus location
    latest_location = await get_latest_location_update(db, active_trip.id)
    current_location_data = None
    distance_meters = None
    distance_km = None
    has_arrived = False
    eta_minutes = None
    nearest_stop_name = None

    if latest_location:
        now_ts = datetime.now(latest_location.timestamp.tzinfo) if latest_location.timestamp.tzinfo else datetime.now()
        seconds_ago = int((now_ts - latest_location.timestamp).total_seconds()) if latest_location.timestamp else 0

        current_location_data = {
            "latitude": float(latest_location.latitude),
            "longitude": float(latest_location.longitude),
            "speed": float(latest_location.speed) if latest_location.speed else 0.0,
            "heading": float(latest_location.heading) if latest_location.heading else 0.0,
            "timestamp": latest_location.timestamp,
            "updated_seconds_ago": max(0, seconds_ago)
        }

        # Calculate distance to student's assigned stop
        if stop_lat is not None and stop_lon is not None:
            distance_meters = round(calculate_distance_meters(
                latest_location.latitude,
                latest_location.longitude,
                stop_lat,
                stop_lon
            ), 1)
            distance_km = round(distance_meters / 1000.0, 2)
            # Bus has arrived if within 120m of the stop, or student is already dropped off / at destination
            is_arrived_at_destination = (
                current_student_status in [
                    StudentStatus.DROPPED_OFF.value,
                    StudentStatus.AT_SCHOOL.value,
                ]
                or (
                    active_trip.direction == TripDirection.FROM_SCHOOL
                    and current_student_status == StudentStatus.AT_HOME.value
                )
            )
            has_arrived = (distance_meters <= 120.0) or is_arrived_at_destination

            # Estimated arrival time
            speed_ms = latest_location.speed if (latest_location.speed and latest_location.speed > 2.0) else 6.94  # ~25 km/h
            if has_arrived:
                eta_minutes = 0.0
            else:
                eta_minutes = round((distance_meters / speed_ms) / 60.0, 1)

    # Calculate nearest stop on route
    if active_trip.route and hasattr(active_trip.route, 'stops') and active_trip.route.stops and latest_location:
        min_dist = float('inf')
        for rs in active_trip.route.stops:
            if rs.stop:
                try:
                    s_lat = float(rs.stop.latitude)
                    s_lon = float(rs.stop.longitude)
                    d = calculate_distance_meters(latest_location.latitude, latest_location.longitude, s_lat, s_lon)
                    if d < min_dist:
                        min_dist = d
                        nearest_stop_name = rs.stop.name
                except (ValueError, TypeError):
                    pass

    # Status summary message
    bus_num = active_trip.bus.bus_number if active_trip.bus else "Bus"
    if current_student_status == StudentStatus.DROPPED_OFF.value:
        status_summary = f"Student has been dropped off from bus {bus_num}. Waiting for guardian arrival confirmation."
    elif current_student_status == StudentStatus.AT_SCHOOL.value:
        status_summary = f"Student has safely arrived at school."
    elif current_student_status == StudentStatus.AT_HOME.value and active_trip.direction == TripDirection.FROM_SCHOOL:
        status_summary = f"Student is safely at home."
    elif has_arrived:
        stop_name = student.bus_stop.name if student.bus_stop else "stop"
        status_summary = f"Bus {bus_num} has arrived at {stop_name}!"
    elif is_onboard:
        if distance_km is not None:
            status_summary = f"Student is onboard bus {bus_num}. Approaching stop ({distance_km} km away, ~{eta_minutes} mins)."
        else:
            status_summary = f"Student is onboard bus {bus_num}. Trip in progress."
    else:
        # Student waiting for pickup
        if distance_km is not None:
            stop_name = student.bus_stop.name if student.bus_stop else "stop"
            status_summary = f"Bus {bus_num} is on the way to {stop_name} ({distance_km} km away, ~{eta_minutes} mins)."
        else:
            status_summary = f"Bus {bus_num} trip is in progress. Student is waiting for pickup."

    # Build route stops list
    route_stops_list = []
    if active_trip.route and hasattr(active_trip.route, 'stops') and active_trip.route.stops:
        sorted_stops = sorted(active_trip.route.stops, key=lambda s: s.sequence)
        for rs in sorted_stops:
            if rs.stop:
                try:
                    rs_lat = float(rs.stop.latitude)
                    rs_lon = float(rs.stop.longitude)
                except (ValueError, TypeError):
                    rs_lat = 0.0
                    rs_lon = 0.0
                route_stops_list.append({
                    "id": rs.stop.id,
                    "name": rs.stop.name,
                    "address": rs.stop.address,
                    "latitude": rs_lat,
                    "longitude": rs_lon,
                    "sequence": rs.sequence,
                    "estimated_arrival_time": rs.estimated_arrival_time
                })

    return {
        "student": {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "grade": student.grade,
            "student_id": student.student_id,
            "is_onboard": is_onboard,
            "status": current_student_status,
            "boarded_at": boarded_at,
            "disembarked_at": disembarked_at,
            "assigned_stop": assigned_stop_data
        },
        "trip": {
            "id": active_trip.id,
            "name": active_trip.name,
            "type": active_trip.type.value if hasattr(active_trip.type, 'value') else str(active_trip.type),
            "direction": active_trip.direction.value if hasattr(active_trip.direction, 'value') else str(active_trip.direction),
            "status": active_trip.status.value if hasattr(active_trip.status, 'value') else str(active_trip.status),
            "scheduled_start": active_trip.scheduled_start,
            "actual_start": active_trip.actual_start
        },
        "bus": {
            "id": active_trip.bus.id,
            "bus_number": active_trip.bus.bus_number,
            "capacity": active_trip.bus.capacity,
            "license_plate": active_trip.bus.license_plate,
            "make": active_trip.bus.make,
            "model": active_trip.bus.model
        } if active_trip.bus else None,
        "driver": {
            "id": active_trip.driver.id,
            "name": f"{active_trip.driver.first_name} {active_trip.driver.last_name}",
            "phone": active_trip.driver.phone
        } if active_trip.driver else None,
        "route": {
            "id": active_trip.route.id,
            "name": active_trip.route.name,
            "description": active_trip.route.description,
            "stops": route_stops_list
        } if active_trip.route else None,
        "current_location": current_location_data,
        "arrival_status": {
            "has_arrived_at_student_stop": has_arrived,
            "distance_to_student_stop_meters": distance_meters,
            "distance_to_student_stop_km": distance_km,
            "estimated_minutes_to_stop": eta_minutes,
            "nearest_stop_name": nearest_stop_name,
            "status_summary": status_summary
        },
        "websocket_endpoint": f"/ws/trips/{active_trip.id}/location",
        "is_trip_active": (active_trip.status == TripStatus.IN_PROGRESS)
    }