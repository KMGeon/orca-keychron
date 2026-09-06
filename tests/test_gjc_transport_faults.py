"""Requirement-driven transport audit; all endpoints/processes are temporary and owned."""

import copy
import json
import queue
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager

import pytest
import test_gjc_source as source_fixtures
from test_gjc_protocol import frame
from test_gjc_source import connect

from orca_keychron_gjc import gjc_source
from orca_keychron_gjc.gjc_protocol import MAX_FRAME_BYTES, GjcProtocolError
from orca_keychron_gjc.gjc_source import GjcStatusSource, request_control

endpoint = source_fixtures.endpoint
source = source_fixtures.source


@pytest.fixture
def observed(source, monkeypatch):
    """Wait for receiver work, never infer processing order from send packet boundaries."""
    events = queue.Queue()
    original = source._frame

    def capture(client, line):
        try:
            return original(client, line)
        finally:
            events.put(line)

    monkeypatch.setattr(source, "_frame", capture)
    return events


def emit(client, row, observed):
    client.sendall(json.dumps(row).encode() + b"\n")
    observed.get(timeout=3)


def healthy(source, observed):
    row = frame("done")
    with connect(source) as client:
        emit(client, row, observed)
        found = next(r for r in request_control(source.socket_path)["status"]["launches"]
                     if r["launchId"] == row["launchId"])
        observed.get(timeout=3)  # status control
        assert found["state"] == "done" and found["connected"]


@pytest.mark.parametrize("payload", [b"", b"\xff", b"[", b"null", b"[]",
                                      b'{"type":"control","version":1,"command":[]}'])
def test_bad_frame_drops_only_offender_and_next_launch_works(source, observed, payload):
    with connect(source) as offender:
        offender.sendall(payload + b"\n")
        observed.get(timeout=3)
        assert offender.recv(1) == b""
    assert source.status()["launches"] == []
    healthy(source, observed)


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-32-le"])
def test_non_utf8_snapshot_is_rejected_without_registry_write(source, observed, encoding):
    with connect(source) as offender:
        offender.sendall(json.dumps(frame()).encode(encoding) + b"\n")
        observed.get(timeout=3)
        assert source.status()["launches"] == []
        assert offender.recv(1) == b""
    assert source.status()["launches"] == []
    assert not source.tracker.registry_path.exists()
    healthy(source, observed)


def test_identity_change_disconnects_original_but_preserves_other_root(source, observed):
    first, second = frame(), frame("waiting")
    with connect(source) as offender, connect(source) as independent:
        emit(offender, first, observed)
        emit(independent, second, observed)
        before = source.tracker.registry_path.read_bytes()
        emit(offender, frame("done"), observed)
        assert offender.recv(1) == b""
        status = request_control(source.socket_path)["status"]
        observed.get(timeout=3)
        rows = {r["launchId"]: r for r in status["launches"]}
        assert len(rows) == 2
        assert rows[first["launchId"]]["state"] == "unknown"
        assert rows[second["launchId"]]["state"] == "waiting"
        assert source.tracker.registry_path.read_bytes() == before
        emit(independent, dict(second, sequence=2), observed)
        assert source.status()["launches"][1]["sequence"] == 2


def test_duplicate_reconnect_cannot_disconnect_live_owner(source, observed):
    row = frame("waiting")
    with connect(source) as owner, connect(source) as duplicate:
        emit(owner, row, observed)
        emit(duplicate, row, observed)
        duplicate.shutdown(socket.SHUT_WR)
        assert duplicate.recv(1) == b""
        assert source.indicators()[0].state == "waiting"
        emit(owner, dict(row, sequence=2), observed)
        assert source.status()["launches"][0]["sequence"] == 2
        with connect(source) as replacement:
            newer = copy.deepcopy(row)
            newer.update(sequence=3)
            newer["sessions"][0]["state"] = "done"
            emit(replacement, newer, observed)
            assert owner.recv(1) == b""
            owner.close()
            emit(replacement, dict(newer, sequence=4), observed)
            assert source.indicators()[0].state == "done"
            assert source.indicators()[0].slot == 0


@pytest.mark.parametrize("extra", [0, 1])
def test_exact_frame_cap_then_healthy_continuation(source, observed, extra):
    row = frame("waiting")
    data = json.dumps(row).encode()
    data += b" " * (MAX_FRAME_BYTES + extra - len(data))
    with connect(source) as client:
        client.sendall(data + b"\n")
        if extra:
            assert client.recv(1) == b""
            assert source.status()["launches"] == []
        else:
            observed.get(timeout=3)
            assert source.indicators()[0].state == "waiting"
            emit(client, dict(row, sequence=2), observed)
            assert source.status()["launches"][0]["sequence"] == 2
    healthy(source, observed)


