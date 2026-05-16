import os
import sys
import asyncio
import signal
import random
from pathlib import Path
from app.core.config import settings
from app.core.logger import logger
from app.core.lock import singleton
from app.core.telegram import tg_session
from app.core.db import db
from app.bot.bot import control_bot
from app.core.downloader import download_manager
from app.core.scheduler import tier_scheduler
from app.core.monitor import resource_monitor

async def shutdown(sig=None):
    """Graceful shutdown handler."""
    if sig:
        logger.info("shutdown_signal_received", signal=sig.name)
    
    logger.info("shutdown_sequence_started")
    
    # 1. Stop Resource Monitor
    await resource_monitor.stop()

    # 2. Stop Tier Scheduler
    await tier_scheduler.stop()

    # 2. Stop Download Worker
    await download_manager.stop_worker()
    
    # 2. Stop Control Bot
    await control_bot.stop()
    
    # 2. Disconnect Telegram
    await tg_session.disconnect()
    
    # 2. Release singleton lock
    singleton.release()
    
    logger.info("shutdown_complete")
    
    # Stop the loop
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [t.cancel() for t in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)
    asyncio.get_event_loop().stop()

def validate_environment():
    """Perform boot-time sanity checks."""
    logger.info("boot_validation_started", version="0.1.0")
    
    required_dirs = [
        settings.archive_root,
        settings.log_dir,
        settings.session_dir,
        settings.download_tmp_dir,
        Path(settings.database_url.replace("sqlite:///", "")).parent
    ]
    
    for d in required_dirs:
        d.mkdir(parents=True, exist_ok=True)
        # Verify writeability
        test_file = d / ".boot_test"
        try:
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            logger.error("directory_not_writable", path=str(d), error=str(e))
            sys.exit(1)

    logger.info("boot_validation_complete", status="success")

async def main():
    # 1. Acquire singleton lock
    singleton.acquire()
    
    # 2. Setup signal handlers (POSIX only)
    if os.name != 'nt':
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))
            except NotImplementedError:
                # Fallback for some environments
                pass
    else:
        # On Windows, we'll rely on KeyboardInterrupt for local development
        logger.info("windows_signal_handling_limited")

    try:
        # 3. Environment validation
        validate_environment()
        
        # 4. Startup Jitter
        delay = random.uniform(settings.startup_delay_min, settings.startup_delay_max)
        logger.info("startup_jitter_applied", seconds=round(delay, 2))
        await asyncio.sleep(delay)

        # 5. Connect Telegram
        if not await tg_session.connect():
            # If not authorized, start interactive login
            # NOTE: In Phase 1, we expect the user to handle this manually 
            # if running for the first time.
            logger.info("telegram_interactive_login_required")
            if not await tg_session.login():
                logger.error("telegram_authentication_failed")
                await shutdown()
                return

        # 6. Start Control Bot
        await control_bot.start()
        
        # 7. Start Download Worker
        await download_manager.start_worker()
        
        # 8. Start Tier Scheduler
        await tier_scheduler.start()
        
        # 9. Start Resource Monitor
        await resource_monitor.start()

        logger.info("downline_appliance_online")

        # 11. Maintenance Loop (Phase 1: Just keep session alive)
        while True:
            # Check session health every 5 minutes
            await asyncio.sleep(300)
            if not await tg_session.validate_session():
                logger.warning("telegram_session_lost_reconnecting")
                await tg_session.connect()

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("unhandled_runtime_exception", error=str(e))
        await shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
