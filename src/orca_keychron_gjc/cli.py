from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import shutil
import signal
import subprocess
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from orca_keychron.config import DEFAULT_LED_TOTAL, DEFAULT_LEDS
from orca_keychron.indicator import Indicator
from orca_keychron.keychron_hid import (
    KeychronDevice,
    KeychronError,
    enumerate_keychron_interfaces,
)
from orca_keychron.orca_status import default_orca_command
from orca_keychron.permissions import macos_permission_status
from orca_keychron.rendering import YELLOW

from . import __version__, autostart, gjc_install
from .autostart import AutostartError
from .config import (
    Config,
    ConfigError,
    ensure_private_config_dir,
    load_config,
    registry_path,
    save_config,
    socket_path,
)
from .gjc_install import SUPPORTED_GJC_VERSION, GjcInstallError
from .gjc_source import GjcStatusSource, request_control
from .gjc_tracker import GjcTracker


def parse_leds(value: str) -> list[int]:
    try:
        leds = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("LEDs must be comma-separated integers") from exc
    if not leds or any(led < 0 or led > 255 for led in leds):
        raise argparse.ArgumentTypeError("LEDs must contain values from 0 to 255")
    return list(dict.fromkeys(leds))


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("value must be a finite number greater than zero")
    return number


def nonnegative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("value must be a finite non-negative number")
    return number


