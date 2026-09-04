from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from .config import config_dir

LABEL = "io.github.kmgeon.orca-keychron"


class AutostartError(RuntimeError):
    pass


def launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def service_target() -> str:
    return f"gui/{os.getuid()}/{LABEL}"


def autostart_status(
    path: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, bool]:
    target = path or launch_agent_path()
    if sys.platform != "darwin":
        return target.exists(), False
    completed = runner(
        ["launchctl", "print", service_target()],
        check=False,
        capture_output=True,
        text=True,
    )
    return target.exists(), completed.returncode == 0


def install_autostart(
    python: str | None = None,
    path: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Path:
    if sys.platform != "darwin":
        raise AutostartError("Login autostart is currently supported only on macOS")
    target = path or launch_agent_path()
    logs = config_dir() / "logs"
    target.parent.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    if python is not None:
        program_arguments = [python, "-m", "orca_keychron", "run"]
    else:
        program_arguments = [sys.executable, "-m", "orca_keychron", "run"]
    payload = {
        "Label": LABEL,
        "ProgramArguments": program_arguments,
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        },
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
    }
    temporary = target.with_suffix(".tmp")
    try:
        temporary.write_bytes(plistlib.dumps(payload, sort_keys=True))
        temporary.chmod(0o600)
        os.replace(temporary, target)
    except OSError as exc:
        raise AutostartError(f"Could not write LaunchAgent {target}: {exc}") from exc

    domain = f"gui/{os.getuid()}"
    runner(["launchctl", "bootout", service_target()], check=False, capture_output=True, text=True)
    completed = runner(
        ["launchctl", "bootstrap", domain, str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise AutostartError(f"Could not load LaunchAgent: {detail}")
    return target


def uninstall_autostart(
    path: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    if sys.platform != "darwin":
        raise AutostartError("Login autostart is currently supported only on macOS")
    target = path or launch_agent_path()
    runner(["launchctl", "bootout", service_target()], check=False, capture_output=True, text=True)
    try:
        target.unlink()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise AutostartError(f"Could not remove LaunchAgent {target}: {exc}") from exc
    return True
