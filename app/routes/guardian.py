from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.db.session import get_db
from app.core.jwt import get_current_guardian
from app.schemas.student import StudentResponse
from app.schemas.trip import TripResponse, LocationUpdateResponse
from app.services.student import get_guardian_students, get_student_by_id, get_guardian_by_user_id, get_guardian_student_relationship
from app.services.trip import get_student_trips, get_trip_location_updates as get_trip_location_updates_service, get_trip_by_id, get_trip_students, get_active_student_trip, update_trip_student, get_trip_student
from app.services.student import update_guardian
from app.core.exceptions import NotFoundException
from app.services.notification import notify_admin_arrival_confirmation
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

    students = await get_guardian_students(db, guardian.id)
    return students


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

    try:
        active_trip = await get_active_student_trip(db, student_id)
    except NotFoundException:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active trip found for this student"
        )

    try:
        trip_student = await get_trip_student(db, active_trip.id, student_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    update_data = {
        "status": "at_school" if confirmed else "on_bus",
        "disembarked_at": datetime.now() if confirmed else None
    }

    await update_trip_student(db, active_trip.id, student_id, update_data)

    student = await get_student_by_id(db, student_id)
    await notify_admin_arrival_confirmation(db, student, current_user, confirmed)

    return {"message": f"Arrival {'confirmed' if confirmed else 'not confirmed'} successfully"}