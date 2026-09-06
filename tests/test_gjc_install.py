from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from orca_keychron_gjc import gjc_install

SOCKET = "/tmp/orca-keychron-gjc-test.sock"


def _kwargs(root: Path) -> dict:
    return {"agent_dir": root, "socket_path": SOCKET}


def _manifest(root: Path) -> dict:
    return json.loads((root / gjc_install.MANIFEST).read_text(encoding="utf-8"))


def _managed_contents(root: Path) -> dict[str, bytes]:
    manifest = _manifest(root)
    names = [*manifest["files"], gjc_install.MANIFEST]
    return {name: (root / name).read_bytes() for name in names}


def test_user_default_is_actual_gjc_agent_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GJC_CODING_AGENT_DIR", raising=False)
    expected = (Path.home() / ".gjc" / "agent").parent.resolve() / "agent"
    assert gjc_install._native_dir("user", None, None) == expected


def test_explicit_agent_dir_and_project_scope_are_isolated(tmp_path: Path) -> None:
    agent = tmp_path / "profile"
    project = tmp_path / "project"
    project.mkdir()

    assert gjc_install._native_dir("user", None, agent) == agent
    assert gjc_install._native_dir("project", project, None) == project / ".gjc"
    with pytest.raises(gjc_install.GjcInstallError, match="only valid for user"):
        gjc_install.plan_install(scope="project", project_path=project, agent_dir=agent)
    with pytest.raises(gjc_install.GjcInstallError, match="requires project_path"):
        gjc_install.plan_install(scope="project")


def test_packaged_assets_resolve_from_gjc_package(monkeypatch: pytest.MonkeyPatch) -> None:
    original = gjc_install.resources.files
    packages: list[str] = []

    def recording_files(package: str):
        packages.append(package)
        return original(package)

    monkeypatch.setattr(gjc_install.resources, "files", recording_files)
    assert b"createHook" in gjc_install._asset("gjc_hook.ts")
    assert b"keychron-decision-worker" in gjc_install._asset("decision-worker.md")
    assert b"agent://<actual-child-id>" in gjc_install._asset("decision-parent.md")
    assert packages == ["orca_keychron_gjc"] * 3


def test_dry_run_is_read_only_and_describes_owned_files(tmp_path: Path) -> None:
    root = tmp_path / "profile"

    plan = gjc_install.dry_run(**_kwargs(root))

    assert not root.exists()
    assert plan["dry_run"] is True
    assert plan["can_apply"] is True
    assert plan["decision_agent"] == "keychron-decision-worker"
    assert plan["decision_tools"] == ["read", "yield"]
    paths = {Path(item["path"]).relative_to(root).as_posix() for item in plan["files"]}
    assert gjc_install.LOADER in paths
    assert gjc_install.WORKER in paths
    assert sum(path.endswith("gjc_hook.ts") for path in paths) == 1
    assert sum(path.endswith("decision-parent.md") for path in paths) == 1


def test_install_status_idempotency_and_loader_boundary(tmp_path: Path) -> None:
    root = tmp_path / "profile"

    first = gjc_install.install(**_kwargs(root))
    before = _managed_contents(root)
    second = gjc_install.install(**_kwargs(root))
    current = gjc_install.status(agent_dir=root)

    assert first["installed"] is True and first["dry_run"] is False
    assert second["installed"] is True
    assert all(item["action"] == "unchanged" for item in second["files"])
    assert _managed_contents(root) == before
    assert current["installed"] is True and current["healthy"] is True
    assert current["socket_path"] == SOCKET
    manifest = _manifest(root)
    assert set(manifest["files"]) == set(before) - {gjc_install.MANIFEST}
    assert all(
        stat.S_IMODE((root / name).stat().st_mode) == 0o600
        for name in [*manifest["files"], gjc_install.MANIFEST]
    )

    loader = (root / gjc_install.LOADER).read_text(encoding="utf-8")
    release_hook = next(name for name in manifest["files"] if name.endswith("gjc_hook.ts"))
    assert str(root / release_hook) in loader
    assert "createHook(api," in loader
    assert str(root / "hooks") not in str(root / release_hook)
    assert '"socketPath": "/tmp/orca-keychron-gjc-test.sock"' in loader
    assert "agent://<actual-child-id>" in loader


