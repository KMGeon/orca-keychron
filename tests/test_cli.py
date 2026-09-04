import pytest

from orca_keychron import __version__, cli
from orca_keychron.cli import build_parser
from orca_keychron.config import Config


@pytest.mark.parametrize(
    "arguments",
    [
        ["run", "--poll-interval", "0"],
        ["run", "--poll-interval", "nan"],
        ["run", "--open-hold", "-1"],
        ["run", "--open-hold", "inf"],
        ["run", "--led-total", "0"],
        ["run", "--led-total", "257"],
        ["preview", "working", "--seconds", "-1"],
        ["preview", "working", "--led", "256"],
    ],
)
def test_cli_rejects_invalid_numeric_options(arguments):
    with pytest.raises(SystemExit):
        build_parser().parse_args(arguments)


def test_cli_accepts_boundary_numeric_options():
    args = build_parser().parse_args(
        [
            "run",
            "--poll-interval",
            "0.1",
            "--open-hold",
            "0",
            "--led-total",
            "1",
        ]
    )

    assert args.poll_interval == 0.1
    assert args.open_hold == 0
    assert args.led_total == 1


def test_cli_prints_package_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"orca-keychron {__version__}\n"


def test_run_uses_saved_keyboard_config(monkeypatch):
    captured = {}

    class FakeIndicator:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: Config("Saved Q65", (4, 5), 72, ("orca-dev",), ("local",)),
    )
    monkeypatch.setattr(cli, "Indicator", FakeIndicator)

    assert cli.run_command(build_parser().parse_args(["run"])) == 0
    assert captured["zone"] == [4, 5]
    assert captured["product"] == "Saved Q65"
    assert captured["led_total"] == 72
    assert captured["source"].command == ["orca-dev"]
    assert captured["source"].host_ids == ("local",)
    assert captured["ran"] is True


def test_setup_verifies_previews_restores_and_saves(monkeypatch, tmp_path):
    saved = {}

    class FakeSource:
        def __init__(self, *_args):
            pass

        def snapshot(self):
            return [object()]

    class FakeDevice:
        product = "Keychron Q65 Max"

        def supports_per_key_rgb(self):
            return True

        def get_effect(self):
            return 7

        def get_brightness(self):
            return 42

        def led_count(self):
            return 72

        def configure_mixed_per_key_indicator(self, leds, total):
            saved["configured"] = (tuple(leds), total)

        def set_zone(self, colors, total):
            saved["colors"] = (colors, total)

        def restore_lighting(self, effect, brightness):
            saved["restored"] = (effect, brightness)

        def close(self):
            saved["closed"] = True

    path = tmp_path / "config.json"
    monkeypatch.setattr(cli, "OrcaStatusSource", FakeSource)
    monkeypatch.setattr(cli, "enumerate_keychron_interfaces", lambda: [object()])
    monkeypatch.setattr(cli, "KeychronDevice", lambda **_kwargs: FakeDevice())
    monkeypatch.setattr(cli, "save_config", lambda config: saved.update(config=config) or path)
    monkeypatch.setattr(cli, "macos_permission_status", lambda request: None)
    monkeypatch.setattr(cli, "default_orca_command", lambda: ["orca"])

    args = build_parser().parse_args(
        ["setup", "--leds", "1,2,3", "--preview-seconds", "0", "--no-autostart"]
    )

    assert cli.setup_command(args) == 0
    assert saved["configured"] == ((1, 2, 3), 72)
    assert saved["restored"] == (7, 42)
    assert saved["config"] == Config("Keychron Q65 Max", (1, 2, 3), 72, ("orca",), ())
    assert saved["closed"] is True
