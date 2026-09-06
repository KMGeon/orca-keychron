from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest

from orca_keychron.indicator import Indicator as SharedIndicator
from orca_keychron_gjc import __version__, cli
from orca_keychron_gjc.cli import build_parser
from orca_keychron_gjc.config import Config
from orca_keychron_gjc.gjc_install import GjcInstallError
from orca_keychron_gjc.gjc_source import GjcStatusSource, request_control


@pytest.fixture
def short_tmp_path():
    with TemporaryDirectory(prefix="gjc-cli-", dir="/tmp") as path:
        yield Path(path)


@pytest.mark.parametrize(
    "arguments",
    [
        ["run", "--poll-interval", "0"],
        ["run", "--poll-interval", "nan"],
        ["run", "--open-hold", "-1"],
        ["run", "--led-total", "257"],
        ["setup", "--preview-seconds", "-1"],
        ["serve", "--slots", "0"],
        ["status", "--socket", "/" + "x" * 104],
    ],
)
def test_gjc_cli_rejects_invalid_numeric_options(arguments):
    with pytest.raises(SystemExit):
        build_parser().parse_args(arguments)


@pytest.mark.parametrize(
    "arguments,command",
    [
        (["setup", "--no-preview"], "setup"),
        (["run"], "run"),
        (["serve"], "serve"),
        (["status"], "status"),
        (["clear", "00000000-0000-0000-0000-000000000000"], "clear"),
        (["install", "--dry-run"], "install"),
        (["uninstall", "--dry-run"], "uninstall"),
        (["doctor"], "doctor"),
        (["autostart", "status"], "autostart"),
    ],
)
def test_gjc_cli_exposes_dedicated_commands(arguments, command):
    assert build_parser().parse_args(arguments).command == command


def test_gjc_cli_prints_package_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"orca-keychron-gjc {__version__}\n"


def test_gjc_run_uses_only_gjc_config_and_shared_indicator(monkeypatch, tmp_path):
    captured = {}

    class FakeSource:
        def __init__(self, **kwargs):
            captured["source"] = kwargs
            self.command = kwargs["command"]

    class FakeIndicator:
        def __init__(self, **kwargs):
            captured["indicator"] = kwargs

        def run(self):
            captured["ran"] = True

    saved = Config(
        "Saved Q65",
        (4, 5),
        72,
        ("orca-dev",),
        str(tmp_path / "bridge.sock"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: saved)
    monkeypatch.setattr(cli, "registry_path", lambda: tmp_path / "registry.json")
    monkeypatch.setattr(cli, "GjcStatusSource", FakeSource)
    monkeypatch.setattr(cli, "Indicator", FakeIndicator)

    assert cli.run_command(build_parser().parse_args(["run"])) == 0
    assert captured["source"] == {
        "socket_path": tmp_path / "bridge.sock",
        "command": ["orca-dev"],
        "max_slots": 2,
        "registry_path": tmp_path / "registry.json",
    }
    assert captured["indicator"]["zone"] == [4, 5]
    assert captured["indicator"]["product"] == "Saved Q65"
    assert captured["indicator"]["led_total"] == 72
    assert captured["indicator"]["mode"] == "gjc"
    assert captured["ran"] is True


def test_status_falls_back_to_registry_and_labels_it_offline(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "load_config", lambda: None)
    monkeypatch.setattr(cli, "socket_path", lambda: tmp_path / "gjc.sock")
    monkeypatch.setattr(cli, "registry_path", lambda: tmp_path / "registry.json")
    monkeypatch.setattr(
        cli,
        "request_control",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()),
    )
    monkeypatch.setattr(
        cli,
        "_offline_status",
        lambda _path, slots: {
            "version": 1,
            "maxSlots": slots,
            "launches": [],
            "overflow": [],
        },
    )

    assert cli.status_command(build_parser().parse_args(["status", "--json"])) == 0
    assert '"source": "registry"' in capsys.readouterr().out


