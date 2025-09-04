from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.db.session import get_db
from app.core.jwt import get_current_superadmin
from app.schemas.school import SchoolCreate, SchoolResponse, SchoolUpdate
from app.schemas.user import UserCreate, UserResponse
from app.services.school import create_school, get_schools, get_school_by_id, update_school, delete_school
from app.services.user import create_user, get_user_by_email
from app.models.user import UserRole
from app.core.exceptions import NotFoundException

router = APIRouter(
    prefix="/superadmin",
    tags=["superadmin"],
    dependencies=[Depends(get_current_superadmin)]
)


@router.post(
    "/schools", 
    response_model=SchoolResponse,
    summary="Register a new school",
    description="Allows a superadmin to register a new school in the system."
)
async def register_school(
    school_data: SchoolCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_superadmin)
):
    school = await create_school(db, school_data=school_data.dict())
    return school

@router.put(
    "/schools/{school_id}",
    response_model=SchoolResponse,
    summary="Update school details",
    description="Allows a superadmin to update the details of an existing school."
)
async def update_school_details(
    school_id: int,
    school_data: SchoolUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_superadmin)
):
    try:
        updated_school = await update_school(db, school_id, school_data.dict(exclude_unset=True))
        return updated_school
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

@router.post(
    "/schools/{school_id}/admin", 
    response_model=UserResponse,
    summary="Create a school admin",
    description="Allows a superadmin to create or assign an admin account for a specific school."
)
async def create_school_admin(
    school_id: int,
    admin_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_superadmin)
):
    try:
        existing_user = await get_user_by_email(db, email=admin_data.email)
    except NotFoundException:
        existing_user = None

    # Get the school (raise 404 if not found)
    try:
        school = await get_school_by_id(db, school_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    if existing_user:
        # Optionally update role and school_id if needed
        existing_user.role = UserRole.ADMIN
        existing_user.school_id = school.id
        await db.commit()
        await db.refresh(existing_user)
        return existing_user

    # Create new admin user
    user_data = admin_data.dict()
    user_data["role"] = UserRole.ADMIN
    user_data["school_id"] = school.id
    admin = await create_user(db, user_data=user_data)
    return admin

@router.delete(
    "/schools/{school_id}",
    summary="Delete a school",
    description="Allows a superadmin to delete a school from the system, which will also delete all associated data."
)
async def delete_school_details(
    school_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_superadmin)
):
    try:
        await delete_school(db, school_id)
        return {"message": f"School with ID {school_id} has been deleted successfully."}
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )