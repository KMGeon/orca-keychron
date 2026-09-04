import plistlib
import subprocess

from orca_keychron import autostart


def completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def test_install_autostart_writes_and_bootstraps_launch_agent(tmp_path, monkeypatch):
    path = tmp_path / "LaunchAgents" / "agent.plist"
    logs = tmp_path / "config"
    calls = []

    def runner(args, **_kwargs):
        calls.append(args)
        return completed(args)

    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    monkeypatch.setattr(autostart, "config_dir", lambda: logs)

    assert autostart.install_autostart("/python", path, runner) == path

    payload = plistlib.loads(path.read_bytes())
    assert payload["Label"] == autostart.LABEL
    assert payload["ProgramArguments"] == ["/python", "-m", "orca_keychron", "run"]
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] == {"SuccessfulExit": False}
    assert payload["ThrottleInterval"] == 10
    assert calls[0][1:3] == ["bootout", autostart.service_target()]
    assert calls[1][1:3] == ["bootstrap", f"gui/{autostart.os.getuid()}"]


def test_install_autostart_uses_current_python_by_default(tmp_path, monkeypatch):
    path = tmp_path / "agent.plist"
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    monkeypatch.setattr(autostart, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(autostart.sys, "executable", "/tools/python")
    runner = lambda args, **_kwargs: completed(args)

    autostart.install_autostart(path=path, runner=runner)

    payload = plistlib.loads(path.read_bytes())
    assert payload["ProgramArguments"] == ["/tools/python", "-m", "orca_keychron", "run"]


def test_uninstall_autostart_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "agent.plist"
    path.write_text("placeholder")
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    runner = lambda args, **_kwargs: completed(args)

    assert autostart.uninstall_autostart(path, runner) is True
    assert autostart.uninstall_autostart(path, runner) is False


def test_autostart_status_distinguishes_installed_and_loaded(tmp_path, monkeypatch):
    path = tmp_path / "agent.plist"
    path.write_text("placeholder")
    monkeypatch.setattr(autostart.sys, "platform", "darwin")

    loaded = lambda args, **_kwargs: completed(args)
    stopped = lambda args, **_kwargs: completed(args, returncode=113)

    assert autostart.autostart_status(path, loaded) == (True, True)
    assert autostart.autostart_status(path, stopped) == (True, False)
