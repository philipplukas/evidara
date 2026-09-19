"""A stored `acquisition_spec` that no longer validates is reported, not raised (#953).

`SourceVersionResponse.acquisition_spec` is a union discriminated on `provider`, so a
stored row whose JSON predates a provider — or was written past the service layer, as
the demo seeder did — used to blow up response construction. That surfaced as an
unhandled 500 on `GET /v1/sources/{id}/versions`, and the admin's dashboard rendered
that 500 as an em dash, identical to "this source has no versions". A failure read as
an absence is the collapse ADR-0052 names, and #958 promotes to a system property.

The load-bearing assertions here are therefore about *distinguishability*: the row
comes back, and the reason it is unreadable comes back with it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from platform_control.domain import ExecutionMode, SourceVersionStatus
from platform_control.models.source_version import SourceVersion
from platform_control.schemas.source import SourceVersionResponse

#: What the demo seeder wrote before #953: no `provider`, so no union member matches.
UNREADABLE_SPEC = {"kind": "demo_fixture", "targets": []}

READABLE_SPEC = {
    "provider": "deterministic_http",
    "seed_urls": ["https://example.invalid/norms"],
}


def _orm_row(spec: dict) -> SourceVersion:
    """A `SourceVersion` row as the ORM hands it to response construction."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return SourceVersion(
        source_version_id="sv_test",
        source_id="src_test",
        extractor_profile_id=None,
        version_label="test-label",
        status=SourceVersionStatus.DRAFT,
        execution_mode=ExecutionMode.SHADOW,
        acquisition_spec=spec,
        created_at=now,
        updated_at=now,
    )


def test_readable_spec_round_trips_with_no_error() -> None:
    response = SourceVersionResponse.model_validate(_orm_row(READABLE_SPEC))

    assert response.acquisition_spec is not None
    assert response.acquisition_spec.provider == "deterministic_http"
    assert response.acquisition_spec_error is None


def test_unreadable_spec_is_reported_rather_than_raised() -> None:
    """The row survives. Before #953 this call raised and the request became a 500."""
    response = SourceVersionResponse.model_validate(_orm_row(UNREADABLE_SPEC))

    assert response.source_version_id == "sv_test"
    assert response.version_label == "test-label"
    assert response.execution_mode == ExecutionMode.SHADOW
    assert response.acquisition_spec is None
    assert response.acquisition_spec_error is not None
    assert "provider" in response.acquisition_spec_error


def test_spec_error_names_the_failing_location_without_echoing_the_spec() -> None:
    """The reason is diagnostic, but a stored spec can hold provider credentials.

    Pydantic's own `str(exc)` embeds the whole input on every line. If this summary
    ever starts echoing it, a secret in an `acquisition_spec` reaches any operator
    who can read a version list.
    """
    row = _orm_row({"provider": "deterministic_http", "seed_urls": [], "seed_url": None})
    response = SourceVersionResponse.model_validate(row)

    assert response.acquisition_spec is None
    assert response.acquisition_spec_error is not None
    assert "seed_url" in response.acquisition_spec_error
    assert "https://errors.pydantic.dev" not in response.acquisition_spec_error


def test_a_stored_null_spec_is_reported_rather_than_raising() -> None:
    """The column is NOT NULL, so this is defence, not a case we have seen.

    The mutual-exclusion guard below would otherwise turn a surprise NULL straight
    back into the 500 this change removes. Production has 0 of 26 rows like this
    (measured 2026-09-19), which is exactly why it must not be the one shape that
    still raises.
    """
    row = _orm_row(READABLE_SPEC)
    row.acquisition_spec = None

    response = SourceVersionResponse.model_validate(row)

    assert response.acquisition_spec is None
    assert response.acquisition_spec_error is not None
    assert "null" in response.acquisition_spec_error


def test_null_spec_without_a_reason_is_refused() -> None:
    """The mutation test for the `spec_is_readable_or_says_why` guard.

    Delete that `model_validator(mode="after")` and this test goes red: a null spec
    with no stated reason would construct, and the wire payload would say "no spec"
    for a version that has one nobody could read.
    """
    with pytest.raises(ValidationError, match="mutually exclusive"):
        SourceVersionResponse.model_validate(
            {
                "source_version_id": "sv_test",
                "source_id": "src_test",
                "extractor_profile_id": None,
                "version_label": "test-label",
                "status": SourceVersionStatus.DRAFT,
                "execution_mode": ExecutionMode.SHADOW,
                "acquisition_spec": None,
                "acquisition_spec_error": None,
                "created_at": "2026-09-19T00:00:00Z",
                "updated_at": "2026-09-19T00:00:00Z",
            }
        )


def test_a_readable_spec_may_not_also_carry_a_reason() -> None:
    """The other half of the same guard: a populated spec is not also 'unreadable'."""
    with pytest.raises(ValidationError, match="mutually exclusive"):
        SourceVersionResponse.model_validate(
            {
                "source_version_id": "sv_test",
                "source_id": "src_test",
                "extractor_profile_id": None,
                "version_label": "test-label",
                "status": SourceVersionStatus.DRAFT,
                "execution_mode": ExecutionMode.SHADOW,
                "acquisition_spec": READABLE_SPEC,
                "acquisition_spec_error": "something went wrong",
                "created_at": "2026-09-19T00:00:00Z",
                "updated_at": "2026-09-19T00:00:00Z",
            }
        )