def test_serve_uses_saved_custom_socket_and_orca_command(monkeypatch, tmp_path):
    captured = {}

    class FakeSource:
        def __init__(self, **kwargs):
            captured["source"] = kwargs

    saved = Config(
        "Saved Q65",
        (4, 5),
        72,
        ("orca-dev",),
        str(tmp_path / "custom.sock"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: saved)
    monkeypatch.setattr(cli, "registry_path", lambda: tmp_path / "registry.json")
    monkeypatch.setattr(cli, "GjcStatusSource", FakeSource)
    monkeypatch.setattr(
        cli,
        "_serve",
        lambda source, endpoint: captured.update(served=(source, endpoint)),
    )

    assert cli.serve_command(build_parser().parse_args(["serve"])) == 0
    assert captured["source"] == {
        "socket_path": tmp_path / "custom.sock",
        "command": ["orca-dev"],
        "max_slots": 12,
        "registry_path": tmp_path / "registry.json",
    }
    assert captured["served"][1] == tmp_path / "custom.sock"


def test_install_dry_run_does_not_require_installed_gjc(monkeypatch, tmp_path, capsys):
    captured = {}
    monkeypatch.setattr(cli, "load_config", lambda: None)
    monkeypatch.setattr(cli, "socket_path", lambda: tmp_path / "gjc.sock")
    monkeypatch.setattr(cli, "_gjc_version", lambda: {"supported": False})
    monkeypatch.setattr(
        cli.gjc_install,
        "install",
        lambda **kwargs: captured.update(kwargs) or {"dry_run": True, "can_apply": True},
    )

    assert cli.install_command(build_parser().parse_args(["install", "--dry-run"])) == 0
    assert captured["dry_run"] is True
    assert captured["socket_path"] == tmp_path / "gjc.sock"
    assert '"can_apply": true' in capsys.readouterr().out


def test_real_install_refuses_unverified_gjc_before_mutation(monkeypatch):
    monkeypatch.setattr(cli, "_gjc_version", lambda: {"supported": False})
    monkeypatch.setattr(
        cli.gjc_install,
        "install",
        lambda **_kwargs: pytest.fail("installer must not run"),
    )

    with pytest.raises(GjcInstallError, match="verified for"):
        cli.install_command(build_parser().parse_args(["install"]))


def test_setup_saves_gjc_settings_without_installing_hook(monkeypatch, tmp_path):
    saved = {}

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

    monkeypatch.setattr(cli, "enumerate_keychron_interfaces", lambda: [object()])
    monkeypatch.setattr(cli, "KeychronDevice", lambda **_kwargs: FakeDevice())
    monkeypatch.setattr(cli, "save_config", lambda value: saved.update(config=value) or Path("x"))
    monkeypatch.setattr(cli, "macos_permission_status", lambda request: None)
    monkeypatch.setattr(cli, "socket_path", lambda: tmp_path / "gjc.sock")
    monkeypatch.setattr(
        cli.gjc_install,
        "install",
        lambda **_kwargs: pytest.fail("setup must not install the real hook"),
    )

    args = build_parser().parse_args(
        ["setup", "--leds", "1,2,3", "--preview-seconds", "0"]
    )
    assert cli.setup_command(args) == 0
    assert saved["config"] == Config(
        "Keychron Q65 Max",
        (1, 2, 3),
        72,
        tuple(cli.default_orca_command()),
        str(tmp_path / "gjc.sock"),
    )
    assert saved["restored"] == (7, 42)
    assert saved["closed"] is True


def test_gjc_autostart_status_uses_dedicated_service(monkeypatch, tmp_path, capsys):
    path = tmp_path / "orca-keychron-gjc.plist"
    monkeypatch.setattr(cli.autostart, "launch_agent_path", lambda: path)
    monkeypatch.setattr(cli.autostart, "autostart_status", lambda value: (True, False))

    assert cli.autostart_command(build_parser().parse_args(["autostart", "status"])) == 0
    assert capsys.readouterr().out == f"GJC login autostart installed but not loaded: {path}\n"


def test_clear_rejects_invalid_uuid_before_contacting_live_bridge(short_tmp_path, capsys):
    endpoint = short_tmp_path / "gjc.sock"
    source = GjcStatusSource(endpoint, ["orca"])
    source.start()
    try:
        with pytest.raises(SystemExit) as exit_info:
            cli.main(["clear", "not-a-uuid", "--socket", str(endpoint)])

        assert exit_info.value.code == 2
        assert "launch ID must be a canonical UUID" in capsys.readouterr().err
        assert request_control(endpoint)["ok"] is True
    finally:
        source.stop()


def test_clear_reports_unreachable_bridge_for_valid_uuid(short_tmp_path):
    endpoint = short_tmp_path / "missing.sock"

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["clear", str(uuid4()), "--socket", str(endpoint)])

    assert exit_info.value.code == (
        "GJC bridge is not reachable; start orca-keychron-gjc run or serve before clearing"
    )