@pytest.mark.parametrize("kind", ["symlink", "regular"])
def test_bind_leaf_replacement_never_chmods_or_removes_replacement(endpoint, monkeypatch, kind):
    target = endpoint.parent / "preserve"
    target.write_text("user file")
    target.chmod(0o644)
    original = socket.socket.bind

    def replace_after_bind(sock, address):
        original(sock, address)
        endpoint.unlink()
        if kind == "symlink":
            endpoint.symlink_to(target)
        else:
            endpoint.write_text("replacement")
            endpoint.chmod(0o644)

    monkeypatch.setattr(socket.socket, "bind", replace_after_bind)
    receiver = GjcStatusSource(endpoint, [])
    try:
        with pytest.raises(PermissionError):
            receiver.start()
    finally:
        receiver.stop()
    assert target.read_text() == "user file"
    assert target.stat().st_mode & 0o777 == 0o644
    assert endpoint.exists()
    if kind == "regular":
        assert endpoint.read_text() == "replacement"
        assert endpoint.stat().st_mode & 0o777 == 0o644


@contextmanager
def reply_server(endpoint, wire):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(endpoint))
        listener.listen(1)
        listener.settimeout(3)
        failures = queue.Queue()

        def serve():
            try:
                client, _ = listener.accept()
                with client:
                    client.settimeout(3)
                    client.recv(4096)
                    client.sendall(wire)
            except OSError as exc:
                failures.put(exc)

        thread = threading.Thread(target=serve)
        thread.start()
        try:
            yield
        finally:
            thread.join(4)
            assert not thread.is_alive()
            if not failures.empty():
                raise failures.get_nowait()


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-32-le"])
def test_non_utf8_control_response_rejected(endpoint, encoding):
    row = {"version": 1, "type": "response", "ok": True,
           "status": {"version": 1, "maxSlots": 2, "launches": [], "overflow": []}}
    with reply_server(endpoint, json.dumps(row).encode(encoding) + b"\n"), \
            pytest.raises(GjcProtocolError):
        request_control(endpoint)


@pytest.mark.parametrize("same_socket", [False, True])
def test_process_contention_preserves_live_owner(source, observed, same_socket):
    row = frame("waiting")
    with connect(source) as client:
        emit(client, row, observed)
        before = source.tracker.registry_path.read_bytes()
        path = source.socket_path if same_socket else source.socket_path.with_name("second.sock")
        registry = (source.socket_path.parent / "other.json" if same_socket
                    else source.tracker.registry_path)
        code = '''
import sys
from orca_keychron_gjc.gjc_source import GjcStatusSource
receiver = GjcStatusSource(sys.argv[1], [], registry_path=sys.argv[2])
try:
    receiver.start()
except RuntimeError as exc:
    print(str(exc))
else:
    raise AssertionError("second receiver acquired ownership")
finally:
    receiver.stop()
'''
        result = subprocess.run([sys.executable, "-c", code, str(path), str(registry)],
                                capture_output=True, text=True, timeout=5, check=False)
        assert result.returncode == 0, result.stderr
        assert "already owns this " + ("socket" if same_socket else "registry") in result.stdout
        assert source.tracker.registry_path.read_bytes() == before
        emit(client, dict(row, sequence=2), observed)
        assert source.indicators()[0].state == "waiting"
        assert source.status()["launches"][0]["sequence"] == 2
        if not same_socket:
            assert not path.exists()


def test_fragmented_utf8_and_coalesced_snapshots_replace_full_state(source, observed, monkeypatch):
    reads = queue.Queue()
    original = source._read

    def capture(client):
        try:
            return original(client)
        finally:
            reads.put(None)

    monkeypatch.setattr(source, "_read", capture)
    row = frame("waiting")
    row["root"]["sessionId"] = row["sessions"][0]["sessionId"] = "루트"
    data = json.dumps(row, ensure_ascii=False).encode()
    split = data.index("루".encode()) + 1
    with connect(source) as client:
        client.sendall(data[:split])
        reads.get(timeout=3)
        assert source.indicators() == []
        latest = copy.deepcopy(row)
        latest.update(sequence=8)
        latest["sessions"][0]["state"] = "done"
        client.sendall(data[split:] + b"\n" + json.dumps(latest).encode() + b"\n"
                       + json.dumps(dict(row, sequence=3)).encode() + b"\n")
        for _ in range(3):
            observed.get(timeout=3)
        assert source.status()["launches"][0]["sequence"] == 8
        assert source.indicators()[0].state == "done"


