from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.db.session import get_db
from app.core.jwt import get_current_admin, verify_school_resource_access, get_current_active_user
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.schemas.student import StudentCreate, StudentResponse, StudentUpdate, GuardianUpdate, GuardianCreate, GuardianResponse, GuardianWithStudentsResponse
from app.schemas.bus import (
    BusCreate, BusResponse, BusRouteCreate, BusRouteResponse, 
    BusUpdate, BusRouteUpdate, BusDriverCreate, BusRouteStopCreate, 
    BusRouteStopResponse, BusRouteStopsBulkUpdate,
    BusMaintenanceCreate, BusMaintenanceResponse, FleetExpiryAlert
)
from app.core.exceptions import NotFoundException, InvalidDataException
from app.services.user import create_user, get_users, get_user_by_id, get_user_by_email, update_user, delete_user
from app.services.student import create_student, get_students, get_student_by_id, update_student, delete_student, get_guardian_by_user_id, update_guardian, delete_guardian_by_user_id
from app.services.bus import (
    create_bus, get_buses, create_bus_route, get_bus_routes, assign_driver_to_bus, 
    get_bus_by_id, update_bus, delete_bus, get_bus_route_by_id, 
    update_bus_route, delete_bus_route, add_stop_to_route, get_bus_route_stops,
    update_route_stops_bulk, delete_route_stop
)
from app.utils.email import send_new_user_email
from app.models.user import UserRole, User
from app.models.incident import Incident, IncidentType, IncidentStatus
from app.models.student import Student
from app.models.bus import Bus, BusMaintenance
from app.models.trip import Trip, TripStudent, StudentStatus, TripDirection
from sqlalchemy import func, select, and_
from app.services.student import create_guardian_student, GuardianStudent, create_guardian, get_guardians, get_guardian_by_user_id, delete_guardian_by_user_id,  update_student as update_student_service,delete_student as delete_student_service, get_student_by_id, get_guardian_by_id
from app.schemas.bus import BusStopCreate, BusStopUpdate, BusStopResponse, BusRouteResponse
from app.services.bus import create_bus_stop, get_bus_stops as get_bus_stops_service, update_bus_stop, delete_bus_stop, get_bus_stop_by_id
from app.services.trip import get_active_trips_with_locations, cleanup_old_location_updates
from app.core.config import settings
from datetime import datetime, timedelta
from fastapi.responses import Response
from app.schemas.trip import TripResponse, EmergencyTransferRequest, EmergencyTransferResponse
from app.services.incident import get_incidents, create_incident, update_incident, get_incident_by_id, delete_incident
from app.schemas.incident import IncidentResponse, IncidentUpdate, IncidentCreate
from sqlalchemy.orm import selectinload, Session, joinedload
from app.models.student import Guardian
from app.services.student import get_guardian_students, get_students_by_bus_route
from app import models, services, schemas
from app.services.notification import notify_guardians_incident
from app.utils.qrcode import generate_student_qr_code




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
        
        driver_data_dict = driver_data.model_dump()
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
        user_dict = guardian_data.model_dump(exclude={"student_ids"})
        user_dict["school_id"] = current_user.school_id
        user_dict["role"] = UserRole.GUARDIAN
        
        # Include password if provided
        if guardian_data.password:
            user_dict["password"] = guardian_data.password
            
        guardian_user = await create_user(db, user_data=user_dict)

        # Create guardian record
        guardian = await create_guardian(db, {"user_id": guardian_user.id})

        # ✅ ADD EMAIL NOTIFICATION WITH ERROR HANDLING
        try:
            await send_new_user_email(guardian_user.email, guardian_user.id)
        except Exception as email_error:
            print(f"Failed to send welcome email: {email_error}")
            # Log the error but don't fail the guardian creation

        # Assign students and collect student data for response
        assigned_students_data = []
        for student_id in guardian_data.student_ids or []:
            try:
                student = await get_student_by_id(db, student_id)
                if student.school_id != current_user.school_id:
                    continue

                # Create guardian-student relationship
                gs_data = {
                    "guardian_id": guardian.id,
                    "student_id": student.id,
                    "relationship_type": "parent",
                    "is_primary": False
                }
                gs = await create_guardian_student(db, gs_data)
                assigned_students_data = []
                
                # ✅ FIX: Create proper response data instead of ORM object
                # Use the input data plus the returned ID, not the ORM object
                # assigned_students_data.append({
                #     "id": gs.id,  # This should be the ID from the created relationship
                #     "guardian_id": guardian.id,
                #     "student_id": student.id,
                #     "relationship_type": "parent",
                #     "is_primary": False,
                #     "created_at": datetime.utcnow(),
                #     "updated_at": datetime.utcnow(),
                #     # Add student details
                #     "student": {
                #         "id": student.id,
                #         "first_name": student.first_name,
                #         "last_name": student.last_name,
                #         "student_id": student.student_id,
                #         "grade": student.grade
                #     },
                #     # ✅ ADD THE REQUIRED GUARDIAN FIELD
                #     "guardian": {
                #         "id": guardian.id,
                #         "user_id": guardian_user.id,
                #         "email": guardian_user.email,
                #         "first_name": guardian_user.first_name,
                #         "last_name": guardian_user.last_name,
                #         "phone": guardian_user.phone,
                #         "fcm_token": guardian.fcm_token or "",
                #         "created_at": guardian.created_at,
                #         "updated_at": guardian.updated_at
                #     }
                # })
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
            "fcm_token": guardian.fcm_token or "",
            "created_at": guardian.created_at,
            "updated_at": guardian.updated_at,
            "students": assigned_students_data
        }
        
    except Exception as e:
        print(f"Error creating guardian: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create guardian: {str(e)}"
        )

