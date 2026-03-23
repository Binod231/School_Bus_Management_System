# school_bus_management/app/utils/fcm.py
import firebase_admin
from firebase_admin import credentials, messaging
from app.core.config import settings

firebase_app = None

# Initialize Firebase Admin SDK with the service account credentials
if settings.FCM_CREDENTIALS_PATH:
    try:
        cred = credentials.Certificate(settings.FCM_CREDENTIALS_PATH)
        firebase_app = firebase_admin.initialize_app(cred)
    except FileNotFoundError:
        print(f"Firebase credentials file not found at {settings.FCM_CREDENTIALS_PATH}")
    except Exception as e:
        print(f"Failed to initialize Firebase Admin SDK: {str(e)}")
else:
    print("FCM credentials path not configured. Push notifications will not be sent.")


async def send_push_notification(fcm_tokens: list, title: str, message: str, data: dict = None):
    """Send push notification to devices using FCM V1 API"""
    if not firebase_app:
        print(f"FCM not configured. Would send notification: {title} - {message}")
        return
    
    if not fcm_tokens:
        print("No FCM tokens provided")
        return
    
    try:
        if len(fcm_tokens) == 1:
            # Send a single message
            message_obj = messaging.Message(
                notification=messaging.Notification(title=title, body=message),
                data=data,
                token=fcm_tokens[0]
            )
            response = messaging.send(message_obj)
            print(f"Successfully sent message: {response}")
            return response
        else:
            # Send multiple messages
            messages = [
                messaging.Message(
                    notification=messaging.Notification(title=title, body=message),
                    data=data,
                    token=token
                )
                for token in fcm_tokens
            ]
            batch_response = messaging.send_all(messages)
            print(f"Sent {batch_response.success_count} messages, failed to send {batch_response.failure_count}")
            if batch_response.failure_count > 0:
                for error in batch_response.errors:
                    print(f"Error sending message to token {error.index}: {error.exception}")
            return batch_response
    except Exception as e:
        print(f"Failed to send push notification: {str(e)}")
        return None


async def send_student_boarding_notification(guardian_tokens: list, student_name: str, bus_number: str, time: str):
    """Send notification when student boards the bus"""
    title = "Student Boarded Bus"
    message = f"{student_name} has boarded bus {bus_number} at {time}"
    data = {
        "type": "boarding",
        "student_name": student_name,
        "bus_number": bus_number,
        "time": time
    }
    
    await send_push_notification(guardian_tokens, title, message, data)


async def send_bus_location_update(guardian_tokens: list, student_name: str, bus_number: str, location: str, eta: str):
    """Send bus location update notification"""
    title = "Bus Location Update"
    message = f"Bus {bus_number} carrying {student_name} is at {location}. ETA: {eta}"
    data = {
        "type": "location_update",
        "student_name": student_name,
        "bus_number": bus_number,
        "location": location,
        "eta": eta
    }
    
    await send_push_notification(guardian_tokens, title, message, data)


async def send_incident_notification(guardian_tokens: list, student_name: str, incident_type: str, details: str):
    """Send incident notification"""
    title = f"Incident Alert - {incident_type}"
    message = f"An incident has been reported for {student_name}: {details}"
    data = {
        "type": "incident",
        "student_name": student_name,
        "incident_type": incident_type,
        "details": details
    }
    
    await send_push_notification(guardian_tokens, title, message, data)


async def send_arrival_notification(guardian_tokens: list, student_name: str, location: str, time: str):
    """Send arrival notification"""
    title = "Student Arrived"
    message = f"{student_name} has arrived at {location} at {time}"
    data = {
        "type": "arrival",
        "student_name": student_name,
        "location": location,
        "time": time
    }
    
    await send_push_notification(guardian_tokens, title, message, data)