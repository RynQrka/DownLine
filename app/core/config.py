import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # --- Telegram Credentials ---
    telegram_api_id: int = Field(..., env="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(..., env="TELEGRAM_API_HASH")
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    telegram_phone: Optional[str] = Field(None, env="TELEGRAM_PHONE")

    # --- Control Bot Settings ---
    allowed_chat_id: int = Field(..., env="ALLOWED_CHAT_ID")

    # --- Storage & Paths ---
    archive_root: Path = Field(Path("./app/archive"), env="ARCHIVE_ROOT")
    database_url: str = Field("sqlite:///app/database/downline.db", env="DATABASE_URL")
    log_dir: Path = Field(Path("./app/logs"), env="LOG_DIR")
    session_dir: Path = Field(Path("./app/sessions"), env="SESSION_DIR")
    download_tmp_dir: Path = Field(Path("./app/downloads/tmp"), env="DOWNLOAD_TMP_DIR")

    # --- Operational Pacing ---
    min_download_delay: int = 18
    max_download_delay: int = 69
    startup_delay_min: int = 5
    startup_delay_max: int = 30

    # --- Scheduler Tiers (Intervals in hours) ---
    tier_1_interval: int = 2
    tier_2_interval: int = 5
    tier_3_interval: int = 12

    # --- Resource Limits ---
    disk_min_free_gb: int = 1
    max_ram_mb: int = 500
    max_tmp_size_gb: int = 2

    # --- Dashboard ---
    dashboard_port: int = 8000
    dashboard_host: str = "0.0.0.0"

    @field_validator("archive_root", "log_dir", "session_dir", "download_tmp_dir", mode="before")
    @classmethod
    def ensure_dir_exists(cls, v: str) -> Path:
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path

# Global settings instance
settings = Settings()
