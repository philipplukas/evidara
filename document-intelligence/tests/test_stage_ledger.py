from __future__ import annotations

import pytest

from document_intelligence.observability.stage_ledger import (
    STAGE_NAMES,
    StageLedger,
    UnknownStageError,
)


def test_records_a_stage_with_its_counts() -> None:
    ledger = StageLedger()
    with ledger.stage("sectionize", items_in=1) as entry:
        entry.items_out = 24

    (recorded,) = ledger.entries
    assert recorded.name == "sectionize"
    assert recorded.items_in == 1
    assert recorded.items_out == 24
    assert recorded.failed is False
    assert recorded.duration_ms >= 0


def test_records_stages_in_execution_order() -> None:
    ledger = StageLedger()
    for name in ("normalize", "sectionize", "extract"):
        with ledger.stage(name):
            pass

    assert [entry.name for entry in ledger.entries] == ["normalize", "sectionize", "extract"]


def test_a_failing_stage_is_still_recorded_and_the_error_propagates() -> None:
    """The ledger must not be systematically absent for the documents someone is
    trying to debug. Delete the ``except`` branch in ``StageLedger.stage`` and
    this fails: the entry never reaches ``_entries``.
    """
    ledger = StageLedger()

    with pytest.raises(ValueError, match="boom"):
        with ledger.stage("extract", items_in=3):
            raise ValueError("boom")

    (recorded,) = ledger.entries
    assert recorded.name == "extract"
    assert recorded.failed is True
    assert recorded.error_type == "ValueError"
    assert recorded.items_in == 3


def test_an_unknown_stage_name_is_refused() -> None:
    """A typo'd stage name would produce a row nothing aggregates, which reads
    downstream as 'that stage never ran'. Remove the membership check and this
    fails.
    """
    ledger = StageLedger()
    with pytest.raises(UnknownStageError, match="preprocesss"):
        with ledger.stage("preprocesss"):
            pass


def test_serialises_only_the_fields_it_actually_measured() -> None:
    """A stage with no counts must omit them rather than emit 0. `0 in → 0 out`
    is a claim; a missing key is an absence, and the two are different facts.
    """
    ledger = StageLedger()
    with ledger.stage("finalize"):
        pass

    (payload,) = ledger.to_list()
    assert payload["name"] == "finalize"
    assert "duration_ms" in payload
    assert "items_in" not in payload
    assert "items_out" not in payload
    assert "failed" not in payload
    assert "details" not in payload


def test_details_is_absent_until_something_populates_it() -> None:
    """ADR-0044's transformation disclosure is not implemented. `details` must
    therefore be absent, not an empty object: an empty object renders as
    "nothing was removed", which is a stronger claim than we can make.
    """
    ledger = StageLedger()
    with ledger.stage("normalize"):
        pass

    (payload,) = ledger.to_list()
    assert "details" not in payload


def test_total_duration_sums_the_stages() -> None:
    ledger = StageLedger()
    with ledger.stage("normalize"):
        pass
    with ledger.stage("finalize"):
        pass

    assert ledger.total_duration_ms() == sum(entry.duration_ms for entry in ledger.entries)


def test_stage_vocabulary_is_the_pipeline_order() -> None:
    assert STAGE_NAMES == (
        "normalize",
        "sectionize",
        "extract",
        "assemble",
        "enrich",
        "finalize",
    )


def test_there_is_no_persist_stage() -> None:
    """The ledger is carried by the processing manifest, and the manifest is what
    persistence writes — a stage covering that write cannot appear inside it.
    Declaring one anyway would put a row in the vocabulary no producer can fill,
    which reads to an operator as "persistence never ran".
    """
    assert "persist" not in STAGE_NAMES
