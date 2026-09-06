"""Ownership tests use private temporary files and never open the keyboard."""

import os
import selectors
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from orca_keychron import device_lock
from orca_keychron.device_lock import DeviceLockError, DeviceOwnershipLock

CHILD_SOURCE = """
import sys
from pathlib import Path
from orca_keychron import device_lock

device_lock._default_lock_path = lambda: Path(sys.argv[1])
lock = device_lock.DeviceOwnershipLock()
try:
    lock.acquire()
except device_lock.DeviceLockError:
    print('BLOCKED', flush=True)
    raise SystemExit(0)
try:
    if sys.argv[2] == 'hold':
        print('READY', flush=True)
        for command in sys.stdin:
            if command.strip() == 'release':
                lock.release()
                print('RELEASED', flush=True)
            elif command.strip() == 'stop':
                break
    else:
        print('ACQUIRED', flush=True)
finally:
    lock.release()
"""


@pytest.fixture
def lock_path(tmp_path, monkeypatch):
    path = tmp_path / "private" / "device.lock"
    monkeypatch.setattr(device_lock, "_default_lock_path", lambda: path)
    return path


@pytest.fixture
def child_processes():
    processes = []

    def start(path, mode="probe"):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", CHILD_SOURCE, str(path), mode],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        processes.append(process)
        return process

    yield start
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def read_signal(process):
    # A readiness message is authoritative; elapsed time alone is not readiness.
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(timeout=5), "lock subprocess did not report its state"
        line = process.stdout.readline().strip()
    assert line, f"lock subprocess exited unexpectedly (exit={process.poll()})"
    return line


def test_default_path_is_account_scoped_and_ignores_runtime_settings(tmp_path, monkeypatch):
    account_home = Path(device_lock.pwd.getpwuid(os.getuid()).pw_dir)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "other-runtime"))
    monkeypatch.setenv("ORCA_KEYCHRON_LOCK_PATH", str(tmp_path / "other.lock"))

    assert device_lock._default_lock_path() == account_home / ".orca-keychron" / "device.lock"


def test_acquire_creates_private_files_and_release_preserves_inode(lock_path):
    lock = DeviceOwnershipLock()
    lock.release()
    try:
        lock.acquire()
        directory = lock_path.parent.stat()
        original = lock_path.stat()
        assert stat.S_IMODE(directory.st_mode) == 0o700
        assert stat.S_IMODE(original.st_mode) == 0o600
        assert stat.S_ISREG(original.st_mode)
        assert original.st_uid == directory.st_uid == os.getuid()
        assert original.st_nlink == 1
        with pytest.raises(DeviceLockError):
            lock.acquire()
    finally:
        lock.release()
        lock.release()

    assert lock_path.stat().st_ino == original.st_ino
    try:
        lock.acquire()
        assert lock_path.stat().st_ino == original.st_ino
    finally:
        lock.release()


def test_two_actual_processes_contend_then_release_allows_new_owner(lock_path, child_processes):
    owner = child_processes(lock_path, "hold")
    assert read_signal(owner) == "READY"
    contender = child_processes(lock_path)
    assert contender.pid != owner.pid
    assert read_signal(contender) == "BLOCKED"
    assert contender.wait(timeout=5) == 0
    assert owner.poll() is None

    inode = lock_path.stat().st_ino
    owner.stdin.write("release\n")
    owner.stdin.flush()
    assert read_signal(owner) == "RELEASED"
    assert owner.poll() is None
    successor = child_processes(lock_path)
    assert read_signal(successor) == "ACQUIRED"
    assert successor.wait(timeout=5) == 0
    assert lock_path.stat().st_ino == inode


def test_sigkill_owner_releases_lock_without_removing_file(lock_path, child_processes):
    owner = child_processes(lock_path, "hold")
    assert read_signal(owner) == "READY"
    inode = lock_path.stat().st_ino
    owner.kill()
    assert owner.wait(timeout=5) != 0

    successor = child_processes(lock_path)
    assert read_signal(successor) == "ACQUIRED"
    assert successor.wait(timeout=5) == 0
    assert lock_path.stat().st_ino == inode


