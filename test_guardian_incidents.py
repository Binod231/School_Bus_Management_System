#!/usr/bin/env python3
"""
Simple test script to verify the guardian incidents endpoint works
"""
import asyncio
import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.services.incident import get_guardian_incidents_filtered

async def test_guardian_incidents():
    """Test the guardian incidents functionality"""
    async with AsyncSessionLocal() as db:
        try:
            # Test with guardian user ID 42 (from the logs)
            incidents = await get_guardian_incidents_filtered(db, 42, skip=0, limit=10)
            print(f"Found {len(incidents)} incidents for guardian user ID 42")
            
            for incident in incidents:
                print(f"- Incident {incident.id}: {incident.title} (Type: {incident.type}, Status: {incident.status})")
                print(f"  Reported by: {incident.reported_by.first_name} {incident.reported_by.last_name} ({incident.reported_by.role})")
                if incident.student_id:
                    print(f"  Student ID: {incident.student_id}")
                if incident.trip_id:
                    print(f"  Trip ID: {incident.trip_id}")
                print()
                
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_guardian_incidents())