"""The `environment` tag on every structured log line must name the real environment.

Regression guard for #712: the tag was read from a separate, unprefixed `ENVIRONMENT`
variable that no deployment set, so every production log line was tagged "unknown".
It now derives from `Settings.environment`, which has no default (#683).
"""

from __future__ import annotations

import json
import logging

import pytest

from platform_control.config import get_settings
from platform_control.observability import event_logging


@pytest.fixture(autouse=True)
def _clear_caches():
    """Both the tag and the settings it derives from are process-cached."""
    event_logging._environment.cache_clear()
    get_settings.cache_clear()
    yield
    event_logging._environment.cache_clear()
    get_settings.cache_clear()


def _emit(caplog: pytest.LogCaptureFixture) -> dict:
    logger = logging.getLogger("test.event_logging")
    with caplog.at_level(logging.INFO, logger="test.event_logging"):
        event_logging.log_event(logger, logging.INFO, "run_started")
    return json.loads(caplog.records[-1].getMessage())


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
def test_tag_reflects_the_configured_environment(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    environment: str,
) -> None:
    monkeypatch.setenv("PLATFORM_CONTROL_ENVIRONMENT", environment)

    fields = _emit(caplog)

    assert fields["environment"] == environment
    assert fields["service"] == "platform-control"


def test_the_retired_unprefixed_variable_no_longer_wins(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#712: a stray `ENVIRONMENT` must not override the configured environment.

    Two variables meaning the same thing is what let them drift apart, so the old one
    is not merely unused — it must be inert.
    """
    monkeypatch.setenv("PLATFORM_CONTROL_ENVIRONMENT", "production")
    monkeypatch.setenv("ENVIRONMENT", "somewhere-else")

    assert _emit(caplog)["environment"] == "production"


# The complementary half of #712 — that a *missing* environment fails loudly instead of
# being mislabelled — is a property of `Settings.environment` having no default, and is
# already covered by tests/unit/test_config_environment.py (#683). Deriving the log tag
# from that setting is what extends the guarantee to log lines; it is not re-asserted here.
