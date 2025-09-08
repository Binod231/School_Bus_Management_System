from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_
from app.models.student import Student, Guardian, GuardianStudent
from app.core.exceptions import NotFoundException, InvalidDataException
from typing import Optional, List
from sqlalchemy.orm import selectinload
from app.models.user import User
from app.schemas.student import StudentCreate, StudentUpdate, GuardianCreate, GuardianUpdate
from datetime import date


async def get_student_by_id(db: AsyncSession, student_id: int) -> Student:
    """Get student by ID"""
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise NotFoundException("Student", student_id)
    return student


async def get_students(
    db: AsyncSession, 
    school_id: Optional[int] = None,
    skip: int = 0, 
    limit: int = 100
) -> List[Student]:
    """Get students with optional school filter"""
    query = select(Student)
    
    if school_id is not None:
        query = query.where(Student.school_id == school_id)
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()


async def get_students_by_bus_route(db: AsyncSession, bus_route_id: int) -> List[Student]:
    """Get students assigned to a bus route"""
    result = await db.execute(
        select(Student).where(Student.bus_route_id == bus_route_id)
    )
    return result.scalars().all()


async def create_student(db: AsyncSession, student_data: dict) -> Student:
    """Create a new student"""
    # Add validation
    try:
        # Validate against your Pydantic schema
        StudentCreate(**student_data)
    except Exception as e:
        raise InvalidDataException(f"Invalid student data: {str(e)}")
    
    db_student = Student(**student_data)
    db.add(db_student)
    await db.commit()
    await db.refresh(db_student)
    return db_student


async def update_student(db: AsyncSession, student_id: int, student_data: StudentUpdate):
    """
    Updates a student's information in the database.
    """
    student = await get_student_by_id(db, student_id)
    if not student:
        return None

    # Get the update data as a dictionary, excluding unset values
    update_data = student_data.dict(exclude_unset=True)

    # Update the student object with the new data
    for key, value in update_data.items():
        setattr(student, key, value)

    await db.commit()
    await db.refresh(student)
    return student


async def delete_student(db: AsyncSession, student_id: int) -> bool:
    """Delete a student"""
    result = await db.execute(delete(Student).where(Student.id == student_id))
    await db.commit()
    if result.rowcount == 0:
        raise NotFoundException("Student", student_id)
    return True


async def get_guardian_by_id(db: AsyncSession, guardian_id: int) -> Guardian:
    """Get guardian by ID"""
    result = await db.execute(select(Guardian).where(Guardian.id == guardian_id))
    guardian = result.scalar_one_or_none()
    if not guardian:
        raise NotFoundException("Guardian", guardian_id)
    return guardian


async def get_guardian_by_user_id(db: AsyncSession, user_id: int) -> Guardian:
    """Get guardian by user ID"""
    result = await db.execute(select(Guardian).where(Guardian.user_id == user_id))
    guardian = result.scalar_one_or_none()
    if not guardian:
        raise NotFoundException("Guardian", user_id)
    return guardian


async def get_guardians(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Guardian]:
    """Get all guardians"""
    result = await db.execute(
        select(Guardian)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def create_guardian(db: AsyncSession, guardian_data: dict) -> Guardian:
    """
    Create a new Guardian record. Must include user_id.
    """
    if "user_id" not in guardian_data or not guardian_data["user_id"]:
        raise InvalidDataException("user_id is required to create a Guardian")

    db_guardian = Guardian(**guardian_data)
    db.add(db_guardian)
    await db.commit()
    await db.refresh(db_guardian)
    return db_guardian



async def update_guardian(db: AsyncSession, guardian_id: int, guardian_data: dict) -> Guardian:
    """Update a guardian"""
    result = await db.execute(
        update(Guardian)
        .where(Guardian.id == guardian_id)
        .values(**guardian_data)
        .returning(Guardian)
    )
    await db.commit()
    updated_guardian = result.scalar_one_or_none()
    if not updated_guardian:
        raise NotFoundException("Guardian", guardian_id)
    return updated_guardian


async def delete_guardian_by_user_id(db: AsyncSession, user_id: int) -> bool:
    """Delete a guardian by user ID"""
    guardian = await get_guardian_by_user_id(db, user_id)
    await db.delete(guardian)
    await db.commit()
    return True


async def get_guardian_students(db: AsyncSession, guardian_id: int) -> List[Student]:
    """Get all students for a guardian"""
    result = await db.execute(
        select(Student)
        .join(GuardianStudent, GuardianStudent.student_id == Student.id)
        .where(GuardianStudent.guardian_id == guardian_id)
    )
    return result.scalars().all()


async def get_student_guardians(db: AsyncSession, student_id: int) -> List[Guardian]:
    """Get all guardians for a student"""
    result = await db.execute(
        select(Guardian)
        .join(GuardianStudent, GuardianStudent.guardian_id == Guardian.id)
        .where(GuardianStudent.student_id == student_id)
        .options(selectinload(Guardian.user))
    )
    return result.scalars().all()


async def get_guardian_student_relationship(db: AsyncSession, guardian_id: int, student_id: int) -> GuardianStudent:
    """Get guardian-student relationship"""
    result = await db.execute(
        select(GuardianStudent)
        .where(
            and_(
                GuardianStudent.guardian_id == guardian_id,
                GuardianStudent.student_id == student_id
            )
        )
    )
    relationship = result.scalar_one_or_none()
    if not relationship:
        raise NotFoundException("GuardianStudentRelationship", f"guardian_id: {guardian_id}, student_id: {student_id}")
    return relationship


async def create_guardian_student(db: AsyncSession, relationship_data: dict) -> GuardianStudent:
    """Create a guardian-student relationship"""
    db_relationship = GuardianStudent(**relationship_data)
    db.add(db_relationship)
    await db.commit()
    await db.refresh(db_relationship)
    return db_relationship


async def update_guardian_student(db: AsyncSession, relationship_id: int, relationship_data: dict) -> GuardianStudent:
    """Update a guardian-student relationship"""
    result = await db.execute(
        update(GuardianStudent)
        .where(GuardianStudent.id == relationship_id)
        .values(**relationship_data)
        .returning(GuardianStudent)
    )
    await db.commit()
    updated_relationship = result.scalar_one_or_none()
    if not updated_relationship:
        raise NotFoundException("GuardianStudentRelationship", relationship_id)
    return updated_relationship


async def delete_guardian_student(db: AsyncSession, relationship_id: int) -> bool:
    """Delete a guardian-student relationship"""
    result = await db.execute(delete(GuardianStudent).where(GuardianStudent.id == relationship_id))
    await db.commit()
    if result.rowcount == 0:
        raise NotFoundException("GuardianStudentRelationship", relationship_id)
    return True

# Add this function to get guardians with school filtering
async def get_guardians(
    db: AsyncSession,
    school_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Guardian]:
    """Get guardians with optional school filter"""
    query = select(Guardian).join(User).options(selectinload(Guardian.user))
    
    if school_id is not None:
        query = query.where(User.school_id == school_id)
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()