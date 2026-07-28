"""The attribution rule — which jurisdiction a measurement belongs to, and when we admit
we cannot say.

The failure this guards against is silent: a provider reports `entity_id: 26`, the ledger
needs `jur_ch_zh`, and the only bridge is the source's single jurisdiction. Guessing a
split across several entities would attribute one canton's published total to another,
which is worse than reporting nothing.
"""

from __future__ import annotations

from platform_control.domain import CoverageAttributionStatus, DenominatorTier
from platform_control.services.coverage_reconciliation import parse_coverage_payload


def _coverage(**overrides) -> dict:
    payload = {
        "strategy": "systematic_digit_union",
        "denominator_tier": "published",
        "denominator_source": "/api/frontend/v1/{lang}/entities/extended",
        "complete": True,
        "entities": [
            {"entity_id": 26, "expected": 1377, "observed": 1377, "gap": 0},
        ],
    }
    payload.update(overrides)
    return {"captured": 1377, "coverage": payload}


def test_a_run_without_coverage_records_nothing() -> None:
    """Searching templates legitimately have nothing to reconcile."""
    assert parse_coverage_payload({"captured": 4}) is None
    assert parse_coverage_payload(None) is None
    assert parse_coverage_payload({"coverage": "not-a-dict"}) is None


def test_single_entity_coverage_attributes_cleanly() -> None:
    parsed = parse_coverage_payload(_coverage())
    assert parsed is not None
    assert parsed.attribution_status is CoverageAttributionStatus.ATTRIBUTED
    assert parsed.entity_id == "26"
    assert parsed.expected == 1377
    assert parsed.observed == 1377
    assert parsed.denominator_tier is DenominatorTier.PUBLISHED


def test_multi_entity_coverage_is_recorded_as_unattributed_not_dropped() -> None:
    """The attempt must leave evidence, following `Run.refused`.

    Dropping it would make "two runs measured something we could not attribute" look
    identical to "nothing has ever been measured".
    """
    parsed = parse_coverage_payload(
        _coverage(
            entities=[
                {"entity_id": 26, "expected": 1377, "observed": 1377},
                {"entity_id": 4, "expected": 1121, "observed": 1121},
            ]
        )
    )
    assert parsed is not None
    assert parsed.attribution_status is CoverageAttributionStatus.AMBIGUOUS_MULTI_ENTITY
    # No expected: a denominator spanning two cantons belongs to neither.
    assert parsed.expected is None
    assert parsed.observed == 2498


def test_zero_expected_is_unstatable_not_a_denominator() -> None:
    parsed = parse_coverage_payload(
        _coverage(entities=[{"entity_id": 26, "expected": 0, "observed": 0}])
    )
    assert parsed is not None
    assert parsed.expected is None


def test_unrecognised_tier_degrades_to_none_rather_than_raising() -> None:
    """A provider inventing a tier must not break the read model — nor be trusted."""
    parsed = parse_coverage_payload(_coverage(denominator_tier="totally-made-up"))
    assert parsed is not None
    assert parsed.denominator_tier is DenominatorTier.NONE


def test_truncation_is_carried_through() -> None:
    parsed = parse_coverage_payload(_coverage(truncated_by_max_documents=True))
    assert parsed is not None
    assert parsed.truncated is True


# --------------------------------------------------------------------------
# The write path — the anti-drift gate for a second producer of one fact
# --------------------------------------------------------------------------


def test_parsed_row_agrees_with_the_payload_it_came_from() -> None:
    """The scalars must equal what `provider_jobs.response_payload` will carry.

    A second home for a fact that already has one is how #675/#713 happened. The row is
    built from the same in-memory object that becomes the payload, so they cannot drift —
    and if that ever stops being true, this fails rather than misleading an operator.
    """
    payload = _coverage()
    parsed = parse_coverage_payload(payload)
    assert parsed is not None

    stored = payload["coverage"]
    entity = stored["entities"][0]
    assert parsed.expected == entity["expected"]
    assert parsed.observed == entity["observed"]
    assert parsed.denominator_tier.value == stored["denominator_tier"]
    assert parsed.denominator_source == stored["denominator_source"]
    assert parsed.strategy == stored["strategy"]
    assert parsed.provider_complete_claim == stored["complete"]


def test_provider_complete_claim_is_recorded_not_re_derived() -> None:
    """We store the provider's claim verbatim.

    Re-deriving it here would mean two implementations of "complete", and the ledger
    disagreeing with the provider is a finding worth seeing rather than one to paper over.
    """
    parsed = parse_coverage_payload(
        _coverage(
            complete=True,
            entities=[{"entity_id": 26, "expected": 1377, "observed": 4}],
        )
    )
    assert parsed is not None
    assert parsed.provider_complete_claim is True
    assert parsed.observed == 4
    assert parsed.expected == 1377


def test_enumerating_specs_pass_the_seed_preflight() -> None:
    """An enumerating spec has no seed and no query, and is still launchable.

    `_QUERY_DISCOVERY_KEY_BY_PROVIDER` demands a `search_text` for lexfind_api, which an
    enumeration deliberately does not carry — it walks the source's key space instead of
    asking it a question. Without the enumeration branch the run is refused at preflight
    with "must define a non-empty 'search_text'", which reads as a config error and is
    not one.

    Found by dispatching the real thing against a live stack, not by reading the code —
    it is the third place the search_text rule was written down.
    """
    from types import SimpleNamespace

    from platform_control.domain import RunMode, SourceVersionStatus
    from platform_control.services.run_service import RunService

    version = SimpleNamespace(
        source_version_id="sv_enum",
        source_id="src_enum",
        status=SourceVersionStatus.APPROVED,
        execution_mode="live",
        overlay_id=None,
        provider_template_id=None,
        acquisition_spec={
            "provider": "lexfind_api",
            "enumeration": "systematic_digit_union",
            "entity_ids": [26],
        },
    )
    source = SimpleNamespace(source_id="src_enum", status="active")

    readiness = RunService(session=None).assess_run_readiness(
        source=source,
        source_version=version,
        source_id="src_enum",
        source_version_id="sv_enum",
        mode=RunMode.ACCEPTANCE,
    )
    seed_check = next(c for c in readiness.checks if c.code == "acquisition_seed_present")
    assert seed_check.ok, seed_check.detail
    assert "enumerates the source's key space" in seed_check.detail
