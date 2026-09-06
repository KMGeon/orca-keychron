from __future__ import annotations

import plistlib
import stat
import subprocess
from pathlib import Path

import pytest

from orca_keychron_gjc import autostart


def completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


class Launchctl:
    def __init__(self, loaded=(), failures=None):
        self.loaded = set(loaded)
        self.failures = failures or {}
        self.calls = []

    def __call__(self, args, **kwargs):
        assert kwargs == {"check": False, "capture_output": True, "text": True}
        self.calls.append(args)
        key = tuple(args[1:])
        if key in self.failures:
            return completed(args, returncode=5, stderr=self.failures[key])
        if args[1] == "print":
            return completed(args, returncode=0 if args[2] in self.loaded else 113)
        return completed(args)


@pytest.fixture
def mac_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    return tmp_path


def owned_payload(python="/tools/python"):
    logs = autostart.config_dir() / "gjc-logs"
    return {
        "Label": autostart.LABEL,
        "ProgramArguments": [python, "-m", "orca_keychron_gjc", "run"],
        "RunAtLoad": True,
        "WorkingDirectory": str(autostart.config_dir()),
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
    }


def write_owned(path: Path, python="/tools/python") -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = plistlib.dumps(owned_payload(python), sort_keys=True)
    path.write_bytes(raw)
    return raw


def test_launch_agent_uses_separate_gjc_namespace(mac_home):
    assert autostart.LABEL == "io.github.kmgeon.orca-keychron-gjc"
    assert autostart.launch_agent_path() == (
        mac_home / "Library" / "LaunchAgents" / f"{autostart.LABEL}.plist"
    )
    assert autostart.service_target().endswith(f"/{autostart.LABEL}")


def test_install_writes_atomic_private_gjc_agent_and_logs(mac_home, monkeypatch):
    monkeypatch.setattr(autostart.sys, "executable", "/current/python")
    runner = Launchctl()

    path = autostart.install_autostart(runner=runner)

    payload = plistlib.loads(path.read_bytes())
    logs = autostart.config_dir() / "gjc-logs"
    assert payload["Label"] == autostart.LABEL
    assert payload["ProgramArguments"] == [
        "/current/python", "-m", "orca_keychron_gjc", "run"
    ]
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] == {"SuccessfulExit": False}
    assert payload["ThrottleInterval"] == 10
    assert payload["WorkingDirectory"] == str(autostart.config_dir())
    assert payload["StandardOutPath"] == str(logs / "stdout.log")
    assert payload["StandardErrorPath"] == str(logs / "stderr.log")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert logs.is_dir()
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))
    assert runner.calls[-2] == ["launchctl", "bootout", autostart.service_target()]
    assert runner.calls[-1] == [
        "launchctl", "bootstrap", f"gui/{autostart.os.getuid()}", str(path)
    ]


def test_install_accepts_explicit_python_for_base_api_compatibility(mac_home):
    runner = Launchctl()

    path = autostart.install_autostart("/explicit/python", runner=runner)

    assert plistlib.loads(path.read_bytes())["ProgramArguments"][0] == "/explicit/python"


@pytest.mark.parametrize("label", [autostart.ORCA_LABEL, autostart.LEGACY_ORCA_LABEL])
def test_install_refuses_installed_orca_agent_without_changing_it(mac_home, label):
    conflict = mac_home / "Library" / "LaunchAgents" / f"{label}.plist"
    conflict.parent.mkdir(parents=True)
    conflict.write_text("leave me alone", encoding="utf-8")
    runner = Launchctl()

    with pytest.raises(autostart.AutostartError, match="no existing service was changed"):
        autostart.install_autostart(runner=runner)

    assert conflict.read_text(encoding="utf-8") == "leave me alone"
    assert not autostart.launch_agent_path().exists()
    assert not any(call[1] == "bootout" for call in runner.calls)


def test_install_refuses_loaded_orca_agent_without_booting_it_out(mac_home):
    conflict_target = f"gui/{autostart.os.getuid()}/{autostart.ORCA_LABEL}"
    runner = Launchctl(loaded={conflict_target})

    with pytest.raises(autostart.AutostartError, match="loaded service"):
        autostart.install_autostart(runner=runner)

    assert not any(call[1] == "bootout" for call in runner.calls)
    assert not autostart.launch_agent_path().exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"Label": "someone.else", "ProgramArguments": ["/python", "-m", "orca_keychron_gjc", "run"]},
        {"Label": autostart.LABEL, "ProgramArguments": ["/python", "-m", "other", "run"]},
        {"Label": autostart.LABEL, "ProgramArguments": ["/python", "-m", "orca_keychron_gjc", "serve"]},
    ],
)
def test_install_and_uninstall_refuse_unowned_or_different_command_plist(
    mac_home, payload
):
    path = autostart.launch_agent_path()
    path.parent.mkdir(parents=True)
    raw = plistlib.dumps(payload)
    path.write_bytes(raw)

    with pytest.raises(autostart.AutostartError, match="unowned or different-command"):
        autostart.install_autostart(runner=Launchctl())
    with pytest.raises(autostart.AutostartError, match="unowned or different-command"):
        autostart.uninstall_autostart(runner=Launchctl())

    assert path.read_bytes() == raw


