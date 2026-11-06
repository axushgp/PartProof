import os
import sys
import logging
from typing import Optional

logger = logging.getLogger("partproof.worker.lock")


class HostLockError(Exception):
    """Raised when host worker lock cannot be acquired or manipulated."""
    pass


class HostLock:
    """
    Advisory host file lock ensuring only one PartProof worker process runs on the host.
    Uses fcntl on POSIX systems with msvcrt fallback on Windows.
    """

    def __init__(self, lock_file_path: str):
        self.lock_file_path = lock_file_path
        self._file_obj: Optional[object] = None
        self._is_locked: bool = False

    def acquire(self) -> bool:
        """
        Attempts non-blocking acquisition of the host advisory lock.
        Returns True if acquired, False if already held by another process.
        """
        if self._is_locked:
            return True

        lock_dir = os.path.dirname(os.path.abspath(self.lock_file_path))
        if lock_dir:
            os.makedirs(lock_dir, exist_ok=True)

        try:
            self._file_obj = open(self.lock_file_path, "a+")
        except OSError as e:
            logger.error("Failed to open lock file %s: %s", self.lock_file_path, e)
            raise HostLockError(f"Cannot open lock file: {e}") from e

        if sys.platform != "win32":
            import fcntl
            try:
                fcntl.flock(self._file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._is_locked = True
            except (BlockingIOError, OSError):
                self._file_obj.close()
                self._file_obj = None
                return False
        else:
            import msvcrt
            try:
                self._file_obj.seek(0)
                if os.path.getsize(self.lock_file_path) == 0:
                    self._file_obj.write("1")
                    self._file_obj.flush()
                self._file_obj.seek(0)
                msvcrt.locking(self._file_obj.fileno(), msvcrt.LK_NBLCK, 1)
                self._is_locked = True
            except (OSError, IOError):
                self._file_obj.close()
                self._file_obj = None
                return False

        try:
            self._file_obj.seek(0)
            self._file_obj.truncate()
            self._file_obj.write(f"pid={os.getpid()}\n")
            self._file_obj.flush()
        except Exception as e:
            logger.warning("Failed to write PID to lock file: %s", e)

        logger.info("Host advisory lock acquired: %s (pid=%s)", self.lock_file_path, os.getpid())
        return True

    def release(self) -> None:
        """Releases the held advisory lock."""
        if not self._is_locked:
            if self._file_obj:
                try:
                    self._file_obj.close()
                except Exception:
                    pass
                self._file_obj = None
            return

        try:
            if sys.platform != "win32":
                import fcntl
                if self._file_obj:
                    fcntl.flock(self._file_obj.fileno(), fcntl.LOCK_UN)
            else:
                import msvcrt
                if self._file_obj:
                    self._file_obj.seek(0)
                    msvcrt.locking(self._file_obj.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception as e:
            logger.warning("Error releasing host lock: %s", e)
        finally:
            if self._file_obj:
                try:
                    self._file_obj.close()
                except Exception:
                    pass
                self._file_obj = None
            self._is_locked = False
            logger.info("Host advisory lock released: %s", self.lock_file_path)

    def __enter__(self):
        if not self.acquire():
            raise HostLockError(f"Another worker process holds host lock '{self.lock_file_path}'")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    @property
    def is_locked(self) -> bool:
        return self._is_locked
