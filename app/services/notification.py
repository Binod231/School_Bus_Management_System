from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.fcm import send_push_notification, send_student_boarding_notification, send_bus_location_update, send_incident_notification, send_arrival_notification
from app.utils.email import send_notification_email
from app.services.student import get_students_by_bus_route, get_student_guardians
from typing import List, Optional
from app.services.trip import get_trip_by_id


async def notify_guardians_student_boarding(
    db: AsyncSession, 
    student_id: int, 
    bus_number: str, 
    time: str
):
    """Notify guardians when a student boards the bus"""
    from app.services.student import get_student_guardians, get_student_by_id
    
    student = await get_student_by_id(db, student_id)
    if not student:
        return
    
    guardians = await get_student_guardians(db, student_id)
    guardian_tokens = [guardian.fcm_token for guardian in guardians if guardian.fcm_token]
    guardian_emails = [guardian.user.email for guardian in guardians if guardian.user.email]
    
    # Send push notifications
    if guardian_tokens:
        await send_student_boarding_notification(
            guardian_tokens,
            f"{student.first_name} {student.last_name}",
            bus_number,
            time
        )
    
    # Send email notifications
    for email in guardian_emails:
        await send_notification_email(
            email,
            f"{student.first_name} {student.last_name}",
            "Student Boarded Bus",
            f"Your child has boarded bus {bus_number} at {time}",
            redirect_path="/guardian/dashboard"
        )


async def notify_guardians_bus_location(
    db: AsyncSession,
    student_id: int,
    bus_number: str,
    location: str,
    eta: str
):
    """Notify guardians about bus location updates"""
    from app.services.student import get_student_guardians, get_student_by_id
    
    student = await get_student_by_id(db, student_id)
    if not student:
        return
    
    guardians = await get_student_guardians(db, student_id)
    guardian_tokens = [guardian.fcm_token for guardian in guardians if guardian.fcm_token]
    guardian_emails = [guardian.user.email for guardian in guardians if guardian.user.email]
    
    # Send push notifications
    if guardian_tokens:
        await send_bus_location_update(
            guardian_tokens,
            f"{student.first_name} {student.last_name}",
            bus_number,
            location,
            eta
        )
    
    # Send email notifications
    for email in guardian_emails:
        await send_notification_email(
            email,
            f"{student.first_name} {student.last_name}",
            "Bus Location Update",
            f"Bus {bus_number} is at {location}. Estimated arrival time: {eta}",
            redirect_path="/guardian/dashboard"
        )


async def notify_guardians_incident(
    db: AsyncSession,
    student_id: int,
    incident_type: str,
    details: str
):
    """Notify guardians about incidents"""
    from app.services.student import get_student_guardians, get_student_by_id
    
    student = await get_student_by_id(db, student_id)
    if not student:
        return
    
    guardians = await get_student_guardians(db, student_id)
    guardian_tokens = [guardian.fcm_token for guardian in guardians if guardian.fcm_token]
    guardian_emails = [guardian.user.email for guardian in guardians if guardian.user.email]
    
    # Send push notifications
    if guardian_tokens:
        await send_incident_notification(
            guardian_tokens,
            f"{student.first_name} {student.last_name}",
            incident_type,
            details
        )
    
    # Send email notifications
    for email in guardian_emails:
        await send_notification_email(
            email,
            f"{student.first_name} {student.last_name}",
            f"Incident Alert - {incident_type}",
            details,
            redirect_path="/guardian/dashboard"
        )


async def notify_guardians_arrival(
    db: AsyncSession,
    student_id: int,
    location: str,
    time: str
):
    """Notify guardians about student arrival"""
    from app.services.student import get_student_guardians, get_student_by_id
    
    student = await get_student_by_id(db, student_id)
    if not student:
        return
    
    guardians = await get_student_guardians(db, student_id)
    guardian_tokens = [guardian.fcm_token for guardian in guardians if guardian.fcm_token]
    guardian_emails = [guardian.user.email for guardian in guardians if guardian.user.email]
    
    # Send push notifications
    if guardian_tokens:
        await send_arrival_notification(
            guardian_tokens,
            f"{student.first_name} {student.last_name}",
            location,
            time
        )
    
    # Send email notifications
    for email in guardian_emails:
        await send_notification_email(
            email,
            f"{student.first_name} {student.last_name}",
            "Student Arrived",
            f"Your child has arrived at {location} at {time}",
            redirect_path="/guardian/dashboard"
        )

