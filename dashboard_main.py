import asyncio
import signal
from app.dashboard.app import dashboard
from app.core.logger import logger
from app.core.config import settings

async def shutdown():
    """Graceful shutdown for the dashboard."""
    logger.info("dashboard_shutdown_initiated")
    await dashboard.stop()
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [t.cancel() for t in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)
    asyncio.get_event_loop().stop()

async def main():
    logger.info("dashboard_standalone_mode_starting")
    
    # Start the dashboard
    # Note: We don't acquire the singleton lock here because the bot process 
    # likely already has it, and the dashboard only needs read-only access to the DB.
    # SQLite allows multiple readers in WAL mode.
    
    try:
        await dashboard.start()
    except Exception as e:
        logger.error("dashboard_startup_failed", error=str(e))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("dashboard_interrupted_by_user")
