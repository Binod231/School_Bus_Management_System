#!/usr/bin/env python3
"""
Stand-alone database cleanup script for location_updates table.
Deletes raw GPS pings older than a specified number of days to prevent table bloat.

Usage:
    python scripts/cleanup_locations.py --days 60
    # Inside docker:
    docker exec -e PYTHONPATH=/app school_bus_web python3 scripts/cleanup_locations.py --days 60
"""
import sys
import os
import argparse
import asyncio
from datetime import datetime

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.trip import cleanup_old_location_updates


async def run_cleanup(days: int, batch_size: int):
    print(f"[{datetime.utcnow().isoformat()} UTC] Starting cleanup of location updates older than {days} days (batch size: {batch_size})...")
    async with AsyncSessionLocal() as db:
        result = await cleanup_old_location_updates(db=db, days=days, batch_size=batch_size)
    print(f"[{datetime.utcnow().isoformat()} UTC] Completed successfully:")
    print(f"  - Deleted records: {result['deleted_count']}")
    print(f"  - Retention cutoff: {result['cutoff_date']}")
    print(f"  - Batches processed: {result['batches_processed']}")


def main():
    parser = argparse.ArgumentParser(description="Purge old GPS location updates from the database.")
    parser.add_argument(
        "--days",
        type=int,
        default=settings.LOCATION_RETENTION_DAYS,
        help=f"Number of retention days (default: {settings.LOCATION_RETENTION_DAYS})"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.LOCATION_CLEANUP_BATCH_SIZE,
        help=f"Batch size per deletion batch (default: {settings.LOCATION_CLEANUP_BATCH_SIZE})"
    )
    args = parser.parse_args()

    asyncio.run(run_cleanup(days=args.days, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
