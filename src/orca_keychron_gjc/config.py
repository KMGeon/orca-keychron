from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MAX_CONFIG_BYTES = 1024 * 1024


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    product: str
    leds: tuple[int, ...]
    led_total: int
    orca_command: tuple[str, ...] = ()
    socket_path: str = ""


def config_dir() -> Path:
    """Return a private GJC child without changing the existing Orca directory."""
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        configured = os.environ.get("XDG_CONFIG_HOME")
        root = Path(configured).expanduser() if configured else Path.home() / ".config"
    return root / "orca-keychron" / "gjc"


def config_path() -> Path:
    return config_dir() / "config.json"


def socket_path() -> Path:
    return config_dir() / "bridge.sock"


def registry_path() -> Path:
    return config_dir() / "registry.json"


# Kept as an explicit compatibility name for the installer/source boundary.
gjc_socket_path = socket_path
gjc_registry_path = registry_path


def effective_socket_path(config: Config | None) -> Path:
    return Path(config.socket_path) if config and config.socket_path else socket_path()


def ensure_private_config_dir(path: Path | None = None) -> Path:
    """Create only the GJC leaf, then reject loose, unowned, or symlinked leaves."""
    target = path or config_dir()
    try:
        if target.is_symlink() or target.parent.is_symlink():
            raise ConfigError(f"A private user-owned directory is required: {target}")
        existed = target.exists()
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not existed:
            target.chmod(0o700)
        info = target.lstat()
    except OSError as exc:
        raise ConfigError(f"Could not prepare private GJC directory {target}: {exc}") from exc
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ConfigError(f"A private user-owned directory is required: {target}")
    return target


def _read_private_config(target: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK
    try:
        descriptor = os.open(target, flags)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ConfigError(f"Could not read GJC config {target}: {exc}") from exc
    with os.fdopen(descriptor, "rb") as stream:
        try:
            directory = target.parent.lstat()
        except OSError as exc:
            raise ConfigError(f"Could not inspect GJC config directory {target.parent}: {exc}") from exc
        if (
            not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != os.getuid()
            or stat.S_IMODE(directory.st_mode) != 0o700
        ):
            raise ConfigError(f"A private user-owned directory is required: {target.parent}")
        if target.parent.parent.is_symlink():
            raise ConfigError(
                f"A private user-owned directory is required: {target.parent.parent}"
            )
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077
            or info.st_size > _MAX_CONFIG_BYTES
        ):
            raise ConfigError(f"GJC config must be a bounded private user-owned file: {target}")
        try:
            return stream.read(_MAX_CONFIG_BYTES + 1).decode("utf-8")
        except UnicodeError as exc:
            raise ConfigError(f"Could not read GJC config {target}: {exc}") from exc


def load_config(path: Path | None = None) -> Config | None:
    target = path or config_path()
    try:
        payload = json.loads(_read_private_config(target))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Could not read GJC config {target}: {exc}") from exc
    return parse_config(payload, target)


def parse_config(payload: Any, source: Path | None = None) -> Config:
    label = str(source or "GJC config")
    if not isinstance(payload, dict):
        raise ConfigError(f"Invalid {label}: expected a JSON object")
    if set(payload) - {"product", "leds", "led_total", "orca_command", "socket_path"}:
        raise ConfigError(f"Invalid {label}: contains unsupported settings")
    product = payload.get("product")
    leds = payload.get("leds")
    led_total = payload.get("led_total")
    orca_command = payload.get("orca_command", [])
    configured_socket = payload.get("socket_path", "")
    if not isinstance(product, str) or not product:
        raise ConfigError(f"Invalid {label}: product must be a non-empty string")
    if (
        not isinstance(leds, list)
        or not leds
        or any(not isinstance(led, int) or isinstance(led, bool) for led in leds)
        or any(led < 0 or led > 255 for led in leds)
        or len(leds) != len(set(leds))
    ):
        raise ConfigError(f"Invalid {label}: leds must contain unique integers from 0 to 255")
    if (
        not isinstance(led_total, int)
        or isinstance(led_total, bool)
        or led_total < 1
        or led_total > 256
        or any(led >= led_total for led in leds)
    ):
        raise ConfigError(f"Invalid {label}: led_total must include every configured LED")
    if not isinstance(orca_command, list) or any(
        not isinstance(part, str) or not part for part in orca_command
    ):
        raise ConfigError(f"Invalid {label}: orca_command must contain non-empty strings")
    if not isinstance(configured_socket, str):
        raise ConfigError(f"Invalid {label}: socket_path must be a string")
    if configured_socket:
        candidate = Path(configured_socket)
        if not candidate.is_absolute() or "\0" in configured_socket:
            raise ConfigError(f"Invalid {label}: socket_path must be an absolute path")
        if len(os.fsencode(candidate)) > 103:
            raise ConfigError(f"Invalid {label}: socket_path must fit within 103 bytes")
    return Config(
        product=product,
        leds=tuple(leds),
        led_total=led_total,
        orca_command=tuple(orca_command),
        socket_path=configured_socket,
    )


def save_config(config: Config, path: Path | None = None) -> Path:
    # Validate the exact serialized representation before touching the destination.
    payload = {
        "product": config.product,
        "leds": list(config.leds),
        "led_total": config.led_total,
        "orca_command": list(config.orca_command),
        "socket_path": config.socket_path,
    }
    parse_config(payload, path)
    target = path or config_path()
    ensure_private_config_dir(target.parent)
    if target.exists() or target.is_symlink():
        try:
            info = target.lstat()
        except OSError as exc:
            raise ConfigError(f"Could not inspect GJC config {target}: {exc}") from exc
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise ConfigError(f"Refusing to replace an unsafe GJC config: {target}")
    descriptor = -1
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".config-", dir=target.parent)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            os.fchmod(stream.fileno(), 0o600)
            stream.write(json.dumps(payload, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as exc:
        raise ConfigError(f"Could not write GJC config {target}: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return target
