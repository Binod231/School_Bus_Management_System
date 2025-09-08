from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from app.models.school import School
from app.core.exceptions import NotFoundException
from typing import List
from app.core.cache import redis_client
import json
from datetime import datetime
from app.models.user import User, UserRole
from sqlalchemy import func
from app.schemas.school import SchoolResponse


# Helper to serialize School objects, handling datetime
def school_serializer(school: School) -> dict:
    """Serialize School object to dict with datetime conversion"""
    school_dict = school.to_dict()
    for key, value in school_dict.items():
        if isinstance(value, datetime):
            school_dict[key] = value.isoformat()
    return school_dict


# Helper to deserialize cached school data
def school_deserializer(school_data: dict) -> dict:
    """Deserialize cached school data with datetime conversion"""
    for key in ['created_at', 'updated_at']:
        if school_data.get(key):
            school_data[key] = datetime.fromisoformat(school_data[key])
    return school_data


async def get_school_by_id(db: AsyncSession, school_id: int) -> School:
    """Get school by ID with caching"""
    cache_key = f"school:{school_id}"
    
    # Try to get from cache first
    cached_school = await redis_client.get(cache_key)
    if cached_school:
        school_data = json.loads(cached_school)
        school_data = school_deserializer(school_data)
        return School(**school_data)

    # If not in cache, get from database
    result = await db.execute(select(School).where(School.id == school_id))
    school = result.scalar_one_or_none()
    if not school:
        raise NotFoundException("School", school_id)

    # Cache the school data
    await redis_client.set(cache_key, json.dumps(school_serializer(school)), ex=3600)  # Cache for 1 hour
    return school


async def get_schools(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100
) -> List[School]:
    """Get all schools with caching"""
    cache_key = f"all_schools:skip={skip}:limit={limit}"
    
    # Try to get from cache first
    cached_schools = await redis_client.get(cache_key)
    if cached_schools:
        schools_list = json.loads(cached_schools)
        deserialized_schools = []
        for school_data in schools_list:
            school_data = school_deserializer(school_data)
            deserialized_schools.append(School(**school_data))
        return deserialized_schools

    # If not in cache, get from database
    result = await db.execute(
        select(School)
        .offset(skip)
        .limit(limit)
        .order_by(School.id)
    )
    schools = result.scalars().all()
    
    # Cache the schools list
    await redis_client.set(
        cache_key, 
        json.dumps([school_serializer(s) for s in schools]), 
        ex=3600  # Cache for 1 hour
    )
    return schools


async def create_school(db: AsyncSession, school_data: dict) -> School:
    """Create a new school and invalidate cache"""
    db_school = School(**school_data)
    db.add(db_school)
    await db.commit()
    await db.refresh(db_school)
    
    # Invalidate cache for all schools lists
    keys = await redis_client.keys("all_schools:*")
    if keys:
        await redis_client.delete(*keys)
    
    return db_school


async def update_school(db: AsyncSession, school_id: int, school_data: dict) -> School:
    """Update a school and invalidate cache"""
    # First check if school exists
    result = await db.execute(select(School).where(School.id == school_id))
    existing_school = result.scalar_one_or_none()
    if not existing_school:
        raise NotFoundException("School", school_id)

    # Update the school
    result = await db.execute(
        update(School)
        .where(School.id == school_id)
        .values(**school_data)
        .returning(School)
    )
    await db.commit()
    updated_school = result.scalar_one_or_none()
    
    if not updated_school:
        raise NotFoundException("School", school_id)

    # Invalidate caches
    await redis_client.delete(f"school:{school_id}")
    keys = await redis_client.keys("all_schools:*")
    if keys:
        await redis_client.delete(*keys)
    
    return updated_school


async def delete_school(db: AsyncSession, school_id: int) -> bool:
    """Delete a school and all related data, invalidate cache"""
    # First check if school exists
    result = await db.execute(select(School).where(School.id == school_id))
    school_to_delete = result.scalar_one_or_none()
    
    if not school_to_delete:
        raise NotFoundException("School", school_id)

    # Delete the school
    await db.delete(school_to_delete)
    await db.commit()

    # Invalidate caches
    await redis_client.delete(f"school:{school_id}")
    keys = await redis_client.keys("all_schools:*")
    if keys:
        await redis_client.delete(*keys)
    
    return True


