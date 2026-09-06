"""Installed-wheel tests. Set GJC_TEST_WHEEL_DIR to a freshly built wheel directory."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def wheel_install(tmp_path_factory):
    directory = os.environ.get("GJC_TEST_WHEEL_DIR")
    if not directory:
        pytest.skip("Build a wheel and set GJC_TEST_WHEEL_DIR; CI enables this suite explicitly")
    wheels = list(Path(directory).resolve().glob("*.whl"))
    assert len(wheels) == 1, "The wheel gate requires exactly one unambiguous artifact"
    wheel = wheels[0]
    root = tmp_path_factory.mktemp("wheel-install").resolve()
    venv = root / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True,
                   capture_output=True, text=True, timeout=60)
    python = venv / "bin" / "python"
    # These transport/loader checks need no HID dependencies. The separate full
    # install gate verifies dependency resolution; this install is offline.
    subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps",
                    str(wheel)], check=True, capture_output=True, text=True, timeout=30)
    return wheel, python


def test_wheel_contains_both_commands_and_exact_current_assets(wheel_install, rig_factory):
    wheel, python = wheel_install
    rig = rig_factory(python, installed=True)
    repo = Path(__file__).resolve().parents[2]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        entrypoints = archive.read(next(n for n in names if n.endswith("entry_points.txt")))
        assert b"orca-keychron = orca_keychron.cli:main" in entrypoints
        assert b"orca-keychron-gjc = orca_keychron_gjc.cli:main" in entrypoints
        files = [*list((repo / "src").rglob("*.py")),
                 *list((repo / "src/orca_keychron_gjc/assets").glob("*"))]
        for source in files:
            if source.is_file() and "__pycache__" not in source.parts:
                member = str(source.relative_to(repo / "src"))
                assert archive.read(member) == source.read_bytes(), f"Stale wheel member: {member}"
    script = """import json, orca_keychron, orca_keychron_gjc
print(json.dumps([orca_keychron.__file__, orca_keychron_gjc.__file__]))
"""
    result = subprocess.run([str(python), "-c", script], cwd=rig.root, env=rig.env,
                            check=True, capture_output=True, text=True, timeout=10)
    for filename in json.loads(result.stdout):
        assert Path(filename).resolve().is_relative_to(python.parent.parent)
    for command in ("orca-keychron", "orca-keychron-gjc"):
        result = subprocess.run([str(python.with_name(command)), "--version"],
                                cwd=rig.root, env=rig.env, check=True,
                                capture_output=True, text=True, timeout=10)
        assert result.stdout.startswith(command + " ")


def test_installed_cli_preserves_human_priority_and_rejects_live_clear(wheel_install, rig_factory):
    _, python = wheel_install
    rig = rig_factory(python, installed=True)
    rig.start()
    child = rig.child()
    client = rig.connect()
    frame = rig.frame(child.pid)
    frame["sessions"] = [{"sessionId": frame["root"]["sessionId"], "role": "root",
                          "state": "done", "pendingAsks": 0, "pendingDecisions": 0}]
    frame["sessions"] += [{"sessionId": f"child-{i}", "role": "child", "state": "working",
                           "pendingAsks": 0, "pendingDecisions": 0} for i in range(10)]
    frame["sessions"].append({"sessionId": "human-child", "role": "child", "state": "waiting",
                               "pendingAsks": 1, "pendingDecisions": 0})
    rig.send(client, frame)
    value = rig.wait_status(lambda r: bool(r["status"]["launches"]))
    assert value["status"]["launches"][0]["state"] == "waiting"
    assert value["status"]["launches"][0]["pendingRequests"] == 1
    result = rig.run("clear", frame["launchId"], "--socket", rig.endpoint, "--json", expected=1)
    assert json.loads(result.stdout)["error"]["reason"] == "connected"
    client.close()
    rig.wait_status(lambda r: r["status"]["launches"][0]["state"] == "unknown")
    child.terminate()
    child.wait(timeout=5)
    assert json.loads(rig.run("clear", frame["launchId"], "--socket", rig.endpoint,
                               "--json").stdout)["cleared"]
    assert not rig.status()["status"]["launches"]
    rig.stop_server()


def test_installed_managed_loader_executes_and_streams_to_installed_receiver(
    wheel_install, rig_factory,
):
    bun = shutil.which("bun")
    if bun is None:
        pytest.skip("Bun is required to execute the packaged TypeScript loader")
    _, python = wheel_install
    rig = rig_factory(python, installed=True)
    # A version-only GJC stub isolates installer compatibility checks. Actual
    # GJC discovery/child/UI behavior is tested by tests/e2e/run_gjc_e2e.py.
    bin_dir = rig.root / "bin"
    bin_dir.mkdir()
    gjc = bin_dir / "gjc"
    gjc.write_text("#!/bin/sh\n[ \"$1\" = --version ] || exit 97\nprintf '%s\\n' 'gjc/0.16.4'\n")
    gjc.chmod(0o700)
    rig.env["PATH"] = str(bin_dir) + os.pathsep + rig.env.get("PATH", "")
    agent = rig.root / "agent profile"
    plan = rig.run("install", "--agent-dir", agent, "--socket", rig.endpoint, "--dry-run")
    assert plan.returncode == 0
    assert not agent.exists()
    rig.run("install", "--agent-dir", agent, "--socket", rig.endpoint)
    loader = agent / "hooks/pre/orca-keychron.ts"
    assert loader.is_file()
    rig.start()
    script = rig.root / "load-installed.ts"
    script.write_text("""import { pathToFileURL } from 'node:url';
