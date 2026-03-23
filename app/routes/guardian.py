from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List
from app.db.session import get_db
from app.core.jwt import get_current_guardian
from app.schemas.student import StudentResponse
from app.schemas.trip import TripResponse, LocationUpdateResponse
from app.schemas.incident import IncidentResponse
from app.services.student import get_guardian_students, get_student_by_id, get_guardian_by_user_id, get_guardian_student_relationship
from app.services.trip import get_student_trips, get_trip_location_updates as get_trip_location_updates_service, get_trip_by_id, get_trip_students, get_active_student_trip, update_trip_student, get_trip_student
from app.services.student import update_guardian, get_students_by_guardian_id
from app.core.exceptions import NotFoundException
from app.services.notification import notify_admin_arrival_confirmation
from app.services.incident import get_guardian_incidents_filtered
from app.models.trip import StudentStatus, Trip, TripStudent, TripDirection
from sqlalchemy import select, and_, or_
from datetime import datetime

router = APIRouter(
    prefix="/guardian",
    tags=["guardian"],
    dependencies=[Depends(get_current_guardian)]
)


@router.get(
    "/students",
    response_model=List[StudentResponse],
    summary="Get my students",
    description="Retrieves a list of all students associated with the current guardian's account."
)
async def get_my_students(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_guardian)
):
    try:
        guardian = await get_guardian_by_user_id(db, current_user.id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    students = await get_students_by_guardian_id(db, guardian.id)

    return students


@router.get(
    "/trips/{trip_id}",
    response_model=TripResponse, # Make sure to create this schema
    summary="Get trip details",
    description="Retrieves detailed information for a specific trip, provided the guardian has a student on that trip."
)
async def get_trip_details(
    trip_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_guardian)
):
    try:
        guardian = await get_guardian_by_user_id(db, current_user.id)
        trip = await get_trip_by_id(db, trip_id)
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)

    # Security check: Ensure the guardian has a student on this trip
    guardian_students = await get_guardian_students(db, guardian.id)
    trip_students = await get_trip_students(db, trip_id)
    guardian_student_ids = {student.id for student in guardian_students}
    trip_student_ids = {ts.student_id for ts in trip_students}

    if guardian_student_ids.isdisjoint(trip_student_ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this trip's details.")

    # Here you would typically gather more details for the response
    # For now, we return the main trip object. You should expand this.
    return trip

@router.get(
    "/students/{student_id}/trips",
    response_model=List[TripResponse],
    summary="Get trip history for a student",
    description="Retrieves the past and current trips for a specific student, accessible by their guardian."
)
async def get_student_trips_history(
    student_id: int,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_guardian)
):
    try:
        guardian = await get_guardian_by_user_id(db, current_user.id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    relationship = await get_guardian_student_relationship(db, guardian.id, student_id)
    if not relationship:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this student"
        )

    trips = await get_student_trips(db, student_id, skip=skip, limit=limit)

    for trip in trips:
        trip_student_info = None
        # The service needs to be adapted to eager load trip.students.
        # This loop assumes it's available.
        for ts in trip.students:
             if ts.student_id == student_id:
                 trip_student_info = ts
                 break

        if trip_student_info:
            # Priority 1: Check if student is dropped off (Waiting for confirmation)
            # This must take precedence over 'completed' status
            if trip_student_info.status == StudentStatus.DROPPED_OFF:
                trip.student_trip_status = "Waiting for Confirmation"
            
            # Priority 2: Trip Status
            elif trip.status == 'COMPLETED':
                if trip_student_info.boarded_at:
                    trip.student_trip_status = "Completed"
                else:
                    trip.student_trip_status = "Missed"
            
            elif trip.status == 'IN_PROGRESS':
                if trip_student_info.status == StudentStatus.AT_HOME:
                    trip.student_trip_status = "Arrived"
                elif trip_student_info.status == StudentStatus.ON_BUS:
                    trip.student_trip_status = "In Progress"
                else:
                    trip.student_trip_status = "Waiting for Pickup"
            
            else:
                trip.student_trip_status = trip.status.replace('_', ' ').title()

    return trips


@router.get(
    "/trips/{trip_id}/location",
    response_model=List[LocationUpdateResponse],
    summary="Get location updates for a trip",
    description="Retrieves a list of location updates for a specific trip, provided the guardian has a student on that trip."
)
async def get_trip_location_updates(
    trip_id: int,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_guardian)
):
    try:
        guardian = await get_guardian_by_user_id(db, current_user.id)
        trip = await get_trip_by_id(db, trip_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    guardian_students = await get_guardian_students(db, guardian.id)
    trip_students = await get_trip_students(db, trip_id)

    guardian_student_ids = {student.id for student in guardian_students}
    trip_student_ids = {ts.student_id for ts in trip_students}

    has_access = not guardian_student_ids.isdisjoint(trip_student_ids)

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this trip"
        )

    location_updates = await get_trip_location_updates_service(db, trip_id, skip=skip, limit=limit)
    return location_updates


