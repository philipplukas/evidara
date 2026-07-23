"""Unit tests for the pure coverage-loop logic.

These pin the CLI's mirror of the ADR-0030 two-key lock to the rule in
`platform-control/src/platform_control/services/run_service.py`. If the lock changes
there, these fail here — which is the point.
"""

from __future__ import annotations

from typing import Any

import pytest

from evidara_cli.coverage import (
    BLOCKER_PROVIDER_AWAITING_EVIDENCE,
    BLOCKER_PROVIDER_SCAFFOLD,
    BLOCKER_TEMPLATE_DISABLED_BY_OPERATOR,
    BLOCKER_TEMPLATE_NEVER_ENABLED,
    CONFIG_KEY_CLOSED_BY_OPERATOR,
    CONFIG_KEY_NEVER_TURNED,
    CONFIG_KEY_OPEN,
    EVIDENCE_EXECUTION_MODE_SHADOW,
    EVIDENCE_MODE_NOT_ACCEPTANCE,
    EVIDENCE_NO_CAPTURED_RESOURCES,
    EVIDENCE_RUN_NOT_COMPLETED,
    EVIDENCE_RUN_REFUSED,
    LOCK_ACCEPTANCE_ONLY,
    LOCK_CLOSED,
    LOCK_OPEN,
    MODE_ACCEPTANCE,
    MODE_PREVIEW,
    MODE_PRODUCTION,
    READINESS_AWAITING_EVIDENCE,
    READINESS_LIVE,
    READINESS_SCAFFOLD,
    REMEDY_ENGINEERING,
    REMEDY_NONE,
    REMEDY_REOPEN_CONFIG_KEY,
    REMEDY_RUN_ACCEPTANCE_LOOP,
    STALL_DI_CONSUMER_SILENT,
    STALL_NO_DISPATCH_WORKER,
    STALL_PUBLISH_PATH_DISABLED,
    STALL_RUN_REFUSED,
    acceptance_evidence_verdict,
    classify_template,
    config_key_state,
    diagnose_stall,
    dispatchable_modes,
    normalise_readiness,
    summarise_templates,
)


def template(
    *,
    readiness: str = READINESS_LIVE,
    enabled: bool = True,
    source: str = "default",
    launchable: bool | None = None,
    **extra: Any,
) -> dict[str, Any]:
    if launchable is None:
        launchable = enabled and readiness == READINESS_LIVE
    return {
        "overlay_id": "ch",
        "provider_template_id": "fedlex_sparql_constitution_de",
        "provider": "fedlex_sparql",
        "acquisition_readiness": readiness,
        "enabled": enabled,
        "source": source,
        "launchable": launchable,
        "notes": [],
        **extra,
    }


# --- readiness normalisation ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("live", READINESS_LIVE),
        ("LIVE", READINESS_LIVE),
        ("awaiting_evidence", READINESS_AWAITING_EVIDENCE),
        ("scaffold", READINESS_SCAFFOLD),
        # Fails closed, mirroring provider_readiness(): unknown is never dispatchable.
        ("something_new", READINESS_SCAFFOLD),
        (None, READINESS_SCAFFOLD),
        ("", READINESS_SCAFFOLD),
    ],
)
def test_normalise_readiness_fails_closed(raw: Any, expected: str) -> None:
    assert normalise_readiness(raw) == expected


# --- config key -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("enabled", "provenance", "expected"),
    [
        (True, "default", CONFIG_KEY_OPEN),
        (True, "override", CONFIG_KEY_OPEN),
        (False, "override", CONFIG_KEY_CLOSED_BY_OPERATOR),
        (False, "default", CONFIG_KEY_NEVER_TURNED),
        (False, None, CONFIG_KEY_NEVER_TURNED),
    ],
)
def test_config_key_state(enabled: bool, provenance: Any, expected: str) -> None:
    assert config_key_state(enabled=enabled, provenance=provenance) == expected


# --- dispatchable modes (the lock rule itself) ------------------------------------


def test_scaffold_dispatches_nothing_even_for_acceptance() -> None:
    """ADR-0030 §6: acceptance admits AWAITING_EVIDENCE and *never* SCAFFOLD."""
    for config_key in (CONFIG_KEY_OPEN, CONFIG_KEY_NEVER_TURNED, CONFIG_KEY_CLOSED_BY_OPERATOR):
        assert dispatchable_modes(readiness=READINESS_SCAFFOLD, config_key=config_key) == []


