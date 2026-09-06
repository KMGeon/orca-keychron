import errno
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
from test_gjc_protocol import frame

from orca_keychron_gjc import gjc_source
from orca_keychron_gjc.gjc_protocol import MAX_FRAME_BYTES, GjcProtocolError
from orca_keychron_gjc.gjc_source import GjcStatusSource, request_control


def eventually(check, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.01)
    assert check()


@pytest.fixture
def endpoint():
    # macOS sockaddr_un is limited to 104 bytes, including the terminating NUL.
    with tempfile.TemporaryDirectory(prefix="gjc-", dir="/tmp") as directory:
        yield Path(directory) / "bridge.sock"


@pytest.fixture
def source(endpoint):
    receiver = GjcStatusSource(endpoint, ["orca"], max_slots=2,
                               registry_path=endpoint.parent / "registry.json")
    receiver.start()
    try:
        yield receiver
    finally:
        receiver.stop()


@pytest.fixture
def exited_pid():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=3)
    return child.pid


def connect(source):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(2)
    client.connect(str(source.socket_path))
    return client


def send(client, row):
    client.sendall(json.dumps(row).encode() + b"\n")


def test_fragmentation_coalescing_disconnect_and_reconnect(source):
    row = frame("waiting")
    encoded = json.dumps(row).encode() + b"\n"
    with connect(source) as client:
        client.sendall(encoded[:20])
        assert source.indicators() == []
        client.sendall(encoded[20:])
        eventually(lambda: len(source.indicators()) == 1)
        assert source.indicators()[0].state == "waiting"
        row.update(sequence=5)
        row["sessions"][0]["state"] = "done"
        old = dict(row, sequence=2)
        client.sendall(json.dumps(row).encode() + b"\n" + json.dumps(old).encode() + b"\n")
        eventually(lambda: source.indicators()[0].state == "done")
        assert source.status()["launches"][0]["sequence"] == 5
    eventually(lambda: source.indicators()[0].state == "unknown")
    with connect(source) as client:
        row["sequence"] = 6
        send(client, row)
        eventually(lambda: source.indicators()[0].state == "done")
        assert source.indicators()[0].slot == 0


def test_new_connection_supersedes_old_without_false_disconnect(source):
    row = frame()
    with connect(source) as old, connect(source) as new:
        send(old, row)
        eventually(lambda: len(source.indicators()) == 1)
        row["sequence"] = 2
        send(new, row)
        eventually(lambda: source.status()["launches"][0]["sequence"] == 2)
        assert old.recv(1) == b""
        old.close()
        assert request_control(source.socket_path)["status"]["launches"][0]["connected"]


def test_status_clear_and_shared_roots(source, exited_pid):
    rows = [frame(), frame(), frame()]
    rows[0]["pid"] = exited_pid
    clients = [connect(source) for _ in rows]
    try:
        for client, row in zip(clients, rows):
            send(client, row)
        eventually(lambda: len(source.status()["launches"]) == 3)
        result = request_control(source.socket_path)
        assert result["ok"] is True
        assert len(result["status"]["overflow"]) == 1
        launch = rows[0]["launchId"]
        before = source.tracker.registry_path.read_bytes()
        rejected = request_control(source.socket_path, "clear", launch)
        assert rejected["error"] == {"code": "clear_refused", "reason": "connected"}
        assert len(rejected["status"]["overflow"]) == 1
        assert source.tracker.registry_path.read_bytes() == before
        assert not source.tracker._retired
        clients[0].close()
        eventually(lambda: rows[0]["producerId"] not in source._owners)
        cleared = request_control(source.socket_path, "clear", launch)
        assert cleared["cleared"] is True
        assert len(cleared["status"]["launches"]) == 2
        assert not cleared["status"]["overflow"]
        before = source.tracker.registry_path.read_bytes()
        assert request_control(source.socket_path, "clear", launch)["cleared"] is False
        assert source.tracker.registry_path.read_bytes() == before
    finally:
        for client in clients:
            client.close()


