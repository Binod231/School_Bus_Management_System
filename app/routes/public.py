from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel

from app.db.session import get_db
from app.models.school import School
from app.schemas.public import PublicAnalyticsResponse
from app.services.analytics import get_public_landing_analytics

router = APIRouter(
    prefix="/public",
    tags=["public"]
)

class PublicSchoolItem(BaseModel):
    id: int
    name: str
    city: str
    state: str
    website: Optional[str] = None
    logo_url: Optional[str] = None

    class Config:
        from_attributes = True


@router.get(
    "/analytics",
    response_model=PublicAnalyticsResponse,
    summary="Get Landing Page Analytics",
    description="Public endpoint providing platform analytics, live metrics, and safety stats for the landing page without requiring authentication."
)
async def get_landing_analytics(db: AsyncSession = Depends(get_db)):
    """
    Returns aggregated public analytics for the landing page:
    - Overview counts (schools, students, buses, routes, drivers, guardians, trips)
    - Live metrics (active trips, buses on road, students in transit)
    - Safety and reliability metrics (safety score, resolution rate, uptime)
    - Formatted display stats (e.g., '500+', '10K+', '99.9%')
    """
    return await get_public_landing_analytics(db)


@router.get(
    "/stats",
    response_model=PublicAnalyticsResponse,
    summary="Get Landing Page Stats (Alias)",
    description="Alias endpoint for landing page statistics."
)
async def get_landing_stats_alias(db: AsyncSession = Depends(get_db)):
    return await get_public_landing_analytics(db)


@router.get(
    "/schools",
    response_model=List[PublicSchoolItem],
    summary="Get Public Schools List",
    description="Public list of active partner schools for landing page showcase."
)
async def get_public_schools(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(School).where(School.is_active == True).order_by(School.name)
    )
    return result.scalars().all()