async def notify_guardians_of_trip_incident(
    db: AsyncSession,
    trip_id: int,
    incident_type: str,
    details: str
):
    """Notify all guardians of students on a specific trip about an incident."""
    try:
        trip = await get_trip_by_id(db, trip_id)
        if not trip:
            return

        # Use the already loaded students from the trip object
        students_on_trip = [ts.student for ts in trip.students]
        
        for student in students_on_trip:
            guardians = await get_student_guardians(db, student.id)
            guardian_tokens = [g.fcm_token for g in guardians if g.fcm_token]
            guardian_emails = [g.user.email for g in guardians if g.user.email]

            title = f"Incident Alert on Trip: {incident_type.replace('_', ' ').title()}"
            message = f"An incident ('{details}') has been reported for the trip '{trip.name}' involving bus {trip.bus.bus_number}."
            
            if guardian_tokens:
                await send_push_notification(guardian_tokens, title, message)

            for email in guardian_emails:
                await send_notification_email(email, student.first_name, title, message, redirect_path="/guardian/dashboard")

    except Exception as e:
        print(f"Error notifying guardians of trip incident: {e}")


async def notify_admin_arrival_confirmation(
    db: AsyncSession,
    student,
    guardian,
    confirmed: bool
):
    """Notify admin about arrival confirmation"""
    from app.services.user import get_users
    
    # Get all admin users in the school
    admins = await get_users(db, school_id=student.school_id, role="admin")
    admin_emails = [admin.email for admin in admins if admin.email]
    
    for email in admin_emails:
        await send_notification_email(
            email,
            f"{student.first_name} {student.last_name}",
            "Arrival Confirmation",
            f"Guardian {guardian.first_name} {guardian.last_name} has {'confirmed' if confirmed else 'not confirmed'} the arrival of {student.first_name} {student.last_name}",
            redirect_path="/admin/dashboard"
        )


async def notify_driver_assignment(
    db: AsyncSession,
    driver,
    bus
):
    """Notify driver about bus assignment"""
    if driver.email:
        await send_notification_email(
            driver.email,
            f"{driver.first_name} {driver.last_name}",
            "Bus Assignment",
            f"You have been assigned to bus {bus.bus_number} ({bus.make} {bus.model})",
            redirect_path="/driver/dashboard"
        )


async def notify_trip_status_change(
    db: AsyncSession,
    trip,
    old_status: str,
    new_status: str
):
    """Notify relevant users about trip status changes"""
    from app.services.student import get_students_by_bus_route
    
    if new_status == "IN_PROGRESS":
        # Notify guardians that the trip has started
        students = await get_students_by_bus_route(db, trip.route_id)
        for student in students:
            guardians = await get_student_guardians(db, student.id)
            guardian_emails = [guardian.user.email for guardian in guardians if guardian.user.email]
            
            for email in guardian_emails:
                await send_notification_email(
                    email,
                    f"{student.first_name} {student.last_name}",
                    "Trip Started",
                    f"Bus {trip.bus.bus_number} has started the {trip.type} trip on route {trip.route.name}",
                    redirect_path="/guardian/dashboard"
                )
    
    elif new_status == "COMPLETED":
        # Notify guardians that the trip has completed
        students = await get_students_by_bus_route(db, trip.route_id)
        for student in students:
            guardians = await get_student_guardians(db, student.id)
            guardian_emails = [guardian.user.email for guardian in guardians if guardian.user.email]
            
            for email in guardian_emails:
                await send_notification_email(
                    email,
                    f"{student.first_name} {student.last_name}",
                    "Trip Completed",
                    f"Bus {trip.bus.bus_number} has completed the {trip.type} trip on route {trip.route.name}",
                    redirect_path="/guardian/dashboard"
                )


async def notify_dropoff_pending_confirmation(
    db: AsyncSession,
    student,
    trip
):
    """Notify guardians and admins about student drop-off pending confirmation"""
    from app.services.student import get_student_guardians
    from app.services.user import get_users

    # 1. Notify Guardians
    guardians = await get_student_guardians(db, student.id)
    guardian_emails = [guardian.user.email for guardian in guardians if guardian.user.email]
    guardian_tokens = [guardian.fcm_token for guardian in guardians if guardian.fcm_token]

    for email in guardian_emails:
        await send_notification_email(
            email,
            f"{student.first_name} {student.last_name}",
            "Dropped Off - waiting for confirmation",
            f"Your child has been dropped off from bus {trip.bus.bus_number}. Please login to the app to CONFIRM their safe arrival.",
            redirect_path="/guardian/dashboard"
        )
    
    # 2. Notify Admins
    admins = await get_users(db, school_id=student.school_id, role="admin")
    admin_emails = [admin.email for admin in admins if admin.email]

    for email in admin_emails:
        await send_notification_email(
            email,
            f"{student.first_name} {student.last_name}",
            "Student Pending Confirmation",
            f"Student {student.first_name} {student.last_name} was dropped off from trip {trip.id}. Waiting for guardian confirmation.",
            redirect_path="/admin/dashboard"
        )