def test_stop_restart_restores_unknown_and_new_complete_snapshot(source):
    row = frame("done")
    with connect(source) as client:
        send(client, row)
        eventually(lambda: len(source.indicators()) == 1)
        thread = source._thread
        source.stop()
        assert not thread.is_alive()
        assert not source.socket_path.exists()
        assert source.indicators()[0].state == "unknown"
    restarted = GjcStatusSource(source.socket_path, ["orca"], max_slots=2,
                                registry_path=source.tracker.registry_path)
    assert restarted.indicators()[0].state == "unknown"
    restarted.start()
    try:
        with connect(restarted) as client:
            row["sequence"] = 9
            send(client, row)
            eventually(lambda: restarted.indicators()[0].state == "done")
            assert restarted.indicators()[0].slot == 0
    finally:
        restarted.stop()


def test_second_receiver_never_unlinks_live_socket(source):
    inode = source.socket_path.stat().st_ino
    second = GjcStatusSource(source.socket_path, ["orca"])
    with pytest.raises((OSError, RuntimeError)):
        second.start()
    second.stop()
    assert source.socket_path.stat().st_ino == inode
    assert request_control(source.socket_path)["ok"]
    assert source.socket_path.stat().st_mode & 0o777 == 0o600


def test_stale_socket_recovery_and_unowned_file_refusal(endpoint):
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(endpoint))
    stale.close()
    source = GjcStatusSource(endpoint, ["orca"])
    source.start()
    assert request_control(endpoint)["ok"]
    source.stop()
    endpoint.write_text("keep")
    with pytest.raises(PermissionError):
        source.start()
    assert endpoint.read_text() == "keep"


@pytest.mark.parametrize("data", [b'{"type":"snapshot"}\n', b'\xff\n', b'[]\n',
                                  b'{"version":1,"version":1}\n'])
def test_bad_frame_drops_only_its_client(source, data):
    with connect(source) as client:
        client.sendall(data)
        assert client.recv(1) == b""
    assert request_control(source.socket_path)["ok"]


def test_oversize_line_buffer_is_bounded(source):
    with connect(source) as client:
        try:
            client.sendall(b"x" * (MAX_FRAME_BYTES + 10000))
            assert client.recv(1) == b""
        except OSError as exc:
            # macOS may detect the receiver close at different send boundaries.
            assert exc.errno in (errno.ECONNRESET, errno.EPIPE, errno.ENOTCONN)
    eventually(lambda: not source._clients)
    assert request_control(source.socket_path)["ok"]


def test_idle_and_max_clients_bounded(source, monkeypatch):
    monkeypatch.setattr(gjc_source, "MAX_CLIENTS", 2)
    monkeypatch.setattr(gjc_source, "CLIENT_TIMEOUT", 0.5)
    with connect(source), connect(source):
        eventually(lambda: len(source._clients) == 2)
        with connect(source) as extra:
            assert extra.recv(1) == b""
        eventually(lambda: len(source._clients) == 0)
    assert request_control(source.socket_path)["ok"]


def test_receiver_surfaces_storage_failure_and_marks_unknown(source, monkeypatch):
    row = frame()
    with connect(source) as client:
        send(client, row)
        eventually(lambda: len(source.indicators()) == 1)
        def fail():
            raise OSError("disk failure")
        monkeypatch.setattr(source.tracker, "_persist", fail)
        row["sequence"] = 2
        send(client, row)
        eventually(lambda: source._error is not None)
        with pytest.raises(RuntimeError, match="receiver failed"):
            source.indicators()
        eventually(lambda: not source._thread.is_alive())
        assert source.tracker.indicators()[0].state == "unknown"


