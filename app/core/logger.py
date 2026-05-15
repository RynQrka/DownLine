import logging
import logging.handlers
import os
import sys
import structlog
from datetime import datetime, timezone
from pathlib import Path
from .config import settings

def timestamper(_, __, event_dict):
    """Ensure all logs use UTC ISO-8601 timestamps."""
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    return event_dict

def setup_logging():
    # Ensure log directory exists
    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # --- Standard Logging Configuration ---
    # We define handlers for different log files
    
    # 1. General Operation Log
    general_handler = logging.handlers.RotatingFileHandler(
        log_dir / "operation.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    
    # 2. Error Log
    error_handler = logging.handlers.RotatingFileHandler(
        log_dir / "error.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    
    # 3. Download Log
    download_handler = logging.handlers.RotatingFileHandler(
        log_dir / "downloads.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )

    # Stream handler for console
    console_handler = logging.StreamHandler(sys.stdout)

    # Base logging config
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[general_handler, error_handler, console_handler]
    )

    # --- Structlog Configuration ---
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer() if os.getenv("LOG_FORMAT") == "json" else structlog.processors.KeyValueRenderer(
                key_order=["timestamp", "level", "event", "logger"]
            ),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

# Initialize logging on import
setup_logging()

# Export specific loggers
logger = structlog.get_logger("downline")
download_logger = structlog.get_logger("downline.downloads")

# Add a specific filter/handler for the download logger if needed
# For now, standard logger handles it via child name
