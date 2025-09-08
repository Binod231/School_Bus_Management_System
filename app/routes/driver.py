from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.db.session import get_db
from app.core.jwt import get_current_driver, verify_school_resource_access
from app.schemas.trip import TripCreate, TripResponse, TripUpdate, TripStudentUpdate, LocationUpdateCreate, LocationUpdateResponse, TripStudentResponse
from app.schemas.student import StudentResponse
from app.schemas.bus import BusResponse, BusRouteResponse # Import bus schemas
from app.services.trip import create_trip, get_driver_trips, get_trip_by_id, update_trip, get_trip_students, update_trip_student, create_location_update, mark_all_students_boarded
from app.services.student import get_students_by_bus_route, get_student_by_id, get_student_guardians
from app.services.notification import notify_guardians_student_boarding
from app.utils.qrcode import verify_student_qr_code
from app.services.bus import get_bus_by_id, get_bus_route_by_id, get_bus_drivers, get_buses, get_bus_routes # Import bus services
from app.core.exceptions import NotFoundException, InvalidDataException
from app.models.trip import StudentStatus
from datetime import datetime
from app.utils.websocket import manager
from app.schemas.user import UserRole
from app.services.user import get_users
from app.schemas.incident import IncidentCreate, IncidentResponse
from app.services.incident import create_incident, get_incident_by_id, update_incident, delete_incident, get_user_reported_incidents
from app.schemas.incident import IncidentUpdate

router = APIRouter(
    prefix="/driver",
    tags=["driver"],
    dependencies=[Depends(get_current_driver)]
)

