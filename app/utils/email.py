import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings
from app.core.security import create_access_token
from datetime import timedelta

async def send_email(to_email: str, subject: str, body: str):
    """Send email using SMTP server"""
    if not all([settings.SMTP_SERVER, settings.SMTP_PORT, settings.SMTP_USERNAME, settings.SMTP_PASSWORD]):
        print(f"Email configuration missing. Would send email to {to_email}: {subject}")
        return
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = settings.FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body to email
        msg.attach(MIMEText(body, 'html'))
        
        # Create server
        server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
        server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        
        # Send email
        text = msg.as_string()
        server.sendmail(settings.FROM_EMAIL, to_email, text)
        server.quit()
        
        print(f"Email sent successfully to {to_email}")
    except Exception as e:
        print(f"Failed to send email to {to_email}: {str(e)}")


async def send_password_reset_email(email: str, reset_token: str):
    """Send password reset email"""
    subject = "Password Reset Request - School Bus Management System"
    # Use the configurable frontend URL
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    
    body = f"""
    <html>
    <body>
        <h2>Password Reset Request</h2>
        <p>You have requested to reset your password for the School Bus Management System.</p>
        <p>Please click the link below to reset your password:</p>
        <p><a href="{reset_url}">Reset Password</a></p>
        <p>This link will expire in 30 minutes.</p>
        <p>If you did not request this reset, please ignore this email.</p>
        <br>
        <p>Best regards,<br>School Bus Management Team</p>
    </body>
    </html>
    """
    
    await send_email(email, subject, body)


async def send_new_user_email(email: str, user_id: int):
    """Send welcome email with a password reset link for new users"""
    subject = "Welcome to School Bus Management System"
    
    # Generate a password reset token
    reset_token_expires = timedelta(minutes=60 * 24) # 24 hours
    reset_token = create_access_token(
        data={"sub": str(user_id), "purpose": "password_reset"},
        expires_delta=reset_token_expires
    )
    
    # Use the configurable frontend URL
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    
    body = f"""
    <html>
    <body>
        <h2>Welcome to School Bus Management System</h2>
        <p>Your account has been created successfully.</p>
        <p>Please click the link below to set your password and get started:</p>
        <p><a href="{reset_url}">Set Your Password</a></p>
        <p>This link will expire in 24 hours.</p>
        <br>
        <p>Best regards,<br>School Bus Management Team</p>
    </body>
    </html>
    """
    await send_email(email, subject, body)


async def send_notification_email(email: str, student_name: str, event_type: str, details: str):
    """Send notification email to guardians"""
    subject = f"School Bus Notification - {event_type}"
    
    body = f"""
    <html>
    <body>
        <h2>School Bus Notification</h2>
        <p>Hello,</p>
        <p>This is to notify you about your child {student_name}:</p>
        <p><strong>Event:</strong> {event_type}</p>
        <p><strong>Details:</strong> {details}</p>
        <br>
        <p>Best regards,<br>School Bus Management Team</p>
    </body>
    </html>
    """
    
    await send_email(email, subject, body)