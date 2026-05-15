import asyncio
import random
from datetime import datetime, timezone, timedelta
from app.core.config import settings
from app.core.logger import logger
from app.core.db import db
from app.core.discovery import discovery_engine

class TierScheduler:
    """Manages adaptive polling tiers and cooldowns."""

    def __init__(self):
        self.worker_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self):
        """Starts the scheduler loop."""
        logger.info("tier_scheduler_starting")
        self._stop_event.clear()
        self.worker_task = asyncio.create_task(self._loop())

    async def stop(self):
        """Stops the scheduler loop."""
        logger.info("tier_scheduler_stopping")
        self._stop_event.set()
        if self.worker_task:
            self.worker_task.cancel()

    async def _loop(self):
        """Main scheduler loop."""
        while not self._stop_event.is_set():
            try:
                # 1. Get channels due for polling
                due_channels = self._get_due_channels()
                
                for channel in due_channels:
                    # 2. Poll the channel
                    new_items = await discovery_engine.poll_channel(
                        channel['channel_id'], 
                        channel['username_or_link']
                    )
                    
                    # 3. Update tier transitions and cooldowns
                    self._update_scheduler_state(channel, new_items)
                    
                    # Small randomized gap between polling different channels
                    await asyncio.sleep(random.uniform(30, 90))

                # 4. Long sleep if nothing is due
                if not due_channels:
                    await asyncio.sleep(300) # Check every 5 mins

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_loop_error", error=str(e))
                await asyncio.sleep(60)

    def _get_due_channels(self):
        """Fetches active channels where cooldown has expired."""
        now = datetime.now(timezone.utc).isoformat()
        return db.fetch_all("""
            SELECT s.*, c.username_or_link
            FROM scheduler_state s
            JOIN channels c ON s.channel_id = c.id
            WHERE c.is_active = 1 AND c.is_periodic = 1
            AND (s.cooldown_until IS NULL OR s.cooldown_until <= ?)
            ORDER BY s.tier ASC, s.cooldown_until ASC
        """, (now,))

    def _update_scheduler_state(self, state, new_items: int):
        """Handles tier transitions and calculates next cooldown."""
        current_tier = state['tier']
        empty_streak = state['empty_poll_streak']
        active_streak = state['active_poll_streak']
        
        # Determine streaks
        if new_items == 0:
            empty_streak += 1
            active_streak = 0
        elif new_items >= 8: # Active poll threshold
            active_streak += 1
            empty_streak = 0
        else:
            active_streak = 0
            empty_streak = 0

        # Tier Transitions
        new_tier = current_tier
        
        if current_tier == 1 and empty_streak >= 5:
            new_tier = 2
            empty_streak = 0
            logger.info("tier_demoted", channel=state['username_or_link'], from_tier=1, to_tier=2)
        elif current_tier == 2:
            if empty_streak >= 3:
                new_tier = 3
                empty_streak = 0
                logger.info("tier_demoted", channel=state['username_or_link'], from_tier=2, to_tier=3)
            elif active_streak >= 10:
                new_tier = 1
                active_streak = 0
                logger.info("tier_promoted", channel=state['username_or_link'], from_tier=2, to_tier=1)
        elif current_tier == 3 and active_streak >= 5:
            new_tier = 2
            active_streak = 0
            logger.info("tier_promoted", channel=state['username_or_link'], from_tier=3, to_tier=2)

        # Calculate Cooldown
        intervals = {1: settings.tier_1_interval, 2: settings.tier_2_interval, 3: settings.tier_3_interval}
        interval_hours = intervals.get(new_tier, 2)
        
        # Add Jitter (±10%, max 15 mins) as per Phase 8 early implementation
        jitter_mins = (interval_hours * 60) * 0.10
        jitter_mins = min(jitter_mins, 15)
        offset = random.uniform(-jitter_mins, jitter_mins)
        
        next_poll = datetime.now(timezone.utc) + timedelta(hours=interval_hours, minutes=offset)
        
        db.execute("""
            UPDATE scheduler_state SET 
                tier = ?, 
                empty_poll_streak = ?, 
                active_poll_streak = ?, 
                cooldown_until = ?,
                last_polled_at = ?
            WHERE channel_id = ?
        """, (new_tier, empty_streak, active_streak, next_poll.isoformat(), 
              datetime.now(timezone.utc).isoformat(), state['channel_id']))

# Global scheduler instance
tier_scheduler = TierScheduler()
