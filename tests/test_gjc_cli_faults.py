import json
from pathlib import Path
from uuid import uuid4

from orca_keychron_gjc import cli
from orca_keychron_gjc.config import Config


def test_human_status_exposes_incomplete_coverage_without_hiding_work_or_waiting(capsys):
    for state in ("working", "waiting"):
        row = {"slot": 0, "state": state, "connected": True, "agentCount": 256,
               "pendingRequests": int(state == "waiting"), "launchId": "launch",
               "complete": False}
        cli._print_status({"launches": [row]})
        output = capsys.readouterr().out
        assert f"1: {state} (live)" in output
        assert "incomplete coverage" in output
        row["complete"] = True
        cli._print_status({"launches": [row]})
        assert "incomplete coverage" not in capsys.readouterr().out


def test_human_status_distinguishes_assigned_slot_after_key_range_from_overflow(capsys):
    """Only an unassigned slot is overflow, even when no shortcut key names it."""
    cli._print_status({
        "launches": [
            {
                "slot": 12,
                "state": "done",
                "connected": True,
                "agentCount": 1,
                "pendingRequests": 0,
                "launchId": "assigned-thirteen",
            },
            {
                "slot": None,
                "state": "unknown",
                "connected": False,
                "agentCount": 1,
                "pendingRequests": 0,
                "launchId": "actual-overflow",
            },
        ]
    })

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("slot 13: done (live)")
    assert lines[1].startswith("overflow: unknown (offline)")


def test_saved_socket_reaches_status_clear_install_and_doctor(monkeypatch, tmp_path, capsys):
    saved_socket = tmp_path / "saved.sock"
    saved = Config("Keychron", (1,), 4, ("orca",), str(saved_socket))
    empty_status = {"version": 1, "maxSlots": 1, "launches": [], "overflow": []}
    calls = []
    installed = {}
    monkeypatch.setattr(cli, "load_config", lambda: saved)
    monkeypatch.setattr(cli, "registry_path", lambda: tmp_path / "registry.json")
    monkeypatch.setattr(cli, "_gjc_version", lambda: {
        "available": True,
        "supported": True,
        "version": "gjc/0.16.4",
        "expected": "gjc/0.16.4",
    })
    monkeypatch.setattr(cli.gjc_install, "status", lambda **_kwargs: {"installed": False})
    monkeypatch.setattr(
        cli.gjc_install,
        "install",
        lambda **kwargs: installed.update(kwargs) or {"dry_run": True},
    )
    monkeypatch.setattr(cli.autostart, "autostart_status", lambda: (False, False))

    def control(endpoint, command="status", launch_id=None):
        calls.append((Path(endpoint), command, launch_id))
        response = {"ok": True, "status": empty_status}
        if command == "clear":
            response["cleared"] = False
        return response

    monkeypatch.setattr(cli, "request_control", control)

    assert cli.status_command(cli.build_parser().parse_args(["status", "--json"])) == 0
    assert cli.clear_command(
        cli.build_parser().parse_args(["clear", str(uuid4()), "--json"])
    ) == 1
    assert cli.install_command(cli.build_parser().parse_args(["install", "--dry-run"])) == 0
    assert cli.doctor_command(cli.build_parser().parse_args(["doctor"])) == 0
    capsys.readouterr()

    assert [call[0] for call in calls] == [saved_socket, saved_socket, saved_socket]
    assert installed["socket_path"] == saved_socket


def test_doctor_reports_each_partial_health_dimension(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "load_config", lambda: None)
    monkeypatch.setattr(cli, "socket_path", lambda: tmp_path / "default.sock")
    monkeypatch.setattr(cli, "registry_path", lambda: tmp_path / "registry.json")
    monkeypatch.setattr(cli, "_gjc_version", lambda: {
        "available": False,
        "supported": False,
        "version": None,
    })
    monkeypatch.setattr(cli.gjc_install, "status", lambda **_kwargs: {"installed": False})
    monkeypatch.setattr(
        cli,
        "request_control",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()),
    )
    monkeypatch.setattr(
        cli.autostart,
        "autostart_status",
        lambda: (_ for _ in ()).throw(cli.AutostartError("launchctl unavailable")),
    )

    assert cli.doctor_command(cli.build_parser().parse_args(["doctor"])) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["gjc"]["available"] is False
    assert result["config"] == {
        "configured": False,
        "socket": str(tmp_path / "default.sock"),
        "registry": str(tmp_path / "registry.json"),
    }
    assert result["installation"] == {"installed": False}
    assert result["bridge"] == {"ok": False, "error": "GJC bridge is not reachable"}
    assert result["autostart"] == {
        "ok": False,
        "error": "launchctl unavailable",
    }