const { default: load } = await import(pathToFileURL(process.env.TEST_LOADER!).href);
const handlers = new Map<string, Function>();
load({ on: (type: string, handler: Function) => handlers.set(type, handler) });
const emit = (type: string, value: object = {}) => handlers.get(type)!(value, {
  hasUI: true, sessionManager: { getSessionId: () => 'installed-root' },
  hasQueuedMessages: () => false,
});
emit('session_start'); emit('agent_start');
emit('tool_execution_start', { toolName: 'ask', toolCallId: 'installed-ask',
  args: { questions: [{ id: 'request', question: 'PRIVATE_QUESTION_927',
    options: [{ label: 'PRIVATE_OPTION_927' }] }] } });
await new Promise(resolve => process.stdin.once('data', resolve));
process.stdin.pause(); emit('session_shutdown');
await Bun.sleep(300);
""")
    env = {k: v for k, v in rig.env.items() if not k.startswith("ORCA_KEYCHRON_")}
    env.update(TEST_LOADER=str(loader), ORCA_TERMINAL_HANDLE="term_packaged",
               ORCA_PANE_KEY="packaged:leaf", ORCA_WORKTREE_ID="packaged-worktree")
    log = (rig.root / "loader.log").open("w+")
    rig.logs.append(log)
    process = subprocess.Popen([bun, str(script)], cwd=rig.root, env=env,
                               stdin=subprocess.PIPE, stdout=log, stderr=log)
    rig.processes.append(process)
    value = rig.wait_status(lambda r: bool(r["status"]["launches"]))
    row = value["status"]["launches"][0]
    assert row["state"] == "waiting" and row["pendingRequests"] == 1
    assert row["root"]["sessionId"] == "installed-root"
    assert "PRIVATE_" not in json.dumps(value)
    assert "PRIVATE_" not in rig.registry.read_text()
    assert process.stdin is not None
    process.stdin.write(b"close\n")
    process.stdin.flush()
    process.stdin.close()
    process.wait(timeout=5)
    assert process.returncode == 0
    rig.wait_status(lambda r: not r["status"]["launches"])
    rig.stop_server()
    rig.run("uninstall", "--agent-dir", agent)
    assert not loader.exists()
