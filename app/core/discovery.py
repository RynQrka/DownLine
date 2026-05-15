import asyncio
from datetime import datetime, timezone
from telethon import types
from app.core.config import settings
from app.core.logger import logger
from app.core.db import db
from app.core.telegram import tg_session
from app.core.utils import compute_media_id

class DiscoveryEngine:
    """Scans channels for media and enqueues new items."""

    async def poll_channel(self, channel_id: int, username_or_link: str):
        """Polls a single channel for new media."""
        logger.info("discovery_polling_started", channel=username_or_link)
        
        # 1. Get last message ID from DB
        state = db.fetch_one("SELECT last_message_id FROM scheduler_state WHERE channel_id = ?", (channel_id,))
        min_id = state['last_message_id'] or 0
        
        new_media_count = 0
        max_seen_id = min_id

        try:
            # 2. Fetch history
            async for message in tg_session.client.iter_messages(username_or_link, min_id=min_id, reverse=True):
                max_seen_id = max(max_seen_id, message.id)
                
                # 3. Detect media
                media_type = self._get_media_type(message)
                if not media_type:
                    # Log skip if it's not media we care about
                    if message.text and len(message.text) < 50:
                        logger.debug("skipping_non_media_message", msg_id=message.id, text=message.text)
                    continue
                media_id = compute_media_id(channel_id, message.id)
                
                if self._is_already_known(media_id):
                    continue
                
                # 5. Insert into Media and Queue
                self._enqueue_media(channel_id, message, media_id, media_type)
                new_media_count += 1

            # 6. Update scheduler state
            db.execute(
                "UPDATE scheduler_state SET last_message_id = ?, last_polled_at = ? WHERE channel_id = ?",
                (max_seen_id, datetime.now(timezone.utc).isoformat(), channel_id)
            )
            
            logger.info("discovery_polling_complete", channel=username_or_link, new_items=new_media_count)
            return new_media_count

        except Exception as e:
            logger.error("discovery_polling_failed", channel=username_or_link, error=str(e))
            return 0

    def _get_media_type(self, message) -> str:
        """Determines if a message is Photo, Video, or GIF."""
        if not message.media:
            return None
        
        if isinstance(message.media, types.MessageMediaPhoto):
            return "image"
        
        if isinstance(message.media, types.MessageMediaDocument):
            doc = message.media.document
            # 1. Check attributes for Video or GIF
            for attr in getattr(doc, 'attributes', []):
                if isinstance(attr, types.DocumentAttributeVideo):
                    return "video"
                if isinstance(attr, types.DocumentAttributeAnimated):
                    return "gif"
            
            # 2. Check mime_type as fallback
            if doc.mime_type.startswith('video/'):
                return "video"
            if doc.mime_type == 'image/gif':
                return "gif"
        
        return None

    def _is_already_known(self, media_id: str) -> bool:
        """Checks if media_id is already in the database."""
        row = db.fetch_one("SELECT 1 FROM media WHERE media_id = ?", (media_id,))
        return row is not None

    def _enqueue_media(self, channel_id: int, message, media_id: str, media_type: str):
        """Inserts media into DB and enqueues it."""
        file_size = getattr(message.media, 'document', None)
        if file_size:
            file_size = file_size.size
        elif hasattr(message.media, 'photo'):
            # Photo size is tricky in MTProto, we'll leave as null or take largest
            file_size = None 

        now = datetime.now(timezone.utc).isoformat()
        
        # Insert into media
        db.execute(
            """
            INSERT INTO media (
                channel_id, message_id, media_id, file_type, 
                file_size_bytes, status, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (channel_id, message.id, media_id, media_type, file_size, 'pending', now)
        )
        
        # Insert into queue
        db.execute(
            "INSERT INTO queue (media_id, status, enqueued_at) VALUES (?, ?, ?)",
            (media_id, 'pending', now)
        )

# Global discovery instance
discovery_engine = DiscoveryEngine()