# fix the list_guardians endpoint
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
    # Use the proper query to get guardians with user data
    query = (
        select(Guardian)
        .join(User)
        .where(User.school_id == current_user.school_id)
        .where(User.role == UserRole.GUARDIAN)
        .options(selectinload(Guardian.user))
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(query)
    guardians = result.scalars().all()
    
    guardian_responses = []
    for guardian in guardians:
        # Get the student count for this guardian
        student_count_result = await db.execute(
            select(func.count(GuardianStudent.id))
            .where(GuardianStudent.guardian_id == guardian.id)
        )
        student_count = student_count_result.scalar() or 0
        
        guardian_responses.append({
            "id": guardian.id,
            "user_id": guardian.user.id,
            "email": guardian.user.email,
            "first_name": guardian.user.first_name,
            "last_name": guardian.user.last_name,
            "phone": guardian.user.phone,
            "fcm_token": guardian.fcm_token,
            "created_at": guardian.created_at,
            "updated_at": guardian.updated_at,
            "is_active": guardian.user.is_active,  # Make sure this is included
            "student_count": student_count,  # Add student count
        })
    
    return guardian_responses

@router.get(
    "/guardians/{guardian_id}",
    response_model=GuardianWithStudentsResponse,
    summary="Get guardian by ID"
)
async def get_guardian(
    guardian_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Get a specific guardian by ID with their associated students.

    This function uses a single, efficient query with eager loading to fetch all
    necessary data and then constructs the response to perfectly match the schema,
    preventing validation errors.
    """
    # 1. Define the single, comprehensive query to fetch all data at once.
    stmt = (
        select(Guardian)
        .where(Guardian.id == guardian_id)
        .options(
            # Load the related User object to get email, name, etc.
            selectinload(Guardian.user),
            # Load the list of student relationships (GuardianStudent objects)
            selectinload(Guardian.students).options(
                # For each relationship, load the full Student object
                selectinload(GuardianStudent.student),
                # And also load the Guardian and their User for the nested response schema
                selectinload(GuardianStudent.guardian).selectinload(Guardian.user)
            )
        )
    )

    # 2. Execute the query.
    result = await db.execute(stmt)
    # Use .unique() to prevent duplicates from joins and .first() to get the single result
    guardian = result.scalars().unique().first()

    # 3. Handle validation and security checks.
    if not guardian:
        raise HTTPException(status_code=404, detail="Guardian not found")

    if not guardian.user:
         raise HTTPException(status_code=404, detail="Guardian user data not found")

    if guardian.user.school_id != current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this guardian."
        )

    # 4. Manually construct the response to match the Pydantic schema.
    #    This step explicitly solves the "Field required" validation error.
    response_data = {
        "id": guardian.id,
        "user_id": guardian.user_id,
        # Pull required fields from the eagerly loaded 'user' object
        "email": guardian.user.email,
        "first_name": guardian.user.first_name,
        "last_name": guardian.user.last_name,
        "phone": guardian.user.phone,
        # 'is_active' and other fields might be on the user or guardian model
        "is_active": guardian.user.is_active, 
        "created_at": guardian.created_at,
        "updated_at": guardian.updated_at,
        "student_count": len(guardian.students),
        # Pydantic can now correctly serialize this list because we eager-loaded
        # all the nested data it needs (student, guardian, user).
        "students": guardian.students
    }

    return response_data


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
        student = await create_student(db, student_data=student_data.model_dump())
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
    
    bus = await create_bus(db, bus_data=bus_data.model_dump())
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
    
    route = await create_bus_route(db, route_data=route_data.model_dump())
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
    # This query now joins the bus data, so you get the bus number
    query = (
        select(models.BusRoute)
        .options(selectinload(models.BusRoute.bus))
        .where(models.BusRoute.school_id == current_user.school_id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    routes = result.scalars().all()
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
    
        assignment = await assign_driver_to_bus(db, assignment_data=assignment_data.model_dump())
        
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
            Trip.status == "IN_PROGRESS"
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
    
    return await update_user(db, driver_id, driver_data.model_dump(exclude_unset=True))

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
        update_data = guardian_data.model_dump(exclude={"student_ids", "fcm_token"}, exclude_unset=True)
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


@router.put(
    "/students/{student_id}",
    response_model=StudentResponse,
    summary="Update a student"
)
async def update_student(
    student_id: int,
    student_data: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Updates a student's details by calling the student service,
    which handles database operations and relationship loading.
    """
    try:
        # Security Check: Ensure the admin has permission to update this student.
        student_to_update = await get_student_by_id(db, student_id)
        if student_to_update.school_id != current_user.school_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to edit this student."
            )
        
        # ✅ THE FIX: Call the service function to perform the update.
        # This service function is already set up to handle eager loading correctly.
        updated_student = await update_student_service(db, student_id, student_data)
        return updated_student

    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))

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
    
    return await update_bus(db, bus_id, bus_data.model_dump(exclude_unset=True))

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
    
    return await update_bus_route(db, route_id, route_data.model_dump(exclude_unset=True))

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


