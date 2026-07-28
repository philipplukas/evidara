"""Turn a provider's `coverage` payload into a reconciliation row's fields.

Deliberately session-free and side-effect-free: the attribution rule is the part most
likely to be wrong, and it should be testable without a database or a dispatched run.

THE ATTRIBUTION RULE
--------------------
Providers speak their own entity ids — LexFind says `entity_id: 26`, never `jur_ch_zh`.
The only mapping the platform has is `Source.jurisdiction_id`, and a source names exactly
one jurisdiction. So a reconciliation covering one entity attributes cleanly, and one
covering several does not: splitting a single jurisdiction across several entities, or
picking one of them, would both be inventions.

The unattributable case is **still recorded**, following `Run.refused`: the attempt
leaves evidence rather than silence, so an operator sees "two runs could not be
attributed" instead of a ledger that looks like nothing ever measured anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from platform_control.domain import CoverageAttributionStatus, DenominatorTier


@dataclass(slots=True)
class ParsedCoverage:
    """The scalars a `CoverageReconciliation` row needs, already decided."""

    attribution_status: CoverageAttributionStatus
    entity_id: str | None
    strategy: str | None
    denominator_tier: DenominatorTier
    denominator_source: str | None
    expected: int | None
    observed: int
    provider_complete_claim: bool
    truncated: bool
    as_of: datetime


def _coerce_tier(value: Any) -> DenominatorTier:
    """Unknown tiers degrade to NONE rather than raising.

    A provider inventing a tier we do not model must not take down the read model, and it
    must not be trusted either — NONE is the reading under which nothing may be claimed.
    """
    try:
        return DenominatorTier(str(value))
    except ValueError:
        return DenominatorTier.NONE


def _positive_int_or_none(value: Any) -> int | None:
    """Mirror of the provider-side rule: zero is not a denominator."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value) if value > 0 else None


def parse_coverage_payload(
    response_payload: dict[str, Any] | None, *, now: datetime | None = None
) -> ParsedCoverage | None:
    """Return the row fields for a provider response, or None if it carries no coverage.

    Returning None is the common case — only an enumerating run reports coverage at all,
    and a searching run legitimately has nothing to reconcile.
    """
    if not isinstance(response_payload, dict):
        return None
    coverage = response_payload.get("coverage")
    if not isinstance(coverage, dict):
        return None

    entities = coverage.get("entities")
    entities = entities if isinstance(entities, list) else []
    as_of = now or datetime.now(UTC)

    tier = _coerce_tier(coverage.get("denominator_tier"))
    strategy = coverage.get("strategy")
    denominator_source = coverage.get("denominator_source")
    truncated = bool(coverage.get("truncated_by_max_documents"))
    provider_complete = bool(coverage.get("complete"))

    if len(entities) != 1:
        # Ambiguous (or empty). Record the attempt with no jurisdiction and no numbers to
        # attribute — an aggregate across entities would be a number about no
        # jurisdiction in particular, which is worse than admitting the gap.
        return ParsedCoverage(
            attribution_status=CoverageAttributionStatus.AMBIGUOUS_MULTI_ENTITY,
            entity_id=None,
            strategy=strategy if isinstance(strategy, str) else None,
            denominator_tier=tier,
            denominator_source=(
                denominator_source if isinstance(denominator_source, str) else None
            ),
            expected=None,
            observed=sum(int(e.get("observed") or 0) for e in entities if isinstance(e, dict)),
            provider_complete_claim=provider_complete,
            truncated=truncated,
            as_of=as_of,
        )

    entity = entities[0] if isinstance(entities[0], dict) else {}
    entity_id = entity.get("entity_id")

    return ParsedCoverage(
        attribution_status=CoverageAttributionStatus.ATTRIBUTED,
        entity_id=str(entity_id) if entity_id is not None else None,
        strategy=strategy if isinstance(strategy, str) else None,
        denominator_tier=tier,
        denominator_source=denominator_source if isinstance(denominator_source, str) else None,
        expected=_positive_int_or_none(entity.get("expected")),
        observed=int(entity.get("observed") or 0),
        provider_complete_claim=provider_complete,
        truncated=truncated,
        as_of=as_of,
    )
