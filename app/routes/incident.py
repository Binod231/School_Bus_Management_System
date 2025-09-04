from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.db.session import get_db
from app.core.jwt import get_current_active_user
from app.schemas.incident import IncidentCreate, IncidentResponse, IncidentUpdate
from app.services.incident import create_incident, get_incidents, get_incident_by_id, update_incident, get_user_reported_incidents, get_guardian_incidents
from app.models.user import UserRole
from app.services.student import get_student_by_id, get_guardian_by_user_id, get_guardian_student_relationship
from app.services.notification import notify_guardians_incident
from app.core.exceptions import NotFoundException

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
    current_user = Depends(get_current_active_user)
):
    try:
        incident_data_dict = incident_data.dict()
        incident_data_dict["reported_by_id"] = current_user.id
        
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
    current_user = Depends(get_current_active_user)
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
    current_user = Depends(get_current_active_user)
):
    try:
        incident = await get_incident_by_id(db, incident_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    
    if current_user.role == UserRole.ADMIN and incident.school_id != current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this incident"
        )
    
    if current_user.role == UserRole.DRIVER and incident.reported_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this incident"
        )
    
    if current_user.role == UserRole.GUARDIAN:
        if not incident.student_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this incident"
            )
        
        try:
            guardian = await get_guardian_by_user_id(db, current_user.id)
            relationship = await get_guardian_student_relationship(db, guardian.id, incident.student_id)
            if not relationship:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this incident"
                )
        except NotFoundException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this incident"
            )
    
    return incident


@router.patch(
    "/incidents/{incident_id}", 
    response_model=IncidentResponse,
    summary="Update incident status",
    description="Allows an admin or superadmin to update the status of an incident."
)
async def update_incident_status(
    incident_id: int,
    incident_data: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPERADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update incidents"
        )
    
    try:
        incident = await get_incident_by_id(db, incident_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    
    if current_user.role == UserRole.ADMIN and incident.school_id != current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this incident"
        )
    
    if incident_data.status == "resolved" and not incident.resolved_by_id:
        incident_data_dict = incident_data.dict(exclude_unset=True)
        incident_data_dict["resolved_by_id"] = current_user.id
        updated_incident = await update_incident(db, incident_id, incident_data_dict)
    else:
        updated_incident = await update_incident(db, incident_id, incident_data.dict(exclude_unset=True))
    
    return updated_incident