@router.post(
    "/bus-routes/{route_id}/stops",
    response_model=BusRouteStopResponse,
    summary="Add a bus stop to a route"
)
async def add_stop_to_bus_route(
    route_id: int,
    stop_data: BusRouteStopCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    try:
        route = await get_bus_route_by_id(db, route_id)
        if route.school_id != current_user.school_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        stop_data_dict = stop_data.model_dump()
        stop_data_dict["route_id"] = route_id
        return await add_stop_to_route(db, stop_data_dict)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/bus-routes/{route_id}/stops",
    response_model=List[BusRouteStopResponse],
    summary="List all stops for a bus route"
)
async def list_route_stops(
    route_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    try:
        route = await get_bus_route_by_id(db, route_id)
        if route.school_id != current_user.school_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        return await get_bus_route_stops(db, route_id)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/bus-routes/{route_id}/stops",
    response_model=List[BusRouteStopResponse],
    summary="Replace all stops for a bus route"
)
async def set_route_stops(
    route_id: int,
    stops_data: BusRouteStopsBulkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    try:
        route = await get_bus_route_by_id(db, route_id)
        if route.school_id != current_user.school_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Extract stop IDs from flexible schema formats
        stop_ids = []
        if stops_data.stop_ids is not None:
            stop_ids = stops_data.stop_ids
        elif stops_data.bus_stop_ids is not None:
            stop_ids = stops_data.bus_stop_ids
        elif stops_data.stops is not None:
            stop_ids = [s.stop_id for s in stops_data.stops]
        else:
            raise HTTPException(status_code=422, detail="No stop IDs found. Use stop_ids, bus_stop_ids, or stops array.")

        return await update_route_stops_bulk(db, route_id, [int(sid) for sid in stop_ids])
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/bus-routes/{route_id}/stops/{stop_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a stop from a route"
)
async def remove_stop_from_route(
    route_id: int,
    stop_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    try:
        route = await get_bus_route_by_id(db, route_id)
        if route.school_id != current_user.school_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        success = await delete_route_stop(db, route_id, stop_id)
        if not success:
            raise HTTPException(status_code=404, detail="Stop not found on this route")
            
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"DEBUG ADMIN: ERROR {e}")
        raise e

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
    return await create_bus_stop(db, bus_stop_data.model_dump())

@router.get(
    "/bus-stops",
    response_model=List[BusStopResponse],
    summary="List all bus stops for a school",
)
async def list_bus_stops(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    # Return all bus stops (including those not yet linked to routes)
    # Bus stops can be created independently and linked to routes later
    return await get_bus_stops_service(db, school_id=None)


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
    return await update_bus_stop(db, stop_id, bus_stop_data.model_dump(exclude_unset=True))

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

@router.post(
    "/incidents",
    response_model=IncidentResponse,
    summary="Create a new incident as admin",
    description="Allows an admin to create a new incident on behalf of others."
)
async def admin_create_incident(
    incident_data: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    try:
        incident_data_dict = incident_data.dict()
        incident_data_dict["reported_by_id"] = current_user.id
        incident_data_dict["school_id"] = current_user.school_id
        
        if incident_data.student_id:
            student = await get_student_by_id(db, incident_data.student_id)
            if student.school_id != current_user.school_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Student does not belong to your school."
                )
        
        incident = await create_incident(db, incident_data_dict)
        
        if incident.student_id:
            await notify_guardians_incident(
                db,
                incident.student_id,
                incident.type,
                incident.description
            )
        
        return incident
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

# In school_bus_management/app/routes/admin.py

@router.get(
    "/incidents",
    response_model=List[dict],
    summary="Get all incidents with trip and bus info",
    description="Allows admin to view all incidents with related trip and bus details."
)
async def admin_get_all_incidents(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    # Use a query with proper eager loading
    query = (
        select(Incident)
        .options(
            selectinload(Incident.trip).selectinload(Trip.bus),
            selectinload(Incident.trip).selectinload(Trip.route),
            selectinload(Incident.trip).selectinload(Trip.students).selectinload(TripStudent.student).selectinload(Student.guardians).selectinload(GuardianStudent.guardian).selectinload(Guardian.user),
            joinedload(Incident.student),
            selectinload(Incident.reported_by)
        )
        .where(Incident.school_id == current_user.school_id)
        .order_by(Incident.reported_at.desc())
        .offset(skip)
        .limit(limit)
    )
    
    if status is not None:
        query = query.where(Incident.status == status)
    
    result = await db.execute(query)
    incidents = result.scalars().unique().all()

    result_list = []
    for incident in incidents:
        trip_id = None
        bus_id = None
        
        # Get trip and bus info if needed (without triggering lazy loading)
        if incident.trip_id:
            trip_id = incident.trip_id
        
        is_driver_reported = incident.reported_by.role == UserRole.DRIVER if incident.reported_by else False

        result_list.append({
            "incident": IncidentResponse.from_orm(incident),
            "trip_id": trip_id,
            "bus_id": bus_id,
            "is_driver_reported": is_driver_reported
        })

    return result_list

@router.patch(
    "/incidents/{incident_id}",
    response_model=IncidentResponse,
    summary="Update an existing incident"
)
async def admin_update_incident(
    incident_id: int,
    incident_data: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    # Security check: ensure the incident belongs to the admin's school
    incident_to_update = await get_incident_by_id(db, incident_id)
    if incident_to_update.school_id != current_user.school_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this incident")
        
    return await update_incident(db, incident_id, incident_data)

# NEW: Endpoint to handle DELETING an incident
@router.delete(
    "/incidents/{incident_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an incident"
)
async def admin_delete_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    # Security check: ensure the incident belongs to the admin's school
    incident_to_delete = await get_incident_by_id(db, incident_id)
    if incident_to_delete.school_id != current_user.school_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this incident")
        
    await delete_incident(db, incident_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post(
    "/students/{student_id}/generate-qr",
    response_model=StudentResponse,
    summary="Generate and save a QR code for a student",
    description="Generates a new QR code for the specified student and saves it to their profile."
)
async def generate_qr_for_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    try:
        # First, ensure the student exists and belongs to the admin's school
        student_to_update = await get_student_by_id(db, student_id)
        if student_to_update.school_id != current_user.school_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this student."
            )

        # Generate the QR code string
        qr_code_string = await generate_student_qr_code(student_id, db)

        if not qr_code_string:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate QR code."
            )

        # CORRECTED LINE: Call update_student with named arguments to ensure correct order
        updated_student = await update_student(
            student_id=student_id, 
            student_data=StudentUpdate(qr_code=qr_code_string), 
            db=db,
            current_user=current_user # Pass the current_user as well
        )
        
        return updated_student

    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    
    
    
@router.post("/trips/backfill-students", summary="[Admin] Backfill students for old trips")
async def backfill_students_for_old_trips(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    This is a one-time utility endpoint to find trips created before the student
    association logic was added and populate their rosters.
    """
    # Find all trips that have no associated students
    subquery = select(TripStudent.trip_id).distinct()
    
    # FIX: Eagerly load the 'route' relationship to prevent lazy loading errors
    query = select(Trip).options(selectinload(Trip.route)).where(Trip.id.notin_(subquery))
    
    result = await db.execute(query)
    trips_to_fix = result.scalars().unique().all()

    if not trips_to_fix:
        return {"message": "No trips found that need fixing."}

    newly_added_associations = 0
    for trip in trips_to_fix:
        # This check is now safe because trip.route was pre-loaded
        if trip.route and trip.route.school_id == current_user.school_id:
            students_on_route = await get_students_by_bus_route(db, trip.route_id)
            for student in students_on_route:
                # Check if an association already exists (just in case)
                existing_association_result = await db.execute(
                    select(TripStudent).where(
                        TripStudent.trip_id == trip.id,
                        TripStudent.student_id == student.id
                    )
                )
                if existing_association_result.scalar_one_or_none() is None:
                    trip_student_entry = TripStudent(
                        trip_id=trip.id,
                        student_id=student.id,
                        status=StudentStatus.AT_HOME
                    )
                    db.add(trip_student_entry)
                    newly_added_associations += 1
    
    await db.commit()
    
    return {
        "message": f"Data backfill complete. Fixed {len(trips_to_fix)} trips and added {newly_added_associations} student associations."
    }
    
@router.get(
    "/schools/{school_id}/live-locations",
    response_model=List[schemas.bus.ActiveBusLocation] 
)
async def get_all_bus_locations(
    school_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.user.User = Depends(get_current_admin)
):
    """
    Get live locations for all active buses by fetching active trips,
    including detailed student counts.
    """
    active_trips = await services.trip.get_active_trips_with_locations(db=db, school_id=school_id)
    
    response_data = []
    for trip in active_trips:
        driver = trip.driver
        latest_location = sorted(trip.location_updates, key=lambda lu: lu.timestamp, reverse=True)[0] if trip.location_updates else None
        
        
        
        # Calculate the different student counts
        # Total Students: Count of all students assigned to this trip
        total_students = len(trip.students)

        # Boarded: Count of students who have a boarded_at time (implies they were picked up)
        boarded_students = sum(1 for ts in trip.students if ts.boarded_at is not None)
        
        # Arrived: Count of students who have reached their destination
        # For TO_SCHOOL trips, this means they are AT_SCHOOL
        # For FROM_SCHOOL trips, this means they are AT_HOME (and boarded_at is set)
        if trip.direction == TripDirection.TO_SCHOOL:
             arrived_students = sum(1 for ts in trip.students if ts.status == StudentStatus.AT_SCHOOL)
        else:
             # Default to FROM_SCHOOL behavior
             arrived_students = sum(1 for ts in trip.students if ts.status == StudentStatus.AT_HOME and ts.boarded_at is not None)
        
        # Dropped Off: Count of students currently waiting for confirmation
        dropped_off_students = sum(1 for ts in trip.students if ts.status == StudentStatus.DROPPED_OFF)

        # Build Detailed Roster
        roster = []
        for ts in trip.students:
            guardian_name = "N/A"
            guardian_phone = "N/A"
            
            # Find a guardian (Prioritize primary, else take first)
            if ts.student and ts.student.guardians:
                # guard_rel is GuardianStudent object
                primary_guard = next((g for g in ts.student.guardians if g.is_primary), None)
                target_guard_rel = primary_guard if primary_guard else ts.student.guardians[0]
                
                if target_guard_rel.guardian and target_guard_rel.guardian.user:
                    user = target_guard_rel.guardian.user
                    guardian_name = f"{user.first_name} {user.last_name}"
                    guardian_phone = user.phone

            roster.append({
                "student_id": ts.student_id,
                "first_name": ts.student.first_name,
                "last_name": ts.student.last_name,
                "status": ts.status,
                "boarded_at": ts.boarded_at,
                "guardian_name": guardian_name,
                "guardian_phone": guardian_phone
            })

        response_data.append({
            "id": str(trip.bus.id),
            "bus_number": trip.bus.bus_number,
            "driver_name": f"{driver.first_name} {driver.last_name}" if driver else "N/A",
            "driver_phone": driver.phone if driver else "N/A",
            "route_name": trip.route.name if trip.route else "N/A",
            "current_location": latest_location,
            "status": trip.status,
            "trip_id": str(trip.id),

            #  'students_count' with the new detailed fields
            "total_students": total_students,
            "boarded_students": boarded_students,
            "dropped_off_students": dropped_off_students,
            "arrived_students": arrived_students,
            
            "student_roster": roster
        })
        
    return response_data


@router.post(
    "/buses/{bus_id}/maintenance",
    response_model=BusMaintenanceResponse,
    summary="Log bus maintenance record",
    description="Logs a service, repair, inspection, or oil change for a bus, updating its odometer if provided."
)
async def log_bus_maintenance(
    bus_id: int,
    maintenance_data: BusMaintenanceCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    bus = await get_bus_by_id(db, bus_id)
    if not bus:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bus not found")

    if current_admin.role != UserRole.SUPERADMIN and bus.school_id != current_admin.school_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bus does not belong to your school")

    # If new odometer reading is higher than current, update bus odometer
    if maintenance_data.odometer_reading is not None and (bus.current_odometer is None or maintenance_data.odometer_reading > bus.current_odometer):
        bus.current_odometer = maintenance_data.odometer_reading

    new_maintenance = BusMaintenance(
        bus_id=bus.id,
        school_id=bus.school_id,
        service_type=maintenance_data.service_type,
        status=maintenance_data.status or "COMPLETED",
        cost=maintenance_data.cost,
        currency=maintenance_data.currency or settings.DEFAULT_CURRENCY,
        odometer_reading=maintenance_data.odometer_reading,
        performed_at=maintenance_data.performed_at or datetime.utcnow(),
        next_service_due_date=maintenance_data.next_service_due_date,
        next_service_due_odometer=maintenance_data.next_service_due_odometer,
        performed_by=maintenance_data.performed_by,
        notes=maintenance_data.notes
    )
    db.add(new_maintenance)
    await db.commit()
    await db.refresh(new_maintenance)
    return new_maintenance


@router.get(
    "/buses/{bus_id}/maintenance",
    response_model=List[BusMaintenanceResponse],
    summary="Get bus maintenance history",
    description="Retrieves all logged maintenance and service records for a specific bus."
)
async def get_bus_maintenance_history(
    bus_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    bus = await get_bus_by_id(db, bus_id)
    if not bus:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bus not found")

    if current_admin.role != UserRole.SUPERADMIN and bus.school_id != current_admin.school_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bus does not belong to your school")

    stmt = (
        select(BusMaintenance)
        .where(BusMaintenance.bus_id == bus_id)
        .order_by(BusMaintenance.performed_at.desc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get(
    "/fleet/expiry-alerts",
    response_model=List[FleetExpiryAlert],
    summary="Get fleet document and maintenance expiry alerts",
    description="Identifies buses with insurance or fitness certificates expiring within 30 days, or overdue maintenance."
)
async def get_fleet_expiry_alerts(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    stmt = (
        select(Bus)
        .where(
            and_(
                Bus.school_id == current_admin.school_id,
                Bus.is_active == True
            )
        )
        .options(selectinload(Bus.maintenances))
    )
    res = await db.execute(stmt)
    buses = res.scalars().all()

    now = datetime.utcnow()
    alerts = []

    for bus in buses:
        # Check Insurance
        if bus.insurance_expiry:
            days_left = (bus.insurance_expiry.replace(tzinfo=None) - now).days
            if days_left < 0:
                alerts.append({
                    "bus_id": bus.id,
                    "bus_number": bus.bus_number,
                    "license_plate": bus.license_plate,
                    "alert_type": "INSURANCE_EXPIRED",
                    "severity": "CRITICAL",
                    "due_date": bus.insurance_expiry,
                    "days_remaining": days_left,
                    "message": f"Bus {bus.bus_number} insurance expired {abs(days_left)} days ago!"
                })
            elif days_left <= 30:
                alerts.append({
                    "bus_id": bus.id,
                    "bus_number": bus.bus_number,
                    "license_plate": bus.license_plate,
                    "alert_type": "INSURANCE_EXPIRING",
                    "severity": "WARNING",
                    "due_date": bus.insurance_expiry,
                    "days_remaining": days_left,
                    "message": f"Bus {bus.bus_number} insurance expires in {days_left} days."
                })

        # Check Fitness Certificate
        if bus.fitness_certificate_expiry:
            days_left = (bus.fitness_certificate_expiry.replace(tzinfo=None) - now).days
            if days_left < 0:
                alerts.append({
                    "bus_id": bus.id,
                    "bus_number": bus.bus_number,
                    "license_plate": bus.license_plate,
                    "alert_type": "FITNESS_EXPIRED",
                    "severity": "CRITICAL",
                    "due_date": bus.fitness_certificate_expiry,
                    "days_remaining": days_left,
                    "message": f"Bus {bus.bus_number} fitness certificate expired {abs(days_left)} days ago!"
                })
            elif days_left <= 30:
                alerts.append({
                    "bus_id": bus.id,
                    "bus_number": bus.bus_number,
                    "license_plate": bus.license_plate,
                    "alert_type": "FITNESS_EXPIRING",
                    "severity": "WARNING",
                    "due_date": bus.fitness_certificate_expiry,
                    "days_remaining": days_left,
                    "message": f"Bus {bus.bus_number} fitness certificate expires in {days_left} days."
                })

        # Check Next Maintenance Due
        for m in (bus.maintenances or []):
            if m.next_service_due_date:
                m_days = (m.next_service_due_date.replace(tzinfo=None) - now).days
                if m_days <= 14:
                    alerts.append({
                        "bus_id": bus.id,
                        "bus_number": bus.bus_number,
                        "license_plate": bus.license_plate,
                        "alert_type": "SERVICE_OVERDUE" if m_days < 0 else "SERVICE_DUE_SOON",
                        "severity": "CRITICAL" if m_days < 0 else "WARNING",
                        "due_date": m.next_service_due_date,
                        "days_remaining": m_days,
                        "message": f"Bus {bus.bus_number} scheduled maintenance due in {m_days} days ({m.service_type})."
                    })
                    break

    return alerts


@router.post(
    "/trips/{trip_id}/emergency-transfer",
    response_model=EmergencyTransferResponse,
    summary="Emergency breakdown passenger transfer",
    description="Transfers remaining onboard and scheduled students from a disabled bus to a replacement bus and driver."
)
async def emergency_bus_transfer(
    trip_id: int,
    transfer_data: EmergencyTransferRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    stmt = (
        select(Trip)
        .where(Trip.id == trip_id)
        .options(
            selectinload(Trip.bus),
            selectinload(Trip.driver),
            selectinload(Trip.students).selectinload(TripStudent.student)
        )
    )
    res = await db.execute(stmt)
    old_trip = res.scalar_one_or_none()
    if not old_trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original trip not found")

    if current_admin.role != UserRole.SUPERADMIN and old_trip.bus.school_id != current_admin.school_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trip does not belong to your school")

    target_bus = await get_bus_by_id(db, transfer_data.target_bus_id)
    if not target_bus:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target replacement bus not found")
    if current_admin.role != UserRole.SUPERADMIN and target_bus.school_id != current_admin.school_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Target bus does not belong to your school")

    target_driver = await get_user_by_id(db, transfer_data.target_driver_id)
    if not target_driver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target driver not found")

    # Find uncompleted students (ON_BUS, AT_HOME)
    transfer_students = [
        ts for ts in old_trip.students
        if ts.status in [StudentStatus.ON_BUS, StudentStatus.AT_HOME]
    ]

    # Create emergency breakdown incident
    incident = Incident(
        type=IncidentType.EMERGENCY,
        status=IncidentStatus.REPORTED,
        title=f"Emergency Transfer: Bus {old_trip.bus.bus_number} -> Bus {target_bus.bus_number}",
        description=f"Bus breakdown / emergency transfer: {transfer_data.reason}. {len(transfer_students)} students transferred from Bus {old_trip.bus.bus_number} to Bus {target_bus.bus_number}.",
        occurred_at=datetime.utcnow(),
        school_id=current_admin.school_id,
        reported_by_id=current_admin.id,
        driver_id=old_trip.driver_id,
        bus_id=old_trip.bus_id,
        trip_id=old_trip.id
    )
    db.add(incident)

    # Mark old trip as CANCELLED with transfer explanation
    from app.models.trip import TripStatus
    old_trip.status = TripStatus.CANCELLED
    old_trip.sweep_notes = f"Emergency transferred to Bus {target_bus.bus_number}. Reason: {transfer_data.reason}"

    # Create new replacement trip
    new_trip = Trip(
        name=f"Transfer: {old_trip.name}",
        type=old_trip.type,
        direction=old_trip.direction,
        status=TripStatus.IN_PROGRESS,
        scheduled_start=old_trip.scheduled_start,
        actual_start=datetime.utcnow(),
        scheduled_end=old_trip.scheduled_end,
        bus_id=target_bus.id,
        route_id=old_trip.route_id,
        driver_id=target_driver.id,
        sweep_verified=False
    )
    db.add(new_trip)
    await db.flush()

    # Clone students into new trip
    for ts in transfer_students:
        new_ts = TripStudent(
            trip_id=new_trip.id,
            student_id=ts.student_id,
            status=ts.status,
            boarded_at=ts.boarded_at
        )
        db.add(new_ts)

    await db.commit()

    # Broadcast notification to guardians
    try:
        from app.utils.websocket import manager
        await manager.broadcast({
            "type": "EMERGENCY_TRANSFER",
            "old_trip_id": old_trip.id,
            "new_trip_id": new_trip.id,
            "old_bus_number": old_trip.bus.bus_number,
            "new_bus_number": target_bus.bus_number,
            "reason": transfer_data.reason,
            "message": f"Students on Bus {old_trip.bus.bus_number} have been transferred safely to Bus {target_bus.bus_number}."
        }, str(old_trip.id))
    except Exception as e:
        print(f"Warning: Failed to broadcast transfer message: {e}")

    return {
        "original_trip_id": old_trip.id,
        "new_trip_id": new_trip.id,
        "transferred_students_count": len(transfer_students),
        "new_bus_number": target_bus.bus_number,
        "new_driver_name": f"{target_driver.first_name} {target_driver.last_name}",
        "message": f"Successfully transferred {len(transfer_students)} student(s) to Bus {target_bus.bus_number} with driver {target_driver.first_name}."
    }


@router.post(
    "/system/cleanup-locations",
    summary="Purge historical GPS location pings",
    description="Deletes raw location updates older than specified days (default 60 days) to prevent table bloat and optimize database performance."
)
async def trigger_location_cleanup(
    days: int = Query(default=60, ge=1, le=365, description="Delete records older than this many days"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPERADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can trigger system maintenance."
        )

    result = await cleanup_old_location_updates(
        db=db,
        days=days,
        batch_size=settings.LOCATION_CLEANUP_BATCH_SIZE
    )
    return {
        "status": "success",
        "message": f"Successfully purged {result['deleted_count']} location update(s) older than {days} days.",
        **result
    }

