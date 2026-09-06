"""Real diagnostic CLI boundaries with version/service commands isolated locally."""
import json
import os
import sys
from pathlib import Path

import pytest


def prepare_commands(rig, version="gjc/0.16.4", code=0):
    directory = rig.root / "commands"
    directory.mkdir()
    # The real GJC runtime is exercised by the separate explicit E2E runner.
    (directory / "gjc").write_text(
        f"#!/bin/sh\n[ \"$1\" = --version ] || exit 97\n"
        f"printf '%s\\n' '{version}'\nexit {code}\n"
    )
    (directory / "launchctl").write_text(
        "#!/bin/sh\n[ \"$1\" = print ] || exit 98\nexit 113\n"
    )
    for command in directory.iterdir():
        command.chmod(0o700)
    rig.env["PATH"] = str(directory) + os.pathsep + "/usr/bin:/bin"


def save_config(rig):
    parent = (Path(rig.env["HOME"]) / "Library" / "Application Support"
              if sys.platform == "darwin" else Path(rig.env["XDG_CONFIG_HOME"]))
    directory = parent / "orca-keychron/gjc"
    directory.mkdir(parents=True, mode=0o700)
    path = directory / "config.json"
    path.write_text(json.dumps({"product": "fixture", "leds": [1, 2], "led_total": 72,
                                "socket_path": str(rig.endpoint), "orca_command": ["orca"]}))
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("version,code,supported", [
    ("gjc/0.16.4", 0, True), ("gjc/0.16.5", 0, False), ("gjc/0.16.4", 1, False),
])
def test_doctor_reports_exact_version_and_missing_components_without_mutation(
    cli_rig, version, code, supported,
):
    rig = cli_rig
    prepare_commands(rig, version, code)
    agent = rig.root / "agent"
    result = json.loads(rig.run("doctor", "--agent-dir", agent,
                                "--socket", rig.endpoint).stdout)
    assert result["gjc"]["supported"] is supported
    assert result["config"]["configured"] is False
    assert result["installation"]["installed"] is False
    assert result["installation"]["healthy"] is False
    assert result["bridge"]["ok"] is False
    assert not agent.exists()
    assert not rig.endpoint.exists()
    assert not Path(rig.env["HOME"]).exists()


def test_doctor_distinguishes_live_bridge_from_modified_installation_and_socket_override(cli_rig):
    rig = cli_rig
    prepare_commands(rig)
    save_config(rig)
    agent = rig.root / "agent"
    rig.run("install", "--agent-dir", agent)
    rig.start(saved_socket=True)
    healthy = json.loads(rig.run("doctor", "--agent-dir", agent).stdout)
    assert healthy["gjc"]["supported"] is True
    assert healthy["config"]["socket"] == str(rig.endpoint)
    assert healthy["installation"]["socket_path"] == str(rig.endpoint)
    assert healthy["installation"]["healthy"] is True
    assert healthy["bridge"]["ok"] is True
    assert healthy["autostart"]["installed"] is False
    assert healthy["autostart"]["loaded"] is False

    loader = agent / "hooks/pre/orca-keychron.ts"
    modified = loader.read_bytes() + b"\n// local user edit\n"
    loader.write_bytes(modified)
    changed = json.loads(rig.run("doctor", "--agent-dir", agent).stdout)
    assert changed["installation"]["healthy"] is False
    assert str(loader) in changed["installation"]["modified"]
    assert changed["bridge"]["ok"] is True
    assert loader.read_bytes() == modified

    absent = rig.root / "absent.sock"
    override = json.loads(rig.run("doctor", "--agent-dir", agent, "--socket", absent).stdout)
    assert override["config"]["socket"] == str(absent)
    assert override["bridge"]["ok"] is False
    assert rig.status()["source"] == "live"
    assert not absent.exists()
    rig.stop_server()


def test_doctor_rejects_corrupt_config_without_reporting_healthy_or_rewriting_it(cli_rig):
    rig = cli_rig
    prepare_commands(rig)
    config = save_config(rig)
    broken = b'{"socket_path":'
    config.write_bytes(broken)
    result = rig.run("doctor", "--agent-dir", rig.root / "agent", expected=1)
    assert "config" in result.stderr.lower()
    assert not result.stdout
    assert config.read_bytes() == broken
