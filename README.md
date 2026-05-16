# DownLine — Telegram Archival Appliance

DownLine is a **self-hosted, long-running Telegram archival appliance** designed for quietly preserving media from Telegram channels over extremely long periods of time. 

It behaves like a NAS appliance or a background daemon—passively watching channels and archiving media locally in a slow, stable, and human-like manner.

---

## 🚀 Primary Goals
- **Account Safety**: Intentionally slow and conservative to protect your Telegram account.
- **Operational Stability**: Single-process, SQLite-centric architecture built for months of unattended uptime.
- **Human-Like Behavior**: Jittered delays and adaptive slowdowns to mimic real user patterns.
- **Immutable Archive**: Once a file is verified and moved to the archive, it is never mutated.

---

## 📁 Production-Ready File Structure
Before spinning up the project, ensure your directory structure looks like this:

```text
DownLine/
├── .env                        # System configuration (Create from .env.example)
├── .env.example                # Template for environment variables
├── .gitignore                  # Git exclusion rules
├── .dockerignore               # Docker build exclusion rules
├── Dockerfile                  # Production container definition
├── docker-compose.yml          # Container orchestration (Create from .example)
├── docker-compose.yml.example  # Template for orchestration
├── pyproject.toml              # Dependency management (uv/pip)
├── README.md                   # Project documentation
└── app/
    ├── main.py                 # System Bootstrapper & Lifecycle Manager
    ├── bot/
    │   ├── bot.py              # Control Bot Manager (PTB)
    │   └── handlers.py         # Bot command logic
    ├── core/
    │   ├── config.py           # Pydantic Settings & Validation
    │   ├── db.py               # SQLite Manager & Migrations
    │   ├── discovery.py        # Channel Discovery Engine
    │   ├── downloader.py       # Sequential Download Manager
    │   ├── lock.py             # Singleton Process Enforcement
    │   ├── logger.py           # Structured UTC Logging
    │   ├── monitor.py          # Resource & Health Monitor
    │   ├── scheduler.py        # Tiered Adaptive Scheduler
    │   ├── telegram.py         # Telethon Session Wrapper
    │   └── utils.py            # Sanitization & Base62 Helpers
    ├── dashboard/
    │   ├── app.py              # FastAPI Backend
    │   └── templates/
    │       └── index.html      # Dashboard UI Template
    ├── database/
    │   └── downline.db         # Authoritative SQLite State Store
    ├── logs/
    │   ├── operations.log      # General system logs
    │   ├── downloads.log       # Dedicated download audit trail
    │   └── errors.log          # Critical error logs
    ├── sessions/
    │   ├── user_session.session # MTProto Session (DOCKER VOLUME MOUNT)
    │   └── downline.lock       # Singleton file lock
    ├── archive/                # Final immutable media storage
    └── downloads/
        └── tmp/                # Atomic promotion staging area
```

---

## 🚦 Essential Setup Instructions (Read Before Starting)

### 1. Interactive Login
Telegram requires an interactive OTP/Code for the first login. Since Docker containers are non-interactive, **you must run the appliance locally once** to generate the session file.
1. Install dependencies: `uv sync`
2. Run locally: `uv run python -m app.main`
3. Enter your phone number and the code received on Telegram.
4. Once you see `downline_appliance_online`, stop the process (`Ctrl+C`).
5. Your session is now saved in `app/sessions/user_session.session`.

### 2. Docker Deployment
After generating the session file, you can deploy via Docker:
```bash
docker compose up -d
```
The appliance will now boot silently using the existing session.

---

## 🎮 Telegram Bot Commands

The appliance is managed via a secure Telegram Bot. All commands from unauthorized users are silently ignored.

| Command | Description | Mode |
| :--- | :--- | :--- |
| `/download <link>` | Performs a **one-time** discovery and download of a channel's media. | 📥 One-Time |
| `/poll <link>` | Registers a channel for **periodic** monitoring and tiered updates. | 🔄 Periodic |
| `/remove <link>` | Deactivates a channel. Polling stops, but history is preserved. | - |
| `/list` | Displays all registered channels and their current status. | - |
| `/status` | Shows live queue depth and active download status. | - |
| `/pause` | Pauses the download worker (current download finishes first). | - |
| `/resume` | Resumes the download worker. | - |
| `/help` | Shows the command reference. | - |

---

## 📊 Dashboard Visibility
The appliance includes a premium, read-only dashboard designed for high-level observability and real-time visualization.
- **URL**: `http://localhost:8000/downline/dashboard` (Default)
- **Aesthetics**: Premium dark theme with real-time "System Pulse" monitoring.
- **Live Updates**: Real-time queue status, active downloads, and system resource tracking (CPU/RAM/Disk) without page refreshes.
- **Read-Only**: Designed purely for observability to ensure operational integrity.

---

## 🛠️ Architecture & Tech Stack
- **Language**: Python 3.12 (Asynchronous)
- **State Store**: SQLite with WAL mode (Production-grade durability)
- **Telegram Engine**: Telethon (MTProto)
- **Control Bot**: python-telegram-bot
- **Dashboard**: FastAPI + Jinja2
- **Process Lock**: Singleton enforcement to prevent session corruption.

---

## 📁 Storage Structure
Media is organized deterministically:
```text
/archive/
  /Channel_Name/
    /images/
    /videos/
    /gifs/
```
Files are renamed to `<media_id>_<sanitized_name>.<ext>` to ensure immutability and prevent collisions.

---

## ⚖️ Engineering Doctrine
- **Boring > Complex**: Single writer, single worker, single process.
- **Safety > Speed**: Serialized downloads only (one at a time).
- **Quiet > Loud**: Humanized jitter on every network interaction.
- **Recovery > Continuity**: Atomic file promotion ensures partial files never enter the archive.
