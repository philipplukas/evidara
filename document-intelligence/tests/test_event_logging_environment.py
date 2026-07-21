"""The `environment` tag on every structured log line must name the real environment.

Regression guard for #712: the tag was read from an unprefixed `ENVIRONMENT` variable
that no deployment set, so every production log line was tagged "unknown". It now reads
`DI_ENVIRONMENT`, which `infra/hetzner/apps/configmap.yaml` sets for every DI pod.
"""

from __future__ import annotations

import json
import logging

import pytest

from document_intelligence.observability import event_logging


@pytest.fixture(autouse=True)
def _clear_cache():
    event_logging._environment.cache_clear()
    yield
    event_logging._environment.cache_clear()


def _emit(caplog: pytest.LogCaptureFixture) -> dict:
    logger = logging.getLogger("test.di.event_logging")
    with caplog.at_level(logging.INFO, logger="test.di.event_logging"):
        event_logging.log_event(logger, logging.INFO, "document_processed")
    return json.loads(caplog.records[-1].getMessage())


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
def test_tag_reflects_the_configured_environment(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    environment: str,
) -> None:
    monkeypatch.setenv("DI_ENVIRONMENT", environment)

    fields = _emit(caplog)

    assert fields["environment"] == environment
    assert fields["service"] == "di-consumer"


def test_the_retired_unprefixed_variable_no_longer_wins(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#712: a stray `ENVIRONMENT` must not override the configured environment."""
    monkeypatch.setenv("DI_ENVIRONMENT", "production")
    monkeypatch.setenv("ENVIRONMENT", "somewhere-else")

    assert _emit(caplog)["environment"] == "production"


def test_an_unset_environment_is_reported_not_silently_unknown(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DI has no required settings model, so the tag falls back — but says so.

    Falling back silently is precisely how #712 stayed invisible in production.
    """
    monkeypatch.delenv("DI_ENVIRONMENT", raising=False)

    with caplog.at_level(logging.WARNING):
        assert _emit(caplog)["environment"] == "unknown"

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("environment_tag_unset" in r.getMessage() for r in warnings)


def test_the_unset_warning_is_emitted_once_per_process(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A per-line warning would drown the log stream it is meant to make readable."""
    monkeypatch.delenv("DI_ENVIRONMENT", raising=False)

    with caplog.at_level(logging.WARNING):
        _emit(caplog)
        _emit(caplog)
        _emit(caplog)

    warnings = [r for r in caplog.records if "environment_tag_unset" in r.getMessage()]
    assert len(warnings) == 1
