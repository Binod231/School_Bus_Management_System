from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_
from app.models.student import Student, Guardian, GuardianStudent
from app.models.bus import BusRoute  # Make sure BusRoute is imported
from app.core.exceptions import NotFoundException, InvalidDataException
from typing import Optional, List
from sqlalchemy.orm import selectinload, joinedload  # Import joinedload
from app.models.user import User
from app.schemas.student import StudentCreate, StudentUpdate

async def get_student_by_id(db: AsyncSession, student_id: int) -> Student:
    """Get student by ID with all related info eagerly loaded."""
    result = await db.execute(
        select(Student)
        .options(
            selectinload(Student.guardians)
            .selectinload(GuardianStudent.guardian)
            .selectinload(Guardian.user),
            # Use joinedload for directly related objects that are essential
            joinedload(Student.bus_route).joinedload(BusRoute.bus)
        )
        .where(Student.id == student_id)
    )
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
    """
    Get students with all related info eagerly loaded using JOINs to prevent async errors.
    """
    query = (
        select(Student)
        .options(
            # Eagerly load guardian and user info using separate queries for efficiency
            selectinload(Student.guardians)
            .selectinload(GuardianStudent.guardian)
            .selectinload(Guardian.user),
            
            # ✅ THE FIX: Force a SQL JOIN to load the bus_route and its nested bus object.
            # This ensures the data is available before the response is sent.
            joinedload(Student.bus_route).joinedload(BusRoute.bus)
        )
    )
    
    if school_id is not None:
        query = query.where(Student.school_id == school_id)
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    
    # Use .unique() to prevent duplicate student results from the JOINs
    return result.scalars().unique().all()


async def get_students_by_bus_route(db: AsyncSession, bus_route_id: int) -> List[Student]:
    """Get students assigned to a bus route with their guardian's user info"""
    result = await db.execute(
        select(Student)
        .where(Student.bus_route_id == bus_route_id)
        .options(
            selectinload(Student.guardians)
            .selectinload(GuardianStudent.guardian)
            .selectinload(Guardian.user)
        )
    )
    return result.scalars().all()


async def create_student(db: AsyncSession, student_data: dict) -> Student:
    """Create a new student and return it with guardian info"""
    try:
        StudentCreate(**student_data)
    except Exception as e:
        raise InvalidDataException(f"Invalid student data: {str(e)}")
    
    db_student = Student(**student_data)
    db.add(db_student)
    await db.commit()
    await db.refresh(db_student)
    
    # Re-fetch the student to load the guardian relationship
    return await get_student_by_id(db, db_student.id)


async def update_student(db: AsyncSession, student_id: int, student_data: StudentUpdate) -> Student:
    """Updates a student and returns it with guardian info"""
    student = await get_student_by_id(db, student_id)
    if not student:
        raise NotFoundException("Student", student_id)

    update_data = student_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(student, key, value)

    await db.commit()
    await db.refresh(student)

    # Re-fetch the student to ensure all relationships are loaded
    return await get_student_by_id(db, student_id)


async def delete_student(db: AsyncSession, student_id: int) -> bool:
    """Delete a student"""
    result = await db.execute(delete(Student).where(Student.id == student_id))
    await db.commit()
    if result.rowcount == 0:
        raise NotFoundException("Student", student_id)
    return True


async def get_guardian_by_id(db: AsyncSession, guardian_id: int) -> Guardian:
    """Get guardian by ID with user and student info"""
    result = await db.execute(
        select(Guardian)
        .options(selectinload(Guardian.user), selectinload(Guardian.students).selectinload(GuardianStudent.student))
        .where(Guardian.id == guardian_id)
    )
    guardian = result.scalar_one_or_none()
    if not guardian:
        raise NotFoundException("Guardian", guardian_id)
    return guardian


async def get_guardian_by_user_id(db: AsyncSession, user_id: int) -> Guardian:
    """Get guardian by user ID with user and student info"""
    result = await db.execute(
        select(Guardian)
        .options(selectinload(Guardian.user), selectinload(Guardian.students).selectinload(GuardianStudent.student))
        .where(Guardian.user_id == user_id)
    )
    guardian = result.scalar_one_or_none()
    if not guardian:
        raise NotFoundException("Guardian", f"user_id: {user_id}")
    return guardian


