import asyncio
import os
import shutil
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from telethon import errors
from app.core.config import settings
from app.core.logger import logger, download_logger
from app.core.db import db
from app.core.telegram import tg_session
from app.core.utils import sanitize_name

class DownloadManager:
    """Manages the sequential, serialized download worker."""

    def __init__(self):
        self.worker_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start_worker(self):
        """Starts the background download worker."""
        logger.info("download_worker_starting")
        self._stop_event.clear()
        
        # Reset orphan active items
        self._recover_orphans()
        
        self.worker_task = asyncio.create_task(self._worker_loop())

    async def stop_worker(self):
        """Stops the background download worker."""
        logger.info("download_worker_stopping")
        self._stop_event.set()
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

    def _recover_orphans(self):
        """Resets stuck 'active' items to 'pending'."""
        with db.get_connection() as conn:
            conn.execute("UPDATE queue SET status = 'pending' WHERE status = 'active'")
            conn.execute("UPDATE media SET status = 'pending' WHERE status = 'downloading'")
            conn.commit()
            logger.info("recovered_orphan_downloads")

    async def _worker_loop(self):
        """Main serialized download loop."""
        while not self._stop_event.is_set():
            try:
                # 1. Check if paused
                if self._is_paused():
                    await asyncio.sleep(10)
                    continue

                # 2. Dequeue next item
                item = self._get_next_item()
                if not item:
                    # Nothing to do, sleep and check again
                    await asyncio.sleep(30)
                    continue

                # 3. Process download
                success = await self._process_item(item)
                
                if success:
                    # 4. Human-like delay after success
                    # Phase 8: Heavy activity slowdown
                    base_delay = random.uniform(settings.min_download_delay, settings.max_download_delay)
                    
                    if self._is_heavy_activity():
                        multiplier = random.uniform(1.5, 2.0)
                        base_delay *= multiplier
                        logger.info("heavy_activity_slowdown_applied", multiplier=round(multiplier, 2))
                    
                    logger.info("inter_download_delay", seconds=round(base_delay, 2))
                    await asyncio.sleep(base_delay)
                else:
                    # Failure delay (short jittered)
                    await asyncio.sleep(random.uniform(5, 15))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("worker_loop_error", error=str(e))
                await asyncio.sleep(60)

    def _is_paused(self) -> bool:
        row = db.fetch_one("SELECT value FROM global_state WHERE key = 'paused'")
        return row and row['value'] == '1'

    def _is_heavy_activity(self) -> bool:
        """
        Phase 8: Check if more than 10 downloads happened in the last 60 mins.
        """
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        row = db.fetch_one("""
            SELECT COUNT(*) as count FROM media 
            WHERE status = 'complete' AND downloaded_at > ?
        """, (one_hour_ago,))
        return row and row['count'] > 10

    def _get_next_item(self):
        """Gets the highest priority pending item from queue."""
        return db.fetch_one("""
            SELECT q.*, m.channel_id, m.message_id, m.file_type, c.username_or_link, c.display_name
            FROM queue q
            JOIN media m ON q.media_id = m.media_id
            JOIN channels c ON m.channel_id = c.id
            WHERE q.status = 'pending' AND c.is_active = 1
            ORDER BY q.priority DESC, q.enqueued_at ASC
            LIMIT 1
        """)

    async def _process_item(self, item) -> bool:
        media_id = item['media_id']
        channel_name = sanitize_name(item['display_name'])
        file_type = item['file_type'] # images/videos/gifs
        
        # Ensure correct folder name based on type
        folder_type = "images" if file_type == "image" else f"{file_type}s"
        
        temp_path = settings.download_tmp_dir / f"{media_id}.part"
        final_dir = settings.archive_root / channel_name / folder_type
        final_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Mark Active
            db.execute("UPDATE queue SET status = 'active', last_attempt_at = ? WHERE id = ?", 
                       (datetime.now(timezone.utc).isoformat(), item['id']))
            db.execute("UPDATE media SET status = 'downloading' WHERE media_id = ?", (media_id,))
            
            logger.info("download_started", media_id=media_id, channel=channel_name)

            # 2. Download via Telethon
            # We need to get the message entity first
            message = await tg_session.client.get_messages(item['username_or_link'], ids=item['message_id'])
            
            if not message or not message.media:
                logger.error("message_not_found_or_no_media", media_id=media_id)
                self._mark_failed(item['id'], media_id, "Message or media not found")
                return False

            # Actual download
            await tg_session.client.download_media(message, file=str(temp_path))
            
            # 3. Integrity Verification
            if not temp_path.exists() or temp_path.stat().st_size == 0:
                raise Exception("Downloaded file is empty or missing")

            # 4. Atomic Promotion
            # Determine filename: mediaid_sanitizedname.ext
            original_name = getattr(message.file, 'name', None) or f"media_{message.id}"
            clean_name = sanitize_name(original_name)
            ext = getattr(message.file, 'ext', '.bin')
            final_filename = f"{media_id}_{clean_name}{ext}"
            final_path = final_dir / final_filename

            shutil.move(str(temp_path), str(final_path))
            
            # 5. Mark Complete
            now = datetime.now(timezone.utc).isoformat()
            db.execute("""
                UPDATE media SET status = 'complete', downloaded_at = ?, local_path = ? 
                WHERE media_id = ?
            """, (now, str(final_path), media_id))
            db.execute("UPDATE queue SET status = 'done' WHERE id = ?", (item['id'],))
            
            download_logger.info("download_complete", media_id=media_id, path=str(final_path))
            return True

        except errors.FloodWaitError as e:
            logger.warning("telegram_flood_wait", seconds=e.seconds)
            # Re-queue immediately, loop will sleep
            db.execute("UPDATE queue SET status = 'pending' WHERE id = ?", (item['id'],))
            await asyncio.sleep(e.seconds + random.uniform(2, 5))
            return False
            
        except Exception as e:
            logger.error("download_failed", media_id=media_id, error=str(e))
            self._handle_failure(item, str(e))
            if temp_path.exists():
                temp_path.unlink()
            return False

    def _handle_failure(self, item, error_msg: str):
        retries = item['retry_count'] + 1
        if retries >= 3:
            self._mark_failed(item['id'], item['media_id'], f"Max retries reached. Last error: {error_msg}")
        else:
            db.execute("""
                UPDATE queue SET status = 'pending', retry_count = ?, last_error = ? 
                WHERE id = ?
            """, (retries, error_msg, item['id']))

    def _mark_failed(self, queue_id: int, media_id: str, error_msg: str):
        db.execute("UPDATE queue SET status = 'failed', last_error = ? WHERE id = ?", (error_msg, queue_id))
        db.execute("UPDATE media SET status = 'failed' WHERE media_id = ?", (media_id,))
        logger.error("download_marked_permanent_failure", media_id=media_id, error=error_msg)

# Global manager instance
download_manager = DownloadManager()