def test_client_cap_and_partial_stalls_release_capacity_with_injected_clock(source, monkeypatch):
    from types import SimpleNamespace

    # Install the test clock before starting the receiver's event loop.
    source.stop()
    # _Client's dataclass factory retains the original monotonic callable.
    # Its values must share an epoch with the injected receiver clock: some
    # supported Python 3.9 builds start monotonic close to zero per process.
    clock = [gjc_source.time.monotonic()]
    monkeypatch.setattr(gjc_source, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(gjc_source, "MAX_CLIENTS", 2)
    reads, drops = queue.Queue(), queue.Queue()
    original_read, original_drop = source._read, source._drop

    def read(client):
        try:
            return original_read(client)
        finally:
            reads.put(None)

    def drop(client):
        try:
            return original_drop(client)
        finally:
            drops.put(None)

    monkeypatch.setattr(source, "_read", read)
    monkeypatch.setattr(source, "_drop", drop)
    source.start()
    with connect(source) as first, connect(source) as second:
        try:
            first.sendall(b"{")
            reads.get(timeout=3)
            second.sendall(b"{")
            reads.get(timeout=3)
        except (OSError, queue.Empty) as exc:
            raise AssertionError(
                f"Partial clients failed: receiver_error={source._error!r}, "
                f"accepted_clients={len(source._clients)}"
            ) from exc
        with connect(source) as excess:
            assert excess.recv(1) == b""
        clock[0] += gjc_source.CLIENT_TIMEOUT  # exactly since last partial bytes
        drops.get(timeout=3)
        drops.get(timeout=3)
        assert first.recv(1) == second.recv(1) == b""
    assert source.status()["launches"] == []
    assert request_control(source.socket_path)["ok"]


def test_storage_failure_foreground_and_restart_recovers_committed_state(source, observed, monkeypatch):
    row = frame("waiting")
    with connect(source) as client:
        emit(client, row, observed)
        committed = source.tracker.registry_path.read_bytes()

        def fail():
            raise OSError("audit injected disk failure")

        monkeypatch.setattr(source.tracker, "_persist", fail)
        emit(client, dict(row, sequence=2), observed)
        source._thread.join(3)
        assert not source._thread.is_alive()
        for action in (source.status, source.indicators, source.start):
            with pytest.raises(RuntimeError, match="receiver failed") as raised:
                action()
            assert isinstance(raised.value.__cause__, OSError)
        assert source.tracker.registry_path.read_bytes() == committed
        source.stop()
        assert source._clients == source._owners == {}
        assert source._listener is source._selector is source._lock_fd is None
        assert source._registry_lock_fd is None
        assert not source.socket_path.exists()
    source.start()
    assert source.indicators()[0].state == "unknown"
    with connect(source) as resumed:
        emit(resumed, dict(row, sequence=3), observed)
        assert source.indicators()[0].state == "waiting"
        assert source.indicators()[0].slot == 0


@pytest.mark.parametrize("mutation", [
    {"ok": False}, {"cleared": False}, {"error": {}},
    {"ok": 1}, {"status": []}, {"version": True},
])
def test_status_client_rejects_negative_or_clear_response_shapes(endpoint, mutation):
    row = {"version": 1, "type": "response", "ok": True,
           "status": {"version": 1, "maxSlots": 2, "launches": [], "overflow": []}}
    row.update(mutation)
    with reply_server(endpoint, json.dumps(row).encode() + b"\n"), \
            pytest.raises(GjcProtocolError):
        request_control(endpoint)


def test_clear_serializes_before_queued_reconnect_without_resurrection(source, observed, monkeypatch):
    row = frame("waiting")
    dropped, probing, release = threading.Event(), threading.Event(), threading.Event()
    original_drop = source._drop

    def drop(client):
        try:
            return original_drop(client)
        finally:
            if client.producer == row["producerId"]:
                dropped.set()

    monkeypatch.setattr(source, "_drop", drop)
    with connect(source) as first:
        emit(first, row, observed)
    assert dropped.wait(3)

    def dead_pid(pid, signal):
        assert (pid, signal) == (row["pid"], 0)
        probing.set()
        assert release.wait(3)
        raise ProcessLookupError()

    monkeypatch.setattr(gjc_source.os, "kill", dead_pid)
    results = queue.Queue()

    def clear():
        try:
            results.put(request_control(source.socket_path, "clear", row["launchId"], timeout=4))
        except Exception as exc:  # noqa: BLE001 - propagate worker failure to test thread
            results.put(exc)

    thread = threading.Thread(target=clear)
    thread.start()
    try:
        assert probing.wait(3)
        with connect(source) as queued:
            queued.sendall(json.dumps(dict(row, sequence=2)).encode() + b"\n")
            release.set()
            result = results.get(timeout=4)
            assert isinstance(result, dict), result
            assert result["ok"] and result["cleared"]
            observed.get(timeout=3)  # clear completed
            observed.get(timeout=3)  # queued reconnect processed
            assert source.status()["launches"] == []
            assert source.tracker._retired == {row["launchId"]: row["producerId"]}
            survivor = frame("done")
            emit(queued, survivor, observed)
            assert source.indicators()[0].state == "done"
            assert source.indicators()[0].slot == 0
    finally:
        release.set()
        thread.join(4)
        assert not thread.is_alive()


@pytest.mark.parametrize("excess", [0, 1])
def test_control_response_exact_byte_cap(endpoint, monkeypatch, excess):
    row = {"version": 1, "type": "response", "ok": True,
           "status": {"version": 1, "maxSlots": 2, "launches": [], "overflow": []}}
    wire = json.dumps(row).encode() + b"\n"
    monkeypatch.setattr(gjc_source, "MAX_REGISTRY_BYTES", len(wire) - excess)
    with reply_server(endpoint, wire):
        if excess:
            with pytest.raises(GjcProtocolError, match="exceeds limit"):
                request_control(endpoint)
        else:
            assert request_control(endpoint) == row
