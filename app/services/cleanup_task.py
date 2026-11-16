import asyncio
import logging
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.trip import cleanup_old_location_updates

logger = logging.getLogger(__name__)

_cleanup_task: asyncio.Task = None


async def _periodic_cleanup_loop():
    logger.info("Automated location updates cleanup runner initialized.")
    # Wait 60 seconds after server startup before running the first cycle
    await asyncio.sleep(60)

    interval_seconds = max(settings.LOCATION_CLEANUP_INTERVAL_HOURS * 3600, 300)

    while True:
        try:
            if settings.ENABLE_LOCATION_AUTO_CLEANUP:
                logger.info(
                    f"Running scheduled location updates cleanup (Retention: {settings.LOCATION_RETENTION_DAYS} days)..."
                )
                async with AsyncSessionLocal() as db:
                    result = await cleanup_old_location_updates(
                        db=db,
                        days=settings.LOCATION_RETENTION_DAYS,
                        batch_size=settings.LOCATION_CLEANUP_BATCH_SIZE
                    )
                    logger.info(
                        f"Automated location cleanup complete: purged {result['deleted_count']} updates "
                        f"across {result['batches_processed']} batch(es)."
                    )
        except asyncio.CancelledError:
            logger.info("Automated location cleanup task received cancellation request.")
            break
        except Exception as e:
            logger.error(f"Error during automated location cleanup run: {e}", exc_info=True)

        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            break


def start_location_cleanup_task():
    global _cleanup_task
    if not settings.ENABLE_LOCATION_AUTO_CLEANUP:
        logger.info("Automated location updates cleanup is disabled via ENABLE_LOCATION_AUTO_CLEANUP=false.")
        return None

    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_periodic_cleanup_loop())
        logger.info("Background periodic location cleanup task scheduled.")
    return _cleanup_task


def stop_location_cleanup_task():
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        logger.info("Background periodic location cleanup task stopped.")
        _cleanup_task = None
