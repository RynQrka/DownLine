import re
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes
from app.core.config import settings
from app.core.logger import logger
from app.core.db import db
from app.core.telegram import tg_session

def authorized_only(func):
    """Decorator to restrict bot commands to the ALLOWED_CHAT_ID."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or update.effective_chat.id != settings.allowed_chat_id:
            # Silent ignore as per spec
            return
        return await func(update, context)
    return wrapper

@authorized_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("DownLine Archival Appliance Online.\nUse /help for commands.")

@authorized_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Commands:\n"
        "/download <username_or_link> - One-time media download\n"
        "/poll <username_or_link> - Register for periodic downloads\n"
        "/remove <username_or_link> - Unregister a channel\n"
        "/status - Show appliance status\n"
        "/pause - Pause downloads\n"
        "/resume - Resume downloads\n"
        "/poll <username_or_link> - Force immediate poll"
    )
    await update.message.reply_text(help_text)

@authorized_only
async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /download <username_or_link>")
        return

    channel_input = context.args[0]
    
    # 1. Check if already exists
    existing = db.fetch_one("SELECT id, is_periodic FROM channels WHERE username_or_link = ?", (channel_input,))
    if existing:
        await update.message.reply_text(f"Channel {channel_input} is already registered.")
        return

    # 2. Validate accessibility via Telethon
    try:
        entity = await tg_session.client.get_entity(channel_input)
        display_name = getattr(entity, 'title', channel_input)
        
        # 3. Add to DB as One-Time (is_periodic=0)
        db.execute(
            "INSERT INTO channels (username_or_link, display_name, added_at, is_periodic) VALUES (?, ?, ?, 0)",
            (channel_input, display_name, datetime.now(timezone.utc).isoformat())
        )
        
        # 4. Initialize scheduler state
        row = db.fetch_one("SELECT id FROM channels WHERE username_or_link = ?", (channel_input,))
        db.execute(
            "INSERT INTO scheduler_state (channel_id, tier, cooldown_until) VALUES (?, ?, ?)",
            (row['id'], 1, datetime.now(timezone.utc).isoformat())
        )
        
        await update.message.reply_text(f"Starting one-time download for: {display_name}...")
        logger.info("channel_one_time_download_started", channel=channel_input)
        
        # 5. Immediate Poll
        from app.core.discovery import discovery_engine
        new_count = await discovery_engine.poll_channel(row['id'], channel_input)
        await update.message.reply_text(f"Download discovery complete. Enqueued {new_count} items.")
    except Exception as e:
        logger.error("channel_download_failed", channel=channel_input, error=str(e))
        await update.message.reply_text(f"Failed to start download: {str(e)}")

@authorized_only
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = db.fetch_all("""
        SELECT c.username_or_link, c.display_name, s.tier, c.is_active 
        FROM channels c
        JOIN scheduler_state s ON c.id = s.channel_id
    """)
    
    if not channels:
        await update.message.reply_text("No channels registered.")
        return

    report = "Registered Channels:\n"
    for c in channels:
        status = "✅" if c['is_active'] else "❌"
        mode = "🔄" if c['is_periodic'] else "📥"
        report += f"{status} {mode} {c['display_name']} (Tier {c['tier']}) - {c['username_or_link']}\n"
    
    await update.message.reply_text(report)

@authorized_only
async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /remove <username_or_link>")
        return

    channel_input = context.args[0]
    db.execute("UPDATE channels SET is_active = 0 WHERE username_or_link = ?", (channel_input,))
    await update.message.reply_text(f"Deactivated: {channel_input}")

@authorized_only
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Queue stats
    queue_stats = db.fetch_all("SELECT status, COUNT(*) as count FROM queue GROUP BY status")
    stats_text = "Queue Status:\n"
    for row in queue_stats:
        stats_text += f"- {row['status'].capitalize()}: {row['count']}\n"
    
    # Active download (dummy for now)
    stats_text += "\nActive Download: None"
    
    await update.message.reply_text(stats_text)

@authorized_only
async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.execute("INSERT OR REPLACE INTO global_state (key, value) VALUES ('paused', '1')")
    await update.message.reply_text("System Paused. Downloads will stop after the current item.")
    logger.info("system_paused")

@authorized_only
async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.execute("INSERT OR REPLACE INTO global_state (key, value) VALUES ('paused', '0')")
    await update.message.reply_text("System Resumed.")
    logger.info("system_resumed")

@authorized_only
async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /poll <username_or_link>")
        return
    
    channel_input = context.args[0]
    channel = db.fetch_one("SELECT id, display_name FROM channels WHERE username_or_link = ?", (channel_input,))
    
    if not channel:
        # Register as periodic
        try:
            entity = await tg_session.client.get_entity(channel_input)
            display_name = getattr(entity, 'title', channel_input)
            db.execute(
                "INSERT INTO channels (username_or_link, display_name, added_at, is_periodic) VALUES (?, ?, ?, 1)",
                (channel_input, display_name, datetime.now(timezone.utc).isoformat())
            )
            row = db.fetch_one("SELECT id FROM channels WHERE username_or_link = ?", (channel_input,))
            db.execute(
                "INSERT INTO scheduler_state (channel_id, tier, cooldown_until) VALUES (?, ?, ?)",
                (row['id'], 1, datetime.now(timezone.utc).isoformat())
            )
            channel = row
            await update.message.reply_text(f"Registered {display_name} for periodic updates.")
        except Exception as e:
            await update.message.reply_text(f"Failed to register channel: {str(e)}")
            return
    else:
        # Ensure it's periodic
        db.execute("UPDATE channels SET is_periodic = 1 WHERE id = ?", (channel['id'],))
    
    await update.message.reply_text(f"Triggering poll for {channel_input}...")
    from app.core.discovery import discovery_engine
    new_count = await discovery_engine.poll_channel(channel['id'], channel_input)
    await update.message.reply_text(f"Poll complete. Found {new_count} new items.")