def test_operator_kill_switch_is_absolute() -> None:
    """#768: acceptance waives a key never turned, never one an operator closed."""
    for readiness in (READINESS_LIVE, READINESS_AWAITING_EVIDENCE):
        assert (
            dispatchable_modes(readiness=readiness, config_key=CONFIG_KEY_CLOSED_BY_OPERATOR) == []
        )


def test_awaiting_evidence_admits_only_acceptance() -> None:
    assert dispatchable_modes(
        readiness=READINESS_AWAITING_EVIDENCE, config_key=CONFIG_KEY_OPEN
    ) == [MODE_ACCEPTANCE]


def test_live_provider_with_untouched_config_key_admits_only_acceptance() -> None:
    assert dispatchable_modes(readiness=READINESS_LIVE, config_key=CONFIG_KEY_NEVER_TURNED) == [
        MODE_ACCEPTANCE
    ]


def test_both_keys_turned_admits_every_mode() -> None:
    modes = dispatchable_modes(readiness=READINESS_LIVE, config_key=CONFIG_KEY_OPEN)
    assert set(modes) == {MODE_ACCEPTANCE, MODE_PREVIEW, MODE_PRODUCTION}


# --- classification ----------------------------------------------------------------


def test_classify_open_lock() -> None:
    result = classify_template(template())
    assert result["lock_state"] == LOCK_OPEN
    assert result["blocker"] is None
    assert result["remedy"] == REMEDY_NONE
    assert result["launchable"] is True
    assert result["agrees_with_server"] is True
    assert result["recommended_mode"] == MODE_ACCEPTANCE


def test_classify_scaffold_sends_to_engineering() -> None:
    result = classify_template(template(readiness=READINESS_SCAFFOLD, enabled=False))
    assert result["blocker"] == BLOCKER_PROVIDER_SCAFFOLD
    assert result["remedy"] == REMEDY_ENGINEERING
    assert result["lock_state"] == LOCK_CLOSED
    assert result["recommended_mode"] is None


def test_classify_awaiting_evidence_sends_to_the_operator_not_engineering() -> None:
    """#743: the whole point of the three-state key is not misdirecting operators."""
    result = classify_template(template(readiness=READINESS_AWAITING_EVIDENCE, enabled=False))
    assert result["blocker"] == BLOCKER_PROVIDER_AWAITING_EVIDENCE
    assert result["remedy"] == REMEDY_RUN_ACCEPTANCE_LOOP
    assert result["lock_state"] == LOCK_ACCEPTANCE_ONLY
    assert result["recommended_mode"] == MODE_ACCEPTANCE


def test_classify_operator_closed_key_is_distinct_from_never_turned() -> None:
    closed = classify_template(template(enabled=False, source="override"))
    never = classify_template(template(enabled=False, source="default"))
    assert closed["blocker"] == BLOCKER_TEMPLATE_DISABLED_BY_OPERATOR
    assert closed["remedy"] == REMEDY_REOPEN_CONFIG_KEY
    assert closed["dispatchable_modes"] == []
    assert never["blocker"] == BLOCKER_TEMPLATE_NEVER_ENABLED
    assert never["remedy"] == REMEDY_RUN_ACCEPTANCE_LOOP
    assert never["dispatchable_modes"] == [MODE_ACCEPTANCE]


def test_classify_flags_disagreement_with_the_server() -> None:
    """The CLI is a third copy of the lock rule; it must never assert alone."""
    result = classify_template(template(readiness=READINESS_SCAFFOLD, launchable=True))
    assert result["launchable"] is False
    assert result["server_launchable"] is True
    assert result["agrees_with_server"] is False


def test_classify_never_branches_on_prose_notes() -> None:
    misleading = template(
        readiness=READINESS_AWAITING_EVIDENCE,
        enabled=False,
        notes=["Code key closed: cannot yet acquire this format."],
    )
    result = classify_template(misleading)
    # The prose says "cannot acquire"; the machine-readable key says otherwise.
    assert result["remedy"] == REMEDY_RUN_ACCEPTANCE_LOOP
    assert result["notes"] == ["Code key closed: cannot yet acquire this format."]


