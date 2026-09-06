"""Reversible, account-independent installation of the owned GJC native hook.

The journal contains backups of *owned* files only. A process interrupted during
an update is rolled back before the next mutation. Read-only planning/status
never creates directories, resolves a pending transaction, or loads GJC auth.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Any

from . import __version__
from .config import gjc_socket_path

SUPPORTED_GJC_VERSION = "0.16.4"
OWNER = "orca-keychron"
MANIFEST = ".orca-keychron/manifest.json"
JOURNAL = ".orca-keychron/transaction.json"
LOCK = ".orca-keychron/install.lock"
LOADER = "hooks/pre/orca-keychron.ts"
WORKER = "agents/keychron-decision-worker.md"
_RELEASE_FILE = re.compile(
    r"\.orca-keychron/releases/[a-f0-9]{64}/(gjc_hook\.ts|decision-parent\.md)"
)
_HASH = re.compile(r"[a-f0-9]{64}")
_MAX_METADATA = 8 * 1024 * 1024


class GjcInstallError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _asset(name: str) -> bytes:
    try:
        return resources.files("orca_keychron_gjc").joinpath("assets", name).read_bytes()
    except (OSError, ModuleNotFoundError, TypeError) as exc:
        raise GjcInstallError(f"Packaged GJC asset is missing: {name}") from exc


def _native_dir(scope: str, project_path: Any, agent_dir: Any) -> Path:
    if scope not in ("user", "project"):
        raise GjcInstallError("scope must be 'user' or 'project'")
    if scope == "project":
        if agent_dir is not None:
            raise GjcInstallError("agent_dir is only valid for user scope")
        if project_path is None:
            raise GjcInstallError("project scope requires project_path")
        project = Path(project_path).expanduser().resolve()
        if not project.is_dir():
            raise GjcInstallError(f"Project directory does not exist: {project}")
        path = project / ".gjc"
    else:
        if project_path is not None:
            raise GjcInstallError("project_path is only valid for project scope")
        # The installed GJC 0.16.4 source uses GJC_CODING_AGENT_DIR when set
        # and ~/.gjc/agent otherwise.  An explicit argument always wins so
        # isolated tests and diagnostics cannot accidentally target the user.
        override = agent_dir if agent_dir is not None else os.environ.get("GJC_CODING_AGENT_DIR")
        path = (
            Path(override).expanduser() if override is not None else Path.home() / ".gjc" / "agent"
        )
        path = Path(os.path.abspath(path))
    if path.is_symlink():
        raise GjcInstallError(f"Refusing symlink native directory: {path}")
    # Resolve OS aliases such as macOS /tmp, but retain the installation boundary.
    path = path.parent.resolve() / path.name
    if path.exists() and not path.is_dir():
        raise GjcInstallError(f"Native directory is not a directory: {path}")
    return path


def _safe_path(root: Path, relative: str) -> Path:
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or any(p in (".", "..") for p in parts):
        raise GjcInstallError(f"Invalid managed path: {relative}")
    current = root
    if root.is_symlink():
        raise GjcInstallError(f"Refusing symlink native directory: {root}")
    for part in parts:
        current /= part
        if current.is_symlink():
            raise GjcInstallError(f"Refusing symlink in managed path: {current}")
        if current != root / relative and current.exists() and not current.is_dir():
            raise GjcInstallError(f"Managed parent is not a directory: {current}")
    return current


def _owned_path(relative: str, *, manifest: bool = False) -> bool:
    return (
        relative in (LOADER, WORKER)
        or bool(_RELEASE_FILE.fullmatch(relative))
        or (manifest and relative == MANIFEST)
    )


def _read(root: Path, relative: str, *, limit: int = _MAX_METADATA) -> bytes | None:
    path = _safe_path(root, relative)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise GjcInstallError(f"Cannot read managed file {path}: {exc}") from exc
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise GjcInstallError(f"Managed file is not a regular file: {path}")
        content = handle.read(limit + 1)
    if len(content) > limit:
        raise GjcInstallError(f"Managed file exceeds {limit} bytes: {path}")
    return content


def _mode(root: Path, relative: str) -> int | None:
    path = _safe_path(root, relative)
    try:
        return stat.S_IMODE(os.stat(path, follow_symlinks=False).st_mode)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise GjcInstallError(f"Cannot inspect managed file {path}: {exc}") from exc


def _manifest(root: Path) -> dict[str, Any] | None:
    content = _read(root, MANIFEST)
    if content is None:
        return None
    try:
        data = json.loads(content)
        expected_keys = {
            "owner",
            "schema",
            "package_version",
            "supported_gjc_version",
            "socket_path",
            "files",
        }
        if (
            not isinstance(data, dict)
            or data.get("owner") != OWNER
            or data.get("schema") != 1
            or set(data) != expected_keys
            or _mode(root, MANIFEST) != 0o600
        ):
            raise ValueError("invalid manifest envelope")
        files = data.get("files")
        if (
            not isinstance(files, dict)
            or not 2 <= len(files) <= 32
            or LOADER not in files
            or WORKER not in files
        ):
            raise ValueError("invalid manifest files")
        for name, digest in files.items():
            if (
                not isinstance(name, str)
                or not _owned_path(name)
                or not isinstance(digest, str)
                or _HASH.fullmatch(digest) is None
            ):
                raise ValueError("invalid manifest file entry")
        if data.get("supported_gjc_version") != SUPPORTED_GJC_VERSION:
            raise ValueError("invalid GJC version pin")
        package_version = data.get("package_version")
        if not isinstance(package_version, str) or not package_version:
            raise ValueError("invalid package version")
        socket = data.get("socket_path")
        if (
            not isinstance(socket, str)
            or not Path(socket).is_absolute()
            or "\0" in socket
            or len(os.fsencode(socket)) > 103
        ):
            raise ValueError("invalid socket path")
        return data
    except (ValueError, KeyError, TypeError) as exc:
        raise GjcInstallError(
            f"Invalid or unowned installation manifest: {root / MANIFEST}"
        ) from exc


def _socket_path(socket_path: Any) -> Path:
    try:
        path = Path(socket_path).expanduser() if socket_path is not None else gjc_socket_path()
        path = Path(os.path.abspath(path))
    except (TypeError, ValueError, OSError) as exc:
        raise GjcInstallError("GJC Unix socket path is invalid") from exc
    if "\0" in str(path) or len(os.fsencode(path)) > 103:
        raise GjcInstallError("GJC Unix socket path must fit within 103 bytes")
    return path


def _desired(root: Path, socket_path: Path) -> dict[str, bytes]:
    hook = _asset("gjc_hook.ts")
    parent = _asset("decision-parent.md")
    worker = _asset("decision-worker.md")
    release = _sha(hook + b"\0" + parent + b"\0" + worker)
    prefix = f".orca-keychron/releases/{release}"
    module = str(root / prefix / "gjc_hook.ts")
    options = {"socketPath": str(socket_path), "parentInstructions": parent.decode("utf-8")}
    loader = (
        "// Managed by orca-keychron. Use gjc install/remove to update this file.\n"
        f"import {{ createHook }} from {json.dumps(module, ensure_ascii=True)};\n"
        f"export default (api: any) => createHook(api, {json.dumps(options, ensure_ascii=True)});\n"
    ).encode()
    return {
        f"{prefix}/gjc_hook.ts": hook,
        f"{prefix}/decision-parent.md": parent,
        WORKER: worker,
        LOADER: loader,
    }


def _metadata(root: Path, scope: str) -> dict[str, Any]:
    return {
        "scope": scope,
        "native_dir": str(root),
        "manifest_path": str(root / MANIFEST),
        "supported_gjc_version": SUPPORTED_GJC_VERSION,
        "package_version": __version__,
    }


def status(*, scope: str = "user", project_path: Any = None, agent_dir: Any = None) -> dict:
    root = _native_dir(scope, project_path, agent_dir)
    manifest = _manifest(root)
    result = _metadata(root, scope)
    modified, missing, conflicts = [], [], []
    paths = manifest["files"] if manifest else {LOADER: None, WORKER: None}
    for name, digest in paths.items():
        content = _read(root, name)
        if content is None:
            if manifest:
                missing.append(str(root / name))
        elif not manifest:
            conflicts.append(str(root / name))
        elif _sha(content) != digest or _mode(root, name) != 0o600:
            modified.append(str(root / name))
    result.update(
        installed=manifest is not None,
        healthy=bool(manifest) and not (modified or missing),
        socket_path=manifest.get("socket_path") if manifest else None,
        installed_package_version=manifest.get("package_version") if manifest else None,
        modified=modified,
        missing=missing,
        conflicts=conflicts,
        recovery_required=_read(root, JOURNAL) is not None,
        files=[str(root / name) for name in paths] if manifest else [],
    )
    if result["recovery_required"]:
        result["healthy"] = False
    return result


def plan_install(
    *,
    scope: str = "user",
    project_path: Any = None,
    agent_dir: Any = None,
    socket_path: Any = None,
) -> dict:
    root = _native_dir(scope, project_path, agent_dir)
    socket = _socket_path(socket_path)
    desired = _desired(root, socket)
    manifest = _manifest(root)
    old = manifest["files"] if manifest else {}
    changes, conflicts = [], []
    for name in dict.fromkeys([*desired, *old]):
        content = _read(root, name)
        digest = _sha(content) if content is not None else None
        if content is not None and (
            name not in old or digest != old[name] or _mode(root, name) != 0o600
        ):
            conflicts.append(str(root / name))
        wanted = desired.get(name)
        action = (
            "unchanged"
            if content == wanted
            else ("remove" if wanted is None else "create" if content is None else "update")
        )
        changes.append(
            {
                "path": str(root / name),
                "action": action,
                "sha256": _sha(wanted) if wanted is not None else None,
            }
        )
    result = _metadata(root, scope)
    recovery = _read(root, JOURNAL) is not None
    result.update(
        action="install",
        installed=bool(manifest),
        socket_path=str(socket),
        files=changes,
        conflicts=conflicts,
        can_apply=not conflicts,
        recovery_required=recovery,
        dry_run=True,
        decision_agent="keychron-decision-worker",
        decision_tools=["read", "yield"],
    )
    return result


def dry_run(
    *,
    scope: str = "user",
    project_path: Any = None,
    agent_dir: Any = None,
    socket_path: Any = None,
) -> dict:
    """Return the exact installation plan without creating or recovering files."""
    return plan_install(
        scope=scope,
        project_path=project_path,
        agent_dir=agent_dir,
        socket_path=socket_path,
    )


def _mkdir_private(path: Path) -> None:
    missing = []
    current = path
    while not current.exists():
        if current.is_symlink():
            raise GjcInstallError(f"Refusing symlink directory: {current}")
        missing.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    if current.is_symlink() or not current.is_dir():
        raise GjcInstallError(f"Managed directory parent is unsafe: {current}")
    for directory in reversed(missing):
        created = False
        try:
            directory.mkdir(mode=0o700)
            created = True
        except FileExistsError:
            pass
        if created:
            os.chmod(directory, 0o700)
        try:
            info = directory.lstat()
        except OSError as exc:
            raise GjcInstallError(f"Cannot inspect managed directory {directory}: {exc}") from exc
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise GjcInstallError(f"New managed directory is not private: {directory}")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _unlink(root: Path, relative: str) -> bool:
    path = _safe_path(root, relative)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    _fsync_directory(path.parent)
    return True


def _atomic_write(root: Path, relative: str, data: bytes, mode: int = 0o600) -> None:
    path = _safe_path(root, relative)
    _mkdir_private(path.parent)
    _safe_path(root, relative)
    descriptor, temporary = tempfile.mkstemp(prefix=".orca-keychron-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _safe_path(root, relative)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _locked(root: Path) -> Iterator[None]:
    path = _safe_path(root, LOCK)
    _mkdir_private(path.parent)
    _safe_path(root, LOCK)
    created = False
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        created = True
    except FileExistsError:
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if created:
            os.fchmod(fd, 0o600)
        lock_info = os.fstat(fd)
        if (
            not stat.S_ISREG(lock_info.st_mode)
            or lock_info.st_uid != os.getuid()
            or stat.S_IMODE(lock_info.st_mode) != 0o600
        ):
            raise GjcInstallError(f"Invalid installer lock: {path}")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise GjcInstallError("Another GJC installation operation is running") from exc
        yield
    finally:
        os.close(fd)


def _recover(root: Path) -> bool:
    content = _read(root, JOURNAL)
    if content is None:
        return False
    try:
        if _mode(root, JOURNAL) != 0o600:
            raise ValueError("invalid recovery journal mode")
        journal = json.loads(content)
        if (
            not isinstance(journal, dict)
            or set(journal) != {"owner", "schema", "changes"}
            or journal.get("owner") != OWNER
            or journal.get("schema") != 1
        ):
            raise ValueError("invalid recovery journal envelope")
        entries = journal.get("changes")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 65:
            raise ValueError("invalid recovery journal changes")
        decoded = []
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {
                "path",
                "before",
                "after_sha256",
                "mode",
            }:
                raise ValueError("invalid recovery journal entry")
            name = entry.get("path")
            if (
                not isinstance(name, str)
                or name in seen
                or not _owned_path(name, manifest=True)
            ):
                raise ValueError("invalid recovery journal path")
            seen.add(name)
            encoded_before = entry.get("before")
            if encoded_before is not None and not isinstance(encoded_before, str):
                raise ValueError("invalid recovery journal backup")
            before = (
                base64.b64decode(encoded_before, validate=True)
                if encoded_before is not None
                else None
            )
            after = entry.get("after_sha256")
            if after is not None and (
                not isinstance(after, str) or _HASH.fullmatch(after) is None
            ):
                raise ValueError("invalid recovery journal digest")
            mode = entry.get("mode")
            if not isinstance(mode, int) or isinstance(mode, bool) or mode != 0o600:
                raise ValueError("invalid recovery journal mode")
            current = _read(root, name)
            current_hash = _sha(current) if current is not None else None
            before_hash = _sha(before) if before is not None else None
            if current_hash not in (before_hash, after):
                raise GjcInstallError(f"Recovery would overwrite a modified file: {root / name}")
            decoded.append((name, before, mode))
    except (ValueError, KeyError, TypeError) as exc:
        raise GjcInstallError(f"Invalid recovery journal: {root / JOURNAL}") from exc

    # Restore old dependencies before reactivating the old loader.  When there
    # was no old loader, remove the new loader before deleting its dependencies.
    def recovery_order(item: tuple[str, bytes | None, int]) -> int:
        name, before, _ = item
        if name == MANIFEST:
            return 4
        if name == LOADER:
            return 1
        if before is not None:
            return 0
        return 2

    decoded.sort(key=recovery_order)
    for name, before, mode in decoded:
        if before is not None:
            _atomic_write(root, name, before, mode)
        else:
            _unlink(root, name)
    _unlink(root, JOURNAL)
    return True


def _transaction(root: Path, desired: dict[str, bytes | None]) -> None:
    entries = []
    for name, after in desired.items():
        before = _read(root, name)
        if before == after:
            continue
        mode = stat.S_IMODE((root / name).stat().st_mode) & 0o777 if before is not None else 0o600
        entries.append(
            {
                "path": name,
                "before": base64.b64encode(before).decode() if before is not None else None,
                "after_sha256": _sha(after) if after is not None else None,
                "mode": mode,
            }
        )
    if not entries:
        return
    _atomic_write(root, JOURNAL, _json({"owner": OWNER, "schema": 1, "changes": entries}))
    try:
        # A loader must only point at assets that already exist.  Conversely,
        # uninstall disables discovery before deleting imported assets.  The
        # manifest is the final commit record in both directions.
        def apply_order(entry: dict[str, Any]) -> int:
            name = entry["path"]
            after = desired[name]
            if name == MANIFEST:
                return 4
            if name == LOADER:
                return 0 if after is None else 2
            return 1 if after is not None else 3

        entries.sort(key=apply_order)
        for entry in entries:
            name = entry["path"]
            after = desired[name]
            if after is None:
                _unlink(root, name)
            else:
                _atomic_write(root, name, after, entry["mode"])
        _unlink(root, JOURNAL)
    except Exception:
        _recover(root)
        raise


def install(
    *,
    scope: str = "user",
    project_path: Any = None,
    agent_dir: Any = None,
    socket_path: Any = None,
    dry_run: bool = False,
) -> dict:
    if dry_run:
        return plan_install(
            scope=scope, project_path=project_path, agent_dir=agent_dir, socket_path=socket_path
        )
    root = _native_dir(scope, project_path, agent_dir)
    # Validate resources/destinations before creating even the lock directory.
    initial = plan_install(
        scope=scope, project_path=project_path, agent_dir=agent_dir, socket_path=socket_path
    )
    if initial["conflicts"] and not initial["recovery_required"]:
        raise GjcInstallError(
            "Refusing conflicting or modified files: " + ", ".join(initial["conflicts"])
        )
    try:
        with _locked(root):
            recovered = _recover(root)
            plan = plan_install(
                scope=scope, project_path=project_path, agent_dir=agent_dir, socket_path=socket_path
            )
            if plan["conflicts"]:
                raise GjcInstallError(
                    "Refusing conflicting or modified files: " + ", ".join(plan["conflicts"])
                )
            files = _desired(root, Path(plan["socket_path"]))
            previous = _manifest(root)
            manifest = {
                "owner": OWNER,
                "schema": 1,
                "package_version": __version__,
                "supported_gjc_version": SUPPORTED_GJC_VERSION,
                "socket_path": plan["socket_path"],
                "files": {name: _sha(value) for name, value in files.items()},
            }
            changes: dict[str, bytes | None] = dict(files)
            if previous:
                for name in previous["files"]:
                    if name not in changes:
                        changes[name] = None
            changes[MANIFEST] = _json(manifest)
            _transaction(root, changes)
            plan.update(dry_run=False, installed=True, recovered=recovered)
            return plan
    except OSError as exc:
        raise GjcInstallError(f"GJC installation failed: {exc}") from exc


def uninstall(
    *,
    scope: str = "user",
    project_path: Any = None,
    agent_dir: Any = None,
    dry_run: bool = False,
) -> dict:
    root = _native_dir(scope, project_path, agent_dir)
    initial = status(scope=scope, project_path=project_path, agent_dir=agent_dir)
    initial.update(
        action="uninstall",
        dry_run=dry_run,
        can_apply=not (initial["modified"] or initial["conflicts"]),
    )
    if dry_run or (not initial["installed"] and not initial["recovery_required"]):
        return initial
    try:
        with _locked(root):
            recovered = _recover(root)
            current = status(scope=scope, project_path=project_path, agent_dir=agent_dir)
            if current["modified"] or current["conflicts"]:
                raise GjcInstallError(
                    "Refusing to remove modified or unowned GJC files: "
                    + ", ".join(current["modified"] + current["conflicts"])
                )
            manifest = _manifest(root)
            if manifest:
                # Disable discovery before removing the imported module.
                changes = {
                    LOADER: None,
                    **{name: None for name in manifest["files"]},
                    MANIFEST: None,
                }
                _transaction(root, changes)
            initial.update(installed=False, removed=bool(manifest), recovered=recovered)
            return initial
    except OSError as exc:
        raise GjcInstallError(f"GJC removal failed: {exc}") from exc
