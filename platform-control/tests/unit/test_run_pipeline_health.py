"""Decision support, and the stage projection, as server-side facts (#908).

Both used to live in `platform-control/admin/src/resources/runs/
run-decision-support.ts` — in TypeScript, in the browser. So the CLI, alerting and
any operator agent either could not reach the judgement at all, or had to re-derive
it in a second implementation. AGENTS.md names that failure directly: *"the same rule
enforced in two clients rather than once behind them — the easier path becomes the
real policy, and it is usually the weaker one."*

The tests here are about the judgement itself. `test_admin_does_not_recompute_
decision_support` in the admin surface is the other half: it fails if the TypeScript
derivation comes back.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform_control.domain import (
    PipelineStageStatus,
    RunMode,
    RunStatus,
)
from platform_control.schemas.run import RunPipelineHealthStage
from platform_control.services.run_service import (
    OVERALL_STATUS_STALLED,
    RunService,
)

_NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


def _stage(name: str, status: PipelineStageStatus, *, detail: str = "") -> RunPipelineHealthStage:
    return RunPipelineHealthStage(stage=name, status=status, detail=detail or name, updated_at=None)


class _Run:
    """The attributes the health derivation reads, without a database."""

    def __init__(
        self,
        *,
        mode: RunMode,
        status: RunStatus,
        completed_at: datetime | None = None,
    ) -> None:
        self.mode = mode
        self.status = status
        self.completed_at = completed_at


#: The shape of the five production runs #951 was opened on, measured 2026-09-19:
#: `status=completed`, DI reached `canonical_ready`, and `document_lifecycle_events`
#: is empty 68-74 days later. The stage resolvers turn that into projection
#: `in_progress` and search `pending` (`run_service.py:1448-1470`).
def _stalled_production_stages() -> list[RunPipelineHealthStage]:
    return [
        _stage("acquisition", PipelineStageStatus.OK),
        _stage("document_intelligence", PipelineStageStatus.OK),
        _stage("projection", PipelineStageStatus.IN_PROGRESS),
        _stage("search", PipelineStageStatus.PENDING),
    ]


# ---------------------------------------------------------------------------
# The stage projection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("run_status", [RunStatus.FAILED, RunStatus.CANCELLED])
def test_a_dead_run_reports_unreached_stages_as_not_applicable(run_status: RunStatus) -> None:
    """`pending` on a run that will never advance reads as "work is still coming".

    The API said that for the life of the endpoint, and the admin corrected it in the
    browser. Every other consumer saw the misleading answer.
    """
    stages = [
        _stage("acquisition", PipelineStageStatus.FAILED),
        _stage("document_intelligence", PipelineStageStatus.PENDING),
    ]
    projected = RunService._project_unreachable_stages(stages, run_status)

    assert projected[0].status is PipelineStageStatus.FAILED
    assert projected[1].status is PipelineStageStatus.NOT_APPLICABLE
    assert "Not applicable" in projected[1].detail
    # The wording distinguishes the two ways a run dies.
    expected_word = "cancelled" if run_status is RunStatus.CANCELLED else "failed"
    assert expected_word in projected[1].detail


@pytest.mark.parametrize("run_status", [RunStatus.PENDING, RunStatus.RUNNING, RunStatus.COMPLETED])
def test_a_live_run_keeps_its_pending_stages(run_status: RunStatus) -> None:
    """Without this the projection would erase the queue on healthy runs — `pending`
    is genuinely correct while a run can still advance."""
    stages = [_stage("document_intelligence", PipelineStageStatus.PENDING)]
    assert (
        RunService._project_unreachable_stages(stages, run_status)[0].status
        is PipelineStageStatus.PENDING
    )


# ---------------------------------------------------------------------------
# The four questions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "code"),
    [
        (RunMode.PRODUCTION, "production_run"),
        (RunMode.ACCEPTANCE, "acceptance_run"),
        (RunMode.PREVIEW, "preview_run"),
    ],
)
def test_why_it_matters_has_three_modes_not_two(mode: RunMode, code: str) -> None:
    """The ternary this replaces called an acceptance run "this preview run".

    That is the same mislabelling #743 fixed at the badge sites and missed here, so
    the page contradicted its own header 400px above.
    """
    support = RunService._build_decision_support(
        run=_Run(mode=mode, status=RunStatus.COMPLETED),
        stages=[_stage("acquisition", PipelineStageStatus.OK)],
        overall_status="ok",
        processing_status_event_count=0,
        document_lifecycle_event_count=0,
    )
    assert support.why_it_matters.code == code


def test_every_answer_carries_a_code_an_agent_can_branch_on() -> None:
    """The point of moving this server-side.

    Prose alone would leave an agent pattern-matching English that a later PR may
    reword — which is exactly the defect #908 names in run refusals.
    """
    support = RunService._build_decision_support(
        run=_Run(mode=RunMode.PREVIEW, status=RunStatus.FAILED),
        stages=[
            _stage("acquisition", PipelineStageStatus.FAILED),
            _stage("document_intelligence", PipelineStageStatus.NOT_APPLICABLE),
        ],
        overall_status="failed",
        processing_status_event_count=0,
        document_lifecycle_event_count=0,
    )
    for note in (
        support.why_it_matters,
        support.what_is_blocked,
        support.what_changed_recently,
        support.what_happens_if_ignored,
    ):
        assert note.code
        assert note.text
    assert all(action.code for action in support.next_actions)


def test_blocked_and_never_running_stages_are_lists_not_only_a_sentence() -> None:
    """A caller must be able to act on the stages without parsing the sentence they
    were rendered into."""
    support = RunService._build_decision_support(
        run=_Run(mode=RunMode.PREVIEW, status=RunStatus.FAILED),
        stages=[
            _stage("acquisition", PipelineStageStatus.FAILED),
            _stage("projection", PipelineStageStatus.NOT_APPLICABLE),
        ],
        overall_status="failed",
        processing_status_event_count=0,
        document_lifecycle_event_count=0,
    )
    assert support.blocked_stages == ["acquisition"]
    assert support.never_running_stages == ["projection"]
    # The sentence still names them, for a human.
    assert "acquisition" in support.what_is_blocked.text
    assert "projection" in support.what_is_blocked.text


def test_a_terminal_run_says_relaunch_rather_than_wait() -> None:
    support = RunService._build_decision_support(
        run=_Run(mode=RunMode.PREVIEW, status=RunStatus.FAILED),
        stages=[_stage("acquisition", PipelineStageStatus.FAILED)],
        overall_status="failed",
        processing_status_event_count=0,
        document_lifecycle_event_count=0,
    )
    assert support.what_happens_if_ignored.code == "terminal_needs_relaunch"
    assert "relaunch" in support.what_happens_if_ignored.text


def test_a_healthy_run_is_not_told_to_do_anything() -> None:
    """Without this, every test above is satisfied by an implementation that always
    reports trouble."""
    support = RunService._build_decision_support(
        run=_Run(mode=RunMode.PRODUCTION, status=RunStatus.COMPLETED),
        stages=[_stage("acquisition", PipelineStageStatus.OK)],
        overall_status="ok",
        processing_status_event_count=0,
        document_lifecycle_event_count=0,
    )
    assert support.what_is_blocked.code == "no_stage_blocked"
    assert support.what_happens_if_ignored.code == "nothing_urgent"
    assert support.blocked_stages == []
    assert [action.code for action in support.next_actions] == ["none_required"]


def test_each_stage_gets_its_own_remediation_not_a_generic_one() -> None:
    support = RunService._build_decision_support(
        run=_Run(mode=RunMode.PREVIEW, status=RunStatus.RUNNING),
        stages=[
            _stage("acquisition", PipelineStageStatus.BLOCKED),
            _stage("document_intelligence", PipelineStageStatus.BLOCKED),
            _stage("projection", PipelineStageStatus.BLOCKED),
            _stage("search", PipelineStageStatus.BLOCKED),
        ],
        overall_status="blocked",
        processing_status_event_count=0,
        document_lifecycle_event_count=0,
    )
    assert [action.code for action in support.next_actions] == [
        "inspect_provider_jobs",
        "inspect_di_processing",
        "confirm_lifecycle_events",
        "verify_search_visibility",
    ]


# ---------------------------------------------------------------------------
# A finished run does not get to claim the pipeline is still moving (#951)
# ---------------------------------------------------------------------------


def test_a_long_finished_run_reports_stalled_not_in_progress() -> None:
    """The defect #951 was opened on, in the shape production actually holds it.

    `GET /v1/runs/{id}/pipeline-health` answered `run_status: completed` and
    `overall_status: in_progress` on the same payload, so one screen said the run was
    read-only *and* that the pipeline continued to advance. Measured 2026-09-19, five
    of the twenty-nine production runs were in exactly this state, 68-74 days after
    they ended.
    """
    run = _Run(
        mode=RunMode.PRODUCTION,
        status=RunStatus.COMPLETED,
        completed_at=_NOW - timedelta(days=68),
    )
    assert (
        RunService._resolve_overall_pipeline_status(_stalled_production_stages(), run, _NOW)
        == OVERALL_STATUS_STALLED
    )


def test_a_just_finished_run_is_still_in_progress() -> None:
    """The other half, and the one that keeps the guard from being a blunt rule.

    Acquisition completing is not the pipeline completing - DI, projection and search
    land afterwards. Measured on the same production data: the lag from `completed_at`
    to the last lifecycle event reached 5h58m on the largest run (938 events). Calling
    that run stalled would be the same false claim pointing the other way, so a run
    inside the grace window keeps reporting `in_progress`.
    """
    run = _Run(
        mode=RunMode.PRODUCTION,
        status=RunStatus.COMPLETED,
        completed_at=_NOW - timedelta(hours=6),
    )
    assert (
        RunService._resolve_overall_pipeline_status(_stalled_production_stages(), run, _NOW)
        == "in_progress"
    )


def test_a_running_run_is_never_called_stalled() -> None:
    """A run still executing has pending stages by construction, not by defect."""
    run = _Run(mode=RunMode.PRODUCTION, status=RunStatus.RUNNING, completed_at=None)
    assert (
        RunService._resolve_overall_pipeline_status(_stalled_production_stages(), run, _NOW)
        == "in_progress"
    )


def test_a_completed_run_without_completed_at_is_not_assumed_stalled() -> None:
    """An unknown age is not an old one (ADR-0052): absent must not read as expired."""
    run = _Run(mode=RunMode.PRODUCTION, status=RunStatus.COMPLETED, completed_at=None)
    assert (
        RunService._resolve_overall_pipeline_status(_stalled_production_stages(), run, _NOW)
        == "in_progress"
    )


def test_a_stalled_run_is_not_reported_healthy() -> None:
    """The failure mode worth more than the one in the ticket.

    `in_progress` is a false claim of motion; `ok` would be a false green over
    documents that never became searchable. Neither is acceptable, so this pins the
    rollup against collapsing the stall into health.
    """
    run = _Run(
        mode=RunMode.PRODUCTION,
        status=RunStatus.COMPLETED,
        completed_at=_NOW - timedelta(days=68),
    )
    status = RunService._resolve_overall_pipeline_status(_stalled_production_stages(), run, _NOW)
    assert status not in {"ok", "in_progress"}


def test_a_stalled_run_does_not_say_the_pipeline_is_advancing() -> None:
    """The three sentences the panel rendered, all of which claimed motion.

    `overall_summary` said "At least one stage is still moving through the pipeline",
    `what_happens_if_ignored` said "The pipeline continues to advance", and
    `what_is_blocked` said "the pipeline is still moving". A status fixed without the
    prose would leave the screen saying the same thing in three other places.
    """
    support = RunService._build_decision_support(
        run=_Run(
            mode=RunMode.PRODUCTION,
            status=RunStatus.COMPLETED,
            completed_at=_NOW - timedelta(days=68),
        ),
        stages=_stalled_production_stages(),
        overall_status=OVERALL_STATUS_STALLED,
        processing_status_event_count=3,
        document_lifecycle_event_count=0,
    )

    assert support.overall_summary.code == "pipeline_stalled_after_run_end"
    assert support.what_happens_if_ignored.code == "stall_will_not_clear"
    assert support.what_is_blocked.code == "stalled_no_block"
    for note in (
        support.overall_summary,
        support.what_is_blocked,
        support.what_happens_if_ignored,
    ):
        lowered = note.text.lower()
        assert "still moving" not in lowered
        assert "continues to advance" not in lowered

    # The stages that stopped short are named, not just counted.
    assert "projection" in support.what_is_blocked.text
    assert "search" in support.what_is_blocked.text


def test_a_stall_leaves_the_stage_statuses_alone_for_the_cli() -> None:
    """The CLI already diagnoses these runs correctly; do not take that away.

    `diagnose_stall` names `projection_stalled` only when the projection stage is
    still `pending`/`in_progress` (`tools/evidara-cli/src/evidara_cli/coverage.py:
    340-351`). Re-labelling the stages server-side - the obvious fix, and the one
    `_project_unreachable_stages` applies to failed/cancelled runs - would silence the
    one surface that had this right and regress the CLI to `unknown`.
    """
    stages = _stalled_production_stages()
    run = _Run(
        mode=RunMode.PRODUCTION,
        status=RunStatus.COMPLETED,
        completed_at=_NOW - timedelta(days=68),
    )
    RunService._resolve_overall_pipeline_status(stages, run, _NOW)

    projected = RunService._project_unreachable_stages(stages, run.status)
    by_stage = {s.stage: s.status for s in projected}
    assert by_stage["projection"] is PipelineStageStatus.IN_PROGRESS
    assert by_stage["search"] is PipelineStageStatus.PENDING
