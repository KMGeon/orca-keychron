"""Requirements R: real CLI -> socket -> registry lifecycle without hardware."""
import json
import os
import sys
from pathlib import Path


def test_cli_crash_restart_preserves_slots_then_reclaims_only_dead_launch(cli_rig):
    rig = cli_rig
    rig.start()
    children = [rig.child(), rig.child()]
    frames = [rig.frame(child.pid, "done") for child in children]
    clients = [rig.connect(), rig.connect()]
    for client, frame in zip(clients, frames):
        rig.send(client, frame)
    before = rig.wait_status(lambda r: len(r["status"]["launches"]) == 2)
    slots = {r["launchId"]: r["slot"] for r in before["status"]["launches"]}
    rig.stop_server(crash=True)
    offline = rig.status()
    assert offline["source"] == "registry"
    assert all(r["state"] == "unknown" for r in offline["status"]["launches"])
    assert {r["launchId"]: r["slot"] for r in offline["status"]["launches"]} == slots
    rig.start()
    for client in clients:
        client.close()
    clients = [rig.connect(), rig.connect()]
    for client, frame in zip(clients, frames):
        frame["sequence"] += 1
        rig.send(client, frame)
    restored = rig.wait_status(lambda r: all(x["state"] == "done"
                                            for x in r["status"]["launches"]))
    assert {r["launchId"]: r["slot"] for r in restored["status"]["launches"]} == slots
    result = rig.run("clear", frames[0]["launchId"], "--socket", rig.endpoint,
                     "--json", expected=1)
    assert json.loads(result.stdout)["error"]["reason"] == "connected"
    clients[0].close()
    rig.wait_status(lambda r: not r["status"]["launches"][0]["connected"])
    result = rig.run("clear", frames[0]["launchId"], "--socket", rig.endpoint,
                     "--json", expected=1)
    assert json.loads(result.stdout)["error"]["reason"] == "process_alive"
    children[0].terminate()
    children[0].wait(timeout=5)
    result = rig.run("clear", frames[0]["launchId"], "--socket", rig.endpoint, "--json")
    assert json.loads(result.stdout)["cleared"] is True
    remaining = rig.status()["status"]["launches"]
    assert [(r["launchId"], r["slot"])
            for r in remaining] == [(frames[1]["launchId"], slots[frames[1]["launchId"]])]
    rig.stop_server()


def test_saved_socket_with_spaces_and_nondefault_zone_works_in_real_cli(cli_rig):
    rig = cli_rig
    parent = (Path(rig.env["HOME"]) / "Library" / "Application Support"
              if sys.platform == "darwin" else Path(rig.env["XDG_CONFIG_HOME"]))
    config_dir = parent / "orca-keychron" / "gjc"
    config_dir.mkdir(parents=True, mode=0o700)
    config = config_dir / "config.json"
    config.write_text(json.dumps({"product": "Fixture keyboard", "leds": [4, 7],
                                  "led_total": 72, "socket_path": str(rig.endpoint),
                                  "orca_command": ["unused-orca-fixture"]}))
    config.chmod(0o600)
    rig.start(saved_socket=True)
    client = rig.connect()
    frame = rig.frame(os.getpid())
    rig.send(client, frame)
    rig.wait_status(lambda r: len(r["status"]["launches"]) == 1)
    # No --socket override: status must consume exactly the persisted endpoint.
    status = json.loads(rig.run("status", "--json").stdout)
    assert status["source"] == "live"
    assert status["socket"] == str(rig.endpoint)
    assert status["status"]["launches"][0]["launchId"] == frame["launchId"]
    assert not (config_dir / "bridge.sock").exists()
    rig.stop_server()


def test_cli_errors_do_not_damage_live_receiver_and_corrupt_registry_is_not_empty(cli_rig):
    rig = cli_rig
    rig.start()
    invalid = rig.run("clear", "not-a-uuid", "--socket", rig.endpoint, expected=2)
    assert "canonical UUID" in invalid.stderr
    collision = rig.run("serve", "--socket", rig.endpoint,
                        "--registry", rig.registry, expected=1)
    assert "already owns" in collision.stderr
    assert rig.status()["source"] == "live"
    rig.stop_server()
    rig.registry.write_text('{"broken":')
    rig.registry.chmod(0o600)
    corrupt = rig.run("status", "--socket", rig.endpoint,
                      "--registry", rig.registry, "--json", expected=1)
    assert "registry" in corrupt.stderr.lower()
    assert '"ok": true' not in corrupt.stdout


def test_serve_and_status_never_load_hardware_or_start_external_commands(cli_rig):
    rig = cli_rig
    guard = rig.root / "import-guard"
    guard.mkdir()
    active = guard / "active"
    violation = guard / "violation"
    (guard / "sitecustomize.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        f"Path({str(active)!r}).touch()\n"
        "def audit(event, args):\n"
        "    hardware = event == 'import' and args[0].split('.')[0] in "
        "{'hid', 'pynput', 'Quartz', 'AppKit'}\n"
        "    if hardware or event == 'subprocess.Popen':\n"
        f"        Path({str(violation)!r}).write_text(event)\n"
        "        raise RuntimeError('serve must remain receiver-only')\n"
        "sys.addaudithook(audit)\n"
    )
    rig.env["PYTHONPATH"] = str(guard) + os.pathsep + rig.env["PYTHONPATH"]
    rig.start()
    assert active.exists(), "The child interpreter must actually enable the guard"
    client = rig.connect()
    rig.send(client, rig.frame(os.getpid()))
    status = rig.wait_status(lambda r: bool(r["status"]["launches"]))
    assert status["status"]["launches"][0]["state"] == "working"
    rig.stop_server()
    assert not violation.exists()


def test_plain_live_status_marks_incomplete_coverage_until_complete_followup(cli_rig):
    rig = cli_rig
    rig.start()
    client = rig.connect()
    frame = rig.frame(os.getpid())
    frame["complete"] = False
    rig.send(client, frame)
    rig.wait_status(lambda r: bool(r["status"]["launches"]))
    incomplete = rig.run("status", "--socket", rig.endpoint).stdout
    assert "working (live)" in incomplete
    assert "incomplete coverage" in incomplete
    frame.update(sequence=2, complete=True)
    rig.send(client, frame)
    rig.wait_status(lambda r: r["status"]["launches"][0]["complete"])
    assert "incomplete coverage" not in rig.run("status", "--socket", rig.endpoint).stdout
    rig.stop_server()
