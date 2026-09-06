"""Repeatable, bounded actual-GJC audit driven through owned Orca terminals."""

# ruff: noqa: UP045 -- Optional keeps runtime annotation syntax conservative on Python 3.9.

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from audit_support import (
    AuditFailure,
    assert_decision_correlations,
    assert_distinct_stable_slots,
    assert_mass_waiting,
    assert_outcomes,
    assert_root_lifecycle,
    current_matching_frame,
    only_metadata_frame,
    read_jsonl,
    remaining_child_decision,
    sha256,
    wait_for,
)

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent
PRODUCT_HARNESS = REPO / "experiments" / "gjc-product-qa" / "harness.py"
PARENT_FIXTURE = REPO / "experiments" / "gjc-parent-decisions" / "fixture.py"
COMPONENTS = BASE / "runtime_components.py"
PRODUCT_SOURCE = REPO / "src" / "orca_keychron_gjc"
SHARED_PRODUCT_SOURCE = REPO / "src" / "orca_keychron"


def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=True, **kwargs)


def tree_hash(root: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(
        item for item in root.rglob("*") if item.is_file() and item.suffix in {".py", ".ts", ".md"}
    ):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def product_source_hash() -> str:
    import hashlib

    digest = hashlib.sha256()
    for root in (PRODUCT_SOURCE, SHARED_PRODUCT_SOURCE):
        digest.update(root.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(tree_hash(root)))
    return digest.hexdigest()


def minimal_environment(home: Path) -> dict[str, str]:
    environment = {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "TMPDIR": str(home / "tmp"),
    }
    for key in ("LC_ALL", "TERM", "SHELL"):
        if key in os.environ:
            environment[key] = os.environ[key]
    Path(environment["HOME"]).mkdir(mode=0o700, parents=True, exist_ok=True)
    Path(environment["TMPDIR"]).mkdir(mode=0o700, parents=True, exist_ok=True)
    return environment


def prepare_runtime(runtime: Path) -> None:
    """Make the private root idempotently after isolated env paths may already exist."""

    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    runtime.chmod(0o700)


class Orca:
    def __init__(self) -> None:
        self.owned: list[str] = []
        self.terminals: dict[str, dict[str, Any]] = {}

    def call(self, *args: str) -> dict[str, Any]:
        result = run(["orca", *args, "--json"], cwd=REPO)
        value = json.loads(result.stdout)
        if not value.get("ok"):
            raise AuditFailure(f"Orca command failed: {args}: {value}")
        return value["result"]

    def create(self, title: str, command: str) -> dict[str, Any]:
        result = self.call(
            "terminal",
            "create",
            "--worktree",
            "active",
            "--title",
            title,
            "--command",
            command,
        )["terminal"]
        self.owned.append(result["handle"])
        self.terminals[result["handle"]] = result
        return result

    def read(self, handle: str) -> str:
        result = self.call("terminal", "read", "--terminal", handle)["terminal"]
        return "\n".join(result.get("tail", []))

    def send(self, handle: str, text: str, enter: bool = False) -> None:
        args = ["terminal", "send", "--terminal", handle, "--text", text]
        if enter:
            args.append("--enter")
        self.call(*args)

    def close(self, handle: str) -> None:
        if handle not in self.owned:
            return
        try:
            self.call("terminal", "close", "--terminal", handle)
        finally:
            self.owned.remove(handle)

    def close_all(self) -> list[str]:
        errors = []
        for handle in list(reversed(self.owned)):
            try:
                self.close(handle)
            except Exception as exc:  # noqa: BLE001 - cleanup must continue for every handle
                errors.append(f"{handle}: {exc}")
        return errors


class Audit:
    def __init__(self, runtime: Path, evidence: Path, wheel: Optional[Path]) -> None:
        self.runtime = runtime
        self.evidence_path = evidence
        self.wheel = wheel
        self.orca = Orca()
        self.product_python = sys.executable
        self.component_env = minimal_environment(runtime / "component-home")
        self.component_env["PYTHONPATH"] = str(REPO / "src")
        self.cases: dict[str, dict[str, Any]] = {}
        self.launches: dict[str, str] = {}
        self.checkpoints: dict[str, Any] = {}
        self.source_before = product_source_hash()

    def validate_parent_fixture_contract(self) -> dict[str, Any]:
        spec = importlib.util.spec_from_file_location(
            "gjc_parent_decisions_fixture", PARENT_FIXTURE
        )
        if spec is None or spec.loader is None:
            raise AuditFailure("REQ-DECISION-0 could not load parent-decisions fixture")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        summaries = []
        for request_id in ("req_1", "req_2"):
            value = module.decision(request_id)
            if module.validate_decision(value, request_id) is not True:
                raise AuditFailure(f"REQ-DECISION-0 fixture rejected its {request_id} contract")
            if set(value) != {"status", "request_id", "question", "options", "checkpoint"}:
                raise AuditFailure(f"REQ-DECISION-0 unexpected decision fields for {request_id}")
            summaries.append(
                {
                    "requestId": request_id,
                    "status": value["status"],
                    "optionCount": len(value["options"]),
                    "checkpointPresent": bool(value["checkpoint"]),
                }
            )
        return {"fixture": str(PARENT_FIXTURE.relative_to(REPO)), "contracts": summaries}

    def owned_process_ids(self) -> list[int]:
        result = run(["ps", "-axo", "pid=,command="], cwd=REPO)
        found = []
        marker = str(self.runtime)
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped or marker not in stripped:
                continue
            raw_pid, _separator, _command = stripped.partition(" ")
            try:
                pid = int(raw_pid)
            except ValueError:
                continue
            if pid != os.getpid():
                found.append(pid)
        return sorted(set(found))

    def verify_cleanup(self) -> dict[str, Any]:
        terminated = []
        errors = []
        try:
            wait_for(
                "owned runtime processes to exit",
                self.owned_process_ids,
                lambda pids: not pids,
                3,
            )
        except AuditFailure:
            for pid in self.owned_process_ids():
                try:
                    os.kill(pid, signal.SIGTERM)
                    terminated.append(pid)
                except ProcessLookupError:
                    pass
            try:
                wait_for(
                    "terminated owned runtime processes to exit",
                    self.owned_process_ids,
                    lambda pids: not pids,
                    3,
                )
            except AuditFailure:
                for pid in self.owned_process_ids():
                    try:
                        os.kill(pid, signal.SIGKILL)
                        terminated.append(pid)
                    except ProcessLookupError:
                        pass
                remaining = wait_for(
                    "killed owned runtime processes to exit",
                    self.owned_process_ids,
                    lambda pids: not pids,
                    3,
                )
                if remaining:
                    errors.append(f"owned processes remain: {remaining}")

        live_handles = {
            row["handle"]
            for row in self.orca.call("terminal", "list", "--worktree", "active")["terminals"]
        }
        leaked_handles = sorted(live_handles.intersection(self.orca.terminals))
        if leaked_handles:
            errors.append(f"owned terminal handles remain: {leaked_handles}")

        listeners = []
        unix = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            unix.settimeout(0.2)
            unix.connect(str(self.runtime / "bridge.sock"))
            listeners.append("bridge.sock")
        except OSError:
            pass
        finally:
            unix.close()
        provider_file = self.runtime / "provider.json"
        if provider_file.exists():
            provider = json.loads(provider_file.read_text(encoding="utf-8"))
            tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                tcp.settimeout(0.2)
                tcp.connect(("127.0.0.1", int(provider["port"])))
                listeners.append(f"127.0.0.1:{provider['port']}")
            except OSError:
                pass
            finally:
                tcp.close()
        if listeners:
            errors.append(f"owned listeners remain: {listeners}")
        return {
            "ownedTerminalHandles": sorted(self.orca.terminals),
            "allOwnedTerminalsClosed": not leaked_handles,
            "terminatedOwnedProcessIds": sorted(set(terminated)),
            "noOwnedProcessesRemain": not self.owned_process_ids(),
            "noOwnedListenersRemain": not listeners,
            "errors": errors,
        }

    def setup_python(self) -> None:
        if not self.wheel:
            return
        venv = self.runtime / "wheel-venv"
        build_env = minimal_environment(self.runtime / "build-home")
        run([sys.executable, "-m", "venv", str(venv)], cwd=REPO, env=build_env)
        python = venv / "bin" / "python"
        run(
            [str(python), "-m", "pip", "install", "--no-deps", str(self.wheel)],
            cwd=REPO,
            env=build_env,
        )
        probe = run(
            [
                str(python),
                "-c",
                (
                    "import importlib.resources as r; "
                    "p=r.files('orca_keychron_gjc').joinpath('assets/gjc_hook.ts'); "
                    "print(p.read_bytes().__len__())"
                ),
            ],
            cwd=REPO,
            env=build_env,
        )
        if int(probe.stdout.strip()) <= 0:
            raise AuditFailure("REQ-INSTALL-1 wheel contains no packaged gjc_hook.ts")
        self.product_python = str(python)
        self.component_env.pop("PYTHONPATH", None)

    def component(self, operation: str, *extra: str) -> dict[str, Any]:
        result = run(
            [
                self.product_python,
                str(COMPONENTS),
                operation,
                "--runtime",
                str(self.runtime),
                *extra,
            ],
            cwd=REPO,
            env=self.component_env,
        )
        return json.loads(result.stdout)

    def component_command(self, operation: str, *extra: str) -> str:
        import shlex

        environment = "env -i " + " ".join(
            f"{key}={shlex.quote(value)}" for key, value in self.component_env.items()
        )
        return (
            environment
            + " "
            + shlex.join(
                [
                    self.product_python,
                    str(COMPONENTS),
                    operation,
                    "--runtime",
                    str(self.runtime),
                    *extra,
                ]
            )
        )

    def status(self) -> dict[str, Any]:
        return self.component("status")

    def colors(self) -> dict[str, Any]:
        return self.component("colors")

    def replay_color(self, frame: dict[str, Any]) -> dict[str, Any]:
        return self.component(
            "replay-color",
            "--launch-id",
            str(frame["launchId"]),
            "--sequence",
            str(frame["sequence"]),
        )

    def frames(self) -> list[dict[str, Any]]:
        return read_jsonl(self.runtime / "wire-metadata.jsonl")

    def provider_rows(self) -> list[dict[str, Any]]:
        return read_jsonl(self.runtime / "provider-metadata.jsonl")

    def prepare(self, name: str, scenario: str) -> dict[str, Any]:
        case = self.component("prepare", "--name", name, "--scenario", scenario)
        self.cases[name] = case
        return case

    def start_case(self, name: str, scenario: str) -> dict[str, Any]:
        case = self.prepare(name, scenario)
        terminal = self.orca.create("gjc-e2e-" + name, case["directLaunch"])
        case["terminal"] = terminal
        return case

    def latest_terminal_frame(
        self,
        terminal: dict[str, Any],
        predicate: Optional[Callable[[dict[str, Any]], bool]] = None,
        min_sequence: int = -1,
    ) -> Optional[dict[str, Any]]:
        return current_matching_frame(
            self.frames(),
            terminal["handle"],
            terminal["paneKey"],
            predicate or (lambda _frame: True),
            min_sequence,
        )

    def historical_terminal_frame(
        self,
        terminal: dict[str, Any],
        predicate: Callable[[dict[str, Any]], bool],
        min_sequence: int = -1,
    ) -> Optional[dict[str, Any]]:
        """Return a matching post-fence transition for a unique newly created terminal."""

        matches = [
            frame
            for frame in self.frames()
            if frame.get("root", {}).get("terminalHandle") == terminal["handle"]
            and frame.get("root", {}).get("paneKey") == terminal["paneKey"]
            and int(frame.get("sequence", -1)) > min_sequence
            and predicate(frame)
        ]
        return matches[-1] if matches else None

    def wait_case_frame(
        self,
        case: dict[str, Any],
        description: str,
        predicate: Callable[[dict[str, Any]], bool],
        timeout: float = 90,
        min_sequence: int = -1,
    ) -> dict[str, Any]:
        return wait_for(
            description,
            lambda: self.latest_terminal_frame(case["terminal"], predicate, min_sequence),
            lambda value: value is not None,
            timeout,
        )

    def wait_provider(
        self, predicate: Callable[[dict[str, Any]], bool], description: str
    ) -> dict[str, Any]:
        return wait_for(
            description,
            lambda: next((row for row in reversed(self.provider_rows()) if predicate(row)), None),
            lambda value: value is not None,
            90,
        )

    def start_provider(self) -> dict[str, Any]:
        import shlex

        provider_env = minimal_environment(self.runtime / "provider-home")
        command = (
            "env -i "
            + " ".join(f"{key}={shlex.quote(value)}" for key, value in provider_env.items())
            + " "
            + shlex.join(
                [
                    sys.executable,
                    str(PRODUCT_HARNESS),
                    "provider",
                    "--runtime",
                    str(self.runtime),
                    "--port",
                    "0",
                ]
            )
        )
        terminal = self.orca.create("gjc-e2e-provider", command)
        wait_for(
            "loopback provider readiness",
            lambda: self.runtime.joinpath("provider.json").exists(),
            bool,
            10,
        )
        return terminal

    def start_receiver(self, generation: int) -> dict[str, Any]:
        terminal = self.orca.create(
            f"gjc-e2e-receiver-{generation}",
            self.component_command("receiver", "--generation", str(generation)),
        )
        wait_for(
            f"receiver generation {generation} readiness",
            lambda: (
                self.runtime.joinpath(f"receiver-{generation}.json").exists()
                and self.runtime.joinpath("bridge.sock").exists()
            ),
            bool,
            10,
        )
        return terminal

    def phase_initial_unavailable_and_slots(self) -> tuple[dict[str, Any], dict[str, Any]]:
        first = self.start_case("offline_success", "success")
        self.wait_provider(
            lambda row: (
                row.get("event") == "response_sent"
                and row.get("scenario") == "success"
                and row.get("side") == "parent"
            ),
            "initial success while receiver absent",
        )
        receiver = self.start_receiver(1)
        first_done = self.wait_case_frame(
            first,
            "initial producer reconnect/backfill",
            lambda frame: any(
                row.get("role") == "root" and row.get("state") == "done"
                for row in frame.get("sessions", [])
            ),
        )
        second = self.start_case("second_success", "success")
        second_done = self.wait_case_frame(
            second,
            "second independent root done",
            lambda frame: any(
                row.get("role") == "root" and row.get("state") == "done"
                for row in frame.get("sessions", [])
            ),
        )
        before = self.status()
        slots = assert_distinct_stable_slots(before, before)
        self.launches["success"] = second_done["launchId"]
        self.checkpoints["initialReceiverUnavailableReconnect"] = {
            "launchId": first_done["launchId"],
            "sequence": first_done["sequence"],
            "connected": True,
        }
        self.checkpoints["independentSlots"] = slots
        return receiver, before

    def phase_restart_and_kill(
        self, receiver: dict[str, Any], before: dict[str, Any]
    ) -> dict[str, Any]:
        self.orca.close(receiver["handle"])
        offline = wait_for(
            "registry fallback after receiver stop",
            self.status,
            lambda value: (
                value.get("source") == "registry"
                and value.get("status", {}).get("launches")
                and all(
                    not row.get("connected") and row.get("state") == "unknown"
                    for row in value["status"]["launches"]
                )
            ),
            15,
        )
        receiver2 = self.start_receiver(2)
        after = wait_for(
            "receiver restart backfill",
            self.status,
            lambda value: (
                value.get("source") == "live"
                and len(value.get("status", {}).get("launches", [])) >= 2
                and all(row.get("connected") for row in value["status"]["launches"][:2])
            ),
            30,
        )
        assert_distinct_stable_slots(before, after)
        self.checkpoints["receiverRestart"] = {
            "offline": [
                {"launchId": row["launchId"], "slot": row["slot"], "state": row["state"]}
                for row in offline["status"]["launches"]
            ],
            "backfilled": [
                {
                    "launchId": row["launchId"],
                    "slot": row["slot"],
                    "state": row["state"],
                    "connected": row["connected"],
                }
                for row in after["status"]["launches"][:2]
            ],
        }
        victim_id = next(iter(self.checkpoints["independentSlots"]))
        victim = next(frame for frame in reversed(self.frames()) if frame["launchId"] == victim_id)
        victim_pid = int(victim["pid"])
        if victim["root"]["terminalHandle"] not in self.orca.owned:
            raise AuditFailure("REQ-LIFE-3 producer PID was not owned by this run")
        os.kill(victim_pid, signal.SIGKILL)
        unknown = wait_for(
            "killed producer to become unknown",
            self.status,
            lambda value: any(
                row["launchId"] == victim_id and not row["connected"] and row["state"] == "unknown"
                for row in value.get("status", {}).get("launches", [])
            ),
            15,
        )
        row = next(row for row in unknown["status"]["launches"] if row["launchId"] == victim_id)
        self.checkpoints["producerKillUnknown"] = {
            "launchId": victim_id,
            "pid": victim_pid,
            "slot": row["slot"],
            "state": row["state"],
        }
        return receiver2

    def phase_outcomes_duplicate(self) -> None:
        failed = self.start_case("failed", "failed")
        failed_frame = self.wait_case_frame(
            failed,
            "failed root state",
            lambda frame: any(
                row.get("role") == "root" and row.get("state") == "failed"
                for row in frame.get("sessions", [])
            ),
        )
        self.launches["failed"] = failed_frame["launchId"]
        slow = self.start_case("cancel", "slow")
        working = self.wait_case_frame(
            slow,
            "slow root working",
            lambda frame: any(
                row.get("role") == "root" and row.get("state") == "working"
                for row in frame.get("sessions", [])
            ),
        )
        self.orca.send(slow["terminal"]["handle"], "\x03")
        cancelled = self.wait_case_frame(
            slow,
            "interrupted root cancelled",
            lambda frame: any(
                row.get("role") == "root" and row.get("state") == "cancelled"
                for row in frame.get("sessions", [])
            ),
        )
        if working["launchId"] != cancelled["launchId"]:
            raise AuditFailure("REQ-STATE-3 cancellation changed launch identity")
        self.launches["cancel"] = cancelled["launchId"]
        self.checkpoints["outcomes"] = assert_outcomes(self.frames(), self.launches)

        duplicate = self.start_case("duplicate", "duplicate")
        duplicate_done = self.wait_case_frame(
            duplicate,
            "duplicate-scope launch done",
            lambda frame: any(
                row.get("role") == "root" and row.get("state") == "done"
                for row in frame.get("sessions", [])
            ),
        )
        frames = [
            frame
            for frame in self.frames()
            if frame.get("root", {}).get("terminalHandle") == duplicate["terminal"]["handle"]
        ]
        publishers = {frame["producerId"] for frame in frames}
        launches = {frame["launchId"] for frame in frames}
        if publishers != {duplicate_done["producerId"]} or launches != {duplicate_done["launchId"]}:
            raise AuditFailure(
                f"REQ-INSTALL-2 duplicate user/project hooks published more than once: "
                f"publishers={publishers}, launches={launches}"
            )
        self.checkpoints["duplicateHook"] = {
            "publisherCount": 1,
            "launchCount": 1,
            "launchId": duplicate_done["launchId"],
        }

    def phase_mass(self) -> None:
        mass = self.start_case("mass", "mass")

        def desired(frame: dict[str, Any]) -> bool:
            states = [row.get("state") for row in frame.get("sessions", [])]
            return (
                len(states) == 12
                and states.count("working") == 10
                and states.count("waiting") == 1
                and states.count("done") == 1
            )

        frame = wait_for(
            "10 working + 1 waiting + 1 done transition",
            lambda: self.historical_terminal_frame(mass["terminal"], desired),
            lambda value: value is not None,
            120,
        )
        self.checkpoints["massWaitingOrange"] = assert_mass_waiting(
            frame, self.replay_color(frame)
        )

    def phase_decisions(self) -> None:
        decisions = self.start_case("decisions", "decisions_two")
        handle = decisions["terminal"]["handle"]
        self.wait_provider(
            lambda row: (
                row.get("event") == "parent_question_requested" and row.get("request_id") == "req_1"
            ),
            "first parent question",
        )
        wait_for("first question UI", lambda: "req_1" in self.orca.read(handle), bool, 30)
        before_first_answer = self.latest_terminal_frame(decisions["terminal"])
        if before_first_answer is None:
            raise AuditFailure("REQ-DECISION-1 no current frame before first answer")
        initial_pending_children = {
            row.get("sessionId")
            for row in before_first_answer.get("sessions", [])
            if row.get("role") == "child" and int(row.get("pendingDecisions", 0)) == 1
        }
        if len(initial_pending_children) != 2:
            raise AuditFailure(
                "REQ-DECISION-1 expected two actual pending decision children before first answer"
            )
        self.orca.send(handle, "", enter=True)
        self.wait_provider(
            lambda row: (
                row.get("event") == "child_answer_consumed" and row.get("request_id") == "req_1"
            ),
            "first child answer consumption",
        )
        between = self.wait_case_frame(
            decisions,
            "second decision remains waiting",
            lambda frame: remaining_child_decision(frame, initial_pending_children) is not None,
            min_sequence=int(before_first_answer["sequence"]),
        )
        remaining_child_id = remaining_child_decision(between, initial_pending_children)
        self.wait_provider(
            lambda row: (
                row.get("event") == "parent_question_requested" and row.get("request_id") == "req_2"
            ),
            "second parent question",
        )
        wait_for("second question UI", lambda: "req_2" in self.orca.read(handle), bool, 30)
        self.orca.send(handle, "", enter=True)
        done = self.wait_case_frame(
            decisions,
            "both decisions complete",
            lambda frame: (
                any(
                    row.get("role") == "root" and row.get("state") == "done"
                    for row in frame.get("sessions", [])
                )
                and all(
                    int(row.get("pendingAsks", 0)) + int(row.get("pendingDecisions", 0)) == 0
                    for row in frame.get("sessions", [])
                )
            ),
            120,
        )
        child_ids = {
            row["sessionId"]
            for frame in self.frames()
            if frame.get("launchId") == done["launchId"]
            for row in frame.get("sessions", [])
            if row.get("role") == "child"
        }
        result = assert_decision_correlations(self.provider_rows(), child_ids)
        if remaining_child_id not in result["actualChildIds"]:
            raise AuditFailure("REQ-DECISION-1 remaining child was not an actual resumed child")
        result["remainingChildAfterFirstAnswer"] = remaining_child_id
        result["betweenAnswersPending"] = sum(
            int(row.get("pendingAsks", 0)) + int(row.get("pendingDecisions", 0))
            for row in between["sessions"]
        )
        self.checkpoints["decisions"] = result

    def phase_root_lifecycle(self) -> None:
        case = self.start_case("root_lifecycle", "success")
        initial = self.wait_case_frame(
            case,
            "initial lifecycle root done",
            lambda frame: any(
                row.get("role") == "root" and row.get("state") == "done"
                for row in frame.get("sessions", [])
            ),
        )
        handle = case["terminal"]["handle"]
        original_root = initial["root"]["sessionId"]
        self.orca.send(handle, "/new", enter=True)
        new_frame = self.wait_case_frame(
            case,
            "new root identity",
            lambda frame: frame.get("root", {}).get("sessionId") != original_root,
        )
        new_root = new_frame["root"]["sessionId"]
        self.orca.send(handle, "[PRODUCT_QA:success]", enter=True)
        self.wait_case_frame(
            case,
            "new root turn done",
            lambda frame: (
                frame.get("root", {}).get("sessionId") == new_root
                and any(
                    row.get("role") == "root" and row.get("state") == "done"
                    for row in frame.get("sessions", [])
                )
            ),
        )
        self.orca.send(handle, "/resume", enter=True)
        wait_for("resume selector", lambda: "Resume Session" in self.orca.read(handle), bool, 30)
        before_resume = self.latest_terminal_frame(case["terminal"])
        if before_resume is None:
            raise AuditFailure("REQ-LIFE-4 no current frame before resume selection")
        # The isolated session directory contains exactly current-new then prior-original.
        # Move one row without turning any displayed/session data into a command.
        self.orca.send(handle, "\x1b[B")
        self.orca.send(handle, "", enter=True)
        resumed = self.wait_case_frame(
            case,
            "original root resumed",
            lambda frame: frame.get("root", {}).get("sessionId") == original_root,
            45,
            min_sequence=int(before_resume["sequence"]),
        )
        self.orca.send(handle, "[PRODUCT_QA:success]", enter=True)
        self.wait_case_frame(
            case,
            "resumed root turn done",
            lambda frame: (
                frame.get("sequence", 0) > resumed.get("sequence", 0)
                and frame.get("root", {}).get("sessionId") == original_root
                and any(
                    row.get("role") == "root" and row.get("state") == "done"
                    for row in frame.get("sessions", [])
                )
            ),
        )
        self.orca.send(handle, "/exit", enter=True)
        self.wait_case_frame(
            case, "graceful root closure", lambda frame: frame.get("closed") is True
        )
        self.checkpoints["rootLifecycle"] = assert_root_lifecycle(
            self.frames(), initial["launchId"]
        )

    def validate_hook_and_panes(self) -> None:
        installed = []
        for case in self.cases.values():
            case_dir = Path(case["case"])
            hooks = list((case_dir / "agent" / ".orca-keychron" / "releases").glob("*/gjc_hook.ts"))
            if len(hooks) != 1:
                raise AuditFailure(
                    f"REQ-INSTALL-1 expected one immutable installed hook in {case_dir}"
                )
            installed.append(sha256(hooks[0]))
        source_hash = sha256(PRODUCT_SOURCE / "assets" / "gjc_hook.ts")
        if set(installed) != {source_hash}:
            raise AuditFailure(
                f"REQ-INSTALL-1 installed hook hash differs from product asset: {set(installed)} != {source_hash}"
            )
        for case in self.cases.values():
            frame = self.latest_terminal_frame(case["terminal"])
            terminal = case["terminal"]
            if (
                frame is None
                or frame["root"]["terminalHandle"] != terminal["handle"]
                or frame["root"]["paneKey"] != terminal["paneKey"]
            ):
                raise AuditFailure(
                    f"REQ-IDENTITY-1 actual pane identity mismatch for {case['case']}"
                )
        self.checkpoints["installedHook"] = {
            "sourceSha256": source_hash,
            "installedSha256": min(set(installed)),
        }

    def execute(self) -> dict[str, Any]:
        prepare_runtime(self.runtime)
        self.setup_python()
        gjc_version = run([shutil.which("gjc") or "gjc", "--version"], cwd=REPO).stdout.strip()
        if gjc_version != "gjc/0.16.4":
            raise AuditFailure(f"REQ-RUNTIME-1 requires gjc/0.16.4, got {gjc_version}")
        self.checkpoints["parentDecisionFixture"] = self.validate_parent_fixture_contract()
        self.start_provider()
        receiver, before = self.phase_initial_unavailable_and_slots()
        self.phase_restart_and_kill(receiver, before)
        self.phase_outcomes_duplicate()
        self.phase_mass()
        self.phase_decisions()
        self.phase_root_lifecycle()
        self.validate_hook_and_panes()
        source_after = product_source_hash()
        if source_after != self.source_before:
            raise AuditFailure(
                f"REQ-PROVENANCE-1 product source changed during run: "
                f"{self.source_before} -> {source_after}"
            )
        frames = self.frames()
        evidence = {
            "schemaVersion": 1,
            "verdict": "pass",
            "runtime": {"gjcVersion": gjc_version, "orcaAppVersion": orca_version()},
            "provenance": {
                "productSourceBefore": self.source_before,
                "productSourceAfter": source_after,
                "wheelSha256": sha256(self.wheel) if self.wheel else None,
                "productHarnessSha256": sha256(PRODUCT_HARNESS),
                "parentDecisionsFixtureSha256": sha256(PARENT_FIXTURE),
                "runnerSha256": sha256(Path(__file__)),
                "runtimeComponentsSha256": sha256(COMPONENTS),
            },
            "requirements": self.checkpoints,
            "actualPaneIdentities": [
                {
                    "case": name,
                    "terminalHandle": case["terminal"]["handle"],
                    "paneKey": case["terminal"]["paneKey"],
                }
                for name, case in self.cases.items()
            ],
            "wire": {
                "frameCount": len(frames),
                "finalFrames": [only_metadata_frame(frame) for frame in frames[-12:]],
                "contentRecorded": False,
            },
            "limitations": {
                "realModelCompliance": "unproven",
                "physicalKeyboardAndHid": "unproven and not exercised",
                "globalInstallOrService": "not exercised",
                "supportedRuntime": "GJC 0.16.4 only",
            },
        }
        return evidence


def orca_version() -> str:
    result = run(["orca", "status", "--json"], cwd=REPO)
    value = json.loads(result.stdout)
    return value["result"]["runtime"]["appVersion"]


def write_evidence(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--keep-runtime", action="store_true")
    args = parser.parse_args()
    runtime = args.runtime or Path("/private/tmp") / ("gjc-e2e-audit-" + uuid.uuid4().hex[:12])
    if not str(runtime).startswith("/private/tmp/"):
        parser.error("--runtime must use canonical /private/tmp to satisfy GJC storage guards")
    if runtime.exists():
        parser.error("--runtime must not already exist")
    audit = Audit(runtime, args.evidence, args.wheel.resolve() if args.wheel else None)
    started = time.monotonic()
    evidence: dict[str, Any]
    code = 0
    try:
        evidence = audit.execute()
    except Exception as exc:  # noqa: BLE001 - failures are serialized before cleanup
        evidence = {
            "schemaVersion": 1,
            "verdict": "fail",
            "failureType": type(exc).__name__,
            "failure": str(exc),
            "provenance": {
                "productSourceBefore": audit.source_before,
                "productSourceAfter": product_source_hash(),
                "wheelSha256": sha256(audit.wheel)
                if audit.wheel and audit.wheel.exists()
                else None,
            },
            "limitations": {
                "realModelCompliance": "unproven",
                "physicalKeyboardAndHid": "unproven and not exercised",
            },
        }
        code = 1
    finally:
        cleanup_errors = audit.orca.close_all()
        try:
            cleanup = audit.verify_cleanup()
        except Exception as exc:  # noqa: BLE001 - preserve the primary audit result
            cleanup = {
                "ownedTerminalHandles": sorted(audit.orca.terminals),
                "allOwnedTerminalsClosed": False,
                "noOwnedProcessesRemain": False,
                "noOwnedListenersRemain": False,
                "errors": [f"cleanup verification failed: {exc}"],
            }
        cleanup["errors"] = cleanup_errors + cleanup["errors"]
        cleanup["runtimeRemoved"] = False
        if not args.keep_runtime:
            try:
                shutil.rmtree(runtime, ignore_errors=False)
                cleanup["runtimeRemoved"] = True
            except OSError as exc:
                cleanup["errors"].append(f"runtime removal failed: {exc}")
        if cleanup["errors"]:
            evidence["verdict"] = "fail"
            code = 1
        evidence["cleanup"] = cleanup
        evidence["elapsedSeconds"] = round(time.monotonic() - started, 3)
        write_evidence(args.evidence, evidence)
    print(json.dumps({"verdict": evidence["verdict"], "evidence": str(args.evidence)}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