# NEW: Endpoint for drivers to get a list of buses in their school
@router.get(
    "/buses",
    response_model=List[BusResponse],
    summary="List available buses",
    description="Retrieves a list of all active buses associated with the driver's school."
)
async def list_buses_for_driver(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    buses = await get_buses(db, school_id=current_user.school_id)
    return buses

# NEW: Endpoint for drivers to get a list of routes in their school
@router.get(
    "/routes",
    response_model=List[BusRouteResponse],
    summary="List available routes",
    description="Retrieves a list of all active bus routes associated with the driver's school."
)
async def list_routes_for_driver(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    routes = await get_bus_routes(db, school_id=current_user.school_id)
    return routes


@router.post(
    "/trips", 
    response_model=TripResponse,
    summary="Start a new trip",
    description="Allows a driver to start a new trip, provided they are assigned to the bus and have access to the route."
)
async def start_trip(
    trip_data: TripCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    try:
        bus = await get_bus_by_id(db, trip_data.bus_id)
        route = await get_bus_route_by_id(db, trip_data.route_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    
    if bus.school_id != current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bus doesn't belong to your school"
        )
    
    if route.school_id != current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Route doesn't belong to your school"
        )
    
    drivers = await get_bus_drivers(db, trip_data.bus_id)
    driver_assigned = any(driver.driver_id == current_user.id for driver in drivers)
    
    if not driver_assigned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this bus"
        )
    
    trip_data_dict = trip_data.dict()
    trip_data_dict["driver_id"] = current_user.id
    
    trip = await create_trip(db, trip_data=trip_data_dict)
    return trip


@router.get(
    "/trips", 
    response_model=List[TripResponse],
    summary="List all trips for the driver",
    description="Retrieves a list of all trips assigned to the current driver, ordered by scheduled start time."
)
async def list_trips(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    trips = await get_driver_trips(db, driver_id=current_user.id, skip=skip, limit=limit)
    return trips


@router.get(
    "/trips/{trip_id}/students", 
    response_model=List[StudentResponse],
    summary="Get students for a specific trip",
    description="Retrieves the list of students assigned to the route of a specific trip."
)
async def get_trip_students_list(
    trip_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    try:
        trip = await get_trip_by_id(db, trip_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    
    if trip.driver_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this trip"
        )
    
    students = await get_students_by_bus_route(db, trip.route_id)
    return students


@router.patch(
    "/trips/{trip_id}", 
    response_model=TripResponse,
    summary="Update trip status",
    description="Allows a driver to update the status of an ongoing trip (e.g., from 'scheduled' to 'in_progress')."
)
async def update_trip_status(
    trip_id: int,
    trip_data: TripUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    try:
        trip = await get_trip_by_id(db, trip_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    
    if trip.driver_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this trip"
        )
    
    updated_trip = await update_trip(db, trip_id, trip_data.dict(exclude_unset=True))
    return updated_trip


@router.patch(
    "/trips/{trip_id}/students/{student_id}", 
    response_model=TripStudentResponse,
    summary="Update student status on a trip",
    description="Allows a driver to mark a student's status on a trip (e.g., 'on_bus' or 'at_school')."
)
async def update_student_status(
    trip_id: int,
    student_id: int,
    student_data: TripStudentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    try:
        trip = await get_trip_by_id(db, trip_id)
        student = await get_student_by_id(db, student_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    if trip.driver_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this trip"
        )

    if student.bus_route_id != trip.route_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student not assigned to this route's trip"
        )
    
    updated_student = await update_trip_student(db, trip_id, student_id, student_data.dict(exclude_unset=True))
    
    if student_data.status == StudentStatus.ON_BUS and student_data.boarded_at:
        await notify_guardians_student_boarding(
            db,
            student_id=student_id,
            bus_number=trip.bus.bus_number,
            time=student_data.boarded_at.strftime("%H:%M")
        )
    
    return updated_student


@router.post(
    "/trips/{trip_id}/location", 
    response_model=LocationUpdateResponse,
    summary="Update trip location",
    description="Sends a live location update for an ongoing trip."
)
async def update_trip_location(
    trip_id: int,
    location_data: LocationUpdateCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    try:
        trip = await get_trip_by_id(db, trip_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    
    if trip.driver_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this trip"
        )
    
    location_data_dict = location_data.dict()
    location_data_dict["trip_id"] = trip_id
    
    location_update = await create_location_update(db, location_data=location_data_dict)

    # --- Start WebSocket Broadcast Logic ---
    # 1. Find all admins for the school
    admins = await get_users(db, school_id=current_user.school_id, role=UserRole.ADMIN)
    admin_ids = [str(admin.id) for admin in admins]

    # 2. Find all guardians for students on this trip
    trip_students = await get_trip_students(db, trip_id)
    guardian_ids = []
    for ts in trip_students:
        guardians = await get_student_guardians(db, ts.student_id)
        for guardian in guardians:
            guardian_ids.append(str(guardian.user_id))

    # 3. Combine and broadcast
    recipients = list(set(admin_ids + guardian_ids))
    message = {
        "type": "location_update",
        "trip_id": trip.id,
        "bus_id": trip.bus_id,
        "location": {
            "latitude": float(location_update.latitude),
            "longitude": float(location_update.longitude),
            "speed": float(location_update.speed) if location_update.speed else 0,
            "heading": float(location_update.heading) if location_update.heading else 0,
            "timestamp": location_update.timestamp.isoformat(),
        }
    }
    await manager.broadcast(message, recipients)
    # --- End WebSocket Broadcast Logic ---

    return location_update

@router.get("/incidents", response_model=List[IncidentResponse])
async def list_my_incidents(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    incidents = await get_user_reported_incidents(db, user_id=current_user.id, skip=skip, limit=limit)
    return incidents


@router.post(
    "/incidents",
    response_model=IncidentResponse,
    summary="Report a new incident"
)
async def report_incident(
    incident_data: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    incident_dict = incident_data.dict()
    # Override reporter and school to ensure security
    incident_dict["reported_by_id"] = current_user.id
    incident_dict["school_id"] = current_user.school_id

    incident = await create_incident(db, incident_dict)

    # Notify all school admins via WebSocket
    admins = await get_users(db, school_id=current_user.school_id, role="admin")
    recipients = [str(admin.id) for admin in admins]
    message = {
        "type": "incident_reported",
        "incident": {
            "id": incident.id,
            "title": incident.title,
            "description": incident.description,
            "type": incident.type,
            "status": incident.status,
            "student_id": incident.student_id,
            "reported_by_id": incident.reported_by_id,
            "occurred_at": incident.occurred_at.isoformat()
        }
    }
    await manager.broadcast(message, recipients)

    return incident

@router.patch("/{incident_id}", response_model=IncidentResponse)
async def update_my_incident(
    incident_id: int,
    incident_data: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    incident = await get_incident_by_id(db, incident_id)
    if incident.reported_by_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update incidents you reported")
    updated_incident = await update_incident(db, incident_id, incident_data.dict(exclude_unset=True))
    return updated_incident

# Delete an incident (only by the driver who reported it)
@router.delete("/{incident_id}", response_model=dict)
async def delete_my_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    incident = await get_incident_by_id(db, incident_id)
    if incident.reported_by_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete incidents you reported")
    await delete_incident(db, incident_id)
    return {"message": "Incident deleted successfully"}

@router.post(
    "/students/verify-qr",
    summary="Verify student QR code",
    description="Allows a driver to scan and verify a student's QR code for boarding."
)
async def verify_student_qr(
    qr_data: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    try:
        student = await verify_student_qr_code(qr_data, db)
    except InvalidDataException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    
    if student.school_id != current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student doesn't belong to your school"
        )
    
    return {
        "valid": True,
        "student": {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_id": student.student_id,
            "grade": student.grade
        }
    }


@router.post(
    "/mark-all-boarded",
    summary="Mark all students as boarded",
    description="Marks all students assigned to a trip's route as boarded at the current time."
)
async def mark_all_students_boarded_endpoint(
    trip_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    try:
        trip = await get_trip_by_id(db, trip_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    
    if trip.driver_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this trip"
        )
    
    await mark_all_students_boarded(db, trip_id)
    
    students = await get_students_by_bus_route(db, trip.route_id)
    for student in students:
        await notify_guardians_student_boarding(
            db,
            student_id=student.id,
            bus_number=trip.bus.bus_number,
            time=datetime.now().strftime("%H:%M")
        )
    
    return {"message": "All students marked as boarded"}