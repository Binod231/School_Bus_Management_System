from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.config import settings
from app.db.session import get_db
from app.routes import auth, superadmin, admin, driver, guardian, bus, incident
from app.services.school import get_schools
from app.schemas.school import SchoolResponse
from app.core.cache import redis_client
from fastapi import WebSocket
from typing import Dict
from fastapi import WebSocketDisconnect

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
    schools = await get_schools(db)
    return schools


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            # For now, we'll just echo back messages.
            # In a real app, you would process the data and broadcast updates.
            for connection in active_connections.values():
                await connection.send_text(f"Message from {client_id}: {data}")
    except WebSocketDisconnect:
        del active_connections[client_id]