from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from app.models.incident import Incident
from app.core.exceptions import NotFoundException, DatabaseException
from typing import Optional, List


async def get_incident_by_id(db: AsyncSession, incident_id: int) -> Incident:
    """Get incident by ID"""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise NotFoundException("Incident", incident_id)
    return incident


async def get_incidents(
    db: AsyncSession, 
    school_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0, 
    limit: int = 100
) -> List[Incident]:
    """Get incidents with optional filters"""
    query = select(Incident)
    
    if school_id is not None:
        query = query.where(Incident.school_id == school_id)
    
    if status is not None:
        query = query.where(Incident.status == status)
    
    query = query.offset(skip).limit(limit).order_by(Incident.reported_at.desc())
    
    result = await db.execute(query)
    return result.scalars().all()


async def create_incident(db: AsyncSession, incident_data: dict) -> Incident:
    """Create a new incident"""
    db_incident = Incident(**incident_data)
    db.add(db_incident)
    await db.commit()
    await db.refresh(db_incident)
    return db_incident


async def update_incident(db: AsyncSession, incident_id: int, incident_data: dict) -> Incident:
    """Update an incident"""
    result = await db.execute(
        update(Incident)
        .where(Incident.id == incident_id)
        .values(**incident_data)
        .returning(Incident)
    )
    await db.commit()
    updated_incident = result.scalar_one_or_none()
    if not updated_incident:
        raise NotFoundException("Incident", incident_id)
    return updated_incident


async def delete_incident(db: AsyncSession, incident_id: int) -> bool:
    """Delete an incident"""
    result = await db.execute(delete(Incident).where(Incident.id == incident_id))
    await db.commit()
    if result.rowcount == 0:
        raise NotFoundException("Incident", incident_id)
    return True


async def get_student_incidents(db: AsyncSession, student_id: int, skip: int = 0, limit: int = 100) -> List[Incident]:
    """Get incidents for a specific student"""
    result = await db.execute(
        select(Incident)
        .where(Incident.student_id == student_id)
        .offset(skip)
        .limit(limit)
        .order_by(Incident.reported_at.desc())
    )
    return result.scalars().all()


async def get_user_reported_incidents(db: AsyncSession, user_id: int, skip: int = 0, limit: int = 100) -> List[Incident]:
    """Get incidents reported by a specific user"""
    result = await db.execute(
        select(Incident)
        .where(Incident.reported_by_id == user_id)
        .offset(skip)
        .limit(limit)
        .order_by(Incident.reported_at.desc())
    )
    return result.scalars().all()
    

async def get_guardian_incidents(db: AsyncSession, guardian_user_id: int, skip: int = 0, limit: int = 100) -> List[Incident]:
    """Get incidents for a guardian's students"""
    from app.services.student import get_guardian_by_user_id, get_guardian_students
    
    try:
        guardian = await get_guardian_by_user_id(db, guardian_user_id)
        students = await get_guardian_students(db, guardian.id)
        student_ids = [student.id for student in students]
        
        incidents = []
        for student_id in student_ids:
            student_incidents = await get_student_incidents(db, student_id, skip=skip, limit=limit)
            incidents.extend(student_incidents)
        return incidents
    except NotFoundException:
        return []