@pytest.mark.parametrize("response", [
    b'{}\n', b'{"version":true,"type":"response","ok":true,"status":{}}\n',
    b'{"version":1,"type":"response","ok":true,"status":{}}\n',
    b'{}\n{}\n', b'{"ok":true,"ok":false}\n', b'{}',
])
def test_control_client_rejects_invalid_response(endpoint, response):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(endpoint))
        server.listen()
        def respond():
            client, _ = server.accept()
            with client:
                client.recv(4096)
                client.sendall(response)
        thread = threading.Thread(target=respond)
        thread.start()
        try:
            with pytest.raises(GjcProtocolError):
                request_control(endpoint)
        finally:
            thread.join(2)


def test_control_argument_validation(endpoint):
    for kwargs in ({"command": "delete"}, {"command": "clear"},
                   {"launch_id": "bad"}, {"timeout": 0}, {"timeout": float("nan")}):
        with pytest.raises(ValueError):
            request_control(endpoint, **kwargs)


def test_lease_uses_local_receive_clock_and_retains_slot(source):
    row = frame("done")
    with connect(source) as client:
        send(client, row)
        eventually(lambda: len(source.indicators()) == 1)
        received = source.tracker._launches[row["launchId"]].received_at
        assert source.indicators(received + 7.9)[0].state == "done"
        assert source.indicators(received + 8)[0].state == "unknown"
        assert source.indicators(received + 1000)[0].slot == 0


def test_explicit_close_releases_slot_without_resurrection(source):
    row = frame()
    with connect(source) as client:
        send(client, row)
        eventually(lambda: len(source.indicators()) == 1)
        row.update(sequence=2, closed=True, sessions=[])
        send(client, row)
        eventually(lambda: source.indicators() == [])
        row.update(sequence=3, closed=False, sessions=frame()["sessions"])
        send(client, row)
        assert request_control(source.socket_path)["status"]["launches"] == []


def test_stop_preserves_replacement_path_and_restart_is_supported(source):
    source.socket_path.unlink()
    source.socket_path.write_text("replacement")
    source.stop()
    assert source.socket_path.read_text() == "replacement"
    source.socket_path.unlink()
    source.start()
    source.start()  # Idempotent start does not replace the running thread.
    assert request_control(source.socket_path)["ok"]


def test_initial_storage_failure_never_leaves_connected_launch(source, monkeypatch):
    def fail():
        raise OSError("disk failure")
    monkeypatch.setattr(source.tracker, "_persist", fail)
    with connect(source) as client:
        send(client, frame("done"))
        eventually(lambda: source._error is not None)
        eventually(lambda: not source._thread.is_alive())
    assert source.tracker.indicators()[0].state == "unknown"


def test_control_timeout_is_bounded(endpoint):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(endpoint))
        server.listen()
        started = time.monotonic()
        with pytest.raises(TimeoutError) as raised:
            request_control(endpoint, timeout=0.05)
        assert type(raised.value) is TimeoutError
        assert time.monotonic() - started < 1


def test_shared_registry_refuses_distinct_endpoint_without_mutation(source):
    registry = source.tracker.registry_path
    second = GjcStatusSource(source.socket_path.with_name("second.sock"), ["orca"],
                             registry_path=registry)
    row = frame()
    with connect(source) as client:
        send(client, row)
        eventually(lambda: len(source.indicators()) == 1)
        send(client, dict(row, sequence=2, closed=True, sessions=[]))
        eventually(lambda: not source.indicators())
        before = registry.read_bytes()
        lock = Path(str(registry) + ".lock")
        inode = lock.stat().st_ino
        with pytest.raises(RuntimeError, match="already owns this registry"):
            second.start()
        second.stop()
        assert not second.socket_path.exists()
        assert registry.read_bytes() == before
        assert lock.stat().st_ino == inode
        assert lock.stat().st_mode & 0o777 == 0o600
        assert request_control(source.socket_path)["ok"]
        # Offline inspection does not contend for writer ownership.
        assert GjcStatusSource(second.socket_path, [], registry_path=registry).status()[
            "launches"
        ] == []