def test_install_and_uninstall_refuse_symlink_plist(mac_home):
    outside = mac_home / "outside.plist"
    outside.write_bytes(plistlib.dumps(owned_payload()))
    path = autostart.launch_agent_path()
    path.parent.mkdir(parents=True)
    path.symlink_to(outside)

    with pytest.raises(autostart.AutostartError, match="symlink"):
        autostart.install_autostart(runner=Launchctl())
    with pytest.raises(autostart.AutostartError, match="symlink"):
        autostart.uninstall_autostart(runner=Launchctl())

    assert path.is_symlink()
    assert outside.exists()


def test_failed_bootstrap_removes_new_plist(mac_home):
    path = autostart.launch_agent_path()
    bootstrap = ("bootstrap", f"gui/{autostart.os.getuid()}", str(path))
    runner = Launchctl(failures={bootstrap: "load failed"})

    with pytest.raises(autostart.AutostartError, match="load failed"):
        autostart.install_autostart(runner=runner)

    assert not path.exists()


def test_launchctl_execution_error_is_bounded_and_rolls_back_new_plist(mac_home):
    path = autostart.launch_agent_path()

    class MissingLaunchctl(Launchctl):
        def __call__(self, args, **kwargs):
            if args[1] == "bootstrap":
                raise OSError("x" * 2000)
            return super().__call__(args, **kwargs)

    with pytest.raises(autostart.AutostartError) as raised:
        autostart.install_autostart(runner=MissingLaunchctl())

    assert not path.exists()
    assert len(str(raised.value)) < 600


def test_failed_bootstrap_restores_and_reloads_previous_owned_plist(mac_home):
    path = autostart.launch_agent_path()
    previous = write_owned(path, "/old/python")
    path.chmod(0o644)
    target = autostart.service_target()
    bootstrap = ("bootstrap", f"gui/{autostart.os.getuid()}", str(path))

    class FailFirstBootstrap(Launchctl):
        def __init__(self):
            super().__init__(loaded={target})
            self.bootstrap_count = 0

        def __call__(self, args, **kwargs):
            if args[1] == "bootstrap":
                self.calls.append(args)
                self.bootstrap_count += 1
                if self.bootstrap_count == 1:
                    return completed(args, returncode=5, stderr="new load failed")
                return completed(args)
            return super().__call__(args, **kwargs)

    runner = FailFirstBootstrap()

    with pytest.raises(autostart.AutostartError, match="new load failed"):
        autostart.install_autostart("/new/python", runner=runner)

    assert path.read_bytes() == previous
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert runner.bootstrap_count == 2
    assert tuple(runner.calls[-1][1:]) == bootstrap


def test_uninstall_is_idempotent_and_only_stops_gjc(mac_home):
    path = autostart.launch_agent_path()
    write_owned(path)
    runner = Launchctl(loaded={autostart.service_target()})

    assert autostart.uninstall_autostart(runner=runner) is True
    runner.loaded.clear()
    assert autostart.uninstall_autostart(runner=runner) is False

    bootouts = [call for call in runner.calls if call[1] == "bootout"]
    assert bootouts == [["launchctl", "bootout", autostart.service_target()]]


def test_uninstall_preserves_plist_when_loaded_service_cannot_stop(mac_home):
    path = autostart.launch_agent_path()
    previous = write_owned(path)
    bootout = ("bootout", autostart.service_target())
    runner = Launchctl(
        loaded={autostart.service_target()}, failures={bootout: "operation not permitted"}
    )

    with pytest.raises(autostart.AutostartError, match="plist preserved"):
        autostart.uninstall_autostart(runner=runner)

    assert path.read_bytes() == previous


def test_status_distinguishes_installed_loaded_and_stopped(mac_home):
    path = autostart.launch_agent_path()
    runner = Launchctl()
    assert autostart.autostart_status(runner=runner) == (False, False)

    write_owned(path)
    assert autostart.autostart_status(runner=runner) == (True, False)

    runner.loaded.add(autostart.service_target())
    assert autostart.autostart_status(runner=runner) == (True, True)


def test_non_macos_matches_status_shape_and_refuses_changes(tmp_path, monkeypatch):
    path = tmp_path / "agent.plist"
    path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(autostart.sys, "platform", "linux")

    assert autostart.autostart_status(path=path, runner=Launchctl()) == (True, False)
    with pytest.raises(autostart.AutostartError, match="only on macOS"):
        autostart.install_autostart(path=path, runner=Launchctl())
    with pytest.raises(autostart.AutostartError, match="only on macOS"):
        autostart.uninstall_autostart(path=path, runner=Launchctl())
