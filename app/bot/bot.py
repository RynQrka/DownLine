from telegram.ext import ApplicationBuilder, CommandHandler
from app.core.config import settings
from app.core.logger import logger
from .handlers import (
    start_command, help_command, download_command, 
    list_command, remove_command, status_command,
    pause_command, resume_command, poll_command
)

class ControlBot:
    """Manages the lifecycle of the Telegram Control Bot."""

    def __init__(self):
        self.application = (
            ApplicationBuilder()
            .token(settings.telegram_bot_token)
            .build()
        )
        self._setup_handlers()

    def _setup_handlers(self):
        self.application.add_handler(CommandHandler("start", start_command))
        self.application.add_handler(CommandHandler("help", help_command))
        self.application.add_handler(CommandHandler("download", download_command))
        self.application.add_handler(CommandHandler("list", list_command))
        self.application.add_handler(CommandHandler("remove", remove_command))
        self.application.add_handler(CommandHandler("status", status_command))
        self.application.add_handler(CommandHandler("pause", pause_command))
        self.application.add_handler(CommandHandler("resume", resume_command))
        self.application.add_handler(CommandHandler("poll", poll_command))

    async def start(self):
        """Starts the bot in polling mode."""
        logger.info("control_bot_starting")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

    async def stop(self):
        """Stops the bot."""
        logger.info("control_bot_stopping")
        if self.application.updater and self.application.updater.running:
            await self.application.updater.stop()
        
        if self.application.running:
            await self.application.stop()
            await self.application.shutdown()

# Global bot instance
control_bot = ControlBot()
