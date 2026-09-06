from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from orca_keychron_gjc import gjc_install

SOCKET = "/tmp/orca keychron gjc audit.sock"


def _install(root: Path, **kwargs: object) -> dict:
    return gjc_install.install(agent_dir=root, socket_path=SOCKET, **kwargs)


def _manifest(root: Path) -> dict:
    return json.loads((root / gjc_install.MANIFEST).read_text(encoding="utf-8"))


def _managed_snapshot(root: Path) -> dict[str, bytes]:
    manifest = _manifest(root)
    return {
        name: (root / name).read_bytes()
        for name in [*manifest["files"], gjc_install.MANIFEST]
    }


@pytest.mark.parametrize("requested_umask", [0, 0o777])
def test_new_managed_directory_chain_is_private_independent_of_umask(
    tmp_path: Path, requested_umask: int
) -> None:
    root = tmp_path / "new profile with spaces"
    previous_umask = os.umask(requested_umask)
    try:
        _install(root)
    finally:
        os.umask(previous_umask)

    manifest = _manifest(root)
    managed_directories = {root}
    for relative in [*manifest["files"], gjc_install.MANIFEST, gjc_install.LOCK]:
        current = (root / relative).parent
        while current != root:
            managed_directories.add(current)
            current = current.parent

    assert managed_directories
    assert {
        path.relative_to(root).as_posix(): stat.S_IMODE(path.stat().st_mode)
        for path in managed_directories
    } == {path.relative_to(root).as_posix(): 0o700 for path in managed_directories}


def test_public_managed_file_is_unhealthy_and_never_silently_rewritten_or_removed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "profile"
    _install(root)
    loader = root / gjc_install.LOADER
    original = loader.read_bytes()
    loader.chmod(0o644)

    state = gjc_install.status(agent_dir=root)

    assert state["healthy"] is False
    assert str(loader) in state["modified"]
    with pytest.raises(gjc_install.GjcInstallError, match="modified"):
        _install(root)
    with pytest.raises(gjc_install.GjcInstallError, match="modified"):
        gjc_install.uninstall(agent_dir=root)
    assert loader.read_bytes() == original
    assert stat.S_IMODE(loader.stat().st_mode) == 0o644


def test_manifest_with_wrong_gjc_version_pin_is_rejected_and_preserved(tmp_path: Path) -> None:
    root = tmp_path / "profile"
    _install(root)
    manifest_path = root / gjc_install.MANIFEST
    payload = _manifest(root)
    payload["supported_gjc_version"] = "0.16.5"
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode()
    manifest_path.write_bytes(raw)
    manifest_path.chmod(0o600)

    with pytest.raises(gjc_install.GjcInstallError, match="Invalid or unowned"):
        gjc_install.status(agent_dir=root)
    with pytest.raises(gjc_install.GjcInstallError, match="Invalid or unowned"):
        _install(root)
    with pytest.raises(gjc_install.GjcInstallError, match="Invalid or unowned"):
        gjc_install.uninstall(agent_dir=root)
    assert manifest_path.read_bytes() == raw


@pytest.mark.parametrize("mutation", ["extra-key", "public-mode"])
def test_manifest_shape_and_private_mode_are_part_of_ownership(
    tmp_path: Path, mutation: str
) -> None:
    root = tmp_path / "profile"
    _install(root)
    manifest_path = root / gjc_install.MANIFEST
    if mutation == "extra-key":
        payload = _manifest(root)
        payload["unexpected"] = True
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        manifest_path.chmod(0o600)
    else:
        manifest_path.chmod(0o644)
    before = manifest_path.read_bytes()

    with pytest.raises(gjc_install.GjcInstallError, match="Invalid or unowned"):
        _install(root)
    with pytest.raises(gjc_install.GjcInstallError, match="Invalid or unowned"):
        gjc_install.uninstall(agent_dir=root)
    assert manifest_path.read_bytes() == before


def test_socket_byte_boundary_and_rerun_with_spaces_are_exact(tmp_path: Path) -> None:
    root = tmp_path / "profile with spaces"
    accepted = "/tmp/" + "é" * 49
    rejected = accepted + "x"
    assert len(os.fsencode(accepted)) == 103

    first = gjc_install.install(agent_dir=root, socket_path=accepted)
    before = _managed_snapshot(root)
    second = gjc_install.install(agent_dir=root, socket_path=accepted)

    assert first["socket_path"] == accepted
    assert second["socket_path"] == accepted
    assert _managed_snapshot(root) == before
    with pytest.raises(gjc_install.GjcInstallError, match="103 bytes"):
        gjc_install.install(agent_dir=root, socket_path=rejected)
    assert _managed_snapshot(root) == before


