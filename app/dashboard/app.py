from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import shutil
import psutil
import time
from pathlib import Path
from datetime import datetime, timezone
from app.core.config import settings
from app.core.db import db
from app.core.logger import logger

app = FastAPI(
    title="DownLine Dashboard",
    docs_url=None,
    redoc_url=None,
)

# Template configuration
templates = Jinja2Templates(directory="app/dashboard/templates")

def get_system_stats():
    """Fetch real-time system metrics."""
    cpu_percent = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    disk = shutil.disk_usage(settings.archive_root)
    
    return {
        "cpu": cpu_percent,
        "ram": memory.percent,
        "disk": round((disk.used / disk.total) * 100, 1),
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "uptime": round(time.time() - psutil.boot_time(), 0)
    }

def get_dashboard_data():
    """Collect all metrics for the dashboard."""
    # 1. Fetch Channels
    channels = db.fetch_all("""
        SELECT c.*, s.tier, s.cooldown_until, s.last_polled_at
        FROM channels c
        LEFT JOIN scheduler_state s ON c.id = s.channel_id
        ORDER BY c.added_at DESC
    """)
    
    # 2. Queue Summary
    queue_counts = db.fetch_all("SELECT status, COUNT(*) as count FROM queue GROUP BY status")
    queue_summary = {row['status']: row['count'] for row in queue_counts}
    
    # 3. Storage Breakdown
    storage_stats = db.fetch_all("""
        SELECT file_type, COUNT(*) as count, SUM(file_size_bytes) as total_size 
        FROM media WHERE status = 'complete' GROUP BY file_type
    """)
    
    # 4. Active Downloads
    active_downloads = db.fetch_all("""
        SELECT q.*, m.file_type, m.file_size_bytes, c.display_name 
        FROM queue q 
        JOIN media m ON q.media_id = m.media_id
        JOIN channels c ON m.channel_id = c.id
        WHERE q.status = 'downloading' OR q.status = 'active'
    """)

    # 5. Pending Queue (Detailed)
    pending_queue = db.fetch_all("""
        SELECT q.*, m.file_type, c.display_name 
        FROM queue q 
        JOIN media m ON q.media_id = m.media_id
        JOIN channels c ON m.channel_id = c.id
        WHERE q.status = 'pending'
        ORDER BY q.priority DESC, q.enqueued_at ASC
        LIMIT 10
    """)

    # 6. Global State
    paused_row = db.fetch_one("SELECT value FROM global_state WHERE key = 'paused'")
    is_paused = paused_row['value'] == '1' if paused_row else False

    # 7. Recent Activity (History)
    recent_media = db.fetch_all("""
        SELECT m.*, c.display_name 
        FROM media m
        JOIN channels c ON m.channel_id = c.id
        WHERE m.status = 'complete'
        ORDER BY m.downloaded_at DESC LIMIT 10
    """)

    return {
        "channels": [dict(c) for c in channels],
        "queue": queue_summary,
        "storage": [dict(s) for s in storage_stats],
        "active": [dict(a) for a in active_downloads],
        "pending": [dict(p) for p in pending_queue],
        "is_paused": is_paused,
        "recent": [dict(r) for r in recent_media],
        "system": get_system_stats(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/", response_class=HTMLResponse)
@app.get("/downline/dashboard", response_class=HTMLResponse)
async def dashboard_index(request: Request):
    data = get_dashboard_data()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=data
    )

@app.get("/api/stats")
@app.get("/downline/dashboard/api/stats")
async def dashboard_api():
    """Live JSON endpoint for the frontend."""
    return JSONResponse(get_dashboard_data())

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)

@app.get("/health")
@app.get("/downline/dashboard/health")
async def health_check():
    """Returns system health status."""
    _, _, free = shutil.disk_usage(settings.archive_root)
    free_gb = free / (1024**3)
    
    db_ok = False
    try:
        db.fetch_one("SELECT 1")
        db_ok = True
    except:
        pass

    return JSONResponse({
        "status": "ok" if db_ok and free_gb > settings.disk_min_free_gb else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "disk_free_gb": round(free_gb, 2)
    })

class DashboardServer:
    def __init__(self):
        self.config = uvicorn.Config(
            app, 
            host=settings.dashboard_host, 
            port=settings.dashboard_port, 
            log_level="info",
            proxy_headers=True,
            forwarded_allow_ips="*"
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
