# school_bus_management/app/utils/fcm.py
import firebase_admin
from firebase_admin import credentials, messaging
from app.core.config import settings
from typing import Optional, List, Dict

firebase_app = None

# Initialize Firebase Admin SDK with the service account credentials
if settings.FCM_CREDENTIALS_PATH:
    try:
        cred = credentials.Certificate(settings.FCM_CREDENTIALS_PATH)
        firebase_app = firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully!")
    except FileNotFoundError:
        print(f"Firebase credentials file not found at {settings.FCM_CREDENTIALS_PATH}")
    except Exception as e:
        print(f"Failed to initialize Firebase Admin SDK: {str(e)}")
else:
    print("FCM credentials path not configured. Push notifications will not be sent.")


def _build_platform_configs():
    """Builds Android, APNS, and Webpush configs for high priority and sound."""
    android_config = messaging.AndroidConfig(
        priority="high",
        notification=messaging.AndroidNotification(
            sound="default",
            channel_id="school_bus_alerts",
            default_sound=True,
            default_vibrate_timings=True
        )
    )
    apns_config = messaging.APNSConfig(
        headers={"apns-priority": "10"},
        payload=messaging.APNSPayload(
            aps=messaging.Aps(
                sound="default",
                badge=1,
                content_available=True
            )
        )
    )
    webpush_config = messaging.WebpushConfig(
        headers={"Urgency": "high"}
    )
    return android_config, apns_config, webpush_config


async def send_push_notification(fcm_tokens: list, title: str, message: str, data: Optional[Dict] = None):
    """
    Sends rich, high-priority push notifications to device tokens using FCM V1 API.
    Supports Android heads-up alerts with sound, iOS APNS banners, and webpush.
    """
    if not firebase_app:
        print(f"[FCM Dry-Run] Not initialized. Notification: '{title}' - '{message}'")
        return None

    if not fcm_tokens:
        return None

    # Filter out empty or None tokens
    valid_tokens = list(set([t for t in fcm_tokens if t and isinstance(t, str)]))
    if not valid_tokens:
        return None

    # FCM V1 strictly requires all keys and values in 'data' to be strings
    string_data = {str(k): str(v) for k, v in data.items()} if data else None
    android_config, apns_config, webpush_config = _build_platform_configs()

    try:
        if len(valid_tokens) == 1:
            message_obj = messaging.Message(
                notification=messaging.Notification(title=title, body=message),
                data=string_data,
                token=valid_tokens[0],
                android=android_config,
                apns=apns_config,
                webpush=webpush_config
            )
            response = messaging.send(message_obj)
            return response
        else:
            messages = [
                messaging.Message(
                    notification=messaging.Notification(title=title, body=message),
                    data=string_data,
                    token=token,
                    android=android_config,
                    apns=apns_config,
                    webpush=webpush_config
                )
                for token in valid_tokens
            ]
            batch_response = messaging.send_all(messages)
            if batch_response.failure_count > 0:
                print(f"[FCM Warning] Failed to deliver to {batch_response.failure_count}/{len(valid_tokens)} device(s).")
            return batch_response
    except Exception as e:
        print(f"[FCM Error] Failed to send push notification: {e}")
        return None


async def send_student_boarding_notification(guardian_tokens: list, student_name: str, bus_number: str, time: str):
    """Send notification when student boards the bus"""
    title = f"🎒 Student Boarded Bus #{bus_number}"
    message = f"{student_name} has safely boarded Bus #{bus_number} at {time}."
    data = {
        "type": "boarding",
        "student_name": student_name,
        "bus_number": bus_number,
        "time": time
    }
    await send_push_notification(guardian_tokens, title, message, data)


async def send_student_unboarding_notification(guardian_tokens: list, student_name: str, bus_number: str, stop_name: str, time: str):
    """Send notification when student unboards / drops off at a stop"""
    title = f"🚏 Student Dropped Off - Confirmation Needed"
    message = f"{student_name} was dropped off from Bus #{bus_number} at {stop_name} at {time}. Please confirm arrival in the app."
    data = {
        "type": "unboarding",
        "action": "CONFIRM_ARRIVAL",
        "student_name": student_name,
        "bus_number": bus_number,
        "stop_name": stop_name,
        "time": time
    }
    await send_push_notification(guardian_tokens, title, message, data)


