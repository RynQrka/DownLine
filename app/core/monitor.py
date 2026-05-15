import asyncio
import shutil
import psutil
from app.core.config import settings
from app.core.logger import logger
from app.core.db import db
from app.core.telegram import tg_session

class ResourceMonitor:
    """Monitors system resources and logs warnings/alerts."""

    def __init__(self):
        self.worker_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self):
        logger.info("resource_monitor_starting")
        self._stop_event.clear()
        self.worker_task = asyncio.create_task(self._loop())

    async def stop(self):
        logger.info("resource_monitor_stopping")
        self._stop_event.set()
        if self.worker_task:
            self.worker_task.cancel()

    async def _loop(self):
        while not self._stop_event.is_set():
            try:
                self._check_disk_space()
                self._check_ram_usage()
                self._check_temp_bloat()
                
                # Check every 5 minutes
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("monitor_loop_error", error=str(e))
                await asyncio.sleep(60)

    def _check_disk_space(self):
        total, used, free = shutil.disk_usage(settings.archive_root)
        free_gb = free / (1024**3)
        
        if free_gb < settings.disk_min_free_gb:
            logger.warning("low_disk_space_alert", free_gb=round(free_gb, 2))
            # In Phase 12, we could send a Telegram alert here.
        
    def _check_ram_usage(self):
        process = psutil.Process()
        ram_mb = process.memory_info().rss / (1024 * 1024)
        
        if ram_mb > settings.max_ram_mb:
            logger.warning("high_ram_usage_alert", ram_mb=round(ram_mb, 2))

    def _check_temp_bloat(self):
        temp_dir = settings.download_tmp_dir
        total_size = sum(f.stat().st_size for f in temp_dir.glob('**/*') if f.is_file())
        size_gb = total_size / (1024**3)
        
        if size_gb > settings.max_tmp_size_gb:
            logger.warning("temp_directory_bloat_alert", size_gb=round(size_gb, 2))

# Global monitor instance
resource_monitor = ResourceMonitor()
