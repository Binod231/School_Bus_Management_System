from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.db.session import get_db
from app.core.jwt import get_current_active_user
from app.schemas.incident import IncidentCreate, IncidentResponse, IncidentUpdate
from app.services.incident import create_incident, get_incidents, get_incident_by_id, update_incident, get_user_reported_incidents, get_guardian_incidents
from app.models.user import UserRole
from app.services.student import get_student_by_id, get_guardian_by_user_id, get_guardian_student_relationship
from app.services.notification import notify_guardians_incident, notify_guardians_of_trip_incident
from app.core.exceptions import NotFoundException
from app.models.user import User

router = APIRouter(
    tags=["incidents"]
)

@router.post(
    "/incidents", 
    response_model=IncidentResponse,
    summary="Report a new incident",
    description="Allows any authenticated user to report a new incident."
)
async def report_incident(
    incident_data: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Creates a new incident. 
    The backend will automatically derive the bus_id and route_id from the provided trip_id.
    """
    try:
        # The create_incident service now handles the logic of fetching trip details
        # and notifying guardians, making this endpoint much cleaner and more reliable.
        incident = await create_incident(db, incident_in=incident_data, user_id=current_user.id)
        
        # After creating the incident, notify all guardians on that trip
        await notify_guardians_of_trip_incident(
            db,
            trip_id=incident.trip_id,
            incident_type=incident.type,
            details=incident.description
        )
        
        return incident
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException as e:
        # Re-raise existing HTTP exceptions
        raise e
    except Exception as e:
        # Catch any other unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )

@router.get(
    "/incidents", 
    response_model=List[IncidentResponse],
    summary="List incidents based on user role",
    description="Retrieves a list of incidents, filtered based on the user's role and access permissions."
)
async def list_incidents(
    status: str = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role == UserRole.SUPERADMIN:
        incidents = await get_incidents(db, status=status, skip=skip, limit=limit)
    elif current_user.role == UserRole.ADMIN:
        incidents = await get_incidents(db, school_id=current_user.school_id, status=status, skip=skip, limit=limit)
    elif current_user.role == UserRole.DRIVER:
        incidents = await get_user_reported_incidents(db, current_user.id, skip=skip, limit=limit)
    elif current_user.role == UserRole.GUARDIAN:
        incidents = await get_guardian_incidents(db, current_user.id, skip=skip, limit=limit)
    else:
        incidents = []
    
    return incidents

@router.get(
    "/incidents/{incident_id}", 
    response_model=IncidentResponse,
    summary="Get a specific incident",
    description="Retrieves the details of a specific incident, with access restricted based on user role."
)
async def get_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    try:
        incident = await get_incident_by_id(db, incident_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    
    # --- Authorization Checks ---
    if current_user.role == UserRole.ADMIN and incident.school_id != current_user.school_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this incident")
    
    if current_user.role == UserRole.DRIVER and incident.reported_by_id != current_user.id:
        # Drivers should still be able to see incidents assigned to their trips, even if reported by admin
        # This part of logic might need refinement based on exact requirements.
        # For now, allowing access if they are the reporter.
        pass

    if current_user.role == UserRole.GUARDIAN:
        try:
            guardian = await get_guardian_by_user_id(db, current_user.id)
            # A guardian should have access if their child is on the trip where the incident occurred.
            # This logic requires checking student's association with the trip.
            # Simplified check for now:
            is_related = any(gs.student_id in [s.id for s in incident.students] for gs in guardian.students)
            if not is_related:
                 raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this incident")
        except NotFoundException:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not registered as a guardian.")
            
    return incident

@router.patch("/incidents/{incident_id}", response_model=IncidentResponse, summary="Update incident status or details")
async def update_incident_status(
    incident_id: int,
    incident_data: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    incident_to_update = await get_incident_by_id(db, incident_id)

    # Authorization check: only admin or the original reporter can update
    if not (current_user.role == "admin" or incident_to_update.reported_by_id == current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this incident"
        )
        
    updated_incident = await update_incident(db, incident_id, incident_data)
    
    return updated_incident