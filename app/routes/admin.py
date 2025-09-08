from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.db.session import get_db
from app.core.jwt import get_current_admin, verify_school_resource_access, get_current_active_user
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.schemas.student import StudentCreate, StudentResponse, StudentUpdate, GuardianUpdate, GuardianCreate, GuardianResponse, GuardianWithStudentsResponse
from app.schemas.bus import BusCreate, BusResponse, BusRouteCreate, BusRouteResponse, BusUpdate, BusRouteUpdate, BusDriverCreate
from app.core.exceptions import NotFoundException, InvalidDataException
from app.services.user import create_user, get_users, get_user_by_id, get_user_by_email, update_user, delete_user
from app.services.student import create_student, get_students, get_student_by_id, update_student, delete_student, get_guardian_by_user_id, update_guardian, delete_guardian_by_user_id
from app.services.bus import create_bus, get_buses, create_bus_route, get_bus_routes, assign_driver_to_bus, get_bus_by_id, update_bus, delete_bus, get_bus_route_by_id, update_bus_route, delete_bus_route
from app.utils.email import send_new_user_email
from app.models.user import UserRole, User
from app.models.incident import Incident
from app.models.student import Student
from app.models.bus import Bus
from app.models.trip import Trip
from sqlalchemy import func, select
from app.services.student import create_guardian_student, GuardianStudent, create_guardian, get_guardians, get_guardian_by_user_id, delete_guardian_by_user_id,  update_student as update_student_service,delete_student as delete_student_service, get_student_by_id, get_guardian_by_id
from app.schemas.bus import BusStopCreate, BusStopUpdate, BusStopResponse
from app.services.bus import create_bus_stop, get_bus_stops as get_bus_stops_service, update_bus_stop, delete_bus_stop, get_bus_stop_by_id
from app.services.trip import get_active_trips_with_locations
from datetime import datetime
from fastapi.responses import Response
from app.schemas.trip import TripResponse
from app.services.incident import get_incidents as get_all_incidents, get_incidents
from app.schemas.incident import IncidentResponse
from sqlalchemy.orm import selectinload
from app.models.student import Guardian


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin)]
)