async def get_guardians(
    db: AsyncSession,
    school_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Guardian]:
    """Get guardians with optional school filter, including user and student info"""
    query = select(Guardian).join(User).options(
        selectinload(Guardian.user), 
        selectinload(Guardian.students).selectinload(GuardianStudent.student)
    )
    
    if school_id is not None:
        query = query.where(User.school_id == school_id)
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()


async def create_guardian(db: AsyncSession, guardian_data: dict) -> Guardian:
    """Create a new Guardian and return it with user info"""
    if "user_id" not in guardian_data or not guardian_data["user_id"]:
        raise InvalidDataException("user_id is required to create a Guardian")

    db_guardian = Guardian(**guardian_data)
    db.add(db_guardian)
    await db.commit()
    await db.refresh(db_guardian)
    
    # Re-fetch with user data loaded
    return await get_guardian_by_id(db, db_guardian.id)


async def update_guardian(db: AsyncSession, guardian_id: int, guardian_data: dict) -> Guardian:
    """Update a guardian and return it with user and student info"""
    guardian = await db.get(Guardian, guardian_id)
    if not guardian:
        raise NotFoundException("Guardian", guardian_id)

    for key, value in guardian_data.items():
        setattr(guardian, key, value)
    
    await db.commit()
    
    # Re-fetch the guardian to ensure all relationships are loaded
    return await get_guardian_by_id(db, guardian_id)


async def delete_guardian_by_user_id(db: AsyncSession, user_id: int) -> bool:
    """Delete a guardian by user ID"""
    guardian = await get_guardian_by_user_id(db, user_id)
    await db.delete(guardian)
    await db.commit()
    return True


async def get_guardian_students(db: AsyncSession, guardian_id: int) -> List[Student]:
    """Get all students for a guardian, with their full details"""
    result = await db.execute(
        select(Student)
        .join(GuardianStudent, GuardianStudent.student_id == Student.id)
        .where(GuardianStudent.guardian_id == guardian_id)
        .options(
            selectinload(Student.guardians)
            .selectinload(GuardianStudent.guardian)
            .selectinload(Guardian.user)
        )
    )
    return result.scalars().all()


async def get_student_guardians(db: AsyncSession, student_id: int) -> List[Guardian]:
    """Get all guardians for a student, with their user info"""
    result = await db.execute(
        select(Guardian)
        .join(GuardianStudent, GuardianStudent.guardian_id == Guardian.id)
        .where(GuardianStudent.student_id == student_id)
        .options(selectinload(Guardian.user))
    )
    return result.scalars().all()


async def get_guardian_student_relationship(db: AsyncSession, guardian_id: int, student_id: int) -> GuardianStudent:
    """Get a specific guardian-student relationship"""
    result = await db.execute(
        select(GuardianStudent).where(
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
    relationship = await db.get(GuardianStudent, relationship_id)
    if not relationship:
        raise NotFoundException("GuardianStudentRelationship", relationship_id)
    
    for key, value in relationship_data.items():
        setattr(relationship, key, value)
        
    await db.commit()
    await db.refresh(relationship)
    return relationship


async def delete_guardian_student(db: AsyncSession, relationship_id: int) -> bool:
    """Delete a guardian-student relationship"""
    result = await db.execute(delete(GuardianStudent).where(GuardianStudent.id == relationship_id))
    await db.commit()
    if result.rowcount == 0:
        raise NotFoundException("GuardianStudentRelationship", relationship_id)
    return True

async def get_students_by_guardian_id(db: AsyncSession, guardian_id: int) -> List[Student]:
    """
    Retrieves all students for a specific guardian, eagerly loading all necessary
    relationships (bus route, bus stop, and guardians) to prevent async errors.
    """
    result = await db.execute(
        select(Student)
        .join(GuardianStudent)
        .where(GuardianStudent.guardian_id == guardian_id)
        .options(
            # ✅ THE FIX: Eagerly load the guardians relationship and its nested user data.
            selectinload(Student.guardians)
            .selectinload(GuardianStudent.guardian)
            .selectinload(Guardian.user),
            
            # Also keep the existing eager loads for bus route and stop
            selectinload(Student.bus_route).selectinload(BusRoute.bus),
            selectinload(Student.bus_stop)
        )
    )
    # Use .unique() to avoid duplicate students if they have multiple guardians
    return result.scalars().unique().all()
