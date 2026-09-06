from __future__ import annotations

import os
import plistlib
import stat
import subprocess
from pathlib import Path

import pytest

from orca_keychron_gjc import autostart


def _completed(args: list[str], returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(args, returncode, "", stderr)


class StatefulLaunchctl:
    def __init__(self, *, loaded: set[str] | None = None, failures: dict[tuple[str, ...], str] | None = None):
        self.loaded = set(loaded or ())
        self.failures = dict(failures or {})
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **kwargs: object):
        assert kwargs == {"check": False, "capture_output": True, "text": True}
        self.calls.append(args)
        operation = tuple(args[1:])
        if operation in self.failures:
            return _completed(args, 5, self.failures[operation])
        if args[1] == "print":
            return _completed(args, 0 if args[2] in self.loaded else 113)
        if args[1] == "bootout":
            self.loaded.discard(args[2])
        elif args[1] == "bootstrap":
            self.loaded.add(autostart.service_target())
        return _completed(args)


@pytest.fixture
def mac_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    return tmp_path


@pytest.mark.parametrize("label", [autostart.ORCA_LABEL, autostart.LEGACY_ORCA_LABEL])
def test_orca_service_inspection_error_fails_closed_without_writing(
    mac_home: Path, label: str
) -> None:
    target = f"gui/{os.getuid()}/{label}"
    runner = StatefulLaunchctl(failures={("print", target): "operation not permitted"})

    with pytest.raises(autostart.AutostartError, match="inspect LaunchAgent"):
        autostart.install_autostart(runner=runner)

    assert not autostart.launch_agent_path().exists()
    assert not (autostart.config_dir() / "gjc-logs").exists()
    assert not any(call[1] in {"bootout", "bootstrap"} for call in runner.calls)


@pytest.mark.parametrize("python", ["python3", "./venv/bin/python", "relative python"])
def test_relative_interpreter_is_rejected_before_any_write_or_service_change(
    mac_home: Path, python: str
) -> None:
    runner = StatefulLaunchctl()

    with pytest.raises(autostart.AutostartError, match="absolute Python executable"):
        autostart.install_autostart(python, runner=runner)

    assert not autostart.launch_agent_path().exists()
    assert not autostart.config_dir().exists()
    assert not any(call[1] in {"bootout", "bootstrap"} for call in runner.calls)


def test_definition_has_owned_working_directory_and_private_log_directory(
    mac_home: Path,
) -> None:
    previous_umask = os.umask(0)
    try:
        path = autostart.install_autostart("/tools/python", runner=StatefulLaunchctl())
    finally:
        os.umask(previous_umask)

    payload = plistlib.loads(path.read_bytes())
    runtime = autostart.config_dir()
    logs = runtime / "gjc-logs"
    assert payload["WorkingDirectory"] == str(runtime)
    assert payload["StandardOutPath"] == str(logs / "stdout.log")
    assert payload["StandardErrorPath"] == str(logs / "stderr.log")
    assert stat.S_IMODE(runtime.stat().st_mode) == 0o700
    assert stat.S_IMODE(logs.stat().st_mode) == 0o700


def test_symlink_log_directory_is_refused_without_touching_target(
    mac_home: Path,
) -> None:
    outside = mac_home / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"preserve")
    runtime = autostart.config_dir()
    runtime.mkdir(parents=True, mode=0o700)
    runtime.chmod(0o700)
    (runtime / "gjc-logs").symlink_to(outside, target_is_directory=True)
    runner = StatefulLaunchctl()

    with pytest.raises(autostart.AutostartError, match="private user-owned directory"):
        autostart.install_autostart("/tools/python", runner=runner)

    assert sentinel.read_bytes() == b"preserve"
    assert (runtime / "gjc-logs").is_symlink()
    assert not autostart.launch_agent_path().exists()
    assert not any(call[1] in {"bootout", "bootstrap"} for call in runner.calls)


@pytest.mark.parametrize("name", ["stdout.log", "stderr.log"])
def test_symlink_log_file_is_refused_without_touching_target(
    mac_home: Path, name: str
) -> None:
    outside = mac_home / "outside.log"
    outside.write_bytes(b"user log\n")
    runtime = autostart.config_dir()
    logs = runtime / "gjc-logs"
    logs.mkdir(parents=True, mode=0o700)
    runtime.chmod(0o700)
    logs.chmod(0o700)
    (logs / name).symlink_to(outside)
    runner = StatefulLaunchctl()

    with pytest.raises(autostart.AutostartError, match="unsafe GJC log file"):
        autostart.install_autostart("/tools/python", runner=runner)

    assert outside.read_bytes() == b"user log\n"
    assert (logs / name).is_symlink()
    assert not autostart.launch_agent_path().exists()
    assert not any(call[1] in {"bootout", "bootstrap"} for call in runner.calls)


