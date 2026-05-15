import os
import sys
from pathlib import Path
from app.core.config import settings
from app.core.logger import logger

class SingletonLock:
    """Enforces that only one instance of the appliance runs at a time."""
    
    def __init__(self):
        self.lock_file = settings.session_dir / "downline.lock"
        self.is_locked = False

    def acquire(self):
        """Attempts to acquire the lock file."""
        if self.lock_file.exists():
            # Check if the process is actually running (very basic check)
            # In a container environment, this is often enough as the PID 
            # won't exist if the container restarted.
            try:
                with open(self.lock_file, "r") as f:
                    old_pid = int(f.read().strip())
                
                # Check if old_pid is still running
                # (This is OS specific, but we'll try a generic approach)
                if self._is_pid_running(old_pid):
                    logger.error("instance_already_running", pid=old_pid)
                    sys.exit(1)
                else:
                    logger.warning("found_stale_lock", pid=old_pid)
                    self.lock_file.unlink()
            except Exception:
                # If we can't read it or it's malformed, treat it as stale
                self.lock_file.unlink()

        try:
            with open(self.lock_file, "w") as f:
                f.write(str(os.getpid()))
            self.is_locked = True
            logger.info("singleton_lock_acquired", pid=os.getpid())
        except Exception as e:
            logger.error("failed_to_acquire_lock", error=str(e))
            sys.exit(1)

    def release(self):
        """Releases the lock file."""
        if self.is_locked and self.lock_file.exists():
            self.lock_file.unlink()
            self.is_locked = False
            logger.info("singleton_lock_released")

    def _is_pid_running(self, pid: int) -> bool:
        """Check if a process ID is running."""
        if os.name == 'nt':
            # Windows implementation
            try:
                import ctypes
                PROCESS_QUERY_INFORMATION = 0x0400
                handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    return True
                return False
            except Exception:
                return True # Err on side of caution
        else:
            # POSIX implementation
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            else:
                return True

# Global lock instance
singleton = SingletonLock()
