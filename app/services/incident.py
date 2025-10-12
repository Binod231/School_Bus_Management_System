from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from app.models.incident import Incident
from app.core.exceptions import NotFoundException, DatabaseException
from typing import Optional, List
from sqlalchemy.orm import selectinload, joinedload
from app.models.student import Student
from app.models.trip import TripStudent
from app.schemas.incident import IncidentUpdate
from sqlalchemy import or_, and_
from app.models.bus import BusDriver, BusRoute
from app.models.user import User, UserRole
from app.models.trip import Trip
from fastapi import HTTPException
from app.models.student import GuardianStudent, Guardian
from app.schemas.incident import IncidentCreateForDriver, IncidentUpdateForDriver

async def get_incident_by_id(db: AsyncSession, incident_id: int) -> Incident:
    """Get incident by ID"""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise NotFoundException("Incident", incident_id)
    return incident


async def get_incidents(
    db: AsyncSession,
    school_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Incident]:
    query = (
        select(Incident)
        .options(
            joinedload(Incident.reported_by),
            joinedload(Incident.student),
            joinedload(Incident.trip)  # Eagerly load the trip relationship
        )
    )
    if school_id is not None:
        query = query.where(Incident.school_id == school_id)
    if status is not None:
        query = query.where(Incident.status == status)
    
    query = query.order_by(Incident.reported_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().unique().all()



async def create_incident(db: AsyncSession, incident_data: dict) -> Incident:
    """Create a new incident"""
    db_incident = Incident(**incident_data)
    db.add(db_incident)
    await db.commit()
    await db.refresh(db_incident)
    return db_incident


async def create_incident_for_driver(db: AsyncSession, incident_in: IncidentCreateForDriver, user_id: int, school_id: int) -> Incident:
    """
    Creates an incident for a driver, correctly associating it with a trip
    and a single, optional student.
    """
    # Fetch the trip using the provided trip_id
    trip = await db.get(Trip, incident_in.trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Create the incident object from the input schema
    new_incident = Incident(
        title=incident_in.title,
        description=incident_in.description,
        type=incident_in.type,
        occurred_at=incident_in.occurred_at,
        bus_id=trip.bus_id,
        school_id=school_id,
        reported_by_id=user_id,
        trip_id=trip.id,
        # This is the corrected part that fixes the error:
        # It directly assigns the single student_id.
        student_id=incident_in.student_id
    )

    db.add(new_incident)
    await db.commit()
    await db.refresh(new_incident)

    # Re-fetch the newly created incident with all its relationships
    # to ensure the response sent back to the frontend is complete.
    result = await db.execute(
        select(Incident)
        .where(Incident.id == new_incident.id)
        .options(
            selectinload(Incident.trip).selectinload(Trip.bus),
            selectinload(Incident.trip).selectinload(Trip.route),
            selectinload(Incident.trip).selectinload(Trip.students).selectinload(TripStudent.student).selectinload(Student.guardians).selectinload(GuardianStudent.guardian).selectinload(Guardian.user),
            selectinload(Incident.student),
            selectinload(Incident.reported_by)
        )
    )
    
    return result.scalar_one()

async def update_incident_for_driver(
    db: AsyncSession,
    incident_db_obj: Incident,
    incident_in: IncidentUpdateForDriver
) -> Incident:
    """
    Update an incident for a driver, including status and student association.
    """
    incident_id = incident_db_obj.id
    update_data = incident_in.dict(exclude_unset=True)

    for field, value in update_data.items():
        setattr(incident_db_obj, field, value)

    db.add(incident_db_obj)
    await db.commit()

    # Re-fetch the updated incident with all relationships to ensure a complete response
    updated_incident_query = (
        select(Incident)
        .where(Incident.id == incident_id)
        .options(
            selectinload(Incident.trip).selectinload(Trip.bus),
            selectinload(Incident.trip).selectinload(Trip.route),
            selectinload(Incident.trip).selectinload(Trip.students).selectinload(TripStudent.student).selectinload(Student.guardians).selectinload(GuardianStudent.guardian).selectinload(Guardian.user),
            selectinload(Incident.student),
            selectinload(Incident.reported_by)
        )
    )
    
    result = await db.execute(updated_incident_query)
    updated_incident = result.scalar_one_or_none()

    if not updated_incident:
        raise NotFoundException("Incident", incident_id)

    return updated_incident




async def update_incident(db: AsyncSession, incident_id: int, incident_data: IncidentUpdate) -> Incident:
    """Update an incident using the IncidentUpdate schema."""
    db_incident = await get_incident_by_id(db, incident_id)
    
    # Convert the Pydantic model to a dictionary, excluding unset fields
    update_data = incident_data.dict(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(db_incident, key, value)
        
    await db.commit()
    await db.refresh(db_incident)
    return db_incident



async def delete_incident(db: AsyncSession, incident_id: int) -> bool:
    """Delete an incident"""
    result = await db.execute(delete(Incident).where(Incident.id == incident_id))
    await db.commit()
    if result.rowcount == 0:
        raise NotFoundException("Incident", incident_id)
    return True


async def get_student_incidents(db: AsyncSession, student_id: int, skip: int = 0, limit: int = 100) -> List[Incident]:
    """Get incidents for a specific student"""
    result = await db.execute(
        select(Incident)
        .where(Incident.student_id == student_id)
        .offset(skip)
        .limit(limit)
        .order_by(Incident.reported_at.desc())
    )
    return result.scalars().all()


async def get_user_reported_incidents(db: AsyncSession, user_id: int, skip: int = 0, limit: int = 100) -> List[Incident]:
    """Get incidents reported by a specific user"""
    result = await db.execute(
        select(Incident)
        .where(Incident.reported_by_id == user_id)
        .offset(skip)
        .limit(limit)
        .order_by(Incident.reported_at.desc())
    )
    return result.scalars().all()
    

async def get_guardian_incidents(db: AsyncSession, guardian_user_id: int, skip: int = 0, limit: int = 100) -> List[Incident]:
    """Get incidents for a guardian's students"""
    from app.services.student import get_guardian_by_user_id, get_guardian_students
    
    try:
        guardian = await get_guardian_by_user_id(db, guardian_user_id)
        students = await get_guardian_students(db, guardian.id)
        student_ids = [student.id for student in students]
        
        incidents = []
        for student_id in student_ids:
            student_incidents = await get_student_incidents(db, student_id, skip=skip, limit=limit)
            incidents.extend(student_incidents)
        return incidents
    except NotFoundException:
        return []
    
async def get_driver_incidents(
    db: AsyncSession, driver_id: int, trip_id: Optional[int] = None, skip: int = 0, limit: int = 100
) -> List[Incident]:
    """
    Get all incidents relevant to a driver.
    """
    bus_driver_assignments = await db.execute(
        select(BusDriver.bus_id).where(BusDriver.driver_id == driver_id)
    )
    assigned_bus_ids = [row[0] for row in bus_driver_assignments]

    query = (
        select(Incident)
        .outerjoin(User, Incident.reported_by_id == User.id)
        .options(
            # This is the corrected line to load all nested relationships
            selectinload(Incident.trip).selectinload(Trip.bus),
            selectinload(Incident.trip).selectinload(Trip.route),
            selectinload(Incident.trip).selectinload(Trip.students).selectinload(TripStudent.student).selectinload(Student.guardians).selectinload(GuardianStudent.guardian).selectinload(Guardian.user),
            joinedload(Incident.student),
            selectinload(Incident.reported_by)
        )
        .where(
            or_(
                Incident.reported_by_id == driver_id,
                and_(
                    Incident.bus_id.in_(assigned_bus_ids),
                    User.role == UserRole.ADMIN
                )
            )
        )
    )

    if trip_id:
        query = query.where(Incident.trip_id == trip_id)

    query = query.order_by(Incident.occurred_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    return result.scalars().unique().all()

async def get_guardian_incidents(db: AsyncSession, guardian_user_id: int, skip: int = 0, limit: int = 100) -> List[Incident]:
    """Get incidents for a guardian's students"""
    from app.services.student import get_guardian_by_user_id, get_guardian_students
    
    try:
        guardian = await get_guardian_by_user_id(db, guardian_user_id)
        students = await get_guardian_students(db, guardian.id)
        student_ids = [student.id for student in students]
        
        incidents = []
        for student_id in student_ids:
            student_incidents = await get_student_incidents(db, student_id, skip=skip, limit=limit)
            incidents.extend(student_incidents)
        return incidents
    except NotFoundException:
        return []
async def get_guardian_incidents_filtered(db: AsyncSession, guardian_user_id: int, skip: int = 0, limit: int = 100) -> List[Incident]:
    """Get incidents involving a guardian's students that were reported by drivers or admins.
    Excludes student absence incidents and only shows incidents related to bus operations."""
    from app.services.student import get_guardian_by_user_id
    from app.models.incident import IncidentType
    
    try:
        guardian = await get_guardian_by_user_id(db, guardian_user_id)
        
        # Get the IDs of all students associated with the guardian
        guardian_students_query = select(GuardianStudent.student_id).where(GuardianStudent.guardian_id == guardian.id)
        guardian_students_result = await db.execute(guardian_students_query)
        student_ids = guardian_students_result.scalars().all()
        
        if not student_ids:
            return []
        
        # Get all trip IDs the students have been on
        trip_ids_query = select(TripStudent.trip_id).where(TripStudent.student_id.in_(student_ids))
        trip_ids_result = await db.execute(trip_ids_query)
        trip_ids = trip_ids_result.scalars().unique().all()
        
        # NEW: Get all bus IDs that the guardian's students use
        student_bus_ids_query = select(Student.bus_route_id).where(Student.id.in_(student_ids))
        student_bus_ids_result = await db.execute(student_bus_ids_query)
        student_bus_route_ids = student_bus_ids_result.scalars().all()
        
        # Get bus IDs from the bus routes
        bus_ids_query = select(BusRoute.bus_id).where(BusRoute.id.in_(student_bus_route_ids))
        bus_ids_result = await db.execute(bus_ids_query)
        student_bus_ids = bus_ids_result.scalars().unique().all()
        
        # Build the query to get incidents reported by drivers or admins
        # that involve the guardian's students, excluding absence incidents
        query = (
            select(Incident)
            .join(User, Incident.reported_by_id == User.id)
            .options(selectinload(Incident.reported_by))
            .where(and_(
                # Only incidents reported by drivers or admins
                or_(
                    User.role == UserRole.DRIVER,
                    User.role == UserRole.ADMIN
                ),
                # Exclude absence incidents
                Incident.type != IncidentType.ABSENCE,
                # Incidents involving the guardian's students
                or_(
                    # Incidents directly linked to the student
                    Incident.student_id.in_(student_ids),
                    # Incidents related to a trip the student was on
                    and_(
                        Incident.trip_id.in_(trip_ids),
                        Incident.trip_id.is_not(None)
                    ),
                    # NEW: Admin incidents involving student's buses
                    and_(
                        User.role == UserRole.ADMIN,
                        Incident.bus_id.in_(student_bus_ids)
                    )
                )
            ))
            .offset(skip)
            .limit(limit)
            .order_by(Incident.reported_at.desc())
        )
        
        result = await db.execute(query)
        return result.scalars().unique().all()
        
    except NotFoundException:
        return []