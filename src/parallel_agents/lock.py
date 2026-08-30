import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional

# Platform-specific locking primitives
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


class FileLockError(Exception):
    """Raised when acquiring a file lock fails or times out."""
    pass


class StateLock:
    """Provides a cross-platform re-entrant file lock around state operations."""

    # Thread-local storage for re-entrancy within the same process thread
    _tls = threading.local()

    def __init__(self, lock_dir: Path, lock_name: str = ".lock", timeout_seconds: float = 10.0):
        self.lock_file = lock_dir / lock_name
        self.timeout_seconds = timeout_seconds

    def acquire(self) -> None:
        if not hasattr(self._tls, "depth_map"):
            self._tls.depth_map = {}
        if not hasattr(self._tls, "fd_map"):
            self._tls.fd_map = {}

        lock_key = str(self.lock_file.resolve())
        depth = self._tls.depth_map.get(lock_key, 0)

        # Re-entrant: already holding lock in this thread/process
        if depth > 0:
            self._tls.depth_map[lock_key] = depth + 1
            return

        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        start_time = time.time()

        while True:
            fd = None
            try:
                fd = os.open(str(self.lock_file), os.O_CREAT | os.O_RDWR)
                if sys.platform == "win32":
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                self._tls.fd_map[lock_key] = fd
                self._tls.depth_map[lock_key] = 1
                return
            except (IOError, OSError):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                if (time.time() - start_time) > self.timeout_seconds:
                    raise FileLockError(
                        f"Timeout ({self.timeout_seconds}s) waiting to acquire lock on {self.lock_file}"
                    )
                time.sleep(0.05)

    def release(self) -> None:
        if not hasattr(self._tls, "depth_map") or not hasattr(self._tls, "fd_map"):
            return

        lock_key = str(self.lock_file.resolve())
        depth = self._tls.depth_map.get(lock_key, 0)

        if depth > 1:
            self._tls.depth_map[lock_key] = depth - 1
            return

        fd = self._tls.fd_map.get(lock_key)
        if fd is not None:
            try:
                if sys.platform == "win32":
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except (IOError, OSError):
                pass
            finally:
                try:
                    os.close(fd)
                except OSError:
                    pass
                self._tls.fd_map[lock_key] = None
                self._tls.depth_map[lock_key] = 0

    def __enter__(self) -> "StateLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
