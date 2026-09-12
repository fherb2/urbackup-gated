"""Configuration file loading and validation."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path("/etc/urbackup-gated.conf")

DEFAULT_CHECK_SECONDS = 30
DEFAULT_CHECK_SECONDS_WINDOW_OPEN = 5
DEFAULT_IDLE_NOTIFY_SECONDS = 7200
DEFAULT_PROGRESS_NOTIFY_SECONDS = 900
DEFAULT_NOTIFY_TIMEOUT_SECONDS = 5


class ConfigError(Exception):
    """Configuration is missing, unreadable or invalid."""


@dataclass(frozen=True)
class Config:
    allowed_ssids: frozenset[str]
    check_seconds: int
    check_seconds_window_open: int
    idle_notify_seconds: int
    progress_notify_seconds: int
    notify_timeout_seconds: int


def _positive_int(table: dict, key: str, default: int, where: str) -> int:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{where}.{key} must be a positive integer")
    return value


def _allowed_ssids(document: dict) -> frozenset[str]:
    if "allowed_ssids" not in document:
        raise ConfigError("allowed_ssids is missing")
    value = document["allowed_ssids"]
    if not isinstance(value, list) or not all(isinstance(s, str) for s in value):
        raise ConfigError("allowed_ssids must be a list of strings")
    return frozenset(value)


def _table(document: dict, name: str) -> dict:
    value = document.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a table")
    return value


def load(path: Path = CONFIG_PATH) -> Config:
    """Read and validate the configuration, raising ConfigError on any defect."""
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"{path} does not exist") from None
    except PermissionError:
        raise ConfigError(f"{path} is not readable") from None
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path} is not valid TOML: {error}") from None
    except OSError as error:
        raise ConfigError(f"{path} cannot be read: {error}") from None

    intervals = _table(document, "intervals")
    notify = _table(document, "notify")

    return Config(
        allowed_ssids=_allowed_ssids(document),
        check_seconds=_positive_int(
            intervals, "check_seconds", DEFAULT_CHECK_SECONDS, "intervals"
        ),
        check_seconds_window_open=_positive_int(
            intervals,
            "check_seconds_window_open",
            DEFAULT_CHECK_SECONDS_WINDOW_OPEN,
            "intervals",
        ),
        idle_notify_seconds=_positive_int(
            intervals, "idle_notify_seconds", DEFAULT_IDLE_NOTIFY_SECONDS, "intervals"
        ),
        progress_notify_seconds=_positive_int(
            intervals,
            "progress_notify_seconds",
            DEFAULT_PROGRESS_NOTIFY_SECONDS,
            "intervals",
        ),
        notify_timeout_seconds=_positive_int(
            notify, "timeout_seconds", DEFAULT_NOTIFY_TIMEOUT_SECONDS, "notify"
        ),
    )
