from fastapi import FastAPI, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Optional
from app.core.config import settings
from app.db.session import get_db
from app.routes import auth, superadmin, admin, driver, guardian, bus, incident, school, public
from app.services.school import get_schools_with_admin_status
from app.schemas.school import SchoolResponse
from app.core.cache import redis_client
from starlette.websockets import WebSocketState
from fastapi import WebSocket, WebSocketDisconnect
from app.utils.websocket import ConnectionManager
from app.services.trip import authorize_trip_access
from app.core.jwt import get_current_user_from_token
from app.models.user import User
from app.db.session import AsyncSessionLocal
from app.core.jwt import get_user_for_websocket
from app.services.cleanup_task import start_location_cleanup_task, stop_location_cleanup_task
from app.services.arrival_reminder_task import start_arrival_reminder_task, stop_arrival_reminder_task

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

active_connections: Dict[str, WebSocket] = {}

@app.on_event("startup")
async def startup_event():
    await redis_client.ping()
    start_location_cleanup_task()
    start_arrival_reminder_task()

@app.on_event("shutdown")
async def shutdown_event():
    stop_location_cleanup_task()
    stop_arrival_reminder_task()
    await redis_client.close()

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS if origin != "*"],
    allow_origin_regex=r"^https://.*\.amplifyapp\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["auth"])
app.include_router(superadmin.router, prefix=settings.API_V1_STR, tags=["superadmin"])
app.include_router(admin.router, prefix=settings.API_V1_STR, tags=["admin"])
app.include_router(driver.router, prefix=settings.API_V1_STR, tags=["driver"])
app.include_router(guardian.router, prefix=settings.API_V1_STR, tags=["guardian"])
app.include_router(bus.router, prefix=settings.API_V1_STR, tags=["bus"])
app.include_router(incident.router, prefix=settings.API_V1_STR, tags=["incidents"])
app.include_router(school.router, prefix=settings.API_V1_STR, tags=["schools"])
app.include_router(public.router, prefix=settings.API_V1_STR, tags=["public"])


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

manager = ConnectionManager()

@app.websocket("/ws/trips/{trip_id}/location")
async def websocket_endpoint(
    websocket: WebSocket,
    trip_id: int,
    ticket: Optional[str] = Query(None),
    token: Optional[str] = Query(None)
):
    """
    Handles live location updates.
    Supports secure single-use 60s tickets (issued via POST /api/v1/auth/ws-ticket)
    or fallback JWT tokens for backwards compatibility.
    """
    import json
    db: AsyncSession = AsyncSessionLocal()
    try:
        if ticket:
            ticket_key = f"ws_ticket:{ticket}"
            cached_data = await redis_client.get(ticket_key)
            if cached_data:
                await redis_client.delete(ticket_key)
                ticket_info = json.loads(cached_data)
                if ticket_info.get("trip_id") != trip_id:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Ticket not valid for this trip")
                    return
            else:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired ticket")
                return
        elif token:
            user = await get_user_for_websocket(token, db)
            if not user:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
                return

            is_authorized = await authorize_trip_access(db, user, trip_id)
            if not is_authorized:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
                return
        else:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required (ticket or token)")
            return

        # If valid, accept the connection
        await manager.connect(websocket, str(trip_id))

        # Keep the connection alive
        while websocket.application_state == WebSocketState.CONNECTED:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket, str(trip_id))
    except Exception as e:
        print(f"An unexpected error occurred in websocket for trip {trip_id}: {e}")
    finally:
        await db.close()
 
