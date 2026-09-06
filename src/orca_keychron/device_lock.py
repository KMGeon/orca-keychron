"""One cooperating HID owner per operating-system account.

The lock path deliberately does not depend on project, product, config or runtime
environment settings. Do not remove the lock file: retaining its inode is what
makes a new contender synchronize with the current owner after release.
"""

from __future__ import annotations

import fcntl
import os
import pwd
import stat
from pathlib import Path


class DeviceLockError(RuntimeError):
    pass


def _default_lock_path() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / ".orca-keychron" / "device.lock"


class DeviceOwnershipLock:
    def __init__(self) -> None:
        self._fd: int | None = None

    def acquire(self) -> None:
        if self._fd is not None:
            raise DeviceLockError("This Keychron ownership lock is already acquired")
        path = _default_lock_path()
        directory_fd = None
        fd = None
        try:
            path.parent.mkdir(mode=0o700, exist_ok=True)
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            directory_stat = os.fstat(directory_fd)
            if directory_stat.st_uid != os.getuid() or directory_stat.st_mode & 0o077:
                raise DeviceLockError(
                    f"Keychron lock directory must be private and owned by this user: {path.parent}"
                )
            fd = os.open(
                path.name,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=directory_fd,
            )
            file_stat = os.fstat(fd)
            if (
                not stat.S_ISREG(file_stat.st_mode)
                or file_stat.st_uid != os.getuid()
                or file_stat.st_mode & 0o077
                or file_stat.st_nlink != 1
            ):
                raise DeviceLockError(
                    f"Keychron lock must be a private regular file owned by this user: {path}"
                )
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DeviceLockError(
                    "Another orca-keychron process owns the keyboard. Stop the running "
                    "indicator or preview before opening another command. "
                    f"Ownership lock: {path}"
                ) from exc
            # Fail closed if the directory/file was replaced while being opened.
            current_directory = path.parent.lstat()
            current_file = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                (directory_stat.st_dev, directory_stat.st_ino)
                != (current_directory.st_dev, current_directory.st_ino)
                or (file_stat.st_dev, file_stat.st_ino)
                != (current_file.st_dev, current_file.st_ino)
            ):
                raise DeviceLockError(f"Keychron ownership lock path changed while opening: {path}")
            # Finish every fallible setup step before transferring ownership to
            # the instance, so unsuccessful acquire() never retains the lock.
            os.close(directory_fd)
            directory_fd = None
            self._fd = fd
            fd = None
        except OSError as exc:
            raise DeviceLockError(f"Could not acquire Keychron ownership lock {path}: {exc}") from exc
        finally:
            try:
                if fd is not None:
                    os.close(fd)
            finally:
                if directory_fd is not None:
                    os.close(directory_fd)

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is not None:
            # Closing releases flock even after failure; no separate unlock or
            # unlink is needed, and no stale PID can prevent subsequent startup.
            os.close(fd)
