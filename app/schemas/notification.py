from pydantic import BaseModel, Field
from typing import Optional, Literal


class BroadcastNotificationRequest(BaseModel):
    title: str = Field(..., description="Notification title, e.g., 'Happy Dashain Festival' or 'New Academic Session 2026'")
    message: str = Field(..., description="Notification body content detailing festival holiday or session details")
    target: Literal["GUARDIANS", "DRIVERS", "ALL", "ROUTE"] = Field(
        "GUARDIANS",
        description="Target audience: GUARDIANS, DRIVERS, ALL, or ROUTE"
    )
    category: Optional[str] = Field(
        "FESTIVAL",
        description="Category: FESTIVAL, HOLIDAY, SESSION, WEATHER, EMERGENCY, ANNOUNCEMENT"
    )
    route_id: Optional[int] = Field(
        None,
        description="Optional: specific bus route ID if target is set to ROUTE"
    )
    send_email: bool = Field(
        True,
        description="Whether to also send email notifications in addition to push notifications"
    )


class BroadcastNotificationResponse(BaseModel):
    status: str
    title: str
    target: str
    category: str
    push_tokens_targeted: int
    emails_targeted: int
    message: str