@router.post(
    "/fcm-token",
    summary="Update FCM token",
    description="Allows a guardian to register or update their FCM token for push notifications."
)
async def update_fcm_token(
    fcm_token: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_guardian)
):
    try:
        guardian = await get_guardian_by_user_id(db, current_user.id)
        await update_guardian(db, guardian.id, {"fcm_token": fcm_token})
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    return {"message": "FCM token updated successfully"}


@router.post(
    "/confirm-arrival/{student_id}",
    summary="Confirm student arrival",
    description="Allows a guardian to confirm the safe arrival of their child at a destination."
)
async def confirm_student_arrival(
    student_id: int,
    confirmed: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_guardian)
):
    try:
        guardian = await get_guardian_by_user_id(db, current_user.id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    relationship = await get_guardian_student_relationship(db, guardian.id, student_id)
    if not relationship:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this student"
        )


    # Find the trip where the student is either:
    # 1. DROPPED_OFF (waiting for confirmation after trip completed), OR
    # 2. ON_BUS (still on active FROM_SCHOOL trip but arrived home)

    stmt = (
        select(Trip)
        .join(TripStudent, TripStudent.trip_id == Trip.id)
        .where(
            and_(
                TripStudent.student_id == student_id,
                or_(
                    TripStudent.status == StudentStatus.DROPPED_OFF,
                    and_(
                        TripStudent.status == StudentStatus.ON_BUS,
                        Trip.direction == TripDirection.FROM_SCHOOL
                    )
                )
            )
        )
        .order_by(Trip.scheduled_start.desc()) # Get the most recent one
        .limit(1)
    )
    result = await db.execute(stmt)
    active_trip = result.scalar_one_or_none()

    if not active_trip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active FROM_SCHOOL trip found for this student"
        )

    # Requirement 1: Check if the trip direction is from school
    if active_trip.direction != "from_school":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arrival can only be confirmed for trips from school."
        )

    try:
        trip_student = await get_trip_student(db, active_trip.id, student_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    # Requirement 2: Set the student's status to 'at_home'
    update_data = {
        "status": StudentStatus.AT_HOME if confirmed else StudentStatus.ON_BUS,
        "disembarked_at": datetime.now() if confirmed else None
    }

    await update_trip_student(db, active_trip.id, student_id, update_data)

    student = await get_student_by_id(db, student_id)
    await notify_admin_arrival_confirmation(db, student, current_user, confirmed)

    return {"message": f"Arrival {'confirmed' if confirmed else 'not confirmed'} successfully"}

@router.get(
    "/students/{student_id}/active-trip",
    response_model=TripResponse,
    summary="Get active trip for a student",
    description="Retrieves the active trip for a specific student, accessible by their guardian."
)
async def get_active_trip_for_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_guardian)
):
    try:
        guardian = await get_guardian_by_user_id(db, current_user.id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    if not await get_guardian_student_relationship(db, guardian.id, student_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this student"
        )

    try:
        active_trip = await get_active_student_trip(db, student_id)
    except NotFoundException:
        # Fallback: Check if there is a recently completed trip where the student is waiting for confirmation
        
        stmt = (
            select(Trip)
            .join(TripStudent, TripStudent.trip_id == Trip.id)
            .options(selectinload(Trip.students)) # Must load students for the logic below
            .where(
                and_(
                    TripStudent.student_id == student_id,
                    TripStudent.status == StudentStatus.DROPPED_OFF
                )
            )
            .order_by(Trip.actual_end.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        active_trip = result.scalar_one_or_none()
        
        if not active_trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active trip found for this student"
            )

    #  THE FIX FOR THE DASHBOARD
    trip_student_info = None
    for ts in active_trip.students:
        if ts.student_id == student_id:
            trip_student_info = ts
            break

    if trip_student_info:
        # Apply the same prioritized logic as history
        if trip_student_info.status == StudentStatus.DROPPED_OFF:
            active_trip.student_trip_status = "Waiting for Confirmation"
        elif active_trip.status == 'IN_PROGRESS':
            if trip_student_info.status == StudentStatus.AT_HOME:
                active_trip.student_trip_status = "Arrived"
            elif trip_student_info.status == StudentStatus.ON_BUS:
                active_trip.student_trip_status = "In Progress"
            else:
                active_trip.student_trip_status = "Waiting for Pickup"
        else:
             # For the fallback case (Completed trip), if not dropped_off, it returns here
             if active_trip.status == 'COMPLETED':
                 active_trip.student_trip_status = "Completed"
             else:
                 active_trip.student_trip_status = active_trip.status.replace('_', ' ').title()


    return active_trip


@router.get(
    "/incidents",
    response_model=List[IncidentResponse],
    summary="Get incidents involving my students",
    description="Retrieves incidents reported by drivers and admins that involve the guardian's students. Excludes student absence incidents."
)
async def get_my_students_incidents(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_guardian)
):
    try:
        guardian = await get_guardian_by_user_id(db, current_user.id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    incidents = await get_guardian_incidents_filtered(db, current_user.id, skip=skip, limit=limit)
    return incidents