"""`Settings.environment` must be declared, not defaulted (#683).

`PLATFORM_CONTROL_ENVIRONMENT` was set nowhere in the repo while the field defaulted
to `"development"`, so every deployment reported itself as development. The only read
at the time was benign (uvicorn `reload`), but any safety gate written the obvious way
— "skip destructive seeding unless dev", "allow fixtures only in dev" — would have
taken the dev branch in production and failed *open*, with nothing to notice.

`_env_file=None` on every construction below: the field is otherwise satisfiable from a
developer's local `platform-control/.env`, which would make these pass vacuously.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from platform_control.config import Settings

ENV_VAR = "PLATFORM_CONTROL_ENVIRONMENT"


def test_missing_environment_fails_at_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    assert "environment" in str(excinfo.value)


def test_unknown_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """`prod` is not `production` — a typo must fail loudly, not fall back to dev."""
    monkeypatch.setenv(ENV_VAR, "prod")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["development", "staging", "production"])
def test_known_environments_are_accepted(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, value)
    assert Settings(_env_file=None).environment == value
