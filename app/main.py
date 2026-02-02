from fastapi import FastAPI, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.config import settings
from app.db.session import get_db
from app.routes import auth, superadmin, admin, driver, guardian, bus, incident
from app.services.school import get_schools_with_admin_status
from app.schemas.school import SchoolResponse
from app.core.cache import redis_client
from fastapi import WebSocket
from starlette.websockets import WebSocketState
from typing import Dict
from fastapi import WebSocketDisconnect
from app.utils.websocket import ConnectionManager
from app.services.trip import authorize_trip_access
from app.core.jwt import get_current_user_from_token
from app.models.user import User
from app.db.session import AsyncSessionLocal
from app.core.jwt import get_user_for_websocket

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

active_connections: Dict[str, WebSocket] = {}

@app.on_event("startup")
async def startup_event():
    await redis_client.ping()

@app.on_event("shutdown")
async def shutdown_event():
    await redis_client.close()

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["auth"])
app.include_router(superadmin.router, prefix=settings.API_V1_STR, tags=["superadmin"])
app.include_router(admin.router, prefix=settings.API_V1_STR, tags=["admin"])
app.include_router(driver.router, prefix=settings.API_V1_STR, tags=["driver"])
app.include_router(guardian.router, prefix=settings.API_V1_STR, tags=["guardian"])
app.include_router(bus.router, prefix=settings.API_V1_STR, tags=["bus"])
app.include_router(incident.router, prefix=settings.API_V1_STR, tags=["incidents"])


@app.get(
    "/",
    response_model=List[SchoolResponse],
    summary="Get all schools",
    description="Retrieves a list of all registered schools."
)
async def list_registered_schools(
    db: AsyncSession = Depends(get_db)
):
    schools = await get_schools_with_admin_status(db)
    return schools


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

manager = ConnectionManager()

@app.websocket("/ws/trips/{trip_id}/location")
async def websocket_endpoint(
    websocket: WebSocket,
    trip_id: int,
    token: str = Query(...)
):
    """
    Handles live location updates. This version correctly manages the DB session
    and authentication for robust WebSocket compatibility.
    """
    db: AsyncSession = AsyncSessionLocal()
    try:
        # Step 1: Authenticate the user safely
        user = await get_user_for_websocket(token, db)
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
            return

        # Step 2: Authorize the user for the requested trip
        is_authorized = await authorize_trip_access(db, user, trip_id)
        if not is_authorized:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
            return

        # Step 3: If valid, accept the connection
        await manager.connect(websocket, str(trip_id))
        
        # Step 4: Keep the connection alive
        while websocket.application_state == WebSocketState.CONNECTED:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket, str(trip_id))
    except Exception as e:
        print(f"An unexpected error occurred in websocket for trip {trip_id}: {e}")
    finally:
        # CRITICAL: Always close the database session
        await db.close()
 
