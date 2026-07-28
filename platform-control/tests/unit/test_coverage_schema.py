"""The honesty rules of the acquisition-coverage read model, one test each.

These are the rules that decide whether the ledger is worth having. A ledger that reports
"100%" against an unknown denominator is worse than no ledger — it manufactures exactly
the false green this repo keeps getting caught by (#685, #735, #744, #772). So each rule
below is a validator, and each validator is asserted in both directions: the honest shape
is accepted, and the dishonest one is refused.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from platform_control.domain import DenominatorTier, NormLevel
from platform_control.schemas.coverage import AcquisitionCoverageEntry


def _entry(**overrides) -> dict:
    base = {
        "jurisdiction_id": "jur_ch_zh",
        "name": "Kanton Zürich",
        "slug": "ch-zh",
        "level": NormLevel.CANTONAL,
        "expected": 1377,
        "denominator_tier": DenominatorTier.PUBLISHED,
        "acquired_distinct_urls": 1377,
        "processed_documents": 1374,
        "acquired_gap": 0,
        "processed_gap": 3,
    }
    base.update(overrides)
    return base


def test_a_complete_measurement_is_accepted() -> None:
    entry = AcquisitionCoverageEntry(**_entry())
    assert entry.acquired_gap == 0
    assert entry.processed_gap == 3


def test_unknown_denominator_is_null_never_zero() -> None:
    """No denominator means no gap — not a gap of zero.

    `expected: 0` alongside `observed: 0` is how a ledger says "this canton publishes no
    law and we hold all of it". The tier and the gaps must all collapse together.
    """
    entry = AcquisitionCoverageEntry(
        **_entry(
            expected=None,
            denominator_tier=DenominatorTier.NONE,
            acquired_gap=None,
            processed_gap=None,
        )
    )
    assert entry.expected is None
    assert entry.acquired_gap is None

    with pytest.raises(ValidationError, match="gap without a denominator"):
        AcquisitionCoverageEntry(
            **_entry(expected=None, denominator_tier=DenominatorTier.NONE, acquired_gap=0)
        )


def test_a_tier_may_not_promise_a_denominator_it_does_not_carry() -> None:
    with pytest.raises(ValidationError, match="denominator_tier must be 'none'"):
        AcquisitionCoverageEntry(
            **_entry(
                expected=None,
                denominator_tier=DenominatorTier.PUBLISHED,
                acquired_gap=None,
                processed_gap=None,
            )
        )
    with pytest.raises(ValidationError, match="cannot carry an expected count"):
        AcquisitionCoverageEntry(**_entry(expected=1377, denominator_tier=DenominatorTier.NONE))


def test_registry_tier_never_emits_a_gap() -> None:
    """2110 communes minus 3 documents is a number in no unit at all.

    A registry denominator counts UNITS; the numerators count documents. The subtraction
    is a category error that would render as a coverage gap, so it is refused outright —
    breadth is claimable, depth is not.
    """
    entry = AcquisitionCoverageEntry(
        **_entry(
            jurisdiction_id="jur_ch",
            expected=2110,
            denominator_tier=DenominatorTier.REGISTRY,
            acquired_distinct_urls=3,
            acquired_gap=None,
            processed_gap=None,
        )
    )
    assert entry.expected == 2110
    assert entry.acquired_gap is None

    with pytest.raises(ValidationError, match="counts units, not documents"):
        AcquisitionCoverageEntry(
            **_entry(expected=2110, denominator_tier=DenominatorTier.REGISTRY, acquired_gap=2107)
        )


def test_truncated_run_is_a_sample_not_a_measurement() -> None:
    entry = AcquisitionCoverageEntry(
        **_entry(denominator_truncated=True, acquired_gap=None, processed_gap=None)
    )
    assert entry.denominator_truncated is True

    with pytest.raises(ValidationError, match="sample, not a measurement"):
        AcquisitionCoverageEntry(**_entry(denominator_truncated=True, acquired_gap=1277))


def test_truncated_run_cannot_claim_completeness() -> None:
    with pytest.raises(ValidationError, match="cannot claim completeness"):
        AcquisitionCoverageEntry(
            **_entry(
                denominator_truncated=True,
                provider_complete_claim=True,
                acquired_gap=None,
                processed_gap=None,
            )
        )


def test_gap_may_be_negative() -> None:
    """Holding more than the source publishes is a finding, not a validation error.

    `ge=0` here would clamp away a dedup failure, or a denominator that counts something
    other than what we capture — the exact conditions this endpoint exists to expose.
    """
    entry = AcquisitionCoverageEntry(
        **_entry(acquired_distinct_urls=1400, acquired_gap=-23, processed_gap=-20)
    )
    assert entry.acquired_gap == -23


def test_counts_may_not_be_negative() -> None:
    with pytest.raises(ValidationError):
        AcquisitionCoverageEntry(**_entry(acquired_distinct_urls=-1))
