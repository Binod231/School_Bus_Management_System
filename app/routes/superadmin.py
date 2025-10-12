from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import List

from app.db.session import get_db
from app.core.jwt import get_current_superadmin
from app.schemas.school import SchoolCreate, SchoolResponse, SchoolUpdate
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.school import create_school, update_school, delete_school, get_schools_with_admin_status, get_school_by_id_with_admin_status
from app.services.user import create_user, get_user_by_email, get_users, get_user_by_id, update_user, delete_user
from app.models.user import UserRole, User
from app.models.school import School
from app.core.exceptions import NotFoundException

router = APIRouter(
    prefix="/superadmin",
    tags=["superadmin"],
    dependencies=[Depends(get_current_superadmin)]
)

# Statistics Endpoint

@router.get(
    "/stats",
    summary="Get Superadmin Statistics",
    description="Retrieves aggregated statistics for the superadmin dashboard."
)
async def get_superadmin_stats(db: AsyncSession = Depends(get_db)):
    """
    Get statistics for the superadmin dashboard.
    """
    total_schools = await db.scalar(select(func.count(School.id)))
    total_users = await db.scalar(select(func.count(User.id)))

    return {
        "total_schools": total_schools or 0,
        "total_users": total_users or 0,
        "system_health": 99.9  # Placeholder for system health, can be developed further
    }


# School Management Endpoints

@router.post(
    "/schools",
    response_model=SchoolResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new school",
    description="Allows a superadmin to register a new school in the system."
)
async def register_school(
    school_data: SchoolCreate,
    db: AsyncSession = Depends(get_db),
):
    school = await create_school(db, school_data=school_data.dict())
    return school

@router.get(
    "/schools",
    response_model=List[SchoolResponse],
    summary="Get all schools",
    description="Allows a superadmin to retrieve a list of all schools in the system with admin assignment status."
)
async def get_all_schools(
    db: AsyncSession = Depends(get_db),
):
    # Use the optimized function with admin status
    schools = await get_schools_with_admin_status(db)
    return schools

@router.get(
    "/schools/{school_id}",
    response_model=SchoolResponse,
    summary="Get a specific school",
    description="Allows a superadmin to retrieve the details of a specific school by its ID with admin assignment status."
)
async def get_one_school(
    school_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        # Use the optimized function with admin status
        school = await get_school_by_id_with_admin_status(db, school_id)
        return school
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )


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
):
    try:
        updated_school = await update_school(db, school_id, school_data.dict(exclude_unset=True))
        return updated_school
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

@router.delete(
    "/schools/{school_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a school",
    description="Allows a superadmin to delete a school from the system, which will also delete all associated data."
)
async def delete_school_details(
    school_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_school(db, school_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

# Admin Management Endpoints

@router.post(
    "/schools/{school_id}/admins",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a school admin",
    description="Allows a superadmin to create or assign an admin account for a specific school."
)
async def create_school_admin(
    school_id: int,
    admin_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        # Check if email already exists
        existing_user = await get_user_by_email(db, email=admin_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An admin with this email already exists."
            )
    except NotFoundException:
        pass  # Email doesn't exist, continue

    try:
        school = await get_school_by_id_with_admin_status(db, school_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

    user_data = admin_data.dict()
    user_data["role"] = UserRole.ADMIN
    user_data["school_id"] = school_id
    admin = await create_user(db, user_data=user_data)
    
    # Return the user response
    return UserResponse.from_orm(admin)

# Update the get_school_admins endpoint
@router.get(
    "/schools/{school_id}/admins",
    response_model=List[UserResponse],
    summary="Get all admins for a school",
    description="Allows a superadmin to retrieve a list of all administrators for a specific school."
)
async def get_school_admins(
    school_id: int,
    db: AsyncSession = Depends(get_db),
):
    # Verify school exists first
    try:
        await get_school_by_id_with_admin_status(db, school_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    
    # Get users with admin role for this school
    result = await db.execute(
        select(User).filter(
            User.school_id == school_id,
            User.role == UserRole.ADMIN
        )
    )
    admins = result.scalars().all()
    
    # Convert to response model and include is_active
    admin_responses = []
    for admin in admins:
        admin_dict = UserResponse.from_orm(admin).dict()
        admin_dict["is_active"] = admin.is_active  # Add is_active field
        admin_responses.append(admin_dict)
    
    return admin_responses

@router.get(
    "/admins/{admin_id}",
    response_model=UserResponse,
    summary="Get a specific admin",
    description="Allows a superadmin to retrieve the details of a specific administrator by their user ID."
)
async def get_one_admin(
    admin_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        admin = await get_user_by_id(db, admin_id)
        if admin.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin not found."
            )
        return admin
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

@router.put(
    "/admins/{admin_id}",
    response_model=UserResponse,
    summary="Update admin details",
    description="Allows a superadmin to update the details of an existing school administrator."
)
async def update_admin_details(
    admin_id: int,
    admin_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        updated_admin = await update_user(db, admin_id, admin_data.dict(exclude_unset=True))
        return updated_admin
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )

@router.delete(
    "/admins/{admin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an admin",
    description="Allows a superadmin to delete a school administrator from the system."
)
async def delete_admin_details(
    admin_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_user(db, admin_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )