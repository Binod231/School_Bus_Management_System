from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from app.models.school import School
from app.core.exceptions import NotFoundException
from typing import Optional, List
from app.core.cache import redis_client
import json
from datetime import datetime


# Helper to serialize School objects, handling datetime
def school_serializer(school: School) -> dict:
    school_dict = school.to_dict()
    for key, value in school_dict.items():
        if isinstance(value, datetime):
            school_dict[key] = value.isoformat()
    return school_dict

async def get_school_by_id(db: AsyncSession, school_id: int) -> School:
    """Get school by ID"""
    cache_key = f"school:{school_id}"
    cached_school = await redis_client.get(cache_key)
    if cached_school:
        school_data = json.loads(cached_school)
        # Convert isoformat strings back to datetime objects
        for key in ['created_at', 'updated_at']:
            if school_data.get(key):
                school_data[key] = datetime.fromisoformat(school_data[key])
        return School(**school_data)

    result = await db.execute(select(School).where(School.id == school_id))
    school = result.scalar_one_or_none()
    if not school:
        raise NotFoundException("School", school_id)

    # Use the helper to serialize before caching
    await redis_client.set(cache_key, json.dumps(school_serializer(school)), ex=3600)  # Cache for 1 hour
    return school


async def get_schools(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100
) -> List[School]:
    """Get all schools"""
    cache_key = f"all_schools:skip={skip}:limit={limit}"
    cached_schools = await redis_client.get(cache_key)
    if cached_schools:
        schools_list = json.loads(cached_schools)
        deserialized_schools = []
        for school_data in schools_list:
            # Convert isoformat strings back to datetime objects
            for key in ['created_at', 'updated_at']:
                 if school_data.get(key):
                    school_data[key] = datetime.fromisoformat(school_data[key])
            deserialized_schools.append(School(**school_data))
        return deserialized_schools

    result = await db.execute(
        select(School)
        .offset(skip)
        .limit(limit)
    )
    schools = result.scalars().all()
    # Use the helper to serialize each school object
    await redis_client.set(cache_key, json.dumps([school_serializer(s) for s in schools]), ex=3600)  # Cache for 1 hour
    return schools


async def create_school(db: AsyncSession, school_data: dict) -> School:
    """Create a new school"""
    db_school = School(**school_data)
    db.add(db_school)
    await db.commit()
    await db.refresh(db_school)
    # Invalidate cache
    keys = await redis_client.keys("all_schools:*")
    if keys:
        await redis_client.delete(*keys)
    return db_school


async def update_school(db: AsyncSession, school_id: int, school_data: dict) -> School:
    """Update a school"""
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
    """Delete a school and all related data"""
    school_to_delete = await get_school_by_id(db, school_id)

    if not school_to_delete:
         raise NotFoundException("School", school_id)

    await db.delete(school_to_delete)
    await db.commit()
    # Invalidate caches
    await redis_client.delete(f"school:{school_id}")
    keys = await redis_client.keys("all_schools:*")
    if keys:
        await redis_client.delete(*keys)
    return True