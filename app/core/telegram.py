import asyncio
from telethon import TelegramClient, events, errors
from app.core.config import settings
from app.core.logger import logger
from pathlib import Path

class TelegramSession:
    """Manages the Telethon user session lifecycle."""
    
    def __init__(self):
        self.session_path = settings.session_dir / "user_session"
        self.client: TelegramClient = TelegramClient(
            str(self.session_path),
            settings.telegram_api_id,
            settings.telegram_api_hash,
            device_model="DownLine Archival Appliance",
            system_version="Linux/Docker",
            app_version="0.1.0",
            connection_retries=None, # We handle retries manually for better control
            auto_reconnect=True
        )
        self.is_connected = False

    async def connect(self):
        """Connects to Telegram and validates the session."""
        try:
            logger.info("telegram_connecting", session=str(self.session_path))
            await self.client.connect()
            self.is_connected = True
            
            if not await self.client.is_user_authorized():
                logger.warning("telegram_session_unauthorized")
                return False
                
            me = await self.client.get_me()
            logger.info("telegram_connected", user=me.username, id=me.id)
            return True
        except Exception as e:
            logger.error("telegram_connection_failed", error=str(e))
            self.is_connected = False
            return False

    async def login(self):
        """Performs interactive login flow if needed."""
        if await self.client.is_user_authorized():
            return True

        phone = settings.telegram_phone
        if not phone:
            logger.error("telegram_login_missing_phone", 
                         message="TELEGRAM_PHONE is required for interactive login.")
            return False

        logger.info("telegram_login_started", phone=phone)
        
        # This will be handled in Phase 1 via command line interaction
        # In a real daemon, we'd wait for a signal or use a persistent login script
        try:
            await self.client.start(phone=phone)
            logger.info("telegram_login_success")
            return True
        except EOFError:
            logger.error("telegram_login_headless_error", 
                         message="Cannot perform interactive login in a non-interactive terminal (Docker). "
                                 "Please run the appliance locally once to generate the session file.")
            return False
        except Exception as e:
            logger.error("telegram_login_failed", error=str(e))
            return False

    async def disconnect(self):
        """Gracefully disconnects the client."""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            logger.info("telegram_disconnected")

    async def validate_session(self):
        """Ensures the session is still active and working."""
        try:
            if not self.client.is_connected():
                await self.client.connect()
            
            return await self.client.is_user_authorized()
        except Exception:
            return False

# Global session instance
tg_session = TelegramSession()