def test_distinct_registries_allow_distinct_live_endpoints(source):
    second = GjcStatusSource(source.socket_path.with_name("second.sock"), [],
                             registry_path=source.socket_path.parent / "other.json")
    second.start()
    try:
        with connect(source) as first_client, connect(second) as second_client:
            first, other = frame(), frame()
            send(first_client, first)
            send(second_client, other)
            eventually(lambda: len(source.indicators()) == len(second.indicators()) == 1)
            assert request_control(source.socket_path)["status"]["launches"][0][
                "launchId"
            ] == first["launchId"]
            assert request_control(second.socket_path)["status"]["launches"][0][
                "launchId"
            ] == other["launchId"]
    finally:
        second.stop()


@pytest.mark.parametrize("previously_started", [False, True])
def test_start_reloads_stale_registry_and_preserves_slots_and_tombstones(
    endpoint, previously_started, exited_pid,
):
    registry = endpoint.parent / "registry.json"
    stale = GjcStatusSource(endpoint, [], max_slots=2, registry_path=registry)
    if previously_started:
        stale.start()
        stale.stop()
    writer = GjcStatusSource(endpoint.with_name("writer.sock"), [], max_slots=2,
                             registry_path=registry)
    rows = [frame(), frame()]
    rows[0]["pid"] = exited_pid
    writer.start()
    try:
        for row in rows:
            with connect(writer) as client:
                send(client, row)
                eventually(lambda row=row: any(r.launch_id == row["launchId"]
                                       for r in writer.indicators()))
        eventually(lambda: rows[0]["producerId"] not in writer._owners)
        assert request_control(writer.socket_path, "clear", rows[0]["launchId"])["cleared"]
    finally:
        writer.stop()
    stale.start()
    try:
        assert [(r.launch_id, r.slot, r.state) for r in stale.indicators()] == [
            (rows[1]["launchId"], 1, "unknown"),
        ]
        with connect(stale) as client:
            rows[0]["sequence"] = 10
            send(client, rows[0])
            # A subsequent frame on the same stream proves the retired frame was processed.
            new = frame()
            send(client, new)
            eventually(lambda: len(stale.indicators()) == 2)
        saved = json.loads(registry.read_text())
        assert saved["retired"] == [[rows[0]["launchId"], rows[0]["producerId"]]]
        assert {r["launchId"]: r["slot"] for r in saved["launches"]} == {
            rows[1]["launchId"]: 1, new["launchId"]: 0,
        }
    finally:
        stale.stop()


def test_socket_collision_releases_new_registry_ownership(source):
    registry = source.socket_path.parent / "other.json"
    colliding = GjcStatusSource(source.socket_path, [], registry_path=registry)
    with pytest.raises(RuntimeError, match="already owns this socket"):
        colliding.start()
    replacement = GjcStatusSource(source.socket_path.with_name("other.sock"), [],
                                  registry_path=registry)
    replacement.start()
    try:
        assert request_control(replacement.socket_path)["ok"]
        assert request_control(source.socket_path)["ok"]
    finally:
        replacement.stop()
        colliding.stop()


@pytest.mark.parametrize("unsafe", ["symlink", "public"])
def test_registry_lock_refuses_unsafe_file(endpoint, unsafe):
    registry = endpoint.parent / "registry.json"
    lock = Path(str(registry) + ".lock")
    if unsafe == "symlink":
        target = endpoint.parent / "keep"
        target.write_text("keep")
        lock.symlink_to(target)
    else:
        lock.write_text("keep")
        lock.chmod(0o644)
    source = GjcStatusSource(endpoint, [], registry_path=registry)
    with pytest.raises(OSError):
        source.start()
    source.stop()
    assert lock.read_text() == "keep"
    assert not registry.exists()
    assert not endpoint.exists()


def test_failed_restore_releases_registry_lock(endpoint):
    registry = endpoint.parent / "registry.json"
    source = GjcStatusSource(endpoint, [], registry_path=registry)
    registry.write_text("invalid")
    registry.chmod(0o600)
    with pytest.raises(ValueError):
        source.start()
    registry.unlink()
    replacement = GjcStatusSource(endpoint, [], registry_path=registry)
    replacement.start()
    try:
        assert request_control(endpoint)["ok"]
    finally:
        replacement.stop()


