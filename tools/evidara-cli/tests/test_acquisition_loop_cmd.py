"""The HTTP adapter for the acquisition loop (#980).

The decision tests live in `test_acquisition_loop.py`. What is testable only here is the
adapter's one judgement call: **a 409 on launch is a refusal, not a transport error.**
Reading it as transport would hand the loop an exception, and an exception is the shape a
caller retries — which is how "a refusal is terminal" would be lost in the layer below the
place that enforces it.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from evidara_cli.acquisition_loop_cmd import HttpLoopClient, _refusal_code_from_body
from evidara_cli.client import HttpJsonError
from evidara_cli.main import app

runner = CliRunner()


def _launch(client: HttpLoopClient) -> dict[str, Any]:
    return client.launch(
        source_id="src_zh",
        source_version_id="sv_zh_1",
        mode="acceptance",
        correlation_id="agent:test",
    )


def test_a_409_on_launch_is_a_refusal_not_an_error_the_caller_might_retry() -> None:
    body = json.dumps({"refusals": [{"code": "blueprint_template_not_enabled", "detail": "x"}]})
    with patch(
        "evidara_cli.acquisition_loop_cmd.request_json",
        side_effect=HttpJsonError("HTTP 409", status_code=409, body=body),
    ):
        run = _launch(HttpLoopClient(correlation_id="agent:test"))

    assert run["refused"] is True
    assert run["refusal_code"] == "blueprint_template_not_enabled"


def test_an_unreadable_409_is_still_a_refusal() -> None:
    """Fails closed: an uncoded refusal must never come back looking un-refused."""
    with patch(
        "evidara_cli.acquisition_loop_cmd.request_json",
        side_effect=HttpJsonError("HTTP 409", status_code=409, body="<html>gateway</html>"),
    ):
        run = _launch(HttpLoopClient(correlation_id="agent:test"))

    assert run["refused"] is True
    assert run["refusal_code"] == "refused_without_code"


def test_a_500_on_launch_is_not_swallowed_as_a_refusal() -> None:
    """The inverse: a server fault must not be relabelled as somebody's decision."""
    with patch(
        "evidara_cli.acquisition_loop_cmd.request_json",
        side_effect=HttpJsonError("HTTP 500", status_code=500, body="boom"),
    ):
        try:
            _launch(HttpLoopClient(correlation_id="agent:test"))
        except HttpJsonError as exc:
            assert exc.status_code == 500
        else:  # pragma: no cover - the assertion is the failure
            raise AssertionError("a 500 must propagate, not read as a refusal")


def test_refusal_code_reads_both_shapes_platform_control_emits() -> None:
    assert _refusal_code_from_body(json.dumps({"refusal_code": "a"})) == "a"
    assert _refusal_code_from_body(json.dumps({"code": "b"})) == "b"
    assert _refusal_code_from_body(json.dumps({"refusals": [{"code": "c"}]})) == "c"
    assert _refusal_code_from_body("") == "refused_without_code"


def test_preflight_only_launches_nothing_and_says_so() -> None:
    """The safe way to point the loop at a live source: no run, no upstream request."""
    readiness = {
        "ready": True,
        "checks": [{"code": "acquisition_lock_open", "ok": True, "detail": "Acceptance run."}],
    }
    calls: list[str] = []

    def fake_request_json(method: str, url: str, **kwargs: Any) -> Any:
        calls.append(f"{method} {url}")
        return readiness

    with patch("evidara_cli.acquisition_loop_cmd.request_json", side_effect=fake_request_json):
        result = runner.invoke(
            app,
            [
                "workflow",
                "coverage",
                "drive",
                "--source-id",
                "src_zh",
                "--source-version-id",
                "sv_zh_1",
                "--requests-per-attempt",
                "50",
                "--preflight-only",
            ],
        )

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["side_effect_level"] == "none"
    assert envelope["artifacts"]["journal"]["spend"]["upstream_requests_authorised"] == 0
    assert [c for c in calls if c.startswith("POST")] == []


def test_a_budget_that_bounds_nothing_is_rejected_before_any_request() -> None:
    with patch("evidara_cli.acquisition_loop_cmd.request_json") as request_json:
        result = runner.invoke(
            app,
            [
                "workflow",
                "coverage",
                "drive",
                "--source-id",
                "src_zh",
                "--source-version-id",
                "sv_zh_1",
                "--requests-per-attempt",
                "5000",
                "--max-upstream-requests",
                "100",
            ],
        )
    assert result.exit_code == 2
    request_json.assert_not_called()


def test_the_drive_command_is_registered_on_the_coverage_surface() -> None:
    """One control surface, not a second one (ADR-0056 constraint 1)."""
    result = runner.invoke(app, ["workflow", "coverage", "--help"])
    assert result.exit_code == 0
    assert "drive" in result.stdout