def test_serve_collision_is_a_bounded_cli_error_and_preserves_live_bridge(
    monkeypatch, short_tmp_path, tmp_path
):
    endpoint = short_tmp_path / "gjc.sock"
    source = GjcStatusSource(endpoint, ["orca"])
    source.start()
    monkeypatch.setattr(cli, "load_config", lambda: None)
    try:
        with pytest.raises(SystemExit) as exit_info:
            cli.main(
                [
                    "serve",
                    "--socket",
                    str(endpoint),
                    "--registry",
                    str(tmp_path / "second-registry.json"),
                ]
            )

        assert "Another GJC receiver already owns this socket" in str(exit_info.value)
        assert request_control(endpoint)["ok"] is True
    finally:
        source.stop()


def test_run_receiver_failure_is_a_bounded_cli_error_after_cleanup(
    monkeypatch, short_tmp_path
):
    class FailingSource:
        command = ("orca",)
        started = False
        stopped = False

        def start(self):
            self.started = True

        def indicators(self, _now):
            raise RuntimeError("GJC receiver failed; restart after fixing local storage")

        def stop(self):
            self.stopped = True

    class FakeDevice:
        product = "Keychron Q65 Max"
        closed = False
        restored = None

        def supports_per_key_rgb(self):
            return True

        def get_effect(self):
            return 7

        def get_brightness(self):
            return 42

        def led_count(self):
            return 72

        def configure_mixed_per_key_indicator(self, _zone, _total):
            pass

        def restore_lighting(self, effect, brightness):
            self.restored = (effect, brightness)

        def close(self):
            self.closed = True

    class PassiveListener:
        def start(self):
            pass

        def stop(self):
            pass

    source = FailingSource()
    device = FakeDevice()
    monkeypatch.setattr(cli, "load_config", lambda: None)
    monkeypatch.setattr(cli, "GjcStatusSource", lambda **_kwargs: source)
    monkeypatch.setattr(
        cli,
        "Indicator",
        lambda **kwargs: SharedIndicator(
            **kwargs,
            device_factory=lambda **_device_kwargs: device,
            listener_factory=lambda _selection: PassiveListener(),
        ),
    )

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["run", "--socket", str(short_tmp_path / "gjc.sock")])

    assert exit_info.value.code == (
        "GJC receiver failed; restart after fixing local storage"
    )
    assert source.started is True
    assert source.stopped is True
    assert device.restored == (7, 42)
    assert device.closed is True


@pytest.mark.parametrize("as_json", [False, True])
def test_clear_live_producer_reports_rejection_not_unreachable(
    short_tmp_path, monkeypatch, capsys, as_json,
):
    import json
    import os

    from test_gjc_protocol import frame
    from test_gjc_source import connect, eventually, send

    monkeypatch.setattr(cli, "load_config", lambda: None)
    endpoint = short_tmp_path / "gjc.sock"
    source = GjcStatusSource(endpoint, [])
    source.start()
    try:
        with connect(source) as producer:
            row = dict(frame(), pid=os.getpid())
            send(producer, row)
            eventually(lambda: len(source.indicators()) == 1)
            arguments = ["clear", row["launchId"], "--socket", str(endpoint)]
            if as_json:
                arguments.append("--json")
            with pytest.raises(SystemExit) as result:
                cli.main(arguments)
            assert result.value.code == 1
            output = capsys.readouterr()
            if as_json:
                response = json.loads(output.out)
                assert response["ok"] is False
                assert response["cleared"] is False
                assert response["error"] == {"code": "clear_refused", "reason": "connected"}
            else:
                assert "GJC clear refused: the producer is still connected" in output.err
                assert "launch and slot were preserved" in output.err
                assert "not reachable" not in output.err
                assert "not found" not in output.err
            assert source.indicators()[0].launch_id == row["launchId"]
    finally:
        source.stop()