@router.post(
    "/drivers", 
    response_model=UserResponse,
    summary="Create a new driver account",
    description="Allows an admin to create a new driver account and associate it with their school."
)
async def create_driver(
    driver_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        if driver_data.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role must be 'driver' for driver accounts"
            )
        
        try:
            await get_user_by_email(db, email=driver_data.email)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists."
            )
        except NotFoundException:
            pass
        
        driver_data_dict = driver_data.dict()
        driver_data_dict["school_id"] = current_user.school_id
        
        driver = await create_user(db, user_data=driver_data_dict)
        
        await send_new_user_email(driver.email, driver.id)
        
        return driver
    except InvalidDataException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/drivers", 
    response_model=List[UserResponse],
    summary="List all drivers",
    description="Retrieves a list of all driver accounts associated with the admin's school."
)
async def list_drivers(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    drivers = await get_users(
        db, 
        school_id=current_user.school_id, 
        role=UserRole.DRIVER,
        skip=skip, 
        limit=limit
    )
    return drivers


@router.post(
    "/guardians",
    response_model=GuardianWithStudentsResponse,
    summary="Create a new guardian with assigned students"
)
async def create_guardian_with_students(
    guardian_data: GuardianCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        # Check if user already exists
        try:
            await get_user_by_email(db, guardian_data.email)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists."
            )
        except NotFoundException:
            pass

        # Create user for guardian
        user_dict = guardian_data.dict(exclude={"student_ids"})
        user_dict["school_id"] = current_user.school_id
        user_dict["role"] = UserRole.GUARDIAN
        
        # Include password if provided
        if guardian_data.password:
            user_dict["password"] = guardian_data.password
            
        guardian_user = await create_user(db, user_data=user_dict)

        # Create guardian record
        guardian = await create_guardian(db, {"user_id": guardian_user.id})

        # Assign students
        assigned_students = []
        for student_id in guardian_data.student_ids or []:
            try:
                student = await get_student_by_id(db, student_id)
                if student.school_id != current_user.school_id:
                    continue

                # Create guardian-student relationship
                gs = await create_guardian_student(db, {
                    "guardian_id": guardian.id,
                    "student_id": student.id,
                    "relationship_type": "parent",
                    "is_primary": False
                })
                assigned_students.append(gs)
            except NotFoundException:
                continue

        # Return the response with proper data
        return {
            "id": guardian.id,
            "user_id": guardian_user.id,
            "email": guardian_user.email,
            "first_name": guardian_user.first_name,
            "last_name": guardian_user.last_name,
            "phone": guardian_user.phone,
            "fcm_token": guardian.fcm_token,
            "created_at": guardian.created_at,
            "updated_at": guardian.updated_at,
            "students": assigned_students
        }
        
    except Exception as e:
        print(f"Error creating guardian: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create guardian: {str(e)}"
        )

# Add missing guardian endpoints
@router.get(
    "/guardians",
    response_model=List[GuardianResponse],
    summary="List all guardians"
)
async def list_guardians(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    guardians = await get_guardians(db, school_id=current_user.school_id, skip=skip, limit=limit)
    return [
        {
            "id": g.id,
            "user_id": g.user.id,
            "email": g.user.email,
            "first_name": g.user.first_name,
            "last_name": g.user.last_name,
            "phone": g.user.phone,
            "fcm_token": g.fcm_token,
            "created_at": g.created_at,
            "updated_at": g.updated_at
        }
        for g in guardians
    ]


@router.post("/students", response_model=StudentResponse)
async def create_student_account(
    student_data: StudentCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        # Validate school access
        if student_data.school_id != current_user.school_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot create student for another school"
            )
        
        # Create student
        student = await create_student(db, student_data=student_data.dict())
        return student
        
    except InvalidDataException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Log the actual error for debugging
        print(f"Student creation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/students", 
    response_model=List[StudentResponse],
    summary="List all students",
    description="Retrieves a list of all students associated with the admin's school."
)
async def list_students(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    students = await get_students(
        db, 
        school_id=current_user.school_id,
        skip=skip, 
        limit=limit
    )
    return students


@router.post(
    "/buses", 
    response_model=BusResponse,
    summary="Create a new bus",
    description="Allows an admin to create a new bus and associate it with their school."
)
async def create_bus_account(
    bus_data: BusCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    if bus_data.school_id != current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create bus for another school"
        )
    
    bus = await create_bus(db, bus_data=bus_data.dict())
    return bus


@router.get(
    "/buses", 
    response_model=List[BusResponse],
    summary="List all buses",
    description="Retrieves a list of all buses associated with the admin's school."
)
async def list_buses(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    buses = await get_buses(
        db, 
        school_id=current_user.school_id,
        skip=skip, 
        limit=limit
    )
    return buses


@router.post(
    "/bus-routes", 
    response_model=BusRouteResponse,
    summary="Create a new bus route",
    description="Allows an admin to create a new bus route and associate it with their school."
)
async def create_bus_route_account(
    route_data: BusRouteCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    if route_data.school_id != current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create bus route for another school"
        )
    
    route = await create_bus_route(db, route_data=route_data.dict())
    return route


@router.get(
    "/bus-routes", 
    response_model=List[BusRouteResponse],
    summary="List all bus routes",
    description="Retrieves a list of all bus routes associated with the admin's school."
)
async def list_bus_routes(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    routes = await get_bus_routes(
        db, 
        school_id=current_user.school_id,
        skip=skip, 
        limit=limit
    )
    return routes


@router.post(
    "/bus-drivers", 
    response_model=BusResponse,
    summary="Assign a driver to a bus",
    description="Assigns a driver to a specific bus. The driver's previous bus assignment will be deactivated."
)
async def assign_driver(
    assignment_data: BusDriverCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        driver = await get_user_by_id(db, assignment_data.driver_id)
        bus = await get_bus_by_id(db, assignment_data.bus_id)
    
        if driver.school_id != current_user.school_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Driver does not belong to your school"
            )
        
        if bus.school_id != current_user.school_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bus does not belong to your school"
            )
    
        if driver.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not a driver"
            )
    
        assignment = await assign_driver_to_bus(db, assignment_data=assignment_data.dict())
        
        # Reload bus object with relationships
        await db.refresh(bus, ["drivers"])
        return bus
    
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )


@router.get(
    "/dashboard/stats",
    summary="Get dashboard statistics",
    description="Retrieves a summary of key statistics for the admin's school, including counts of drivers, students, buses, and active incidents/trips."
)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    drivers_count = await db.scalar(
        select(func.count(User.id)).where(
            User.school_id == current_user.school_id,
            User.role == UserRole.DRIVER,
            User.is_active == True
        )
    )
    
    guardians_count = await db.scalar(
        select(func.count(User.id)).where(
            User.school_id == current_user.school_id,
            User.role == UserRole.GUARDIAN,
            User.is_active == True
        )
    )
    
    students_count = await db.scalar(
        select(func.count(Student.id)).where(
            Student.school_id == current_user.school_id,
            Student.is_active == True
        )
    )
    
    buses_count = await db.scalar(
        select(func.count(Bus.id)).where(
            Bus.school_id == current_user.school_id,
            Bus.is_active == True
        )
    )
    
    active_incidents_count = await db.scalar(
        select(func.count(Incident.id)).where(
            Incident.school_id == current_user.school_id,
            Incident.status.in_(["reported", "under_review"])
        )
    )
    
    active_trips_count = await db.scalar(
        select(func.count(Trip.id)).where(
            Trip.status == "in_progress"
        )
    )
    
    return {
        "drivers": drivers_count or 0,
        "guardians": guardians_count or 0,
        "students": students_count or 0,
        "buses": buses_count or 0,
        "active_incidents": active_incidents_count or 0,
        "active_trips": active_trips_count or 0
    }
    

# -------------------- USER UPDATE & DELETE --------------------

@router.put(
    "/drivers/{driver_id}",
    response_model=UserResponse,
    summary="Update a driver account"
)
async def update_driver(
    driver_id: int,
    driver_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        driver = await get_user_by_id(db, driver_id)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Driver not found")

    if driver.role != UserRole.DRIVER or driver.school_id != current_user.school_id:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    return await update_user(db, driver_id, driver_data.dict(exclude_unset=True))

@router.delete(
    "/drivers/{driver_id}",
    summary="Delete a driver account"
)
async def delete_driver(
    driver_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        driver = await get_user_by_id(db, driver_id)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Driver not found")
        
    if driver.role != UserRole.DRIVER or driver.school_id != current_user.school_id:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    await delete_user(db, driver_id)
    return {"detail": "Driver deleted"}

@router.put(
    "/guardians/{guardian_id}",
    response_model=GuardianWithStudentsResponse,
    summary="Update a guardian and their students"
)
async def update_guardian_with_students(
    guardian_id: int,
    guardian_data: GuardianUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        # Get the guardian
        guardian = await get_guardian_by_id(db, guardian_id)
        guardian_user = await get_user_by_id(db, guardian.user_id)
        
        # Verify school access
        if guardian_user.school_id != current_user.school_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Guardian does not belong to your school"
            )

        # Update user data
        update_data = guardian_data.dict(exclude={"student_ids", "fcm_token"}, exclude_unset=True)
        if update_data:
            await update_user(db, guardian.user_id, update_data)

        # Update guardian-specific data
        if guardian_data.fcm_token is not None:
            await update_guardian(db, guardian_id, {"fcm_token": guardian_data.fcm_token})

        # Update student assignments
        if guardian_data.student_ids is not None:
            # Remove existing relationships
            existing_relationships = await db.execute(
                select(GuardianStudent).where(GuardianStudent.guardian_id == guardian_id)
            )
            for rel in existing_relationships.scalars().all():
                await db.delete(rel)

            # Add new relationships
            for student_id in guardian_data.student_ids:
                try:
                    student = await get_student_by_id(db, student_id)
                    if student.school_id == current_user.school_id:
                        await create_guardian_student(db, {
                            "guardian_id": guardian_id,
                            "student_id": student_id,
                            "relationship_type": "parent",
                            "is_primary": False
                        })
                except NotFoundException:
                    continue

        await db.commit()

        # Get updated guardian with students
        result = await db.execute(
            select(Guardian)
            .where(Guardian.id == guardian_id)
            .options(selectinload(Guardian.students).selectinload(GuardianStudent.student))
        )
        updated_guardian = result.scalar_one()

        return {
            "id": updated_guardian.id,
            "user_id": guardian_user.id,
            "email": guardian_user.email,
            "first_name": guardian_user.first_name,
            "last_name": guardian_user.last_name,
            "phone": guardian_user.phone,
            "fcm_token": updated_guardian.fcm_token,
            "created_at": updated_guardian.created_at,
            "updated_at": updated_guardian.updated_at,
            "students": updated_guardian.students
        }
        
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update guardian: {str(e)}"
        )
@router.delete(
    "/guardians/{guardian_user_id}",
    summary="Delete a guardian account"
)
async def delete_guardian_user(
    guardian_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        guardian_user = await get_user_by_id(db, guardian_user_id)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Guardian not found")

    if guardian_user.role != UserRole.GUARDIAN or guardian_user.school_id != current_user.school_id:
        raise HTTPException(status_code=404, detail="Guardian not found")
    
    await delete_guardian_by_user_id(db, guardian_user_id)
    await delete_user(db, guardian_user_id)
    return {"detail": "Guardian deleted"}

@router.put("/students/{student_id}", response_model=StudentResponse)
async def update_student(
    student_id: int,
    student_data: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Update an existing student's information.
    """
    # Use the new service function to update the student
    updated_student = await update_student_service(db, student_id, student_data)

    if updated_student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    return updated_student
@router.delete(
    "/students/{student_id}",
    summary="Delete a student account"
)
@router.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Delete a student by their ID.
    """
    success = await delete_student_service(db, student_id)
    if not success:
        raise HTTPException(status_code=404, detail="Student not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# -------------------- BUS & ROUTE UPDATE & DELETE --------------------

@router.put(
    "/buses/{bus_id}",
    response_model=BusResponse,
    summary="Update a bus"
)
async def update_bus_endpoint(
    bus_id: int,
    bus_data: BusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        bus = await get_bus_by_id(db, bus_id)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Bus not found")

    if bus.school_id != current_user.school_id:
        raise HTTPException(status_code=404, detail="Bus not found")
    
    return await update_bus(db, bus_id, bus_data.dict(exclude_unset=True))

@router.delete(
    "/buses/{bus_id}",
    summary="Delete a bus"
)
async def delete_bus_endpoint(
    bus_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        bus = await get_bus_by_id(db, bus_id)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Bus not found")

    if bus.school_id != current_user.school_id:
        raise HTTPException(status_code=404, detail="Bus not found")

    await delete_bus(db, bus_id)
    return {"detail": "Bus deleted"}

@router.put(
    "/bus-routes/{route_id}",
    response_model=BusRouteResponse,
    summary="Update a bus route"
)
async def update_bus_route_endpoint(
    route_id: int,
    route_data: BusRouteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        route = await get_bus_route_by_id(db, route_id)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Bus route not found")

    if route.school_id != current_user.school_id:
        raise HTTPException(status_code=404, detail="Bus route not found")
    
    return await update_bus_route(db, route_id, route_data.dict(exclude_unset=True))

@router.delete(
    "/bus-routes/{route_id}",
    summary="Delete a bus route"
)
async def delete_bus_route_endpoint(
    route_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    try:
        route = await get_bus_route_by_id(db, route_id)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Bus route not found")
    
    if route.school_id != current_user.school_id:
        raise HTTPException(status_code=404, detail="Bus route not found")

    await delete_bus_route(db, route_id)
    return {"detail": "Bus route deleted"}

# --- BUS STOP MANAGEMENT ---

@router.post(
    "/bus-stops",
    response_model=BusStopResponse,
    summary="Create a new bus stop",
)
async def create_new_bus_stop(
    bus_stop_data: BusStopCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    # In a real app, you might associate stops with a school, but keeping it simple for now.
    return await create_bus_stop(db, bus_stop_data.dict())

@router.get(
    "/bus-stops",
    response_model=List[BusStopResponse],
    summary="List all bus stops for a school",
)
async def list_bus_stops(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    # This assumes stops are indirectly linked to schools via routes.
    return await get_bus_stops_service(db, school_id=current_user.school_id)


@router.put(
    "/bus-stops/{stop_id}",
    response_model=BusStopResponse,
    summary="Update a bus stop"
)
async def update_existing_bus_stop(
    stop_id: int,
    bus_stop_data: BusStopUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    # Add verification logic here to ensure stop belongs to admin's school if needed
    return await update_bus_stop(db, stop_id, bus_stop_data.dict(exclude_unset=True))

@router.delete(
    "/bus-stops/{stop_id}",
    summary="Delete a bus stop",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_existing_bus_stop(
    stop_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    # Add verification logic here
    await delete_bus_stop(db, stop_id)
    return {"detail": "Bus stop deleted"}

@router.get("/live-locations", response_model=List[dict])
async def get_live_bus_locations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get detailed live location and status for all active buses in the admin's school.
    """
    if not current_user.school_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a school")
        
    active_trips = await get_active_trips_with_locations(db, current_user.school_id)
    
    response_data = []
    for trip in active_trips:
        if not trip.bus:
            continue
            
        response_data.append({
            "id": trip.bus.id,
            "trip_id": trip.id,
            "bus_number": trip.bus.bus_number,
            "driver_name": f"{trip.driver.first_name} {trip.driver.last_name}" if trip.driver else "N/A",
            "driver_phone": trip.driver.phone if trip.driver else "N/A",
            "route_name": trip.route.name if trip.route else "N/A",
            "students_count": len(trip.students),
            "status": trip.status.value,
            "current_location": {
                "latitude": trip.bus.latitude,
                "longitude": trip.bus.longitude,
                "timestamp": datetime.utcnow().isoformat(), # Using current time as placeholder
                "speed": 50, # Placeholder
                "heading": 0, # Placeholder
            } if trip.bus.latitude and trip.bus.longitude else None,
            "next_stop": trip.route.stops[0].name if trip.route and trip.route.stops else "N/A", # Placeholder
            "estimated_arrival": datetime.utcnow().isoformat() # Placeholder
        })
        
    return response_data

@router.get(
    "/incidents",
    response_model=List[dict],
    summary="Get all incidents with trip and bus info",
    description="Allows admin to view all incidents with related trip and bus details."
)
async def admin_get_all_incidents(
    school_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    # Fetch incidents with optional filters
    incidents = await get_incidents(db, school_id=school_id, status=status, skip=skip, limit=limit)
    
    result_list = []
    for incident in incidents:
        trip_id = None
        bus_id = None
        # If incident is associated with a student, try to get their trip
        if incident.student_id:
            trip_query = select(Trip).where(Trip.route_id == incident.student.bus_route_id).limit(1)
            trip_result = await db.execute(trip_query)
            trip = trip_result.scalar_one_or_none()
            if trip:
                trip_id = trip.id
                bus_id = trip.bus_id
        
        result_list.append({
            "incident": IncidentResponse.from_orm(incident),
            "trip_id": trip_id,
            "bus_id": bus_id
        })
    
    return result_list