import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings
from app.core.security import create_access_token
from datetime import datetime, timedelta, timezone

def get_nepal_time():
    """Returns formatted current time in Nepal (UTC+5:45)"""
    # Nepal is UTC + 5:45
    nepal_offset = timezone(timedelta(hours=5, minutes=45))
    return datetime.now(nepal_offset).strftime("%B %d, %Y | %I:%M %p")

def get_eduride_template(title: str, content: str, action_url: str = None, action_text: str = None):
    """Returns a professional, attractive and interactive HTML template for EDURIDE"""
    current_time = get_nepal_time()
    
    action_button = ""
    if action_url and action_text:
        action_button = f"""
        <div style="text-align: center; margin: 35px 0;">
            <a href="{action_url}" style="background-color: #1a73e8; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: inline-block; box-shadow: 0 4px 6px rgba(26, 115, 232, 0.2);">
                {action_text}
            </a>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; background-color: #f4f7f9; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
        <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
            <!-- Header -->
            <tr>
                <td style="padding: 40px 0; text-align: center; background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);">
                    <h1 style="color: #ffffff; margin: 0; font-size: 32px; letter-spacing: 2px; font-weight: 800; text-transform: uppercase;">EDURIDE</h1>
                    <p style="color: #bbdefb; margin: 5px 0 0 0; font-size: 14px; letter-spacing: 1px;">Smart School Bus Management</p>
                </td>
            </tr>
            <!-- Content -->
            <tr>
                <td style="padding: 40px 30px; line-height: 1.6; color: #37474f;">
                    <h2 style="color: #1a73e8; margin-top: 0; font-size: 24px;">{title}</h2>
                    <div style="font-size: 16px;">
                        {content}
                    </div>
                    {action_button}
                </td>
            </tr>
            <!-- Footer -->
            <tr>
                <td style="padding: 30px; text-align: center; background-color: #f8f9fa; border-top: 1px solid #eeeeee;">
                    <p style="margin: 0; color: #90a4ae; font-size: 13px;">
                        &copy; {datetime.now().year} <strong>EDURIDE</strong>. All rights reserved.
                    </p>
                    <p style="margin: 10px 0 0 0; color: #b0bec5; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                        Nepal Local Time: {current_time}
                    </p>
                    <div style="margin-top: 20px;">
                        <span style="display: inline-block; width: 30px; height: 3px; background-color: #1a73e8; border-radius: 2px;"></span>
                    </div>
                </td>
            </tr>
        </table>
        <div style="text-align: center; padding: 20px; color: #b0bec5; font-size: 12px;">
            This is an automated notification from EDURIDE core systems.
        </div>
    </body>
    </html>
    """

async def send_email(to_email: str, subject: str, body: str):
    """Send email using SMTP server"""
    if not all([settings.SMTP_SERVER, settings.SMTP_PORT, settings.SMTP_USERNAME, settings.SMTP_PASSWORD]):
        print(f"Email configuration missing. Would send email to {to_email}: {subject}")
        return
    
    try:
        msg = MIMEMultipart()
        msg['From'] = settings.FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
        server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        
        text = msg.as_string()
        server.sendmail(settings.FROM_EMAIL, to_email, text)
        server.quit()
        print(f"Email sent successfully to {to_email}")
    except Exception as e:
        print(f"Failed to send email to {to_email}: {str(e)}")

async def send_password_reset_email(email: str, reset_token: str):
    """Send password reset email"""
    subject = "Reset Your EDURIDE Password"
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    
    content = f"""
        <p>Hello,</p>
        <p>We received a request to reset your password for your <strong>EDURIDE</strong> account.</p>
        <p>Your security is our priority. Click the button below to choose a new password. This link is valid for <strong>30 minutes</strong>.</p>
        <p style="background-color: #fff9c4; padding: 10px; border-left: 4px solid #fbc02d; font-size: 14px;">
            <strong>Note:</strong> If you didn't request this, you can safely ignore this email. Your password will remain unchanged.
        </p>
    """
    body = get_eduride_template("Password Reset Request", content, reset_url, "Reset My Password")
    await send_email(email, subject, body)

async def send_new_user_email(email: str, user_id: int):
    """Send welcome email for new users"""
    subject = "🎯 Welcome to EDURIDE - Get Started Now"
    
    reset_token_expires = timedelta(minutes=60 * 24)
    reset_token = create_access_token(
        data={"sub": str(user_id), "purpose": "password_reset"},
        expires_delta=reset_token_expires
    )
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    
    content = f"""
        <p>Hello and welcome!</p>
        <p>Your account has been successfully created on <strong>EDURIDE</strong>, the ultimate school bus management platform.</p>
        <p>To get started, please click the button below to set up your password and access your dashboard. This link is valid for <strong>24 hours</strong>.</p>
        <p>We're excited to have you on board!</p>
    """
    body = get_eduride_template("Welcome to EDURIDE!", content, reset_url, "Set Up My Account")
    await send_email(email, subject, body)

async def send_notification_email(email: str, student_name: str, event_type: str, details: str, redirect_path: str = "/"):
    """Send dynamic notification email to guardians/admins"""
    subject = f"📢 EDURIDE Alert: {event_type}"
    
    # Construct full redirect URL
    action_url = f"{settings.FRONTEND_URL}{redirect_path}"
    
    content = f"""
        <p>Hello,</p>
        <p>This is an automated update regarding <strong>{student_name}</strong> and their school transit status.</p>
        <div style="background-color: #f0f4f8; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <p style="margin: 0; color: #1a73e8; font-weight: bold; font-size: 18px;">{event_type}</p>
            <p style="margin: 10px 0 0 0; color: #546e7a;">{details}</p>
        </div>
        <p>Log in to your <strong>EDURIDE</strong> dashboard to track the bus in real-time or view more detailed logs.</p>
    """
    body = get_eduride_template("Student Status Update", content, action_url, "Open Dashboard")
    await send_email(email, subject, body)