def test_summarise_templates_counts_by_blocker() -> None:
    rows = [
        classify_template(template()),
        classify_template(template(readiness=READINESS_SCAFFOLD, enabled=False)),
        classify_template(template(readiness=READINESS_AWAITING_EVIDENCE, enabled=False)),
    ]
    summary = summarise_templates(rows)
    assert summary["total"] == 3
    assert summary["launchable"] == 1
    assert summary["acceptance_ready"] == 2
    assert summary["needs_engineering"] == 1
    assert summary["by_blocker"][BLOCKER_PROVIDER_SCAFFOLD] == 1
    assert summary["disagreements_with_server"] == 0


# --- stall diagnosis ----------------------------------------------------------------


def test_diagnose_refused_run_is_not_reported_as_a_stall() -> None:
    result = diagnose_stall(
        {"status": "failed", "refused": True, "failure_reason": "Config key closed"},
        {"stages": []},
    )
    assert result["cause"] == STALL_RUN_REFUSED
    assert result["failure_reason"] == "Config key closed"


def test_diagnose_pending_run_names_the_missing_worker() -> None:
    result = diagnose_stall({"status": "pending", "refused": False}, {"stages": []})
    assert result["cause"] == STALL_NO_DISPATCH_WORKER
    assert "run_dispatch_backend" in result["detail"]


def test_diagnose_completed_run_with_no_di_events_names_the_noop_publisher() -> None:
    """The exact failure that costs a ten-minute DI timeout to discover."""
    result = diagnose_stall(
        {"status": "completed", "refused": False},
        {
            "overall_status": "pending",
            "processing_status_event_count": 0,
            "document_lifecycle_event_count": 0,
            "stages": [{"stage": "document_intelligence", "status": "pending", "detail": ""}],
        },
    )
    assert result["cause"] == STALL_PUBLISH_PATH_DISABLED
    assert "PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND" in result["detail"]


def test_diagnose_di_events_but_no_progress() -> None:
    result = diagnose_stall(
        {"status": "completed", "refused": False},
        {
            "processing_status_event_count": 3,
            "document_lifecycle_event_count": 0,
            "stages": [{"stage": "document_intelligence", "status": "in_progress", "detail": ""}],
        },
    )
    assert result["cause"] == STALL_DI_CONSUMER_SILENT


# --- acceptance evidence verdict -----------------------------------------------------


def test_shadow_run_is_refused_as_acceptance_evidence() -> None:
    """ADR-0030 §2: a SHADOW run replays fixtures and proves nothing about the portal."""
    verdict = acceptance_evidence_verdict(
        run={
            "run_id": "run_1",
            "status": "completed",
            "mode": "acceptance",
            "refused": False,
            "captured_resources_count": 5,
        },
        execution_mode="shadow",
    )
    assert verdict["is_acceptance_evidence"] is False
    assert [r["code"] for r in verdict["refusals"]] == [EVIDENCE_EXECUTION_MODE_SHADOW]


def test_good_acceptance_run_is_accepted() -> None:
    verdict = acceptance_evidence_verdict(
        run={
            "run_id": "run_1",
            "status": "completed",
            "mode": "acceptance",
            "refused": False,
            "captured_resources_count": 5,
        },
        execution_mode="live",
    )
    assert verdict["is_acceptance_evidence"] is True
    assert verdict["refusals"] == []
    # A pass still carries the skipped-gate warning (#744).
    assert "skipped_gates" in verdict["note"]


def test_preview_run_is_not_acceptance_evidence() -> None:
    verdict = acceptance_evidence_verdict(
        run={
            "run_id": "run_1",
            "status": "completed",
            "mode": "preview",
            "refused": False,
            "captured_resources_count": 5,
        },
        execution_mode="live",
    )
    assert EVIDENCE_MODE_NOT_ACCEPTANCE in [r["code"] for r in verdict["refusals"]]


def test_refused_and_incomplete_runs_are_refused() -> None:
    verdict = acceptance_evidence_verdict(
        run={
            "run_id": "run_1",
            "status": "failed",
            "mode": "acceptance",
            "refused": True,
            "captured_resources_count": 0,
        },
        execution_mode="live",
    )
    codes = [r["code"] for r in verdict["refusals"]]
    assert EVIDENCE_RUN_REFUSED in codes
    assert EVIDENCE_RUN_NOT_COMPLETED in codes
    assert EVIDENCE_NO_CAPTURED_RESOURCES in codes
