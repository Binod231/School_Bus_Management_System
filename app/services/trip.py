# school_bus_management/app/services/trip.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, func
from app.models.trip import Trip, TripStudent, LocationUpdate, TripStatus, StudentStatus, TripType, TripDirection
from app.models.bus import Bus, BusRoute
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
            joinedload(TripStudent.student)
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
        # This section now loads the nested 'guardians' relationship as well
        .options(
            selectinload(Trip.students)
            .selectinload(TripStudent.student)
            .selectinload(Student.guardians)
            .selectinload(GuardianStudent.guardian)
            .selectinload(Guardian.user),
            selectinload(Trip.bus),
            selectinload(Trip.route)
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
            selectinload(Trip.students).selectinload(TripStudent.student),
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
            await db.execute(
                update(TripStudent)
                .where(
                    TripStudent.trip_id == trip_id,
                    TripStudent.status == StudentStatus.ON_BUS
                )
                .values(status=StudentStatus.AT_SCHOOL, disembarked_at=datetime.now())
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
                 selectinload(Student.guardians)
                .selectinload(GuardianStudent.guardian)
                .selectinload(Guardian.user)
            )
        )
    )
    return result.scalars().unique().all()

async def update_student_status_on_trip(db: AsyncSession, trip_id: int, student_id: int, status: StudentStatus) -> TripStudent:
    """Update the status of a single student on a specific trip."""
    stmt = (
        update(TripStudent)
        .where(
            and_(
                TripStudent.trip_id == trip_id,
                TripStudent.student_id == student_id
            )
        )
        .values(status=status, boarded_at=datetime.utcnow() if status == StudentStatus.ON_BUS else None)
        .returning(TripStudent)
    )
    result = await db.execute(stmt)
    await db.commit()
    updated_trip_student = result.scalar_one_or_none()
    
    if not updated_trip_student:
        return None
    return updated_trip_student

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
        .selectinload(Student.guardians)
        .selectinload(GuardianStudent.guardian)
        .selectinload(Guardian.user),
        selectinload(Trip.location_updates) # Load all location updates
    ).order_by(Trip.scheduled_start.desc())

    result = await db.execute(query)
    active_trips = result.scalars().unique().all()
    
    return active_trips