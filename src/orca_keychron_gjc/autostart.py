from __future__ import annotations

import os
import plistlib
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import ConfigError, config_dir, ensure_private_config_dir

LABEL = "io.github.kmgeon.orca-keychron-gjc"
ORCA_LABEL = "io.github.kmgeon.orca-keychron"
LEGACY_ORCA_LABEL = "com.tobenetworks.orca-keychron"

_MODULE = "orca_keychron_gjc"
_MAX_PLIST_BYTES = 1024 * 1024
_MAX_ERROR_DETAIL = 500


class AutostartError(RuntimeError):
    pass


class _AtomicWriteError(AutostartError):
    def __init__(self, message: str, *, replaced: bool):
        super().__init__(message)
        self.replaced = replaced


def launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def service_target() -> str:
    return f"gui/{os.getuid()}/{LABEL}"


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _service_target(label: str) -> str:
    return f"{_domain()}/{label}"


def _launch_agent_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _detail(value: object) -> str:
    compact = " ".join(str(value).split()) or "unknown error"
    if len(compact) <= _MAX_ERROR_DETAIL:
        return compact
    return compact[: _MAX_ERROR_DETAIL - 1] + "…"


def _run(
    runner: Callable[..., subprocess.CompletedProcess[str]],
    args: list[str],
    operation: str,
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(args, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise AutostartError(f"Could not {operation}: {_detail(exc)}") from exc


def _completed_detail(completed: subprocess.CompletedProcess[str]) -> str:
    return _detail(completed.stderr.strip() or completed.stdout.strip() or "unknown error")


def _owned_program_arguments(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and isinstance(value[0], str)
        and bool(value[0])
        and Path(value[0]).is_absolute()
        and "\0" not in value[0]
        and value[1:] == ["-m", _MODULE, "run"]
    )


def _runtime_dir() -> Path:
    return config_dir()


def _logs_dir() -> Path:
    return _runtime_dir() / "gjc-logs"


def _read_owned_plist(path: Path) -> bytes | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AutostartError(f"Could not inspect LaunchAgent {path}: {_detail(exc)}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise AutostartError(f"Refusing symlink LaunchAgent: {path}")
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise AutostartError(f"Refusing non-file LaunchAgent: {path}")
    if metadata.st_size > _MAX_PLIST_BYTES:
        raise AutostartError(f"Refusing oversized LaunchAgent: {path}")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK,
        )
        with os.fdopen(descriptor, "rb") as stream:
            current = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.getuid()
                or current.st_size > _MAX_PLIST_BYTES
            ):
                raise AutostartError(f"Refusing unsafe LaunchAgent: {path}")
            raw = stream.read(_MAX_PLIST_BYTES + 1)
        if len(raw) > _MAX_PLIST_BYTES:
            raise AutostartError(f"Refusing oversized LaunchAgent: {path}")
        payload: Any = plistlib.loads(raw)
    except (OSError, plistlib.InvalidFileException, ValueError, TypeError, OverflowError) as exc:
        raise AutostartError(f"Refusing unreadable LaunchAgent {path}: {_detail(exc)}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("Label") != LABEL
        or not _owned_program_arguments(payload.get("ProgramArguments"))
        or (
            "WorkingDirectory" in payload
            and payload.get("WorkingDirectory") != str(_runtime_dir())
        )
        or payload.get("StandardOutPath") != str(_logs_dir() / "stdout.log")
        or payload.get("StandardErrorPath") != str(_logs_dir() / "stderr.log")
    ):
        raise AutostartError(
            f"Refusing unowned or different-command LaunchAgent: {path}"
        )
    return raw


def _validate_log_destinations(logs: Path) -> None:
    for target in (logs / "stdout.log", logs / "stderr.log"):
        try:
            metadata = target.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise AutostartError(f"Could not inspect GJC log file {target}: {_detail(exc)}") from exc
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise AutostartError(f"Refusing unsafe GJC log file: {target}")


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary: Path | None = None
    descriptor = -1
    replaced = False
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        temporary = None
        replaced = True
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as exc:
        raise _AtomicWriteError(
            f"Could not write LaunchAgent {path}: {_detail(exc)}", replaced=replaced
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


def _remove_written_plist(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise AutostartError(f"Could not remove LaunchAgent {path}: {_detail(exc)}") from exc


def _restore_plist_file(target: Path, previous: bytes | None) -> str | None:
    try:
        if previous is None:
            _remove_written_plist(target)
        else:
            _atomic_write(target, previous)
    except AutostartError as exc:
        return str(exc)
    return None


def _is_loaded(
    label: str,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> bool:
    completed = _run(
        runner,
        ["launchctl", "print", _service_target(label)],
        f"inspect LaunchAgent {label}",
    )
    if completed.returncode == 0:
        return True
    if completed.returncode == 113:
        return False
    raise AutostartError(
        f"Could not inspect LaunchAgent {label}: {_completed_detail(completed)}"
    )


def _find_orca_conflicts(
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> list[str]:
    conflicts = []
    for label in (ORCA_LABEL, LEGACY_ORCA_LABEL):
        path = _launch_agent_path(label)
        installed = _lexists(path)
        loaded = _is_loaded(label, runner)
        if installed or loaded:
            states = []
            if installed:
                states.append(f"plist at {path}")
            if loaded:
                states.append(f"loaded service {_service_target(label)}")
            conflicts.append(f"{label} ({', '.join(states)})")
    return conflicts


def _rollback_install(
    target: Path,
    previous: bytes | None,
    previously_loaded: bool,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> str | None:
    failures = []
    restored_file = False
    try:
        stopped = _run(
            runner,
            ["launchctl", "bootout", service_target()],
            "stop failed GJC LaunchAgent",
        )
        if stopped.returncode != 0:
            failures.append(f"rollback bootout: {_completed_detail(stopped)}")
    except AutostartError as exc:
        failures.append(str(exc))
    try:
        if previous is None:
            _remove_written_plist(target)
        else:
            _atomic_write(target, previous)
            restored_file = True
    except AutostartError as exc:
        failures.append(str(exc))
    if restored_file and previously_loaded:
        try:
            restored = _run(
                runner,
                ["launchctl", "bootstrap", _domain(), str(target)],
                "reload previous GJC LaunchAgent",
            )
            if restored.returncode != 0:
                failures.append(f"restore bootstrap: {_completed_detail(restored)}")
        except AutostartError as exc:
            failures.append(str(exc))
    return _detail("; ".join(failures)) if failures else None


def autostart_status(
    path: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, bool]:
    target = path or launch_agent_path()
    installed = _lexists(target)
    if sys.platform != "darwin":
        return installed, False
    if installed:
        _read_owned_plist(target)
    return installed, _is_loaded(LABEL, runner)


def install_autostart(
    python: str | None = None,
    path: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Path:
    if sys.platform != "darwin":
        raise AutostartError("GJC login autostart is currently supported only on macOS")
    target = path or launch_agent_path()
    executable = python if python is not None else sys.executable
    if (
        not isinstance(executable, str)
        or not executable
        or "\0" in executable
        or not Path(executable).is_absolute()
    ):
        raise AutostartError("GJC autostart requires an absolute Python executable")
    previous = _read_owned_plist(target)
    previously_loaded = _is_loaded(LABEL, runner)
    if previously_loaded and previous is None:
        raise AutostartError(
            "Refusing to replace a loaded GJC LaunchAgent without an owned plist; "
            f"stop {_service_target(LABEL)} explicitly first"
        )
    conflicts = _find_orca_conflicts(runner)
    if conflicts:
        raise AutostartError(
            "Existing Orca login service conflicts with GJC autostart: "
            + "; ".join(conflicts)
            + ". Switch explicitly by uninstalling or stopping the Orca service first; "
            "no existing service was changed."
        )

    runtime = _runtime_dir()
    logs = _logs_dir()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        ensure_private_config_dir(runtime)
        ensure_private_config_dir(logs)
        _validate_log_destinations(logs)
    except (OSError, ConfigError) as exc:
        raise AutostartError(f"Could not create GJC autostart directories: {_detail(exc)}") from exc

    payload = {
        "Label": LABEL,
        "ProgramArguments": [executable, "-m", _MODULE, "run"],
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        },
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "WorkingDirectory": str(runtime),
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
    }
    try:
        _atomic_write(target, plistlib.dumps(payload, sort_keys=True))
    except AutostartError as exc:
        rollback_failure = (
            _restore_plist_file(target, previous)
            if not isinstance(exc, _AtomicWriteError) or exc.replaced
            else None
        )
        message = str(exc)
        if rollback_failure:
            message += f"; rollback also failed: {_detail(rollback_failure)}"
        raise AutostartError(message) from exc

    try:
        bootout = _run(
            runner,
            ["launchctl", "bootout", service_target()],
            "stop existing GJC LaunchAgent",
        )
    except AutostartError as exc:
        rollback_failure = _restore_plist_file(target, previous)
        message = str(exc)
        if rollback_failure:
            message += f"; rollback also failed: {_detail(rollback_failure)}"
        raise AutostartError(message) from exc
    if previously_loaded and bootout.returncode != 0:
        rollback_failure = _restore_plist_file(target, previous)
        message = f"Could not stop existing GJC LaunchAgent: {_completed_detail(bootout)}"
        if rollback_failure:
            message += f"; rollback also failed: {_detail(rollback_failure)}"
        raise AutostartError(message)

    try:
        completed = _run(
            runner,
            ["launchctl", "bootstrap", _domain(), str(target)],
            "load GJC LaunchAgent",
        )
    except AutostartError as exc:
        rollback_failure = _rollback_install(target, previous, previously_loaded, runner)
        message = str(exc)
        if rollback_failure:
            message += f"; rollback also failed: {rollback_failure}"
        raise AutostartError(message) from exc
    if completed.returncode != 0:
        rollback_failure = _rollback_install(target, previous, previously_loaded, runner)
        message = f"Could not load GJC LaunchAgent: {_completed_detail(completed)}"
        if rollback_failure:
            message += f"; rollback also failed: {rollback_failure}"
        raise AutostartError(message)
    return target


def uninstall_autostart(
    path: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    if sys.platform != "darwin":
        raise AutostartError("GJC login autostart is currently supported only on macOS")
    target = path or launch_agent_path()
    existing = _read_owned_plist(target)
    loaded = _is_loaded(LABEL, runner)
    if existing is None:
        if loaded:
            raise AutostartError(
                "Refusing to stop a loaded GJC LaunchAgent without an owned plist; "
                f"inspect {_service_target(LABEL)} explicitly"
            )
        return False
    completed = _run(
        runner,
        ["launchctl", "bootout", service_target()],
        "stop GJC LaunchAgent",
    )
    if loaded and completed.returncode != 0:
        raise AutostartError(
            f"Could not stop GJC LaunchAgent: {_completed_detail(completed)}; "
            f"plist preserved at {target}"
        )
    # Revalidate immediately before removal so a swapped symlink is never treated as owned.
    _read_owned_plist(target)
    try:
        target.unlink()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise AutostartError(f"Could not remove LaunchAgent {target}: {_detail(exc)}") from exc
    return True