async def send_arrival_confirmation_reminder_notification(
    guardian_tokens: list,
    student_name: str,
    bus_number: str,
    stop_name: str,
    minutes_ago: int = 10
):
    """Send reminder every 10 minutes until guardian confirms student arrival"""
    title = f"⚠️ Action Required: Confirm Safe Arrival of {student_name}"
    message = f"{student_name} was dropped off from Bus #{bus_number} at {stop_name} (~{minutes_ago} mins ago). Please confirm their safe arrival immediately."
    data = {
        "type": "confirm_arrival_reminder",
        "action": "CONFIRM_ARRIVAL",
        "student_name": student_name,
        "bus_number": bus_number,
        "stop_name": stop_name,
        "minutes_ago": str(minutes_ago)
    }
    await send_push_notification(guardian_tokens, title, message, data)


async def send_bus_stop_arrival_notification(guardian_tokens: list, student_name: str, bus_number: str, stop_name: str, time: str):
    """Send notification when bus arrives at student's stop"""
    title = f"🚌 Bus #{bus_number} Arrived at Stop"
    message = f"Bus #{bus_number} for {student_name} has arrived at {stop_name} ({time})."
    data = {
        "type": "stop_arrival",
        "student_name": student_name,
        "bus_number": bus_number,
        "stop_name": stop_name,
        "time": time
    }
    await send_push_notification(guardian_tokens, title, message, data)


async def send_bus_location_update(guardian_tokens: list, student_name: str, bus_number: str, location: str, eta: str):
    """Send bus location / approaching stop update notification"""
    title = f"🚍 Bus #{bus_number} Approaching"
    message = f"Bus #{bus_number} for {student_name} is near {location}. Estimated Arrival: {eta}."
    data = {
        "type": "location_update",
        "student_name": student_name,
        "bus_number": bus_number,
        "location": location,
        "eta": eta
    }
    await send_push_notification(guardian_tokens, title, message, data)


async def send_incident_notification(guardian_tokens: list, student_name: str, incident_type: str, details: str):
    """Send urgent incident notification"""
    title = f"🚨 Incident Alert: {incident_type.replace('_', ' ').title()}"
    message = f"An incident has been reported for {student_name}: {details}"
    data = {
        "type": "incident",
        "severity": "CRITICAL",
        "student_name": student_name,
        "incident_type": incident_type,
        "details": details
    }
    await send_push_notification(guardian_tokens, title, message, data)


async def send_arrival_notification(guardian_tokens: list, student_name: str, location: str, time: str):
    """Send arrival notification"""
    title = f"✅ Student Arrived at {location}"
    message = f"{student_name} has arrived safely at {location} at {time}."
    data = {
        "type": "arrival",
        "student_name": student_name,
        "location": location,
        "time": time
    }
    await send_push_notification(guardian_tokens, title, message, data)


async def send_trip_started_notification(guardian_tokens: list, bus_number: str, route_name: str, trip_type: str):
    """Send notification when a trip begins"""
    title = f"🚀 Trip Started: Bus #{bus_number}"
    message = f"Bus #{bus_number} has started the {trip_type} trip on route {route_name}."
    data = {
        "type": "trip_started",
        "bus_number": bus_number,
        "route_name": route_name,
        "trip_type": trip_type
    }
    await send_push_notification(guardian_tokens, title, message, data)


async def send_trip_completed_notification(guardian_tokens: list, bus_number: str, route_name: str, trip_type: str):
    """Send notification when a trip completes"""
    title = f"🏁 Trip Completed: Bus #{bus_number}"
    message = f"Bus #{bus_number} has completed the {trip_type} trip on route {route_name}."
    data = {
        "type": "trip_completed",
        "bus_number": bus_number,
        "route_name": route_name,
        "trip_type": trip_type
    }
    await send_push_notification(guardian_tokens, title, message, data)


async def send_emergency_transfer_notification(guardian_tokens: list, old_bus: str, new_bus: str, reason: str):
    """Send notification when students are transferred during an emergency breakdown"""
    title = f"🔄 Bus Transfer: Bus #{old_bus} ➔ Bus #{new_bus}"
    message = f"Students on Bus #{old_bus} have been transferred safely to replacement Bus #{new_bus}. Reason: {reason}."
    data = {
        "type": "emergency_transfer",
        "severity": "HIGH",
        "old_bus": old_bus,
        "new_bus": new_bus,
        "reason": reason
    }
    await send_push_notification(guardian_tokens, title, message, data)
