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
    """Cross-platform re-entrant lock combining an in-process RLock and an OS file lock.

    The file lock serialises across processes; the RLock serialises across threads within
    one process (an OS file lock is held per-process, so threads would otherwise pass
    straight through each other's locks).

    The RLock is scoped **per lock file**, not per class. A single shared RLock would make
    every independent lock in the process serialise against every other one — two lock
    files in different directories, or the state lock and the git lock, would block each
    other for no reason.
    """

    # Per-lock-file re-entrant locks, created on demand.
    _rlocks: dict = {}
    _registry_guard = threading.Lock()
    # Thread-local storage for OS file descriptor tracking
    _tls = threading.local()

    def __init__(self, lock_dir: Path, lock_name: str = ".lock", timeout_seconds: float = 10.0):
        self.lock_file = lock_dir / lock_name
        self.timeout_seconds = timeout_seconds
        # resolve() needs the parent to exist to be stable across calls.
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self._key = str(self.lock_file.resolve())
        self._process_rlock = self._rlock_for(self._key)

    @classmethod
    def _rlock_for(cls, key: str) -> threading.RLock:
        with cls._registry_guard:
            lock = cls._rlocks.get(key)
            if lock is None:
                lock = threading.RLock()
                cls._rlocks[key] = lock
            return lock

    def acquire(self) -> None:
        self._process_rlock.acquire()
        acquired_file = False
        try:
            if not hasattr(self._tls, "depth_map"):
                self._tls.depth_map = {}
            if not hasattr(self._tls, "fd_map"):
                self._tls.fd_map = {}

            lock_key = self._key
            depth = self._tls.depth_map.get(lock_key, 0)

            # Re-entrant: already holding file lock in this thread
            if depth > 0:
                self._tls.depth_map[lock_key] = depth + 1
                acquired_file = True
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
                    acquired_file = True
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
        finally:
            if not acquired_file:
                self._process_rlock.release()

    def release(self) -> None:
        try:
            if not hasattr(self._tls, "depth_map") or not hasattr(self._tls, "fd_map"):
                return

            lock_key = self._key
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
        finally:
            try:
                self._process_rlock.release()
            except RuntimeError:
                pass

    def __enter__(self) -> "StateLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
