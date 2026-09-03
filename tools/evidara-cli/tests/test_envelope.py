"""Tests for the WorkflowCommandEnvelope, on its own terms.

These tests deliberately exercise the envelope as a *third party* would: they import
``evidara_cli.envelope`` and nothing else from the CLI, and they validate against
``contracts/schemas/workflow-command-envelope.schema.json`` rather than against what
this repo's commands happen to emit.

The envelope's only previous tests lived in ``test_workflow_cmd.py``, a module that
imports ``evidara_cli.main``, ``evidara_cli.workflow_cmd`` and ``evidara_cli.proposal``
to test everything else in it. That made the envelope untestable without the whole CLI.
They were moved here unchanged; the rest of this file is new.

See docs/components/workflow-command-envelope.md for the extraction boundary this file
enforces and for what ``side_effect_level`` means.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from evidara_cli.envelope import (
    build_envelope,
    evidence_assertion,
    evidence_count,
    evidence_http,
)
from evidara_cli.repo_root import resolve_repo_root

ENVELOPE_MODULE = Path(__file__).resolve().parents[1] / "src" / "evidara_cli" / "envelope.py"

SCHEMA_PATH = (
    resolve_repo_root(Path(__file__))
    / "contracts"
    / "schemas"
    / "workflow-command-envelope.schema.json"
)

# The module is allowed to import these and nothing else. Anything outside the
# standard library's typing surface would be an upward or third-party coupling and
# would have to travel with the module if it were ever lifted out of this repo.
ALLOWED_IMPORT_ROOTS = {"__future__", "typing"}


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    if not SCHEMA_PATH.exists():
        raise AssertionError(
            f"WorkflowCommandEnvelope schema not found at {SCHEMA_PATH}. "
            "This test validates against the contract, not against the builder's opinion; "
            "it must fail rather than skip when the contract is missing."
        )
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema: dict[str, Any]) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def minimal(**overrides: Any) -> dict[str, Any]:
    """A schema-valid envelope with no domain content, for mutating in tests."""
    envelope = build_envelope(
        ok=True,
        workflow="example-workflow",
        step="example.step",
        status="passed",
        side_effect_level="none",
        inputs={},
    )
    envelope.update(overrides)
    return envelope


# ---------------------------------------------------------------------------
# extraction boundary
# ---------------------------------------------------------------------------


def test_envelope_module_has_no_upward_or_third_party_imports() -> None:
    """The module must stay liftable: no sibling, package, or third-party imports.

    This is the mechanical form of the claim in docs/components/workflow-command-envelope.md.
    A prose claim about separability rots; this one fails the build.
    """
    tree = ast.parse(ENVELOPE_MODULE.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import is by definition an upward coupling
                roots.add("." * node.level + (node.module or ""))
            elif node.module:
                roots.add(node.module.split(".")[0])
    assert roots <= ALLOWED_IMPORT_ROOTS, (
        f"envelope.py gained imports outside {sorted(ALLOWED_IMPORT_ROOTS)}: "
        f"{sorted(roots - ALLOWED_IMPORT_ROOTS)}"
    )


def test_schema_is_self_contained(schema: dict[str, Any]) -> None:
    """No ``$ref`` anywhere: the schema resolves without the rest of contracts/."""
    text = json.dumps(schema)
    assert '"$ref"' not in text


# ---------------------------------------------------------------------------
# envelope builder (moved from test_workflow_cmd.py)
# ---------------------------------------------------------------------------


def test_build_envelope_minimal():
    env = build_envelope(
        ok=True,
        workflow="source-lifecycle",
        step="source.inspect",
        status="passed",
        side_effect_level="none",
        inputs={"source_id": "src_123"},
    )
    assert env["ok"] is True
    assert env["workflow"] == "source-lifecycle"
    assert env["step"] == "source.inspect"
    assert env["status"] == "passed"
    assert env["side_effect_level"] == "none"
    assert env["inputs"] == {"source_id": "src_123"}
    assert env["run_id"] is None
    assert env.get("error") is None
    assert env.get("error_detail") is None


def test_build_envelope_with_error():
    env = build_envelope(
        ok=False,
        workflow="source-lifecycle",
        step="source.apply",
        status="failed_terminal",
        side_effect_level="reversible",
        inputs={},
        error="Service unavailable",
        error_detail={"status_code": 503, "body": ""},
    )
    assert env["ok"] is False
    assert env["error"] == "Service unavailable"
    assert env["error_detail"]["status_code"] == 503


def test_evidence_http_defaults_passed():
    ev = evidence_http("platform-control:/health", status_code=200)
    assert ev["kind"] == "http"
    assert ev["passed"] is True


def test_evidence_http_failed_on_4xx():
    ev = evidence_http("platform-control:/health", status_code=404)
    assert ev["passed"] is False


def test_evidence_assertion():
    ev = evidence_assertion("dup-check", value="none", passed=True)
    assert ev["kind"] == "assertion"
    assert ev["passed"] is True


def test_evidence_count():
    ev = evidence_count("sources", value=5, passed=True)
    assert ev["kind"] == "count"
    assert ev["value"] == 5


# ---------------------------------------------------------------------------
# builder output conforms to the published contract
# ---------------------------------------------------------------------------


def test_minimal_builder_output_validates(validator: Draft202012Validator) -> None:
    validator.validate(minimal())


def test_fully_populated_builder_output_validates(validator: Draft202012Validator) -> None:
    envelope = build_envelope(
        ok=False,
        workflow="example-workflow",
        step="example.apply",
        status="needs_human",
        side_effect_level="irreversible",
        inputs={"target": "example"},
        run_id="wf_example",
        artifacts={"created_id": "obj_1", "count": 3},
        evidence=[
            evidence_http("service:/health", status_code=200),
            evidence_assertion("id-present", value="obj_1", passed=True, note="created"),
            evidence_count("indexed", value=0, passed=False),
            {"kind": "contract", "target": "openapi:/v1/things", "passed": True},
            {"kind": "object-ref", "target": "s3://bucket/key", "passed": True},
        ],
        decision={
            "recommended_action": "approve",
            "reason": "Preconditions met; the act itself is not undoable.",
            "confidence": 0.75,
        },
        next_actions=["approve", "abort"],
        compensation={"available": False, "note": "No rollback exists for this step."},
        error="Awaiting operator approval",
        error_detail={"status_code": None, "body": ""},
    )
    validator.validate(envelope)


@pytest.mark.parametrize(
    "status",
    ["passed", "failed_retriable", "failed_terminal", "needs_human", "compensated"],
)
def test_every_declared_status_validates(validator: Draft202012Validator, status: str) -> None:
    validator.validate(minimal(status=status))


@pytest.mark.parametrize("level", ["none", "reversible", "irreversible"])
def test_every_declared_side_effect_level_validates(
    validator: Draft202012Validator, level: str
) -> None:
    """All three levels are contract-valid.

    ``irreversible`` is included deliberately: no producer in this repo emits it today
    (every call site in workflow_cmd.py and coverage_cmd.py passes ``none`` or
    ``reversible``), so without this test the third level would be unexercised.
    """
    validator.validate(minimal(side_effect_level=level))


# ---------------------------------------------------------------------------
# side_effect_level boundary cases
# ---------------------------------------------------------------------------


def test_builder_does_not_validate_an_unknown_side_effect_level() -> None:
    """Deliberate: the builder is a formatter, not a validator.

    An unknown level passes straight through. That keeps the builder dependency-free
    and puts one authority — the schema — in charge of the vocabulary. A consumer that
    wants rejection at construction time must validate the result.
    """
    envelope = build_envelope(
        ok=True,
        workflow="example-workflow",
        step="example.step",
        status="passed",
        side_effect_level="catastrophic",
        inputs={},
    )
    assert envelope["side_effect_level"] == "catastrophic"


def test_schema_rejects_an_unknown_side_effect_level(validator: Draft202012Validator) -> None:
    errors = list(validator.iter_errors(minimal(side_effect_level="catastrophic")))
    assert errors, "an unknown side_effect_level must not validate"
    assert any("side_effect_level" in list(e.absolute_path) for e in errors)


def test_schema_rejects_a_missing_side_effect_level(validator: Draft202012Validator) -> None:
    envelope = minimal()
    del envelope["side_effect_level"]
    errors = list(validator.iter_errors(envelope))
    assert errors, "side_effect_level is required; its absence must not validate"


def test_builder_requires_side_effect_level_as_a_keyword() -> None:
    """There is no default. A caller must state the mutation class of its step."""
    with pytest.raises(TypeError):
        build_envelope(  # type: ignore[call-arg]
            ok=True,
            workflow="example-workflow",
            step="example.step",
            status="passed",
            inputs={},
        )


def test_schema_rejects_an_unknown_status(validator: Draft202012Validator) -> None:
    assert list(validator.iter_errors(minimal(status="cancelled")))


# ---------------------------------------------------------------------------
# strict where it matters, permissive where the payload lives
# ---------------------------------------------------------------------------


def test_unknown_top_level_field_is_rejected(validator: Draft202012Validator) -> None:
    """The envelope's own shape is closed (``additionalProperties: false``).

    Extending it is a contract change, not something a producer may do unilaterally.
    """
    assert list(validator.iter_errors(minimal(severity="high")))


@pytest.mark.parametrize("bag", ["inputs", "artifacts", "error_detail"])
def test_payload_bags_are_open(validator: Draft202012Validator, bag: str) -> None:
    """``inputs``, ``artifacts`` and ``error_detail`` accept arbitrary keys by design.

    They carry caller-specific payload, so closing them would make the envelope
    unusable outside the domain that defined the keys.
    """
    validator.validate(minimal(**{bag: {"anything_at_all": {"nested": [1, 2, 3]}}}))


def test_unknown_evidence_field_is_rejected(validator: Draft202012Validator) -> None:
    envelope = minimal(evidence=[{"kind": "assertion", "target": "x", "severity": "high"}])
    assert list(validator.iter_errors(envelope))


def test_unknown_evidence_kind_is_rejected(validator: Draft202012Validator) -> None:
    assert list(validator.iter_errors(minimal(evidence=[{"kind": "screenshot"}])))


def test_evidence_requires_a_kind(validator: Draft202012Validator) -> None:
    assert list(validator.iter_errors(minimal(evidence=[{"target": "x", "passed": True}])))


def test_unknown_decision_field_is_rejected(validator: Draft202012Validator) -> None:
    envelope = minimal(decision={"recommended_action": "approve", "urgency": "now"})
    assert list(validator.iter_errors(envelope))


def test_decision_requires_a_recommended_action(validator: Draft202012Validator) -> None:
    assert list(validator.iter_errors(minimal(decision={"reason": "because"})))


def test_decision_confidence_is_bounded(validator: Draft202012Validator) -> None:
    validator.validate(minimal(decision={"recommended_action": "approve", "confidence": 1.0}))
    out_of_range = minimal(decision={"recommended_action": "approve", "confidence": 1.5})
    assert list(validator.iter_errors(out_of_range))


def test_unknown_compensation_field_is_rejected(validator: Draft202012Validator) -> None:
    assert list(validator.iter_errors(minimal(compensation={"available": True, "cost": 3})))


def test_compensation_requires_availability(validator: Draft202012Validator) -> None:
    assert list(validator.iter_errors(minimal(compensation={"note": "call support"})))


@pytest.mark.parametrize("workflow", ["Source-Lifecycle", "source_lifecycle", "-leading", "1x"])
def test_workflow_name_pattern_is_enforced(validator: Draft202012Validator, workflow: str) -> None:
    assert list(validator.iter_errors(minimal(workflow=workflow)))


@pytest.mark.parametrize("step", ["Source.Inspect", "source-inspect", ".leading", "trailing."])
def test_step_pattern_is_enforced(validator: Draft202012Validator, step: str) -> None:
    assert list(validator.iter_errors(minimal(step=step)))


# ---------------------------------------------------------------------------
# key presence: the asymmetry a consumer has to know about
# ---------------------------------------------------------------------------


def test_optional_fields_are_present_as_null_but_error_fields_are_omitted() -> None:
    """Two different ways of saying "nothing here", in one envelope.

    ``run_id``/``artifacts``/``evidence``/``decision``/``next_actions``/``compensation``
    are always emitted as ``null``; ``error``/``error_detail`` are omitted entirely when
    unset. Both are schema-valid, so a consumer must treat "absent" and "null" as the
    same thing. Pinned here so the asymmetry cannot change silently.
    """
    envelope = minimal()
    for key in (
        "run_id",
        "artifacts",
        "evidence",
        "decision",
        "next_actions",
        "compensation",
    ):
        assert key in envelope
        assert envelope[key] is None
    assert "error" not in envelope
    assert "error_detail" not in envelope


def test_evidence_constructors_produce_schema_valid_items(
    validator: Draft202012Validator,
) -> None:
    items = [
        evidence_http("service:/health", status_code=204),
        evidence_http("service:/thing", status_code=500, passed=True, note="expected under test"),
        evidence_assertion("flag", value=None, passed=False),
        evidence_count("rows", value=42, passed=True, note="counted"),
    ]
    validator.validate(minimal(evidence=items))


def test_evidence_http_explicit_passed_overrides_the_status_code_default() -> None:
    ev = evidence_http("service:/thing", status_code=500, passed=True)
    assert ev["passed"] is True


def test_evidence_constructors_omit_an_unset_note() -> None:
    assert "note" not in evidence_http("service:/health", status_code=200)
    assert "note" not in evidence_assertion("flag", value=1, passed=True)
    assert "note" not in evidence_count("rows", value=1, passed=True)
