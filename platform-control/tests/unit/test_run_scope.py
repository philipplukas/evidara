"""`scope.max_resources` is read back from the run (#1010).

The parameter was accepted by the API, stored on the run and read by nothing, so
`--max-resources 25` captured 944 documents. These pin both halves: that the value
is found, and that it can only narrow the template's own limit.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from platform_control.services.run_scope import (
    effective_resource_cap,
    run_scope_max_resources,
)


def run_with(metadata: object) -> SimpleNamespace:
    return SimpleNamespace(run_metadata=metadata)


class TestRunScopeMaxResources:
    def test_reads_the_value(self) -> None:
        assert run_scope_max_resources(run_with({"scope": {"max_resources": 25}})) == 25

    def test_accepts_a_string_because_json_round_trips_are_not_guaranteed(self) -> None:
        assert run_scope_max_resources(run_with({"scope": {"max_resources": "25"}})) == 25

    @pytest.mark.parametrize(
        "metadata",
        [
            None,
            {},
            {"scope": None},
            {"scope": {}},
            {"scope": {"max_resources": None}},
            {"scope": {"max_resources": 0}},
            {"scope": {"max_resources": -3}},
            {"scope": {"max_resources": "not-a-number"}},
            {"scope": {"max_resources": []}},
            "run_metadata is somehow a string",
        ],
    )
    def test_absent_or_unusable_reads_as_no_cap(self, metadata: object) -> None:
        # Never raise out of start_run over a malformed JSON column: "no cap" is
        # the pre-existing behaviour and the safe direction.
        assert run_scope_max_resources(run_with(metadata)) is None

    def test_true_is_not_a_cap_of_one(self) -> None:
        # `bool` is a subclass of `int`; without an explicit check `True` would
        # silently cap a run at a single resource.
        assert run_scope_max_resources(run_with({"scope": {"max_resources": True}})) is None


class TestEffectiveResourceCap:
    def test_run_only(self) -> None:
        assert effective_resource_cap(run_with({"scope": {"max_resources": 25}}), None) == 25

    def test_spec_only(self) -> None:
        assert effective_resource_cap(run_with(None), 500) == 500

    def test_neither(self) -> None:
        assert effective_resource_cap(run_with(None), None) is None

    def test_run_narrows_the_spec(self) -> None:
        assert effective_resource_cap(run_with({"scope": {"max_resources": 25}}), 500) == 25

    def test_run_cannot_widen_the_spec(self) -> None:
        # The template is reviewed and approved; the run scope is a command-line
        # argument. A run must not raise a bounded source's ceiling without a
        # version approval.
        assert effective_resource_cap(run_with({"scope": {"max_resources": 5_000}}), 500) == 500

    def test_zero_spec_cap_means_unset_not_capture_nothing(self) -> None:
        # Several providers spell "no limit" as `0` (lexfind's `max_documents`).
        assert effective_resource_cap(run_with({"scope": {"max_resources": 25}}), 0) == 25
        assert effective_resource_cap(run_with(None), 0) is None