def test_separate_lock_instances_in_one_process_contend(lock_path):
    owner, contender = DeviceOwnershipLock(), DeviceOwnershipLock()
    try:
        owner.acquire()
        with pytest.raises(DeviceLockError):
            contender.acquire()
        contender.release()
        owner.release()
        contender.acquire()
    finally:
        owner.release()
        contender.release()


@pytest.mark.parametrize("mode", [0o755, 0o770, 0o707])
def test_rejects_directory_accessible_by_other_users(lock_path, mode):
    lock_path.parent.mkdir(mode=mode)
    lock_path.parent.chmod(mode)
    with pytest.raises(DeviceLockError):
        DeviceOwnershipLock().acquire()
    assert not lock_path.exists()


@pytest.mark.parametrize("mode", [0o644, 0o660, 0o606])
def test_rejects_lock_accessible_by_other_users(lock_path, mode):
    lock_path.parent.mkdir(mode=0o700)
    lock_path.write_text("existing content")
    lock_path.chmod(mode)
    with pytest.raises(DeviceLockError):
        DeviceOwnershipLock().acquire()
    assert lock_path.read_text() == "existing content"
    assert stat.S_IMODE(lock_path.stat().st_mode) == mode


def test_rejects_symlink_directory(lock_path, tmp_path):
    target = tmp_path / "directory-target"
    target.mkdir(mode=0o700)
    lock_path.parent.symlink_to(target, target_is_directory=True)
    with pytest.raises(DeviceLockError):
        DeviceOwnershipLock().acquire()
    assert not (target / lock_path.name).exists()


def test_rejects_symlink_lock_without_changing_target(lock_path, tmp_path):
    lock_path.parent.mkdir(mode=0o700)
    target = tmp_path / "file-target"
    target.write_text("preserved")
    target.chmod(0o600)
    lock_path.symlink_to(target)
    with pytest.raises(DeviceLockError):
        DeviceOwnershipLock().acquire()
    assert lock_path.is_symlink()
    assert target.read_text() == "preserved"


def test_rejects_fifo_without_blocking(lock_path, child_processes):
    lock_path.parent.mkdir(mode=0o700)
    os.mkfifo(lock_path, 0o600)
    contender = child_processes(lock_path)
    assert read_signal(contender) == "BLOCKED"
    assert contender.wait(timeout=5) == 0
    assert stat.S_ISFIFO(lock_path.stat().st_mode)


def test_rejects_hard_link_lock(lock_path, tmp_path):
    lock_path.parent.mkdir(mode=0o700)
    target = tmp_path / "linked-target"
    target.write_text("preserved")
    target.chmod(0o600)
    os.link(target, lock_path)
    with pytest.raises(DeviceLockError):
        DeviceOwnershipLock().acquire()
    assert target.read_text() == "preserved"
    assert target.stat().st_nlink == 2


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_rejects_other_user_ownership(lock_path, monkeypatch, kind):
    lock_path.parent.mkdir(mode=0o700)
    original_fstat = os.fstat

    def foreign_owner(fd):
        result = original_fstat(fd)
        matching = (
            stat.S_ISDIR(result.st_mode)
            if kind == "directory"
            else stat.S_ISREG(result.st_mode)
        )
        if matching:
            values = list(result)
            values[4] = os.getuid() + 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(device_lock.os, "fstat", foreign_owner)
    with pytest.raises(DeviceLockError):
        DeviceOwnershipLock().acquire()


def test_rejects_replaced_lock_inode_and_closes_failed_owner(lock_path, monkeypatch):
    lock_path.parent.mkdir(mode=0o700)
    replacement = lock_path.parent / "replacement"
    replacement.touch(mode=0o600)
    original_flock = device_lock.fcntl.flock

    def replace_after_lock(fd, operation):
        original_flock(fd, operation)
        replacement.replace(lock_path)

    with monkeypatch.context() as context:
        context.setattr(device_lock.fcntl, "flock", replace_after_lock)
        with pytest.raises(DeviceLockError):
            DeviceOwnershipLock().acquire()

    successor = DeviceOwnershipLock()
    try:
        successor.acquire()
    finally:
        successor.release()
