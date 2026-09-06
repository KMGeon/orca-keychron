"""Product-side components for the GJC audit, run by source or wheel Python.

The provider remains the read-only experiments/gjc-product-qa/harness.py process.
This file imports the installed product for hook installation, receiver, tracker,
and renderer so a final wheel run cannot silently fall back to repository PYTHONPATH.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import signal
import threading
import time
from pathlib import Path
from typing import Any

from orca_keychron.rendering import ORANGE, render_zone
from orca_keychron_gjc import gjc_install
from orca_keychron_gjc.gjc_protocol import parse_snapshot
from orca_keychron_gjc.gjc_source import request_control
from orca_keychron_gjc.gjc_tracker import GjcIndicator, GjcTracker

SELECTOR = "product-qa/fixture"
MODEL = "fixture"
SCENARIOS = {"success", "failed", "slow", "mass", "decisions_two", "duplicate"}
LOCK = threading.Lock()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    with LOCK, path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def prepare(runtime: Path, name: str, scenario: str) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise SystemExit(f"unsupported scenario: {scenario}")
    provider = json.loads((runtime / "provider.json").read_text(encoding="utf-8"))
    case = runtime / "cases" / name
    if case.exists():
        raise SystemExit(f"case already exists: {case}")
    workspace, agent, sessions = case / "workspace", case / "agent", case / "sessions"
    for path in (workspace, agent, sessions, workspace / ".gjc" / "agents"):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    models = {
        "providers": {
            "product-qa": {
                "baseUrl": provider["url"],
                "api": "openai-completions",
                "auth": "none",
                "models": [
                    {
                        "id": MODEL,
                        "name": "Synthetic product integration QA",
                        "contextWindow": 128000,
                        "maxTokens": 4096,
                    }
                ],
            }
        },
        "modelBindings": {"modelRoles": {"default": SELECTOR}},
    }
    write_json(agent / "models.yml", models)
    write_json(
        agent / "config.yml",
        {
            "retry": {"enabled": False, "maxRetries": 0, "requestMaxRetries": 0},
            "task": {"enableLsp": False},
            "notifications": {"enabled": False},
            "telemetry": {"enabled": False},
            "marketplace": {"autoUpdate": False},
        },
    )
    write_json(
        agent / "credential-auto-import-state.json",
        {"lastImportVersion": "0.16.4", "initialImportResolution": "declined"},
    )
    (workspace / "AGENTS.md").write_text(
        "Isolated synthetic product integration QA. Use only the loopback fixture model.\n",
        encoding="utf-8",
    )
    (workspace / ".gjc" / "agents" / "decision-child.md").write_text(
        "---\nname: decision-child\ndescription: Synthetic correlated decision child\n"
        "tools: [read, yield]\nmodel: product-qa/fixture\n---\n"
        "Yield the fixture decision and only consume an exactly correlated resume.\n",
        encoding="utf-8",
    )
    (workspace / ".gjc" / "agents" / "product-child.md").write_text(
        "---\nname: product-child\ndescription: Synthetic product status child\n"
        "tools: [yield, task, subagent]\nmodel: product-qa/fixture\n---\n"
        "Perform only the deterministic loopback fixture action.\n",
        encoding="utf-8",
    )
    socket_path = runtime / "bridge.sock"
    installs = {"user": gjc_install.install(scope="user", agent_dir=agent, socket_path=socket_path)}
    if scenario == "duplicate":
        installs["project"] = gjc_install.install(
            scope="project", project_path=workspace, socket_path=socket_path
        )
    write_json(case / "install-results.json", installs)
    environment = {
        "HOME": str(case / "home"),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "TMPDIR": str(case / "tmp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "GJC_CODING_AGENT_DIR": str(agent),
        "GJC_AGENT_DIR": str(agent),
        "GJC_AUTOMATION": "1",
        "GJC_DISABLE_TELEMETRY": "1",
        "GJC_MODEL_PRESET_REGISTRY_DISABLED": "1",
        "GJC_UI_LANGUAGE": "en",
        "GJC_NO_PTY": "1",
    }
    for directory in (Path(environment["HOME"]), Path(environment["TMPDIR"])):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for key in ("LC_ALL", "TERM", "SHELL"):
        if key in os.environ:
            environment[key] = os.environ[key]
    executable = shutil.which("gjc")
    if not executable:
        raise SystemExit("gjc executable not found")
    command = [
        executable,
        "--model",
        SELECTOR,
        "--no-title",
        "--no-lsp",
        "--no-mcp",
        "--no-rules",
        "--no-pty",
        "--thinking",
        "off",
        "--session-dir",
        str(sessions),
        "--tools",
        "read,ask,task,subagent",
        f"[PRODUCT_QA:{scenario}]",
    ]
    write_json(case / "environment.json", environment)
    write_json(case / "command.json", command)
    direct = (
        "cd "
        + shlex.quote(str(workspace))
        + " && env -i "
        + " ".join(f"{key}={shlex.quote(value)}" for key, value in environment.items())
        + " "
        + " ".join(
            f'{key}="${key}"'
            for key in (
                "ORCA_TERMINAL_HANDLE",
                "ORCA_PANE_KEY",
                "ORCA_TAB_ID",
                "ORCA_WORKTREE_ID",
            )
        )
        + " "
        + shlex.join(command)
    )
    (case / "direct-launch-command.txt").write_text(direct + "\n", encoding="utf-8")
    result = {"case": str(case), "scenario": scenario, "directLaunch": direct}
    print(json.dumps(result), flush=True)
    return result


def receiver(runtime: Path, generation: int) -> None:
    import orca_keychron_gjc.gjc_source as source_module

    original = source_module.parse_snapshot
    wire = runtime / "wire-metadata.jsonl"

    def observed(payload: Any):
        snapshot = original(payload)
        append_jsonl(
            wire,
            {
                "receiverGeneration": generation,
                "observedAt": time.time(),
                "producerId": snapshot.producer_id,
                "launchId": snapshot.launch_id,
                "sequence": snapshot.sequence,
                "pid": snapshot.pid,
                "startedAt": snapshot.started_at,
                "complete": snapshot.complete,
                "closed": snapshot.closed,
                "root": {
                    "sessionId": snapshot.root.session_id,
                    "terminalHandle": snapshot.root.terminal_handle,
                    "paneKey": snapshot.root.pane_key,
                    "worktreeId": snapshot.root.worktree_id,
                },
                "sessions": [
                    {
                        "sessionId": row.session_id,
                        "role": row.role,
                        "state": row.state,
                        "pendingAsks": row.pending_asks,
                        "pendingDecisions": row.pending_decisions,
                    }
                    for row in snapshot.sessions
                ],
            },
        )
        return snapshot

    source_module.parse_snapshot = observed
    source = source_module.GjcStatusSource(
        runtime / "bridge.sock",
        ["orca"],
        max_slots=12,
        registry_path=runtime / "registry.json",
    )
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_args: stop.set())
    source.start()
    write_json(
        runtime / f"receiver-{generation}.json",
        {
            "pid": os.getpid(),
            "generation": generation,
            "socket": str(runtime / "bridge.sock"),
            "wire": str(wire),
        },
    )
    print(json.dumps({"receiverGeneration": generation, "ready": True}), flush=True)
    try:
        while not stop.wait(0.25):
            source.indicators()
    finally:
        source.stop()


def status(runtime: Path) -> dict[str, Any]:
    socket_path, registry = runtime / "bridge.sock", runtime / "registry.json"
    try:
        response = request_control(socket_path, "status")
        return {"source": "live", "status": response["status"]}
    except (OSError, ValueError, RuntimeError):
        return {
            "source": "registry",
            "status": GjcTracker(12, registry).status()
            if registry.exists()
            else {"version": 1, "maxSlots": 12, "launches": [], "overflow": []},
        }


def colors(runtime: Path) -> dict[str, Any]:
    result = status(runtime)
    indicators = [
        GjcIndicator(
            row["launchId"],
            row["state"],
            row["slot"],
            tuple(row["targetPaneKeys"]),
            row["agentCount"],
            row["pendingRequests"],
            row["connected"],
        )
        for row in result["status"]["launches"]
        if row["slot"] is not None
    ]
    zone = tuple(range(12))
    rendered = render_zone(indicators, zone)
    result["colors"] = [
        {
            "launchId": item.launch_id,
            "slot": item.slot,
            "color": list(rendered[zone[item.slot]]),
            "isOrange": rendered[zone[item.slot]] == ORANGE,
        }
        for item in indicators
    ]
    return result


def replay_color(runtime: Path, launch_id: str, sequence: int) -> dict[str, Any]:
    """Replay one observed metadata frame through the installed tracker and renderer.

    The live receiver status may already have advanced by the time the runner inspects
    a transient mass frame.  This operation therefore selects the exact receiver-
    observed sequence and runs only that metadata through the installed product.  It
    never combines historical session counts with a later live renderer state.
    """

    matches = [
        row
        for row in (
            json.loads(line)
            for line in (runtime / "wire-metadata.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if row.get("launchId") == launch_id and row.get("sequence") == sequence
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"expected one observed frame for launch={launch_id} sequence={sequence}; "
            f"got {len(matches)}"
        )
    frame = matches[0]
    payload = {
        "version": 1,
        "type": "snapshot",
        "producerId": frame["producerId"],
        "sequence": frame["sequence"],
        "launchId": frame["launchId"],
        "pid": frame["pid"],
        "startedAt": frame["startedAt"],
        "complete": frame["complete"],
        "closed": frame["closed"],
        "root": frame["root"],
        "sessions": frame["sessions"],
    }
    snapshot = parse_snapshot(payload)
    tracker = GjcTracker(12)
    accepted = tracker.apply(snapshot, now=1.0)
    indicators = tracker.indicators(now=1.0)
    status_row = tracker.status(now=1.0)
    zone = tuple(range(12))
    rendered = render_zone(indicators, zone)
    return {
        "source": "exact-snapshot-installed-product-replay",
        "snapshotIdentity": {
            "producerId": snapshot.producer_id,
            "launchId": snapshot.launch_id,
            "sequence": snapshot.sequence,
        },
        "accepted": accepted,
        "status": status_row,
        "colors": [
            {
                "producerId": snapshot.producer_id,
                "launchId": item.launch_id,
                "sequence": snapshot.sequence,
                "slot": item.slot,
                "color": list(rendered[zone[item.slot]]),
                "isOrange": rendered[zone[item.slot]] == ORANGE,
            }
            for item in indicators
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation", choices=("prepare", "receiver", "status", "colors", "replay-color")
    )
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--name")
    parser.add_argument("--scenario")
    parser.add_argument("--generation", type=int)
    parser.add_argument("--launch-id")
    parser.add_argument("--sequence", type=int)
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare(args.runtime, args.name, args.scenario)
    elif args.operation == "receiver":
        receiver(args.runtime, args.generation)
    elif args.operation == "status":
        print(json.dumps(status(args.runtime), ensure_ascii=False))
    elif args.operation == "colors":
        print(json.dumps(colors(args.runtime), ensure_ascii=False))
    else:
        if not args.launch_id or args.sequence is None:
            parser.error("replay-color requires --launch-id and --sequence")
        print(
            json.dumps(
                replay_color(args.runtime, args.launch_id, args.sequence), ensure_ascii=False
            )
        )


if __name__ == "__main__":
    main()
