from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_LEDS = tuple(range(1, 13))
DEFAULT_LED_TOTAL = 100


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    product: str
    leds: tuple[int, ...]
    led_total: int
    orca_command: tuple[str, ...] = ()
    host_ids: tuple[str, ...] = ()


def config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "orca-keychron"
    configured = os.environ.get("XDG_CONFIG_HOME")
    root = Path(configured).expanduser() if configured else Path.home() / ".config"
    return root / "orca-keychron"


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config(path: Path | None = None) -> Config | None:
    target = path or config_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Could not read config {target}: {exc}") from exc
    return parse_config(payload, target)


def parse_config(payload: Any, source: Path | None = None) -> Config:
    label = str(source or "config")
    if not isinstance(payload, dict):
        raise ConfigError(f"Invalid {label}: expected a JSON object")
    product = payload.get("product")
    leds = payload.get("leds")
    led_total = payload.get("led_total")
    orca_command = payload.get("orca_command", [])
    host_ids = payload.get("host_ids", [])
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
    if not isinstance(host_ids, list) or any(
        not isinstance(host, str) or not host for host in host_ids
    ):
        raise ConfigError(f"Invalid {label}: host_ids must contain non-empty strings")
    return Config(
        product=product,
        leds=tuple(leds),
        led_total=led_total,
        orca_command=tuple(orca_command),
        host_ids=tuple(host_ids),
    )


def save_config(config: Config, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    payload = {
        "product": config.product,
        "leds": list(config.leds),
        "led_total": config.led_total,
        "orca_command": list(config.orca_command),
        "host_ids": list(config.host_ids),
    }
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, target)
    except OSError as exc:
        raise ConfigError(f"Could not write config {target}: {exc}") from exc
    return target
