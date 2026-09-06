import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from orca_keychron_gjc import config
from orca_keychron_gjc.config import Config, ConfigError, load_config, save_config
from orca_keychron_gjc.gjc_source import GjcStatusSource


def test_gjc_config_uses_distinct_owned_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(config.sys, "platform", "linux")

    directory = tmp_path / "orca-keychron" / "gjc"
    assert config.config_path() == directory / "config.json"
    assert config.socket_path() == directory / "bridge.sock"
    assert config.registry_path() == directory / "registry.json"


def test_gjc_config_round_trip_is_private(tmp_path):
    path = tmp_path / "gjc-config.json"
    expected = Config(
        "Keychron Q65 Max",
        (1, 2, 3),
        72,
        ("orca-dev",),
        "/tmp/orca-keychron-gjc-test.sock",
    )

    assert save_config(expected, path) == path
    assert load_config(path) == expected
    assert path.stat().st_mode & 0o777 == 0o600


def test_missing_gjc_config_returns_none(tmp_path):
    assert load_config(tmp_path / "missing.json") is None


@pytest.mark.parametrize("existing_orca_dir", [False, True])
def test_saved_default_config_is_compatible_with_source_private_directory(
    monkeypatch, existing_orca_dir
):
    with tempfile.TemporaryDirectory(prefix="gjc-private-", dir="/tmp") as temporary:
        orca_dir = Path(temporary) / "orca-keychron"
        private_dir = orca_dir / "gjc"
        monkeypatch.setattr(config, "config_dir", lambda: private_dir)
        if existing_orca_dir:
            orca_dir.mkdir(mode=0o755)
            orca_dir.chmod(0o755)
        expected = Config("Q65", (1, 2), 72, ("orca",), str(config.socket_path()))

        assert save_config(expected) == config.config_path()
        if existing_orca_dir:
            assert stat.S_IMODE(orca_dir.stat().st_mode) == 0o755
        assert stat.S_IMODE(config.config_dir().stat().st_mode) == 0o700
        source = GjcStatusSource(
            config.socket_path(), ["orca"], max_slots=2, registry_path=config.registry_path()
        )
        assert source.socket_path == config.socket_path()
        assert source.tracker.registry_path == config.registry_path()


def test_save_refuses_symlink_or_non_private_gjc_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(config.sys, "platform", "linux")
    orca_dir = tmp_path / "orca-keychron"
    orca_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    config.config_dir().symlink_to(outside, target_is_directory=True)
    expected = Config("Q65", (1,), 72, ("orca",), "/tmp/gjc-private-bridge.sock")

    with pytest.raises(ConfigError, match="private user-owned directory"):
        save_config(expected)
    assert not (outside / "config.json").exists()

    config.config_dir().unlink()
    config.config_dir().mkdir(mode=0o755)
    config.config_dir().chmod(0o755)
    with pytest.raises(ConfigError, match="private user-owned directory"):
        save_config(expected)
    assert stat.S_IMODE(config.config_dir().stat().st_mode) == 0o755


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"product": "Q65", "leds": [], "led_total": 100},
        {"product": "Q65", "leds": [1, 1], "led_total": 100},
        {"product": "Q65", "leds": [100], "led_total": 100},
        {"product": "Q65", "leds": [True], "led_total": 100},
        {"product": "Q65", "leds": [1], "led_total": 100, "socket_path": "relative"},
        {"product": "Q65", "leds": [1], "led_total": 100, "extra": True},
    ],
)
def test_invalid_gjc_config_is_rejected(tmp_path, payload):
    path = tmp_path / "gjc-config.json"
    path.write_text(json.dumps(payload))
    path.chmod(0o600)

    with pytest.raises(ConfigError):
        load_config(path)


def test_corrupt_private_config_and_permission_failure_are_typed(tmp_path, monkeypatch):
    path = tmp_path / "gjc-config.json"
    path.write_bytes(b"{not json\n")
    path.chmod(0o600)
    with pytest.raises(ConfigError, match="Could not read GJC config"):
        load_config(path)

    original_open = config.os.open

    def denied_open(candidate, flags, *args):
        if Path(candidate) == path:
            raise PermissionError("injected permission denial")
        return original_open(candidate, flags, *args)

    monkeypatch.setattr(config.os, "open", denied_open)
    with pytest.raises(ConfigError, match="injected permission denial"):
        load_config(path)
    assert path.read_bytes() == b"{not json\n"