def bounded_led_total(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 256:
        raise argparse.ArgumentTypeError("LED total must be between 1 and 256")
    return number


def socket_endpoint(value: str) -> Path:
    if "\0" in value:
        raise argparse.ArgumentTypeError("socket path cannot contain NUL")
    path = Path(os.path.abspath(Path(value).expanduser()))
    if len(os.fsencode(path)) > 103:
        raise argparse.ArgumentTypeError("socket path must fit within 103 bytes")
    return path


def canonical_launch_id(value: str) -> str:
    if len(value) != 36:
        raise argparse.ArgumentTypeError("launch ID must be a canonical UUID")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("launch ID must be a canonical UUID") from exc
    if str(parsed) != value:
        raise argparse.ArgumentTypeError("launch ID must be a canonical UUID")
    return value


def _add_orca_option(parser: argparse.ArgumentParser, *, saved: bool = False) -> None:
    parser.add_argument(
        "--orca-command",
        default=None if saved else " ".join(default_orca_command()),
        help=(
            "Orca CLI command (default: saved GJC config or platform default)"
            if saved
            else "Orca CLI command (default: %(default)s)"
        ),
    )


def _add_install_location(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--project", type=Path, help="Project root for project scope")
    parser.add_argument("--agent-dir", type=Path, help="Explicit user GJC agent profile")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orca-keychron-gjc")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser("setup", help="Verify and save GJC keyboard settings")
    setup.add_argument("--leds", type=parse_leds, default=list(DEFAULT_LEDS))
    setup.add_argument("--led-total", type=bounded_led_total, default=DEFAULT_LED_TOTAL)
    setup.add_argument("--product", help="Preferred product-name substring")
    setup.add_argument(
        "--socket", type=socket_endpoint, default=None, help="Private GJC bridge socket"
    )
    setup.add_argument("--preview-seconds", type=nonnegative_float, default=2.0)
    setup.add_argument("--no-preview", action="store_true")
    setup.add_argument("--no-permission-prompt", action="store_true")
    _add_orca_option(setup)

    run = subparsers.add_parser("run", help="Receive GJC snapshots and render the keyboard")
    run.add_argument("--leds", type=parse_leds, help="Saved keyboard LEDs by default")
    run.add_argument("--led-total", type=bounded_led_total, help="Saved LED total by default")
    run.add_argument("--product", help="Saved keyboard product by default")
    run.add_argument(
        "--socket", type=socket_endpoint, default=None, help="Saved bridge socket by default"
    )
    run.add_argument("--registry", type=Path, default=None)
    run.add_argument("--poll-interval", type=positive_float, default=0.75)
    run.add_argument("--open-hold", type=nonnegative_float, default=0.0)
    _add_orca_option(run, saved=True)

    serve = subparsers.add_parser("serve", help="Run only the private GJC bridge receiver")
    serve.add_argument("--socket", type=socket_endpoint, default=None)
    serve.add_argument("--registry", type=Path, default=None)
    serve.add_argument("--slots", type=bounded_led_total, default=len(DEFAULT_LEDS))
    _add_orca_option(serve, saved=True)

    status = subparsers.add_parser("status", help="Show live or persisted GJC launch status")
    status.add_argument("--socket", type=socket_endpoint, default=None)
    status.add_argument("--registry", type=Path, default=None)
    status.add_argument("--json", action="store_true")

    clear = subparsers.add_parser("clear", help="Clear one disconnected, positively dead launch")
    clear.add_argument(
        "launch_id", type=canonical_launch_id, help="Launch ID shown by status"
    )
    clear.add_argument("--socket", type=socket_endpoint, default=None)
    clear.add_argument("--json", action="store_true")

    install = subparsers.add_parser("install", help="Install the owned GJC native hook")
    _add_install_location(install)
    install.add_argument("--socket", type=socket_endpoint, default=None)
    install.add_argument("--dry-run", action="store_true")

    uninstall = subparsers.add_parser("uninstall", help="Reversibly remove the owned GJC hook")
    _add_install_location(uninstall)
    uninstall.add_argument("--dry-run", action="store_true")

    doctor = subparsers.add_parser("doctor", help="Inspect GJC, hook, config, and bridge health")
    _add_install_location(doctor)
    doctor.add_argument("--socket", type=socket_endpoint, default=None)

    login = subparsers.add_parser("autostart", help="Manage the GJC keyboard login service")
    login.add_argument("action", choices=("install", "uninstall", "status"))
    return parser


def _saved_or_default_socket(explicit: Path | None, config: Config | None) -> Path:
    if explicit is not None:
        return explicit
    if config and config.socket_path:
        return Path(config.socket_path)
    return socket_path()


def _saved_or_default_command(explicit: str | None, config: Config | None) -> list[str]:
    if explicit is not None:
        return shlex.split(explicit)
    if config and config.orca_command:
        return list(config.orca_command)
    return default_orca_command()


def setup_command(args: argparse.Namespace) -> int:
    import time

    interfaces = enumerate_keychron_interfaces()
    if not interfaces:
        raise KeychronError("No Keychron raw HID interface found; connect the keyboard over USB")
    device = KeychronDevice(product=args.product)
    restore_required = False
    try:
        if not device.supports_per_key_rgb():
            raise KeychronError(
                "This keyboard firmware does not enable KC_RGB per-key control (0xA8)"
            )
        previous_effect = device.get_effect()
        previous_brightness = device.get_brightness()
        total = device.led_count() or args.led_total
        invalid_leds = [led for led in args.leds if led >= total]
        if invalid_leds:
            raise KeychronError(
                f"Indicator LEDs {invalid_leds} are outside this keyboard's {total}-LED range"
            )
        if not args.no_preview:
            restore_required = True
            device.configure_mixed_per_key_indicator(args.leds, total)
            device.set_zone(dict.fromkeys(args.leds, YELLOW), total)
            print(
                f"Previewing LEDs {','.join(map(str, args.leds))} on {device.product} "
                f"for {args.preview_seconds:g} seconds"
            )
            time.sleep(args.preview_seconds)
        product = device.product
    finally:
        try:
            if restore_required:
                device.restore_lighting(previous_effect, previous_brightness)
        finally:
            device.close()
    configured_socket = args.socket or socket_path()
    saved = save_config(
        Config(
            product=product,
            leds=tuple(args.leds),
            led_total=total,
            orca_command=tuple(shlex.split(args.orca_command)),
            socket_path=str(configured_socket),
        )
    )
    print(f"GJC config saved: {saved}")
    permissions = macos_permission_status(request=not args.no_permission_prompt)
    if permissions is not None:
        print(
            "Permissions: "
            f"Accessibility={'granted' if permissions.accessibility else 'required'}, "
            f"Input Monitoring={'granted' if permissions.input_monitoring else 'required'}"
        )
    print("Next 1: preview the hook with orca-keychron-gjc install --dry-run")
    print("Next 2: install the hook, then run or enable autostart explicitly")
    return 0


def run_command(args: argparse.Namespace) -> int:
    config = load_config()
    leds = args.leds if args.leds is not None else list(config.leds if config else DEFAULT_LEDS)
    total = args.led_total if args.led_total is not None else (
        config.led_total if config else DEFAULT_LED_TOTAL
    )
    product = args.product if args.product is not None else config.product if config else None
    endpoint = _saved_or_default_socket(args.socket, config)
    source = GjcStatusSource(
        socket_path=endpoint,
        command=_saved_or_default_command(args.orca_command, config),
        max_slots=len(leds),
        registry_path=args.registry or registry_path(),
    )
    Indicator(
        source=source,
        zone=leds,
        product=product,
        poll_interval=args.poll_interval,
        open_hold_seconds=args.open_hold,
        led_total=total,
        mode="gjc",
    ).run()
    return 0


def _serve(source: GjcStatusSource, endpoint: Path) -> None:
    stop = threading.Event()
    previous = {}
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, lambda *_args: stop.set())
        source.start()
        print(f"GJC bridge listening: {endpoint}", flush=True)
        while not stop.wait(0.5):
            source.indicators()
    finally:
        source.stop()
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def serve_command(args: argparse.Namespace) -> int:
    config = load_config()
    endpoint = _saved_or_default_socket(args.socket, config)
    source = GjcStatusSource(
        socket_path=endpoint,
        command=_saved_or_default_command(args.orca_command, config),
        max_slots=args.slots,
        registry_path=args.registry or registry_path(),
    )
    _serve(source, endpoint)
    return 0


def _offline_status(path: Path, slots: int) -> dict:
    if not path.exists():
        return {"version": 1, "maxSlots": slots, "launches": [], "overflow": []}
    return GjcTracker(max_slots=slots, registry_path=path).status()


def _print_status(payload: dict) -> None:
    rows = payload.get("launches", [])
    if not rows:
        print("No GJC launches registered")
        return
    keys = "1234567890-="
    for row in rows:
        slot = row.get("slot")
        if slot is None:
            key = "overflow"
        elif isinstance(slot, int) and 0 <= slot < len(keys):
            key = keys[slot]
        elif isinstance(slot, int) and slot >= 0:
            key = f"slot {slot + 1}"
        else:
            key = "invalid slot"
        connection = "live" if row.get("connected") else "offline"
        coverage = " | incomplete coverage" if row.get("complete") is False else ""
        print(
            f"{key}: {row.get('state', 'unknown')} ({connection}) | "
            f"{row.get('agentCount', 0)} sessions | "
            f"{row.get('pendingRequests', 0)} pending | {row.get('launchId')}{coverage}"
        )


def status_command(args: argparse.Namespace) -> int:
    config = load_config()
    endpoint = _saved_or_default_socket(args.socket, config)
    try:
        response = request_control(endpoint, command="status")
        if not response.get("ok"):
            raise RuntimeError(str(response.get("error", "bridge rejected status")))
        status = response.get("status", {})
        source = "live"
    except (OSError, ValueError, RuntimeError):
        slots = len(config.leds) if config else len(DEFAULT_LEDS)
        try:
            status = _offline_status(args.registry or registry_path(), slots)
        except (OSError, ValueError) as exc:
            raise ConfigError(f"Could not read the GJC status registry: {exc}") from exc
        source = "registry"
    result = {"ok": True, "source": source, "socket": str(endpoint), "status": status}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if source != "live":
            print("GJC bridge is offline; showing persisted entries as unknown")
        _print_status(status)
    return 0


def clear_command(args: argparse.Namespace) -> int:
    config = load_config()
    endpoint = _saved_or_default_socket(args.socket, config)
    try:
        response = request_control(endpoint, command="clear", launch_id=args.launch_id)
    except (OSError, ValueError, RuntimeError) as exc:
        raise GjcInstallError(
            "GJC bridge is not reachable; start orca-keychron-gjc run or serve before clearing"
        ) from exc
    cleared = response.get("ok") is True and response.get("cleared") is True
    if args.json:
        print(json.dumps(response, ensure_ascii=False, indent=2))
    elif response["ok"] is False:
        reason = {
            "connected": "the producer is still connected",
            "process_alive": "the local process is still alive",
            "process_death_unconfirmed": "local process death could not be confirmed",
        }[response["error"]["reason"]]
        print(f"GJC clear refused: {reason}; launch and slot were preserved", file=sys.stderr)
    elif cleared:
        print(f"Cleared GJC launch: {args.launch_id}")
    else:
        print("GJC launch was not found", file=sys.stderr)
    return 0 if cleared else 1


def _location(args: argparse.Namespace) -> dict:
    return {"scope": args.scope, "project_path": args.project, "agent_dir": args.agent_dir}


def _gjc_version() -> dict:
    executable = shutil.which("gjc")
    if executable is None:
        return {"available": False, "supported": False, "version": None}
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": True, "supported": False, "version": None}
    version = completed.stdout.strip()
    expected = f"gjc/{SUPPORTED_GJC_VERSION}"
    return {
        "available": True,
        "supported": completed.returncode == 0 and version == expected,
        "version": version[:100],
        "expected": expected,
    }


def install_command(args: argparse.Namespace) -> int:
    detected = _gjc_version()
    if not args.dry_run and not detected["supported"]:
        raise GjcInstallError(
            f"The native hook is verified for gjc/{SUPPORTED_GJC_VERSION}; "
            "install that version before enabling it"
        )
    config = load_config()
    endpoint = _saved_or_default_socket(args.socket, config)
    result = gjc_install.install(
        **_location(args), socket_path=endpoint, dry_run=args.dry_run
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.dry_run:
        print("Restart GJC sessions to load the owned native hook")
    return 0


def uninstall_command(args: argparse.Namespace) -> int:
    result = gjc_install.uninstall(**_location(args), dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def doctor_command(args: argparse.Namespace) -> int:
    config = load_config()
    endpoint = _saved_or_default_socket(args.socket, config)
    result = {
        "gjc": _gjc_version(),
        "config": {
            "configured": config is not None,
            "socket": str(endpoint),
            "registry": str(registry_path()),
        },
        "installation": gjc_install.status(**_location(args)),
    }
    try:
        result["bridge"] = request_control(endpoint, command="status")
    except (OSError, ValueError, RuntimeError):
        result["bridge"] = {"ok": False, "error": "GJC bridge is not reachable"}
    try:
        installed, loaded = autostart.autostart_status()
        result["autostart"] = {"ok": True, "installed": installed, "loaded": loaded}
    except AutostartError as exc:
        result["autostart"] = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def autostart_command(args: argparse.Namespace) -> int:
    path = autostart.launch_agent_path()
    if args.action == "install":
        ensure_private_config_dir()
        print(f"GJC login autostart installed: {autostart.install_autostart()}")
    elif args.action == "uninstall":
        removed = autostart.uninstall_autostart()
        state = "removed" if removed else "was not installed"
        print(f"GJC login autostart {state}: {path}")
    else:
        installed, loaded = autostart.autostart_status(path)
        if loaded:
            state = "installed and loaded"
        elif installed:
            state = "installed but not loaded"
        else:
            state = "not installed"
        print(f"GJC login autostart {state}: {path}")
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handlers = {
        "setup": setup_command,
        "run": run_command,
        "serve": serve_command,
        "status": status_command,
        "clear": clear_command,
        "install": install_command,
        "uninstall": uninstall_command,
        "doctor": doctor_command,
        "autostart": autostart_command,
    }
    try:
        raise SystemExit(handlers[args.command](args))
    except (
        AutostartError,
        ConfigError,
        GjcInstallError,
        KeychronError,
        OSError,
        RuntimeError,
    ) as exc:
        raise SystemExit(str(exc)) from exc
