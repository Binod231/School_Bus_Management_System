# school_bus_management/app/routes/driver.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.db.session import get_db
from app.core.jwt import get_current_driver, get_current_active_user
# CORRECTED: Import UserResponse, not DriverResponse
from app.schemas.user import UserResponse, UserRole
from app.schemas.trip import TripCreate, TripResponse, TripUpdate, TripStudentUpdate, LocationUpdateCreate, LocationUpdateResponse, TripStudentResponse, MarkStudentsBoardedRequest
from app.schemas.student import StudentResponse
from app.schemas.bus import BusResponse, BusRouteResponse
from app.services.trip import create_trip, get_driver_trips, get_trip_by_id, update_trip, get_trip_students, update_trip_student, create_location_update, get_all_active_trips_for_driver, mark_students_boarded, get_trip_student
from app.services.student import get_students_by_bus_route, get_student_by_id, get_student_guardians
from app.services.notification import notify_guardians_student_boarding
from app.utils.qrcode import verify_student_qr_code
from app.services.bus import get_bus_by_id, get_bus_route_by_id, get_bus_drivers, get_buses, get_bus_routes
from app.core.exceptions import NotFoundException, InvalidDataException
from app.models.trip import StudentStatus, TripStudent
from sqlalchemy import select, func
from datetime import datetime
from app.utils.websocket import manager
from app.services.user import get_users
from app.schemas.incident import IncidentResponse, IncidentUpdate, IncidentCreateForDriver, IncidentUpdateForDriver
from app.models.student import Student
from app.models.bus import BusRoute
from app.models.student import GuardianStudent, Guardian
from sqlalchemy.orm import selectinload
from app.services.trip import get_trip_students, delete_trip, update_student_status_on_trip
from app.services.incident import get_driver_incidents
from app.models.user import User
from app.services.bus import Bus
from app.services.incident import  get_incident_by_id, update_incident_for_driver, delete_incident
from app.services.notification import notify_guardians_of_trip_incident, notify_guardians_incident
from app.services.incident import  get_incident_by_id, update_incident, delete_incident, get_user_reported_incidents, create_incident_for_driver

router = APIRouter(
    prefix="/driver",
    tags=["driver"],
    dependencies=[Depends(get_current_driver)]
)


@router.get(
    "/me",
    response_model=UserResponse, 
    summary="Get current driver profile",
    description="Retrieves the profile of the currently logged-in driver."
)
async def get_my_profile(
    current_user = Depends(get_current_driver)
):
    return current_user

# RESTORED: Endpoint to get the currently active trip
@router.get(
    "/trips/active",
    response_model=List[TripResponse], # <-- Changed to List
    summary="Get all active trips",
    description="Retrieves all currently active trips for the driver."
)
async def get_active_trips( # Renamed function for clarity
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    active_trips = await get_all_active_trips_for_driver(db, driver_id=current_user.id)
    return active_trips

# endpoint to get a single trip's details
@router.get(
    "/trips/{trip_id}",
    response_model=TripResponse,
    summary="Get Trip Details",
    description="Retrieve the full details of a specific trip, including students."
)
async def get_trip_details_endpoint(
    trip_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_driver)
):
    """
    Get a single trip by its ID, ensuring the driver is authorized.
    """
    try:
        trip = await get_trip_by_id(db, trip_id)
        if trip.driver_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this trip."
            )
        return trip
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

# Your endpoint for drivers to get a list of buses
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

# KEPT: Your endpoint for drivers to get a list of routes
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

    if bus.school_id != current_user.school_id or route.school_id != current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bus or Route doesn't belong to your school"
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
    summary="List all trips for the driver"
)
async def list_trips(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    trips = await get_driver_trips(db, driver_id=current_user.id, skip=skip, limit=limit)
    
    # Add student count to each trip
    for trip in trips:
        # Get students for this trip's route
        result = await db.execute(
            select(func.count(Student.id))
            .where(Student.bus_route_id == trip.route_id)
        )
        student_count = result.scalar()
        trip.student_count = student_count
        # You might need to add boarded_count as well if tracking that
    
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

    # Get students and eagerly load all required relationships
    result = await db.execute(
        select(Student)
        .where(Student.bus_route_id == trip.route_id)
        .options(
            selectinload(Student.bus_route).selectinload(BusRoute.bus),
            selectinload(Student.guardians).selectinload(GuardianStudent.guardian).selectinload(Guardian.user)
        )
    )
    students = result.scalars().all()
    
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

    # Check if guardian has already confirmed arrival
    # Fetch the current TripStudent record to check status
    try:
        current_trip_student = await get_trip_student(db, trip_id, student_id)
        
        # If this is a FROM_SCHOOL trip and the student is already AT_HOME with disembarked_at set,
        # it means the guardian has confirmed arrival and driver cannot modify
        if (trip.direction == TripDirection.FROM_SCHOOL and 
            current_trip_student.status == StudentStatus.AT_HOME and 
            current_trip_student.disembarked_at is not None):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify student status - Guardian has already confirmed arrival"
            )
    except NotFoundException:
        # If no record exists yet, it's fine to create one
        pass

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

    # Fixed parameter order: broadcast(message, room_id)
    await manager.broadcast(
        {
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
        },
        str(trip_id)
    )
    

    return location_update



