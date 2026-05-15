from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
import shutil
from app.core.config import settings
from app.core.db import db
from app.core.logger import logger

app = FastAPI(title="DownLine Dashboard")
templates = Jinja2Templates(directory="app/dashboard/templates")

@app.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request):
    # 1. Fetch Channels
    channels = db.fetch_all("""
        SELECT c.*, s.tier, s.cooldown_until, s.last_polled_at
        FROM channels c
        JOIN scheduler_state s ON c.id = s.channel_id
    """)
    
    # 2. Queue Summary
    queue_counts = db.fetch_all("SELECT status, COUNT(*) as count FROM queue GROUP BY status")
    queue_summary = {row['status']: row['count'] for row in queue_counts}
    
    # 3. Storage Breakdown
    storage_stats = db.fetch_all("""
        SELECT file_type, COUNT(*) as count, SUM(file_size_bytes) as total_size 
        FROM media WHERE status = 'complete' GROUP BY file_type
    """)
    
    # 4. Recent Failures
    recent_failures = db.fetch_all("""
        SELECT q.*, c.display_name 
        FROM queue q 
        JOIN media m ON q.media_id = m.media_id
        JOIN channels c ON m.channel_id = c.id
        WHERE q.status = 'failed' 
        ORDER BY q.last_attempt_at DESC LIMIT 10
    """)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "channels": channels,
        "queue": queue_summary,
        "storage": storage_stats,
        "failures": recent_failures
    })

@app.get("/health")
async def health_check():
    """Returns system health status."""
    _, _, free = shutil.disk_usage(settings.archive_root)
    free_gb = free / (1024**3)
    
    # Check DB
    db_ok = False
    try:
        db.fetch_one("SELECT 1")
        db_ok = True
    except:
        pass

    return JSONResponse({
        "status": "ok" if db_ok and free_gb > settings.disk_min_free_gb else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "disk_free_gb": round(free_gb, 2),
        "archive_root": str(settings.archive_root)
    })

class DashboardServer:
    def __init__(self):
        self.config = uvicorn.Config(
            app, 
            host=settings.dashboard_host, 
            port=settings.dashboard_port, 
            log_level="error"
        )
        self.server = uvicorn.Server(self.config)

    async def start(self):
        logger.info("dashboard_starting", host=settings.dashboard_host, port=settings.dashboard_port)
        await self.server.serve()

    async def stop(self):
        logger.info("dashboard_stopping")
        self.server.should_exit = True

# Global dashboard instance
dashboard = DashboardServer()
