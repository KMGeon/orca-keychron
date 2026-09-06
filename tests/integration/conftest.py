"""Real CLI-process fixtures; all mutable paths and processes are test-owned."""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pytest

REPO = Path(__file__).resolve().parents[2]


class CliRig:
    def __init__(self, root: Path, python: Path, *, installed: bool = False):
        self.root = root
        self.python = python
        self.endpoint = root / "custom bridge.sock"
        self.registry = root / "registry.json"
        # HOME is overridden only for owned child processes, never the host session.
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOME": str(root / "home"),
                    "PYTHONPATH": "" if installed else str(REPO / "src"),
                    "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
                    "XDG_CONFIG_HOME": str(root / "xdg")}
        self.processes: list[subprocess.Popen] = []
        self.clients: list[socket.socket] = []
        self.logs = []
        self.server = None

    def run(self, *args: str, expected: int = 0):
        result = subprocess.run(
            [str(self.python), "-m", "orca_keychron_gjc", *map(str, args)],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=10,
            check=False,
        )
        assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
        assert "Traceback" not in result.stderr
        return result

    def start(self, *, saved_socket: bool = False):
        log = (self.root / f"server-{len(self.logs)}.log").open("w+")
        self.logs.append(log)
        args = [str(self.python), "-m", "orca_keychron_gjc", "serve",
                "--registry", str(self.registry), "--slots", "2"]
        if not saved_socket:
            args += ["--socket", str(self.endpoint)]
        self.server = subprocess.Popen(args, cwd=self.root, env=self.env,
                                       stdout=log, stderr=log)
        self.processes.append(self.server)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.server.poll() is not None:
                log.seek(0)
                raise AssertionError(log.read())
            if self.endpoint.exists():
                self.wait_status(lambda value: value["source"] == "live")
                return
            time.sleep(0.01)
        raise AssertionError("CLI receiver did not become ready")

    def status(self):
        return json.loads(self.run("status", "--socket", self.endpoint,
                                   "--registry", self.registry, "--json").stdout)

    def wait_status(self, predicate):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            value = self.status()
            if predicate(value):
                return value
            time.sleep(0.01)
        raise AssertionError(f"Expected status was not observed: {value}")

    def child(self):
        child = subprocess.Popen([str(self.python), "-c", "import time; time.sleep(60)"],
                                 cwd=self.root, env=self.env)
        self.processes.append(child)
        return child

    def connect(self):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(3)
        client.connect(str(self.endpoint))
        self.clients.append(client)
        return client

    @staticmethod
    def frame(pid: int, state: str = "working"):
        return {
            "version": 1, "type": "snapshot", "producerId": str(uuid4()),
            "sequence": 1, "launchId": str(uuid4()), "pid": pid,
            "startedAt": 123456, "complete": True, "closed": False,
            "root": {"sessionId": str(uuid4()), "terminalHandle": "term_test",
                     "paneKey": "test-tab:test-leaf", "worktreeId": "test-worktree"},
            "sessions": [], "_state": state,
        }

    @staticmethod
    def send(client, frame):
        # Fixture-only convenience keys never enter the production wire schema.
        row = {k: v for k, v in frame.items() if not k.startswith("_")}
        if not row["sessions"] and not row["closed"]:
            row["sessions"] = [{"sessionId": row["root"]["sessionId"], "role": "root",
                                "state": frame["_state"], "pendingAsks": 0,
                                "pendingDecisions": 0}]
        client.sendall(json.dumps(row).encode("utf-8") + b"\n")

    def stop_server(self, *, crash: bool = False):
        assert self.server is not None
        self.server.send_signal(signal.SIGKILL if crash else signal.SIGTERM)
        self.server.wait(timeout=5)
        assert self.server.returncode == (-signal.SIGKILL if crash else 0)
        if not crash:
            assert not self.endpoint.exists()

    def close(self):
        for client in self.clients:
            client.close()
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if process.stdin is not None:
                process.stdin.close()
        for log in self.logs:
            log.close()


@pytest.fixture
def rig_factory():
    rigs = []
    temporaries = []

    def create(python=Path(sys.executable), *, installed=False):
        temporary = tempfile.TemporaryDirectory(prefix="g-int-", dir="/tmp")
        temporaries.append(temporary)
        rig = CliRig(Path(temporary.name).resolve(), Path(python), installed=installed)
        rigs.append(rig)
        return rig

    try:
        yield create
    finally:
        for rig in rigs:
            rig.close()
        for temporary in temporaries:
            temporary.cleanup()


@pytest.fixture
def cli_rig(rig_factory):
    return rig_factory()
