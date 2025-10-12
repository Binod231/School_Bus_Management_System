from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from app.models.school import School
from app.models.user import User, UserRole
from app.core.exceptions import NotFoundException
from typing import List
from app.core.cache import redis_client
import json
from datetime import datetime
from app.schemas.school import SchoolResponse

# --- Centralized Cache Invalidation Function ---
async def invalidate_school_cache():
    """
    Invalidates all cache keys related to schools.
    This function is called after any operation that modifies school data.
    """
    keys_to_delete = []
    
    # Use scan_iter to find all relevant keys without blocking the server
    async for key in redis_client.scan_iter("school:*"):
        keys_to_delete.append(key)
    async for key in redis_client.scan_iter("all_schools:*"):
        keys_to_delete.append(key)
    async for key in redis_client.scan_iter("schools_with_admin_status:*"):
        keys_to_delete.append(key)
        
    if keys_to_delete:
        await redis_client.delete(*keys_to_delete)

# --- Serializer for proper JSON conversion ---
def default_serializer(o):
    """Handles objects that the default JSON serializer can't, like datetimes."""
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

# --- Service Functions (Preserving all your features) ---

async def get_schools_with_admin_status(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100
) -> List[SchoolResponse]:
    """
    Gets all schools with their admin assignment status.
    This function is cached for performance.
    """
    cache_key = f"schools_with_admin_status:skip={skip}:limit={limit}"
    
    cached_schools = await redis_client.get(cache_key)
    if cached_schools:
        return [SchoolResponse(**school) for school in json.loads(cached_schools)]

    # Optimized query to get schools and a count of their admins in one go
    query = (
        select(School, func.count(User.id).label("admin_count"))
        .outerjoin(User, (User.school_id == School.id) & (User.role == UserRole.ADMIN))
        .group_by(School.id)
        .order_by(School.name)
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(query)
    schools_data = result.all()
    
    schools_with_status = []
    for school, admin_count in schools_data:
        school_response = SchoolResponse.from_orm(school)
        school_response.admin_assigned = admin_count > 0
        schools_with_status.append(school_response)

    # Serialize Pydantic models to dicts for caching
    schools_for_cache = [s.dict() for s in schools_with_status]
    await redis_client.set(cache_key, json.dumps(schools_for_cache, default=default_serializer), ex=3600) # Cache for 1 hour
    
    return schools_with_status

async def get_school_by_id_with_admin_status(db: AsyncSession, school_id: int) -> SchoolResponse:
    """Gets a single school by ID with its admin assignment status."""
    cache_key = f"school_with_admin_status:{school_id}"
    
    cached_school = await redis_client.get(cache_key)
    if cached_school:
        return SchoolResponse(**json.loads(cached_school))

    query = (
        select(School, func.count(User.id).label("admin_count"))
        .where(School.id == school_id)
        .outerjoin(User, (User.school_id == School.id) & (User.role == UserRole.ADMIN))
        .group_by(School.id)
    )
    
    result = await db.execute(query)
    data = result.first()
    
    if not data:
        raise NotFoundException("School", school_id)
        
    school, admin_count = data
    school_response = SchoolResponse.from_orm(school)
    school_response.admin_assigned = admin_count > 0
    
    await redis_client.set(cache_key, school_response.json(), ex=3600)
    
    return school_response


async def create_school(db: AsyncSession, school_data: dict) -> School:
    """Creates a new school and invalidates the cache."""
    db_school = School(**school_data)
    db.add(db_school)
    await db.commit()
    await db.refresh(db_school)
    
    await invalidate_school_cache() # Invalidate cache after creation
    
    return db_school


async def update_school(db: AsyncSession, school_id: int, school_data: dict) -> School:
    """Updates a school's details and invalidates the cache."""
    result = await db.execute(select(School).where(School.id == school_id))
    existing_school = result.scalar_one_or_none()
    if not existing_school:
        raise NotFoundException("School", school_id)

    await db.execute(update(School).where(School.id == school_id).values(**school_data))
    await db.commit()
    
    updated_school = await db.get(School, school_id)

    await invalidate_school_cache() # Invalidate cache after update
    
    return updated_school


async def delete_school(db: AsyncSession, school_id: int) -> bool:
    """Deletes a school and invalidates the cache."""
    result = await db.execute(select(School).where(School.id == school_id))
    school_to_delete = result.scalar_one_or_none()
    
    if not school_to_delete:
        raise NotFoundException("School", school_id)

    await db.delete(school_to_delete)
    await db.commit()

    await invalidate_school_cache() # Invalidate cache after deletion
    
    return True