async def get_schools_with_admin_status(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100
) -> List[SchoolResponse]:
    """Get all schools with admin assignment status (using Pydantic models)"""
    cache_key = f"schools_with_admin_status:skip={skip}:limit={limit}"
    
    # Try to get from cache first
    cached_schools = await redis_client.get(cache_key)
    if cached_schools:
        return [SchoolResponse(**school) for school in json.loads(cached_schools)]

    # Optimized query
    query = (
        select(
            School,
            func.coalesce(func.count(User.id).filter(User.role == UserRole.ADMIN), 0).label('admin_count')
        )
        .select_from(School)
        .outerjoin(User, (User.school_id == School.id) & (User.role == UserRole.ADMIN))
        .group_by(School.id)
        .order_by(School.id)
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(query)
    schools_with_admin_count = result.all()
    
    # Convert to SchoolResponse with admin status
    schools_with_status = []
    for school, admin_count in schools_with_admin_count:
        school_response = SchoolResponse.from_orm(school)
        school_response.admin_assigned = admin_count > 0
        schools_with_status.append(school_response)
    
    # Convert datetime objects to strings for JSON serialization
    schools_for_cache = []
    for school in schools_with_status:
        school_dict = school.dict()
        # Convert datetime objects to ISO format strings
        school_dict['created_at'] = school_dict['created_at'].isoformat() if school_dict['created_at'] else None
        school_dict['updated_at'] = school_dict['updated_at'].isoformat() if school_dict['updated_at'] else None
        schools_for_cache.append(school_dict)
    
    # Cache the result
    await redis_client.set(cache_key, json.dumps(schools_for_cache), ex=1800)
    
    return schools_with_status


async def get_school_by_id_with_admin_status(db: AsyncSession, school_id: int) -> SchoolResponse:
    """Get school by ID with admin assignment status (using Pydantic models)"""
    cache_key = f"school_with_admin_status:{school_id}"
    
    # Try to get from cache first
    cached_school = await redis_client.get(cache_key)
    if cached_school:
        cached_data = json.loads(cached_school)
        # Convert ISO strings back to datetime objects
        if cached_data.get('created_at'):
            cached_data['created_at'] = datetime.fromisoformat(cached_data['created_at'])
        if cached_data.get('updated_at'):
            cached_data['updated_at'] = datetime.fromisoformat(cached_data['updated_at'])
        return SchoolResponse(**cached_data)

    # Optimized query
    query = (
        select(
            School,
            func.coalesce(func.count(User.id).filter(User.role == UserRole.ADMIN), 0).label('admin_count')
        )
        .where(School.id == school_id)
        .outerjoin(User, (User.school_id == School.id) & (User.role == UserRole.ADMIN))
        .group_by(School.id)
    )
    
    result = await db.execute(query)
    school_with_admin_count = result.first()
    
    if not school_with_admin_count:
        raise NotFoundException("School", school_id)
    
    school, admin_count = school_with_admin_count
    school_response = SchoolResponse.from_orm(school)
    school_response.admin_assigned = admin_count > 0
    
    # Convert datetime objects to strings for JSON serialization
    school_dict = school_response.dict()
    school_dict['created_at'] = school_dict['created_at'].isoformat() if school_dict['created_at'] else None
    school_dict['updated_at'] = school_dict['updated_at'].isoformat() if school_dict['updated_at'] else None
    
    # Cache the result
    await redis_client.set(cache_key, json.dumps(school_dict), ex=1800)
    
    return school_response


async def invalidate_school_cache(school_id: int = None):
    """Invalidate school-related cache"""
    if school_id:
        # Invalidate specific school cache
        await redis_client.delete(f"school:{school_id}")
        await redis_client.delete(f"school_with_admin_status:{school_id}")
    
    # Invalidate all schools lists
    keys = await redis_client.keys("all_schools:*")
    keys.extend(await redis_client.keys("schools_with_admin_status:*"))
    
    if keys:
        await redis_client.delete(*keys)