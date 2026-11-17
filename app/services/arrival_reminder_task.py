import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload
from app.db.session import AsyncSessionLocal
from app.models.trip import TripStudent, Trip, StudentStatus
from app.models.student import Student, GuardianStudent, Guardian
from app.utils.fcm import send_arrival_confirmation_reminder_notification
from app.utils.email import send_notification_email
from app.core.cache import redis_client

logger = logging.getLogger(__name__)

_reminder_task: asyncio.Task = None


async def check_and_send_arrival_reminders():
    """
    Finds all students with status == DROPPED_OFF (waiting for guardian confirmation).
    Sends a high-priority push notification and email reminder every 10 minutes until
    the guardian confirms their safe arrival.
    """
    async with AsyncSessionLocal() as db:
        try:
            stmt = (
                select(TripStudent)
                .options(
                    joinedload(TripStudent.trip).joinedload(Trip.bus),
                    joinedload(TripStudent.student).options(
                        joinedload(Student.bus_stop),
                        selectinload(Student.guardians).joinedload(GuardianStudent.guardian).joinedload(Guardian.user)
                    )
                )
                .where(TripStudent.status == StudentStatus.DROPPED_OFF)
            )
            res = await db.execute(stmt)
            unconfirmed_students = res.scalars().unique().all()

            if not unconfirmed_students:
                return

            now = datetime.now(timezone.utc)

            for ts in unconfirmed_students:
                student = ts.student
                trip = ts.trip
                if not student or not trip:
                    continue

                cache_key = f"arrival_reminder:{ts.id}:last_sent"
                last_sent_str = await redis_client.get(cache_key)

                dropoff_time = ts.disembarked_at or ts.updated_at or ts.created_at
                if dropoff_time and dropoff_time.tzinfo is None:
                    dropoff_time = dropoff_time.replace(tzinfo=timezone.utc)

                should_send = False
                minutes_since_dropoff = 10
                if dropoff_time:
                    elapsed_seconds = (now - dropoff_time).total_seconds()
                    minutes_since_dropoff = max(10, int(elapsed_seconds / 60))

                if not last_sent_str:
                    # Initial dropoff notification is sent by the driver at 0 min.
                    # Send the first reminder after 10 minutes (600 seconds) have elapsed.
                    if dropoff_time and (now - dropoff_time).total_seconds() >= 600:
                        should_send = True
                    elif not dropoff_time:
                        should_send = True
                else:
                    try:
                        if isinstance(last_sent_str, bytes):
                            last_sent_str = last_sent_str.decode("utf-8")
                        last_sent = datetime.fromisoformat(last_sent_str)
                        if last_sent.tzinfo is None:
                            last_sent = last_sent.replace(tzinfo=timezone.utc)
                        # Re-send if at least 10 minutes (600 seconds) have passed since the previous reminder
                        if (now - last_sent).total_seconds() >= 600:
                            should_send = True
                    except Exception as e:
                        logger.warning(f"Failed to parse last_sent timestamp '{last_sent_str}': {e}")
                        should_send = True

                if should_send:
                    bus_number = trip.bus.bus_number if trip.bus else "School Bus"
                    stop_name = student.bus_stop.name if student.bus_stop else "the designated stop"
                    student_full_name = f"{student.first_name} {student.last_name}"

                    guardians = [gs.guardian for gs in student.guardians if gs.guardian]
                    fcm_tokens = [g.fcm_token for g in guardians if g.fcm_token]
                    emails = [g.user.email for g in guardians if g.user and g.user.email]

                    # 1. Send Rich Push Notification
                    if fcm_tokens:
                        await send_arrival_confirmation_reminder_notification(
                            guardian_tokens=fcm_tokens,
                            student_name=student_full_name,
                            bus_number=bus_number,
                            stop_name=stop_name,
                            minutes_ago=minutes_since_dropoff
                        )

                    # 2. Send Reminder Email
                    for email in emails:
                        await send_notification_email(
                            email=email,
                            student_name=student_full_name,
                            event_type=f"Confirm Safe Arrival ({minutes_since_dropoff}m ago)",
                            details=(
                                f"{student_full_name} was dropped off from Bus #{bus_number} at {stop_name} "
                                f"(~{minutes_since_dropoff} minutes ago). Please confirm their safe arrival in the EDURIDE app."
                            ),
                            redirect_path="/guardian/dashboard"
                        )

                    # Cache last sent time, expires in 24 hours
                    await redis_client.set(cache_key, now.isoformat(), ex=86400)
                    logger.info(
                        f"Dispatched 10-minute arrival confirmation reminder for student {student.id} "
                        f"({student_full_name}) on Trip {trip.id}."
                    )

        except Exception as e:
            logger.error(f"Error checking arrival confirmation reminders: {e}", exc_info=True)


async def _periodic_arrival_reminder_loop():
    logger.info("Arrival confirmation reminder runner active (checking every 60s, reminders sent every 10m).")
    # Initial sleep so server starts cleanly
    await asyncio.sleep(30)
    while True:
        try:
            await check_and_send_arrival_reminders()
        except asyncio.CancelledError:
            logger.info("Arrival confirmation reminder task received cancellation.")
            break
        except Exception as e:
            logger.error(f"Error in arrival reminder loop: {e}", exc_info=True)

        try:
            # Poll every 60 seconds
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            break


def start_arrival_reminder_task():
    global _reminder_task
    if _reminder_task is None or _reminder_task.done():
        _reminder_task = asyncio.create_task(_periodic_arrival_reminder_loop())
        logger.info("Background arrival reminder task started.")
    return _reminder_task


def stop_arrival_reminder_task():
    global _reminder_task
    if _reminder_task and not _reminder_task.done():
        _reminder_task.cancel()
        logger.info("Background arrival reminder task stopped.")
        _reminder_task = None
