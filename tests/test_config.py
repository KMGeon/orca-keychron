import json

import pytest

from orca_keychron.config import Config, ConfigError, load_config, save_config


def test_config_round_trip(tmp_path):
    path = tmp_path / "config.json"
    expected = Config("Keychron Q65 Max", (1, 2, 3), 100, ("orca-dev",), ("local",))

    assert save_config(expected, path) == path
    assert load_config(path) == expected
    assert path.stat().st_mode & 0o777 == 0o600


def test_missing_config_returns_none(tmp_path):
    assert load_config(tmp_path / "missing.json") is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"product": "Q65", "leds": [], "led_total": 100},
        {"product": "Q65", "leds": [1, 1], "led_total": 100},
        {"product": "Q65", "leds": [100], "led_total": 100},
        {"product": "Q65", "leds": [True], "led_total": 100},
    ],
)
def test_invalid_config_is_rejected(tmp_path, payload):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(ConfigError):
        load_config(path)
