from pydantic import BaseModel
from typing import Optional, Dict

class OverviewStats(BaseModel):
    total_schools: int
    total_students: int
    total_buses: int
    total_routes: int
    total_drivers: int
    total_guardians: int
    total_trips: int
    completed_trips: int
    total_stops: int
    cities_covered: int

class LiveMetrics(BaseModel):
    active_trips: int
    buses_on_road: int
    students_in_transit: int

class SafetyMetrics(BaseModel):
    safety_score: float
    incident_resolution_rate: float
    total_incidents: int
    resolved_incidents: int
    uptime_percentage: float

class DisplayStats(BaseModel):
    schools: str
    students: str
    buses: str
    trips: str
    safety_rate: str
    uptime: str

class PublicAnalyticsResponse(BaseModel):
    # Flattened direct access for landing page components
    total_schools: int
    total_students: int
    total_buses: int
    total_routes: int
    total_drivers: int
    total_guardians: int
    total_trips: int
    completed_trips: int
    active_trips: int
    cities_covered: int
    safety_score: float
    uptime_percentage: float
    
    # Structured breakdown
    overview: OverviewStats
    live_metrics: LiveMetrics
    safety: SafetyMetrics
    display_stats: DisplayStats