def test_project_install_uses_project_native_directory(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()

    result = gjc_install.install(scope="project", project_path=project, socket_path=SOCKET)

    assert result["native_dir"] == str(project / ".gjc")
    assert (project / ".gjc" / gjc_install.LOADER).is_file()
    assert (project / ".gjc" / gjc_install.WORKER).is_file()


@pytest.mark.parametrize("relative", [gjc_install.LOADER, gjc_install.WORKER])
def test_install_refuses_and_preserves_unowned_conflicts(tmp_path: Path, relative: str) -> None:
    root = tmp_path / "profile"
    target = root / relative
    target.parent.mkdir(parents=True)
    target.write_text("user-owned\n", encoding="utf-8")

    plan = gjc_install.plan_install(**_kwargs(root))

    assert str(target) in plan["conflicts"]
    assert plan["can_apply"] is False
    with pytest.raises(gjc_install.GjcInstallError, match="Refusing conflicting"):
        gjc_install.install(**_kwargs(root))
    assert target.read_text(encoding="utf-8") == "user-owned\n"
    assert not (root / gjc_install.MANIFEST).exists()
    assert not (root / gjc_install.LOCK).exists()


def test_modified_owned_file_blocks_install_and_uninstall(tmp_path: Path) -> None:
    root = tmp_path / "profile"
    gjc_install.install(**_kwargs(root))
    worker = root / gjc_install.WORKER
    worker.write_text("locally modified\n", encoding="utf-8")

    state = gjc_install.status(agent_dir=root)

    assert state["healthy"] is False
    assert state["modified"] == [str(worker)]
    with pytest.raises(gjc_install.GjcInstallError, match="modified files"):
        gjc_install.install(**_kwargs(root))
    with pytest.raises(gjc_install.GjcInstallError, match="modified or unowned"):
        gjc_install.uninstall(agent_dir=root)
    assert worker.read_text(encoding="utf-8") == "locally modified\n"
    assert (root / gjc_install.MANIFEST).is_file()


def test_upgrade_replaces_owned_release_and_removes_old_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "profile"
    gjc_install.install(**_kwargs(root))
    old_manifest = _manifest(root)
    old_release = {name for name in old_manifest["files"] if "/releases/" in name}
    original_asset = gjc_install._asset

    def upgraded_asset(name: str) -> bytes:
        value = original_asset(name)
        return value + b"\n// upgraded test asset\n" if name == "gjc_hook.ts" else value

    monkeypatch.setattr(gjc_install, "_asset", upgraded_asset)
    result = gjc_install.install(**_kwargs(root))
    new_manifest = _manifest(root)
    new_release = {name for name in new_manifest["files"] if "/releases/" in name}

    assert result["installed"] is True
    assert old_release.isdisjoint(new_release)
    assert all(not (root / name).exists() for name in old_release)
    assert all((root / name).is_file() for name in new_release)
    assert "upgraded test asset" in next(
        (root / name).read_text(encoding="utf-8")
        for name in new_release
        if name.endswith("gjc_hook.ts")
    )


def test_failed_upgrade_rolls_back_every_managed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "profile"
    gjc_install.install(**_kwargs(root))
    before = _managed_contents(root)
    old_release = [name for name in before if "/releases/" in name]
    original_asset = gjc_install._asset
    original_write = gjc_install._atomic_write
    failed = False
    recovery_writes: list[str] = []

    def upgraded_asset(name: str) -> bytes:
        value = original_asset(name)
        return value + b"\n// interrupted upgrade\n" if name == "gjc_hook.ts" else value

    def interrupted_write(target_root: Path, relative: str, data: bytes, mode: int = 0o600):
        nonlocal failed
        if relative == gjc_install.MANIFEST and not failed:
            failed = True
            raise OSError("injected write failure")
        if failed:
            recovery_writes.append(relative)
        return original_write(target_root, relative, data, mode)

    monkeypatch.setattr(gjc_install, "_asset", upgraded_asset)
    monkeypatch.setattr(gjc_install, "_atomic_write", interrupted_write)

    with pytest.raises(gjc_install.GjcInstallError, match="installation failed"):
        gjc_install.install(**_kwargs(root))

    assert failed is True
    assert _managed_contents(root) == before
    assert not (root / gjc_install.JOURNAL).exists()
    assert max(recovery_writes.index(name) for name in old_release) < recovery_writes.index(
        gjc_install.LOADER
    )
    state = gjc_install.status(agent_dir=root)
    assert state["installed"] is True and state["healthy"] is True


def test_pending_transaction_is_recovered_before_next_install(tmp_path: Path) -> None:
    root = tmp_path / "profile"
    gjc_install.install(**_kwargs(root))
    worker = root / gjc_install.WORKER
    before = worker.read_bytes()
    after = b"partial transaction"
    journal = {
        "owner": gjc_install.OWNER,
        "schema": 1,
        "changes": [
            {
                "path": gjc_install.WORKER,
                "before": gjc_install.base64.b64encode(before).decode("ascii"),
                "after_sha256": gjc_install._sha(after),
                "mode": 0o600,
            }
        ],
    }
    worker.write_bytes(after)
    (root / gjc_install.JOURNAL).write_bytes(gjc_install._json(journal))
    (root / gjc_install.JOURNAL).chmod(0o600)

    result = gjc_install.install(**_kwargs(root))

    assert result["recovered"] is True
    assert worker.read_bytes() == before
    assert not (root / gjc_install.JOURNAL).exists()


def test_missing_owned_file_is_repaired_without_overwriting_other_files(tmp_path: Path) -> None:
    root = tmp_path / "profile"
    gjc_install.install(**_kwargs(root))
    loader = root / gjc_install.LOADER
    loader_before = loader.read_bytes()
    worker = root / gjc_install.WORKER
    worker.unlink()

    before = gjc_install.status(agent_dir=root)
    result = gjc_install.install(**_kwargs(root))

    assert before["missing"] == [str(worker)]
    assert result["installed"] is True
    assert worker.read_bytes() == gjc_install._asset("decision-worker.md")
    assert loader.read_bytes() == loader_before
    assert gjc_install.status(agent_dir=root)["healthy"] is True


def test_uninstall_dry_run_and_clean_removal(tmp_path: Path) -> None:
    root = tmp_path / "profile"
    gjc_install.install(**_kwargs(root))
    manifest = _manifest(root)

    preview = gjc_install.uninstall(agent_dir=root, dry_run=True)
    assert preview["dry_run"] is True and preview["installed"] is True
    assert all((root / name).is_file() for name in manifest["files"])

    result = gjc_install.uninstall(agent_dir=root)

    assert result["removed"] is True and result["installed"] is False
    assert all(not (root / name).exists() for name in manifest["files"])
    assert not (root / gjc_install.MANIFEST).exists()
    assert gjc_install.status(agent_dir=root)["installed"] is False
    assert gjc_install.uninstall(agent_dir=root)["installed"] is False


def test_failed_uninstall_restores_loader_after_its_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "profile"
    gjc_install.install(**_kwargs(root))
    before = _managed_contents(root)
    releases = [name for name in before if "/releases/" in name]
    original_write = gjc_install._atomic_write
    original_safe_path = gjc_install._safe_path
    failed = False
    recovery_writes: list[str] = []

    def recording_write(target_root: Path, relative: str, data: bytes, mode: int = 0o600):
        if failed:
            recovery_writes.append(relative)
        return original_write(target_root, relative, data, mode)

    def interrupted_safe_path(target_root: Path, relative: str) -> Path:
        nonlocal failed
        if (
            relative == gjc_install.MANIFEST
            and not failed
            and (target_root / gjc_install.JOURNAL).is_file()
            and not (target_root / gjc_install.LOADER).exists()
        ):
            failed = True
            raise OSError("injected uninstall failure")
        return original_safe_path(target_root, relative)

    monkeypatch.setattr(gjc_install, "_atomic_write", recording_write)
    monkeypatch.setattr(gjc_install, "_safe_path", interrupted_safe_path)

    with pytest.raises(gjc_install.GjcInstallError, match="removal failed"):
        gjc_install.uninstall(agent_dir=root)

    assert _managed_contents(root) == before
    assert max(recovery_writes.index(name) for name in releases) < recovery_writes.index(
        gjc_install.LOADER
    )
    assert gjc_install.status(agent_dir=root)["healthy"] is True


def test_invalid_manifest_is_preserved(tmp_path: Path) -> None:
    root = tmp_path / "profile"
    manifest = root / gjc_install.MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"owner":"someone-else"}\n', encoding="utf-8")

    with pytest.raises(gjc_install.GjcInstallError, match="Invalid or unowned"):
        gjc_install.install(**_kwargs(root))
    with pytest.raises(gjc_install.GjcInstallError, match="Invalid or unowned"):
        gjc_install.uninstall(agent_dir=root)
    assert manifest.read_text(encoding="utf-8") == '{"owner":"someone-else"}\n'


