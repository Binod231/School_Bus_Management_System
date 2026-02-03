from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.db.session import get_db
from app.core.jwt import get_current_active_user
from app.schemas.school import SchoolResponse
from app.services.school import get_schools_with_admin_status, get_school_by_id_with_admin_status
from app.models.user import User, UserRole

router = APIRouter(
    prefix="/schools",
    tags=["schools"]
)

@router.get(
    "/",
    response_model=List[SchoolResponse],
    summary="Get all schools",
    description="Retrieves a list of all registered schools. Accessible to all authenticated users."
)
async def list_registered_schools(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    schools = await get_schools_with_admin_status(db)
    return schools

@router.get(
    "/{school_id}",
    response_model=SchoolResponse,
    summary="Get a specific school",
    description="Allows a member of the school or a superadmin to retrieve detailed information."
)
async def get_school_details(
    school_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # Authorization: Only allow access if the user belongs to the school or is a superadmin
    if current_user.role != UserRole.SUPERADMIN and current_user.school_id != school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access information for this school."
        )
        
    try:
        school = await get_school_by_id_with_admin_status(db, school_id)
        return school
    except Exception as e:
        # get_school_by_id_with_admin_status already raises NotFoundException which results in 404
        # but if something else happens, we catch it here.
        raise e
