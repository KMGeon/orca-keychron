from __future__ import annotations

import argparse
import json
import math
import shlex
import sys
from collections.abc import Sequence

from . import __version__
from .autostart import (
    AutostartError,
    autostart_status,
    install_autostart,
    launch_agent_path,
    uninstall_autostart,
)
from .config import (
    DEFAULT_LED_TOTAL,
    DEFAULT_LEDS,
    Config,
    ConfigError,
    load_config,
    save_config,
)
from .indicator import Indicator
from .keychron_hid import KeychronDevice, KeychronError, enumerate_keychron_interfaces
from .orca_status import OrcaStatusError, OrcaStatusSource, default_orca_command
from .permissions import macos_permission_status
from .rendering import GREEN, MAGENTA, OFF, ORANGE, RED, SKY_BLUE, YELLOW


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


def led_total(value: str) -> int:
    number = int(value)
    if number < 1 or number > 256:
        raise argparse.ArgumentTypeError("LED total must be between 1 and 256")
    return number


def led_index(value: str) -> int:
    number = int(value)
    if number < 0 or number > 255:
        raise argparse.ArgumentTypeError("LED index must be between 0 and 255")
    return number


def add_orca_options(parser: argparse.ArgumentParser, use_saved: bool = False) -> None:
    parser.add_argument(
        "--orca-command",
        default=None if use_saved else " ".join(default_orca_command()),
        help=(
            "Orca CLI command (default: saved config or platform default)"
            if use_saved
            else "Orca CLI command (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--host",
        action="append",
        dest="host_ids",
        help="Only show agents from this Orca host ID; repeat for multiple hosts",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orca-keychron")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Print Orca's current normalized agents")
    add_orca_options(status)

    probe = subparsers.add_parser("probe", help="Read the connected Keychron LED layout")
    probe.add_argument("--product", help="Preferred product-name substring")

    run = subparsers.add_parser("run", help="Render Orca agent states on the keyboard")
    run.add_argument(
        "--leds",
        type=parse_leds,
        help="Indicator LED indices (default: saved config or numeric row 1 through =)",
    )
    run.add_argument(
        "--led-total", type=led_total, help="Full frame size (default: saved config or 100)"
    )
    run.add_argument("--product", help="Preferred product-name substring")
    run.add_argument("--poll-interval", type=positive_float, default=0.75)
    run.add_argument(
        "--open-hold",
        type=nonnegative_float,
        default=0.0,
        help=(
            "Seconds to hold Option+lit number before opening its Orca worktree tab (default: 0)"
        ),
    )
    add_orca_options(run, use_saved=True)

    setup = subparsers.add_parser("setup", help="Detect, verify, preview, and save a keyboard")
    setup.add_argument("--leds", type=parse_leds, default=list(DEFAULT_LEDS))
    setup.add_argument("--led-total", type=led_total, default=DEFAULT_LED_TOTAL)
    setup.add_argument("--product", help="Preferred product-name substring")
    setup.add_argument("--preview-seconds", type=nonnegative_float, default=2.0)
    setup.add_argument("--no-preview", action="store_true")
    setup.add_argument("--no-autostart", action="store_true")
    setup.add_argument("--no-permission-prompt", action="store_true")
    add_orca_options(setup)

    autostart = subparsers.add_parser("autostart", help="Manage macOS login autostart")
    autostart.add_argument("action", choices=("install", "uninstall", "status"))

    preview = subparsers.add_parser("preview", help="Temporarily preview one status color")
    preview.add_argument(
        "state", choices=("working", "waiting", "blocked", "done", "mixed", "idle", "off")
    )
    preview.add_argument("--seconds", type=nonnegative_float, default=2.0)
    preview.add_argument(
        "--led", type=led_index, default=1, help="LED index to preview (default: 1)"
    )
    preview.add_argument("--product", help="Preferred product-name substring")
    return parser


def status_command(args: argparse.Namespace) -> int:
    source = OrcaStatusSource(shlex.split(args.orca_command), args.host_ids)
    rows = [agent.__dict__ for agent in source.snapshot()]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def probe_command(args: argparse.Namespace) -> int:
    interfaces = enumerate_keychron_interfaces()
    if not interfaces:
        print("No Keychron raw HID interface found")
        return 1
    print("Keychron raw HID interfaces:")
    for interface in interfaces:
        print(f"- {interface.product} (PID 0x{interface.product_id:04X})")
    device = KeychronDevice(product=args.product)
    try:
        print(f"\nSelected: {device.product}")
        print(f"Keychron protocol: {device.protocol_version()}")
        print(f"Support feature bits: 0x{(device.support_features() or 0):02X}")
        per_key = device.supports_per_key_rgb()
        print(f"KC_RGB response echo: {'available' if per_key else 'unavailable'}")
        if per_key:
            print(f"LED count: {device.led_count()}")
            print("LED matrix (-1 means no LED):")
            for index, row in enumerate(device.led_matrix()):
                print(f"row {index}: {' '.join(str(value) for value in row)}")
        else:
            print("The indicator cannot run without firmware that enables KC_RGB.")
    finally:
        device.close()
    return 0


def run_command(args: argparse.Namespace) -> int:
    config = load_config()
    zone = args.leds if args.leds is not None else list(config.leds if config else DEFAULT_LEDS)
    product = args.product if args.product is not None else config.product if config else None
    total = args.led_total if args.led_total is not None else config.led_total if config else 100
    command = (
        shlex.split(args.orca_command)
        if args.orca_command is not None
        else list(config.orca_command)
        if config and config.orca_command
        else default_orca_command()
    )
    host_ids = args.host_ids if args.host_ids is not None else config.host_ids if config else None
    source = OrcaStatusSource(command, host_ids)
    Indicator(
        source=source,
        zone=zone,
        product=product,
        poll_interval=args.poll_interval,
        open_hold_seconds=args.open_hold,
        led_total=total,
    ).run()
    return 0


def setup_command(args: argparse.Namespace) -> int:
    import time

    source = OrcaStatusSource(shlex.split(args.orca_command), args.host_ids)
    agents = source.snapshot()
    print(f"Orca connected: {len(agents)} agent rows")

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
        selected_product = device.product
    finally:
        try:
            if restore_required:
                device.restore_lighting(previous_effect, previous_brightness)
        finally:
            device.close()

    saved = save_config(
        Config(
            selected_product,
            tuple(args.leds),
            total,
            tuple(shlex.split(args.orca_command)),
            tuple(args.host_ids or ()),
        )
    )
    print(f"Config saved: {saved}")

    permissions = macos_permission_status(request=not args.no_permission_prompt)
    if permissions is not None:
        print(
            "Permissions: "
            f"Accessibility={'granted' if permissions.accessibility else 'required'}, "
            f"Input Monitoring={'granted' if permissions.input_monitoring else 'required'}"
        )

    if not args.no_autostart:
        if sys.platform == "darwin":
            installed = install_autostart()
            print(f"Login autostart installed: {installed}")
        else:
            print("Login autostart skipped: currently supported only on macOS")
    print("Setup complete")
    return 0


def autostart_command(args: argparse.Namespace) -> int:
    path = launch_agent_path()
    if args.action == "install":
        print(f"Login autostart installed: {install_autostart()}")
    elif args.action == "uninstall":
        removed = uninstall_autostart()
        print(f"Login autostart {'removed' if removed else 'was not installed'}: {path}")
    else:
        installed, loaded = autostart_status(path)
        if loaded:
            state = "installed and loaded"
        elif installed:
            state = "installed but not loaded"
        else:
            state = "not installed"
        print(f"Login autostart {state}: {path}")
    return 0


def preview_command(args: argparse.Namespace) -> int:
    import time

    colors = {
        "working": YELLOW,
        "waiting": ORANGE,
        "blocked": RED,
        "done": GREEN,
        "mixed": MAGENTA,
        "idle": SKY_BLUE,
        "off": OFF,
    }
    device = KeychronDevice(product=args.product)
    restore_required = False
    try:
        if not device.supports_per_key_rgb():
            raise KeychronError(
                "This keyboard firmware does not enable KC_RGB per-key control (0xA8)"
            )
        previous_effect = device.get_effect()
        previous_brightness = device.get_brightness()
        total = device.led_count() or 100
        if args.led >= total:
            raise KeychronError(f"LED {args.led} is outside this keyboard's {total}-LED range")
        restore_required = True
        color = colors[args.state]
        device.configure_mixed_indicator(total)
        device.set_mixed_zone(None if color == OFF else color, [args.led], total)
        print(
            f"Previewing {args.state} on LED {args.led} of {device.product} "
            f"for {args.seconds:g} seconds"
        )
        time.sleep(args.seconds)
    finally:
        try:
            if restore_required:
                device.restore_lighting(previous_effect, previous_brightness)
        finally:
            device.close()
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handlers = {
        "status": status_command,
        "probe": probe_command,
        "run": run_command,
        "setup": setup_command,
        "autostart": autostart_command,
        "preview": preview_command,
    }
    try:
        raise SystemExit(handlers[args.command](args))
    except (AutostartError, ConfigError, KeychronError, OrcaStatusError) as exc:
        raise SystemExit(str(exc)) from exc