@router.get("/incidents", response_model=List[IncidentResponse])
async def list_my_incidents(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_driver)
):
    # CHANGE THIS LINE to use the new service function
    incidents = await get_driver_incidents(db, driver_id=current_user.id, skip=skip, limit=limit)
    return incidents


@router.post(
    "/incidents",
    response_model=IncidentResponse,
    summary="Report a new incident"
)
async def report_incident(
    incident_data: IncidentCreateForDriver,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_driver)
):
    # Find the active trip for the driver to associate with the incident
    active_trips = await get_all_active_trips_for_driver(db, driver_id=current_user.id)
    
    if not active_trips:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You do not have an active trip to report an incident for."
        )
    
    active_trip = active_trips[0]
    
    # Set the trip_id directly on the Pydantic model. DO NOT convert to a dict.
    incident_data.trip_id = active_trip.id

    # Call the service function with the updated Pydantic model
    incident = await create_incident_for_driver(
        db, 
        incident_in=incident_data, 
        user_id=current_user.id,
        school_id=current_user.school_id 
    )
    
    bus_number = active_trip.bus.bus_number if active_trip.bus else "N/A"

    # If a student is involved, notify only their guardians
    if incident.student_id:
        student = await get_student_by_id(db, student_id=incident.student_id)
        details = f"An incident '{incident.type}' involving your child, {student.first_name}, has been reported. Details: {incident.description}"
        
        await notify_guardians_incident(
            db,
            student_id=incident.student_id,
            incident_type=incident.type,
            details=details
        )
    else:
        # If no student is involved, notify all guardians on the trip
        details = (
            f"A general incident ('{incident.type}') has been reported for the trip "
            f"on Bus {bus_number}. Details: {incident.description}"
        )
        await notify_guardians_of_trip_incident(
            db,
            trip_id=active_trip.id,
            incident_type=incident.type,
            details=details
        )

    return incident

@router.put(
    "/incidents/{incident_id}",
    response_model=IncidentResponse,
    summary="Update an incident reported by the driver"
)
async def update_driver_incident(
    incident_id: int,
    incident_data: IncidentUpdateForDriver,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_driver)
):
    """
    Allows a driver to update an incident they have reported.
    """
    # Get the incident from the database - FIX THIS LINE
    incident = await get_incident_by_id(db, incident_id=incident_id) 

    # Check if the incident exists
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found"
        )

    # Ensure the driver is updating their own incident
    if incident.reported_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to update this incident"
        )

    # Correctly call the service function
    updated_incident = await update_incident_for_driver(
        db,
        incident_db_obj=incident,  # ✅ Correct parameter name
        incident_in=incident_data
    )

    return updated_incident

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
    summary="Verify student QR code and board onto active trip",
    description="Allows a driver to scan and verify a student's QR code, which boards them onto the current active trip."
)
async def verify_student_qr(
    # FIX: Changed to accept a JSON object, which is standard
    qr_data: dict, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Verifies a student's QR code. If valid, it finds the driver's single active trip
    and updates the student's status to 'on_bus' for that trip.
    """
    try:
        # Pass the actual data string from the JSON object
        student = await verify_student_qr_code(db, qr_data.get("qr_data"), current_user.school_id)
    except InvalidDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or unrecognized QR Code.")

    if student.school_id != current_user.school_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student does not belong to your school.")

    # --- This is the critical new logic ---
    active_trips = await get_all_active_trips_for_driver(db, driver_id=current_user.id)
    
    if not active_trips:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You do not have an active trip to board students onto.")
    
    # Ensure there is only one active trip for clarity
    if len(active_trips) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Multiple active trips found. Please contact an administrator.")
    
    active_trip = active_trips[0]

    # Board the student onto the found active trip
    updated_trip_student = await update_student_status_on_trip(
        db,
        trip_id=active_trip.id,
        student_id=student.id,
        status=StudentStatus.ON_BUS
    )

    if not updated_trip_student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student {student.first_name} is not assigned to this trip.")

    return {"valid": True, "student": student}

@router.post(
    "/trips/{trip_id}/mark-boarded",
    summary="Mark selected students as boarded",
    description="Marks a list of students assigned to a trip's route as boarded."
)
async def mark_students_boarded_endpoint(
    trip_id: int,
    boarding_data: MarkStudentsBoardedRequest,
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

    await mark_students_boarded(db, trip_id, boarding_data.student_ids)

    # Notify guardians only for the students who were marked as boarded
    for student_id in boarding_data.student_ids:
        # This will silently fail if a student isn't found, which is acceptable here
        try:
            student = await get_student_by_id(db, student_id)
            if student:
                 await notify_guardians_student_boarding(
                    db,
                    student_id=student.id,
                    bus_number=trip.bus.bus_number,
                    time=datetime.now().strftime("%H:%M")
                )
        except NotFoundException:
            continue

    return {"message": "Selected students have been marked as boarded."}

