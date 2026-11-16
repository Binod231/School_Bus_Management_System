import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient
from app.main import app
from app.db.session import AsyncSessionLocal
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.models.school import School
from app.models.bus import Bus, BusRoute
from app.models.trip import Trip, TripStatus, TripType, TripDirection, TripStudent, StudentStatus
from app.models.student import Student, Guardian, GuardianStudent
from datetime import datetime, timedelta, date
from sqlalchemy import select

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture
async def test_setup(db_session):
    """Creates a complete sandbox fixture: School, Admin, Driver, Guardian, Student, Bus, Route, Trip."""
    timestamp = int(datetime.utcnow().timestamp() * 1000)
    
    # 1. School
    school = School(
        name=f"Safety Academy {timestamp}",
        address="100 School Way",
        city="Springfield",
        state="IL",
        zip_code="62701",
        phone="555-0100",
        email=f"info_{timestamp}@school.com"
    )
    db_session.add(school)
    await db_session.flush()

    # 2. Users
    admin_user = User(
        email=f"admin_{timestamp}@school.com",
        hashed_password="hashed_pwd_placeholder",
        first_name="Admin",
        last_name="Test",
        role=UserRole.ADMIN,
        school_id=school.id,
        is_active=True
    )
    driver_user = User(
        email=f"driver_{timestamp}@school.com",
        hashed_password="hashed_pwd_placeholder",
        first_name="Driver",
        last_name="Test",
        role=UserRole.DRIVER,
        school_id=school.id,
        is_active=True
    )
    guardian_user = User(
        email=f"guardian_{timestamp}@school.com",
        hashed_password="hashed_pwd_placeholder",
        first_name="Parent",
        last_name="Test",
        role=UserRole.GUARDIAN,
        school_id=school.id,
        is_active=True
    )
    db_session.add_all([admin_user, driver_user, guardian_user])
    await db_session.flush()

    # 3. Guardian profile
    guardian = Guardian(user_id=guardian_user.id)
    db_session.add(guardian)
    await db_session.flush()

    # 4. Bus
    bus = Bus(
        bus_number=f"BUS-{timestamp%1000}",
        capacity=30,
        license_plate=f"LP-{timestamp%1000}",
        school_id=school.id,
        current_odometer=12500.0,
        insurance_expiry=datetime.utcnow() + timedelta(days=20),
        fitness_certificate_expiry=datetime.utcnow() + timedelta(days=15),
        is_active=True
    )
    backup_bus = Bus(
        bus_number=f"BUS-BACKUP-{timestamp%1000}",
        capacity=35,
        license_plate=f"LP-B-{timestamp%1000}",
        school_id=school.id,
        is_active=True
    )
    db_session.add_all([bus, backup_bus])
    await db_session.flush()

    # 5. Route
    route = BusRoute(
        name=f"Route North {timestamp}",
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow() + timedelta(hours=1),
        school_id=school.id,
        bus_id=bus.id,
        is_active=True
    )
    db_session.add(route)
    await db_session.flush()

    # 6. Student
    student = Student(
        first_name="Alice",
        last_name="Smith",
        date_of_birth=date(2015, 5, 20),
        grade="4th Grade",
        student_id=f"STU-{timestamp}",
        school_id=school.id,
        bus_route_id=route.id
    )
    db_session.add(student)
    await db_session.flush()

    # 7. GuardianStudent link
    gs = GuardianStudent(
        guardian_id=guardian.id,
        student_id=student.id,
        relationship_type="Mother",
        is_primary=True,
        alert_radius_meters=500.0,
        notify_on_approaching=True
    )
    db_session.add(gs)
    await db_session.flush()

    # 8. Trip
    trip = Trip(
        name=f"Morning Pickup {timestamp}",
        type=TripType.MORNING,
        direction=TripDirection.TO_SCHOOL,
        status=TripStatus.IN_PROGRESS,
        scheduled_start=datetime.utcnow(),
        actual_start=datetime.utcnow(),
        scheduled_end=datetime.utcnow() + timedelta(minutes=45),
        bus_id=bus.id,
        route_id=route.id,
        driver_id=driver_user.id,
        sweep_verified=False
    )
    db_session.add(trip)
    await db_session.flush()

    # 9. TripStudent
    trip_student = TripStudent(
        trip_id=trip.id,
        student_id=student.id,
        status=StudentStatus.ON_BUS,
        boarded_at=datetime.utcnow()
    )
    db_session.add(trip_student)
    await db_session.commit()

    # Generate Tokens
    admin_token = create_access_token({"sub": str(admin_user.id), "role": admin_user.role.value})
    driver_token = create_access_token({"sub": str(driver_user.id), "role": driver_user.role.value})
    guardian_token = create_access_token({"sub": str(guardian_user.id), "role": guardian_user.role.value})

    return {
        "school": school,
        "admin_user": admin_user,
        "driver_user": driver_user,
        "guardian_user": guardian_user,
        "guardian": guardian,
        "student": student,
        "bus": bus,
        "backup_bus": backup_bus,
        "route": route,
        "trip": trip,
        "trip_student": trip_student,
        "admin_token": admin_token,
        "driver_token": driver_token,
        "guardian_token": guardian_token
    }