@pytest.mark.parametrize("failure", ["replace", "file_fsync"])
def test_save_partial_failure_preserves_previous_config_and_cleans_temp(
    tmp_path, monkeypatch, failure
):
    path = tmp_path / "gjc config with spaces.json"
    previous = Config("Old Q65", (1,), 72, ("orca",), "/tmp/old gjc.sock")
    replacement = Config("New Q65", (2,), 72, ("orca",), "/tmp/new gjc.sock")
    save_config(previous, path)
    before = path.read_bytes()

    if failure == "replace":
        original_replace = config.os.replace

        def fail_replace(source, destination):
            if Path(destination) == path:
                raise PermissionError("injected replace denial")
            original_replace(source, destination)

        monkeypatch.setattr(config.os, "replace", fail_replace)
    else:
        original_fsync = config.os.fsync
        failed = False

        def fail_first_file_fsync(descriptor):
            nonlocal failed
            if stat.S_ISREG(os.fstat(descriptor).st_mode) and not failed:
                failed = True
                raise OSError("injected file fsync denial")
            original_fsync(descriptor)

        monkeypatch.setattr(config.os, "fsync", fail_first_file_fsync)

    with pytest.raises(ConfigError, match="injected"):
        save_config(replacement, path)

    assert path.read_bytes() == before
    assert load_config(path) == previous
    assert not list(tmp_path.glob(".config-*"))


def test_config_supports_spaces_and_enforces_socket_byte_limit(tmp_path):
    path = tmp_path / "directory with spaces" / "config file.json"
    path.parent.mkdir(mode=0o700)
    accepted_socket = "/tmp/" + "é" * 49
    expected = Config("Keychron Q65 Max", (1, 2), 72, ("orca tool", "--flag value"), accepted_socket)

    save_config(expected, path)

    assert len(os.fsencode(accepted_socket)) == 103
    assert load_config(path) == expected
    rejected = Config("Q65", (1,), 72, (), accepted_socket + "x")
    before = path.read_bytes()
    with pytest.raises(ConfigError, match="103 bytes"):
        save_config(rejected, path)
    assert path.read_bytes() == before


def test_load_rejects_private_file_in_nonprivate_directory_without_mutation(tmp_path):
    directory = tmp_path / "shared"
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    path = directory / "config.json"
    payload = {
        "product": "Q65",
        "leds": [1],
        "led_total": 72,
        "orca_command": ["orca"],
        "socket_path": "/tmp/gjc.sock",
    }
    raw = json.dumps(payload).encode()
    path.write_bytes(raw)
    path.chmod(0o600)

    with pytest.raises(ConfigError, match="private user-owned directory"):
        load_config(path)

    assert path.read_bytes() == raw


def test_save_rejects_symlink_product_ancestor_without_writing_outside(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(config.sys, "platform", "linux")
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (tmp_path / "orca-keychron").symlink_to(outside, target_is_directory=True)
    expected = Config("Q65", (1,), 72, ("orca",), "/tmp/gjc.sock")

    with pytest.raises(ConfigError, match="private user-owned directory"):
        save_config(expected)

    assert list(outside.iterdir()) == []


def test_config_fifo_is_rejected_without_blocking_or_mutating_it(tmp_path):
    path = tmp_path / "config.json"
    os.mkfifo(path, 0o600)
    environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(Path.cwd() / "src"),
    }
    script = """
import sys
from pathlib import Path
from orca_keychron_gjc.config import ConfigError, load_config
try:
    load_config(Path(sys.argv[1]))
except ConfigError:
    raise SystemExit(0)
raise SystemExit(9)
"""

    completed = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=5,
    )

    assert completed.returncode == 0, completed.stderr
    assert stat.S_ISFIFO(path.lstat().st_mode)