def test_preexisting_release_asset_without_manifest_is_a_preserved_conflict(
    tmp_path: Path,
) -> None:
    root = tmp_path / "profile"
    desired = gjc_install._desired(root, Path(SOCKET))
    release_name = next(name for name in desired if name.endswith("gjc_hook.ts"))
    release = root / release_name
    release.parent.mkdir(parents=True)
    release.write_bytes(desired[release_name])
    before = release.read_bytes()

    plan = gjc_install.plan_install(agent_dir=root, socket_path=SOCKET)

    assert str(release) in plan["conflicts"]
    with pytest.raises(gjc_install.GjcInstallError, match="conflicting"):
        _install(root)
    assert release.read_bytes() == before
    assert not (root / gjc_install.MANIFEST).exists()


def test_directory_fsync_failure_leaves_recoverable_journal_then_rerun_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "profile"
    original_fsync = gjc_install.os.fsync
    failed = False

    def fail_first_directory_fsync(descriptor: int) -> None:
        nonlocal failed
        if stat.S_ISDIR(os.fstat(descriptor).st_mode) and not failed:
            failed = True
            raise OSError("injected directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(gjc_install.os, "fsync", fail_first_directory_fsync)

    with pytest.raises(gjc_install.GjcInstallError, match="fsync failure"):
        _install(root)

    assert failed is True
    assert (root / gjc_install.JOURNAL).is_file()
    assert gjc_install.status(agent_dir=root)["recovery_required"] is True

    result = _install(root)

    assert result["recovered"] is True
    assert gjc_install.status(agent_dir=root)["healthy"] is True
    assert not (root / gjc_install.JOURNAL).exists()


def test_replace_failure_rolls_back_every_managed_byte_and_preserves_unrelated_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "profile"
    root.mkdir()
    unrelated = root / "user-notes.md"
    unrelated.write_bytes(b"keep me\n")
    original_replace = gjc_install.os.replace
    failed = False

    def fail_loader_replace(source: object, destination: object) -> None:
        nonlocal failed
        if Path(destination) == root / gjc_install.LOADER and not failed:
            failed = True
            raise OSError("injected loader replace failure")
        original_replace(source, destination)

    monkeypatch.setattr(gjc_install.os, "replace", fail_loader_replace)

    with pytest.raises(gjc_install.GjcInstallError, match="replace failure"):
        _install(root)

    assert failed is True
    assert unrelated.read_bytes() == b"keep me\n"
    assert not (root / gjc_install.MANIFEST).exists()
    assert not (root / gjc_install.JOURNAL).exists()
    assert not (root / gjc_install.LOADER).exists()
    assert not (root / gjc_install.WORKER).exists()


def test_dry_run_with_pending_recovery_is_byte_for_byte_read_only(tmp_path: Path) -> None:
    root = tmp_path / "profile"
    _install(root)
    before = _managed_snapshot(root)
    journal = root / gjc_install.JOURNAL
    journal.write_text(
        json.dumps(
            {
                "owner": gjc_install.OWNER,
                "schema": 1,
                "changes": [
                    {
                        "path": gjc_install.LOADER,
                        "before": None,
                        "after_sha256": gjc_install._sha(before[gjc_install.LOADER]),
                        "mode": 0o600,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    journal.chmod(0o600)
    disk_before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }

    plan = _install(root, dry_run=True)

    disk_after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert plan["recovery_required"] is True
    assert disk_after == disk_before


def test_recovery_refuses_a_post_crash_user_edit_and_keeps_journal(tmp_path: Path) -> None:
    root = tmp_path / "profile"
    _install(root)
    before = _managed_snapshot(root)
    loader = root / gjc_install.LOADER
    loader.write_bytes(b"user edit after crash\n")
    loader.chmod(0o600)
    journal = root / gjc_install.JOURNAL
    journal.write_text(
        json.dumps(
            {
                "owner": gjc_install.OWNER,
                "schema": 1,
                "changes": [
                    {
                        "path": gjc_install.LOADER,
                        "before": None,
                        "after_sha256": gjc_install._sha(before[gjc_install.LOADER]),
                        "mode": 0o600,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    journal.chmod(0o600)

    with pytest.raises(gjc_install.GjcInstallError, match="would overwrite a modified file"):
        _install(root)

    assert loader.read_bytes() == b"user edit after crash\n"
    assert journal.is_file()


@pytest.mark.parametrize("journal_mode,entry_mode", [(0o644, 0o600), (0o600, 0o644)])
def test_recovery_rejects_nonprivate_journal_or_restore_mode_without_changes(
    tmp_path: Path, journal_mode: int, entry_mode: int
) -> None:
    root = tmp_path / "profile"
    _install(root)
    loader = root / gjc_install.LOADER
    before = loader.read_bytes()
    journal = root / gjc_install.JOURNAL
    journal.write_text(
        json.dumps(
            {
                "owner": gjc_install.OWNER,
                "schema": 1,
                "changes": [
                    {
                        "path": gjc_install.LOADER,
                        "before": None,
                        "after_sha256": gjc_install._sha(before),
                        "mode": entry_mode,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    journal.chmod(journal_mode)

    with pytest.raises(gjc_install.GjcInstallError, match="Invalid recovery journal"):
        _install(root)

    assert loader.read_bytes() == before
    assert stat.S_IMODE(loader.stat().st_mode) == 0o600
    assert journal.is_file()


def _optimized_rejection(script: str, root: Path) -> subprocess.CompletedProcess[str]:
    environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(Path.cwd() / "src"),
    }
    return subprocess.run(
        [sys.executable, "-O", "-c", script, str(root)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=5,
    )


def test_optimized_python_cannot_bypass_manifest_ownership_or_delete_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "profile"
    _install(root)
    manifest = root / gjc_install.MANIFEST
    payload = _manifest(root)
    payload["owner"] = "not-orca-keychron"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    manifest.chmod(0o600)
    watched = [root / gjc_install.LOADER, root / gjc_install.WORKER, manifest]
    before = {path: path.read_bytes() for path in watched}
    script = """
import sys
from pathlib import Path
from orca_keychron_gjc import gjc_install
try:
    gjc_install.uninstall(agent_dir=Path(sys.argv[1]))
except gjc_install.GjcInstallError:
    raise SystemExit(0)
raise SystemExit(9)
"""

    completed = _optimized_rejection(script, root)

    assert completed.returncode == 0, completed.stderr
    assert {path: path.read_bytes() for path in watched} == before


def test_optimized_python_cannot_bypass_journal_ownership_or_delete_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "profile"
    _install(root)
    loader = root / gjc_install.LOADER
    journal = root / gjc_install.JOURNAL
    journal.write_text(
        json.dumps(
            {
                "owner": "not-orca-keychron",
                "schema": 1,
                "changes": [
                    {
                        "path": gjc_install.LOADER,
                        "before": None,
                        "after_sha256": gjc_install._sha(loader.read_bytes()),
                        "mode": 0o600,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    journal.chmod(0o600)
    before = {loader: loader.read_bytes(), journal: journal.read_bytes()}
    script = """
import sys
from pathlib import Path
from orca_keychron_gjc import gjc_install
try:
    gjc_install._recover(Path(sys.argv[1]))
except gjc_install.GjcInstallError:
    raise SystemExit(0)
raise SystemExit(9)
"""

    completed = _optimized_rejection(script, root)

    assert completed.returncode == 0, completed.stderr
    assert {path: path.read_bytes() for path in before} == before


def test_manifest_fifo_is_rejected_without_blocking_or_mutating_it(tmp_path: Path) -> None:
    root = tmp_path / "profile"
    manifest = root / gjc_install.MANIFEST
    manifest.parent.mkdir(parents=True)
    os.mkfifo(manifest, 0o600)
    script = """
import sys
from pathlib import Path
from orca_keychron_gjc import gjc_install
try:
    gjc_install.status(agent_dir=Path(sys.argv[1]))
except gjc_install.GjcInstallError:
    raise SystemExit(0)
raise SystemExit(9)
"""

    completed = _optimized_rejection(script, root)

    assert completed.returncode == 0, completed.stderr
    assert stat.S_ISFIFO(manifest.lstat().st_mode)