@pytest.mark.parametrize(
    "installed,loaded",
    [
        ((autostart.ORCA_LABEL, autostart.LEGACY_ORCA_LABEL), ()),
        ((), (autostart.ORCA_LABEL, autostart.LEGACY_ORCA_LABEL)),
        ((autostart.ORCA_LABEL,), (autostart.LEGACY_ORCA_LABEL,)),
    ],
)
def test_current_and_legacy_orca_conflict_combinations_never_change_either_service(
    mac_home: Path, installed: tuple[str, ...], loaded: tuple[str, ...]
) -> None:
    originals = {}
    for label in installed:
        path = mac_home / "Library" / "LaunchAgents" / f"{label}.plist"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"user {label}\n".encode())
        originals[path] = path.read_bytes()
    loaded_targets = {f"gui/{os.getuid()}/{label}" for label in loaded}
    runner = StatefulLaunchctl(loaded=loaded_targets)

    with pytest.raises(autostart.AutostartError, match="Existing Orca login service"):
        autostart.install_autostart("/tools/python", runner=runner)

    assert {path: path.read_bytes() for path in originals} == originals
    assert runner.loaded == loaded_targets
    assert not any(call[1] in {"bootout", "bootstrap"} for call in runner.calls)
    assert not autostart.launch_agent_path().exists()


@pytest.mark.parametrize("field", ["WorkingDirectory", "StandardOutPath", "StandardErrorPath"])
def test_modified_owned_definition_is_preserved_on_install_and_uninstall(
    mac_home: Path, field: str
) -> None:
    path = autostart.install_autostart("/tools/python", runner=StatefulLaunchctl())
    payload = plistlib.loads(path.read_bytes())
    payload[field] = str(mac_home / "user-selected-path")
    modified = plistlib.dumps(payload, sort_keys=True)
    path.write_bytes(modified)
    path.chmod(0o600)

    with pytest.raises(autostart.AutostartError, match="unowned or different-command"):
        autostart.install_autostart("/new/python", runner=StatefulLaunchctl())
    with pytest.raises(autostart.AutostartError, match="unowned or different-command"):
        autostart.uninstall_autostart(runner=StatefulLaunchctl())

    assert path.read_bytes() == modified


def test_old_generated_definition_without_working_directory_can_upgrade_and_uninstall(
    mac_home: Path,
) -> None:
    path = autostart.launch_agent_path()
    logs = autostart.config_dir() / "gjc-logs"
    old_payload = {
        "Label": autostart.LABEL,
        "ProgramArguments": ["/old/python", "-m", "orca_keychron_gjc", "run"],
        "EnvironmentVariables": {"PATH": "/usr/bin:/bin"},
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
    }
    raw = plistlib.dumps(old_payload, sort_keys=True)
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    path.chmod(0o600)

    assert autostart.autostart_status(runner=StatefulLaunchctl()) == (True, False)
    upgraded = autostart.install_autostart("/new/python", runner=StatefulLaunchctl())
    upgraded_payload = plistlib.loads(upgraded.read_bytes())
    assert upgraded_payload["ProgramArguments"][0] == "/new/python"
    assert upgraded_payload["WorkingDirectory"] == str(autostart.config_dir())

    path.write_bytes(raw)
    path.chmod(0o600)
    assert autostart.uninstall_autostart(runner=StatefulLaunchctl()) is True
    assert not path.exists()


def test_failed_bootstrap_reports_failed_bootout_during_rollback(mac_home: Path) -> None:
    path = autostart.launch_agent_path()
    bootstrap = ("bootstrap", f"gui/{os.getuid()}", str(path))
    bootout = ("bootout", autostart.service_target())
    runner = StatefulLaunchctl(
        failures={bootstrap: "bootstrap failed", bootout: "rollback bootout failed"}
    )

    with pytest.raises(autostart.AutostartError) as raised:
        autostart.install_autostart("/tools/python", runner=runner)

    assert "bootstrap failed" in str(raised.value)
    assert "rollback also failed" in str(raised.value)
    assert "rollback bootout failed" in str(raised.value)
    assert not path.exists()


def test_launch_agent_directory_fsync_failure_restores_original_before_service_change(
    mac_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial_runner = StatefulLaunchctl()
    path = autostart.install_autostart("/old/python", runner=initial_runner)
    previous = path.read_bytes()
    loaded = {autostart.service_target()}
    runner = StatefulLaunchctl(loaded=loaded)
    original_fsync = autostart.os.fsync
    failed = False

    def fail_first_directory_fsync(descriptor: int) -> None:
        nonlocal failed
        if stat.S_ISDIR(os.fstat(descriptor).st_mode) and not failed:
            failed = True
            raise OSError("injected LaunchAgent directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(autostart.os, "fsync", fail_first_directory_fsync)

    with pytest.raises(autostart.AutostartError, match="directory fsync failure"):
        autostart.install_autostart("/new/python", runner=runner)

    assert failed is True
    assert path.read_bytes() == previous
    assert runner.loaded == loaded
    assert not any(call[1] in {"bootout", "bootstrap"} for call in runner.calls)


def test_uninstall_unlink_failure_is_explicit_and_preserves_definition(
    mac_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = StatefulLaunchctl()
    path = autostart.install_autostart("/tools/python", runner=runner)
    before = path.read_bytes()
    runner.loaded.add(autostart.service_target())
    original_unlink = Path.unlink

    def fail_target_unlink(candidate: Path, *args: object, **kwargs: object) -> None:
        if candidate == path:
            raise PermissionError("injected unlink denial")
        original_unlink(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_target_unlink)

    with pytest.raises(autostart.AutostartError, match="injected unlink denial"):
        autostart.uninstall_autostart(runner=runner)

    assert path.read_bytes() == before
    assert autostart.service_target() not in runner.loaded