def test_receiver_failure_releases_registry_ownership(source, monkeypatch):
    row = frame()
    with connect(source) as client:
        send(client, row)
        eventually(lambda: len(source.indicators()) == 1)
        def fail():
            raise OSError("disk failure")
        monkeypatch.setattr(source.tracker, "_persist", fail)
        send(client, dict(row, sequence=2))
        eventually(lambda: not source._thread.is_alive())
    replacement = GjcStatusSource(source.socket_path.with_name("recovered.sock"), [],
                                  registry_path=source.tracker.registry_path)
    replacement.start()
    try:
        assert replacement.indicators()[0].launch_id == row["launchId"]
        assert replacement.indicators()[0].state == "unknown"
        assert request_control(replacement.socket_path)["ok"]
    finally:
        replacement.stop()


def test_process_crash_releases_lock_and_preserves_registry(endpoint, exited_pid):

    registry = endpoint.parent / "registry.json"
    program = """
import sys
import time
from orca_keychron_gjc.gjc_source import GjcStatusSource
source = GjcStatusSource(sys.argv[1], [], max_slots=2, registry_path=sys.argv[2])
source.start()
print('ready', flush=True)
while True:
    time.sleep(1)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", program, str(endpoint), str(registry)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    rows = [frame(), frame()]
    rows[0]["pid"] = exited_pid
    try:
        eventually(lambda: endpoint.exists() or process.poll() is not None)
        assert process.poll() is None
        for row in rows:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(str(endpoint))
                send(client, row)
                eventually(lambda row=row: any(r["launchId"] == row["launchId"] for r in
                                       request_control(endpoint)["status"]["launches"]))
        eventually(lambda: all(not r["connected"] for r in
                               request_control(endpoint)["status"]["launches"]))
        assert request_control(endpoint, "clear", rows[0]["launchId"])["cleared"]
        process.kill()
        process.wait(timeout=3)
        before = registry.read_bytes()
        lock = Path(str(registry) + ".lock")
        inode = lock.stat().st_ino
        recovered = GjcStatusSource(endpoint, [], max_slots=2, registry_path=registry)
        recovered.start()
        try:
            assert registry.read_bytes() == before
            assert lock.stat().st_ino == inode
            assert [(r.launch_id, r.slot, r.state) for r in recovered.indicators()] == [
                (rows[1]["launchId"], 1, "unknown"),
            ]
            with connect(recovered) as client:
                send(client, dict(rows[0], sequence=10))
                new = frame()
                send(client, new)
                eventually(lambda: len(recovered.indicators()) == 2)
            saved = json.loads(registry.read_text())
            assert saved["retired"] == [[rows[0]["launchId"], rows[0]["producerId"]]]
            assert {r["launchId"]: r["slot"] for r in saved["launches"]} == {
                rows[1]["launchId"]: 1, new["launchId"]: 0,
            }
        finally:
            recovered.stop()
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=3)


def test_live_clear_refusal_preserves_heartbeat_even_after_lease_expiry(source, monkeypatch):
    row = dict(frame(), pid=os.getpid())
    with connect(source) as client:
        send(client, row)
        eventually(lambda: len(source.indicators()) == 1)
        monkeypatch.setattr(source.tracker, "lease_seconds", 0.01)
        eventually(lambda: not source.indicators()[0].connected)
        before = source.tracker.registry_path.read_bytes()
        result = request_control(source.socket_path, "clear", row["launchId"])
        assert result["ok"] is False and result["cleared"] is False
        assert result["error"]["reason"] == "connected"
        assert source.tracker.registry_path.read_bytes() == before
        assert not source.tracker._retired
        monkeypatch.setattr(source.tracker, "lease_seconds", 8)
        row["sequence"] = 2
        row["sessions"][0]["state"] = "done"
        send(client, row)
        eventually(lambda: source.indicators()[0].state == "done")
        assert source.indicators()[0].slot == 0


def test_disconnected_owned_child_only_clears_after_exit(source):
    child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"],
                             stdin=subprocess.PIPE)
    try:
        row = dict(frame(), pid=child.pid)
        with connect(source) as client:
            send(client, row)
            eventually(lambda: len(source.indicators()) == 1)
        eventually(lambda: row["producerId"] not in source._owners)
        before = source.tracker.registry_path.read_bytes()
        result = request_control(source.socket_path, "clear", row["launchId"])
        assert result["error"]["reason"] == "process_alive"
        assert source.tracker.registry_path.read_bytes() == before
        assert not source.tracker._retired
        child.stdin.close()
        child.wait(timeout=3)
        result = request_control(source.socket_path, "clear", row["launchId"])
        assert result["ok"] is True and result["cleared"] is True
        assert result["status"]["launches"] == []
        assert source.tracker._retired == {row["launchId"]: row["producerId"]}
    finally:
        if child.poll() is None:
            child.stdin.close()
            child.wait(timeout=3)


@pytest.mark.parametrize("failure", [PermissionError(errno.EPERM, "denied"),
                                     OSError(errno.EIO, "ambiguous"), OverflowError(), ValueError()])
def test_disconnected_ambiguous_pid_refuses_without_mutation(source, monkeypatch, failure):
    row = dict(frame(), pid=os.getpid())
    with connect(source) as client:
        send(client, row)
        eventually(lambda: len(source.indicators()) == 1)
    eventually(lambda: row["producerId"] not in source._owners)
    before = source.tracker.registry_path.read_bytes()

    def fail(pid, signal):
        assert (pid, signal) == (row["pid"], 0)
        raise failure

    monkeypatch.setattr(gjc_source.os, "kill", fail)
    result = request_control(source.socket_path, "clear", row["launchId"])
    assert result["error"]["reason"] == "process_death_unconfirmed"
    assert source.tracker.registry_path.read_bytes() == before
    assert not source.tracker._retired


def test_unrepresentable_local_pid_is_not_probed(source, monkeypatch):
    row = dict(frame(), pid=2**40)
    with connect(source) as client:
        send(client, row)
        eventually(lambda: len(source.indicators()) == 1)
    eventually(lambda: row["producerId"] not in source._owners)
    before = source.tracker.registry_path.read_bytes()
    monkeypatch.setattr(gjc_source.os, "kill", lambda *_: pytest.fail("invalid local PID probed"))
    result = request_control(source.socket_path, "clear", row["launchId"])
    assert result["error"]["reason"] == "process_death_unconfirmed"
    assert source.tracker.registry_path.read_bytes() == before
    assert not source.tracker._retired


@pytest.mark.parametrize("mutation", [
    {"ok": True}, {"cleared": True}, {"ok": 0}, {"extra": 1},
    {"error": "clear_refused"}, {"error": {"code": "clear_refused"}},
    {"error": {"code": "other", "reason": "connected"}},
    {"error": {"code": "clear_refused", "reason": []}},
    {"error": {"code": "clear_refused", "reason": "other"}},
    {"error": {"code": "clear_refused", "reason": "connected", "extra": 1}},
    {"status": {"version": 1, "maxSlots": 2, "launches": [], "overflow": [1]}},
])
def test_control_client_strictly_rejects_malformed_clear_rejections(endpoint, mutation):
    response = {"version": 1, "type": "response", "ok": False, "cleared": False,
                "error": {"code": "clear_refused", "reason": "connected"},
                "status": {"version": 1, "maxSlots": 2, "launches": [], "overflow": []}}
    response.update(mutation)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(endpoint))
        server.listen()

        def respond():
            client, _ = server.accept()
            with client:
                client.recv(4096)
                client.sendall(json.dumps(response).encode() + b"\n")

        thread = threading.Thread(target=respond)
        thread.start()
        try:
            with pytest.raises(GjcProtocolError):
                request_control(endpoint, "clear", frame()["launchId"])
        finally:
            thread.join(2)