def test_symlink_installation_boundaries_are_refused_and_preserved(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    root_link = tmp_path / "profile-link"
    root_link.symlink_to(real, target_is_directory=True)
    with pytest.raises(gjc_install.GjcInstallError, match="symlink native directory"):
        gjc_install.plan_install(**_kwargs(root_link))

    root = tmp_path / "profile"
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir()
    (root / "hooks").symlink_to(outside, target_is_directory=True)
    with pytest.raises(gjc_install.GjcInstallError, match="symlink in managed path"):
        gjc_install.install(**_kwargs(root))
    assert list(outside.iterdir()) == []


def test_symlinked_managed_file_is_never_followed(tmp_path: Path) -> None:
    root = tmp_path / "profile"
    target = tmp_path / "outside-worker.md"
    target.write_text("outside\n", encoding="utf-8")
    worker = root / gjc_install.WORKER
    worker.parent.mkdir(parents=True)
    worker.symlink_to(target)

    with pytest.raises(gjc_install.GjcInstallError, match="symlink in managed path"):
        gjc_install.plan_install(**_kwargs(root))
    assert target.read_text(encoding="utf-8") == "outside\n"


@pytest.mark.parametrize("socket", ["x" * 104, object()])
def test_invalid_socket_paths_have_typed_errors(tmp_path: Path, socket: object) -> None:
    with pytest.raises(gjc_install.GjcInstallError, match="socket path"):
        gjc_install.plan_install(agent_dir=tmp_path / "profile", socket_path=socket)


def test_explicit_agent_dir_wins_over_profile_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment_profile = tmp_path / "environment-profile"
    explicit_profile = tmp_path / "explicit-profile"
    monkeypatch.setenv("GJC_CODING_AGENT_DIR", str(environment_profile))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(environment_profile))

    gjc_install.install(**_kwargs(explicit_profile))

    assert (explicit_profile / gjc_install.LOADER).is_file()
    assert not environment_profile.exists()


def test_gjc_environment_profile_is_used_when_explicit_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment_profile = tmp_path / "environment-profile"
    monkeypatch.setenv("GJC_CODING_AGENT_DIR", str(environment_profile))

    plan = gjc_install.plan_install(socket_path=SOCKET)

    assert plan["native_dir"] == str(environment_profile)
    assert not environment_profile.exists()
