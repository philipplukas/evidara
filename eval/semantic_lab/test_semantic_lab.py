from dataclasses import replace
from pathlib import Path

from eval.semantic_lab.core import (
    Section,
    certify,
    glue,
    infer,
    load_fixture,
    matching_family,
    semantic_class_count,
)

FIXTURE = Path(__file__).parent / "fixtures" / "reporting_v0.json"


def test_fixture_inference_matches_unique_gluing():
    fixture = load_fixture(FIXTURE)

    glued = glue(fixture, "U")
    assert glued.exists is True
    assert glued.unique is True
    assert glued.section is not None

    inferred = infer(fixture)
    assert inferred.as_mapping() == glued.section.as_mapping()


def test_matching_family_detects_overlap_conflict():
    fixture = load_fixture(FIXTURE)
    ordinary = fixture.sections["B_ordinary"].as_mapping()
    mutated = dict(ordinary)
    mutated["zh_bank_ordinary"] = frozenset(
        {"MATERIAL_INCIDENT", "OBLIGATORY_REPORT", "NOT_PERMITTED_ADMIN_DELAY"}
    )
    bad_section = Section.from_mapping(
        context_id="B_ordinary",
        values=mutated,
        evidence_refs=fixture.sections["B_ordinary"].evidence_refs,
    )
    bad_fixture = replace(
        fixture,
        sections={**fixture.sections, "B_ordinary": bad_section},
    )

    matches, conflicts = matching_family(bad_fixture, "U")
    assert matches is False
    assert len(conflicts) == 1

    result = glue(bad_fixture, "U")
    assert result.exists is False
    assert result.unique is False
    assert result.conflicts


def test_certificate_fails_closed_on_incomplete_cover():
    fixture = load_fixture(FIXTURE)
    incomplete = replace(fixture, covers={"U": ("A_bank",)})

    certificate = certify(incomplete, "U")
    assert certificate.status == "COVERAGE_INCOMPLETE"
    assert certificate.gluing_exists is False
    assert certificate.missing_atoms == ("zh_nonbank_ordinary",)


def test_semantic_equivalence_is_modulo_declared_probes():
    fixture = load_fixture(FIXTURE)
    glued = glue(fixture, "U").section
    assert glued is not None

    hidden_alias_values = {
        atom: set(props) for atom, props in glued.as_mapping().items()
    }
    hidden_alias_values["zh_nonbank_ordinary"].add("HIDDEN_IMPLEMENTATION_LABEL")
    hidden_alias = Section.from_mapping("U", hidden_alias_values)

    assert semantic_class_count([glued, hidden_alias], fixture.probes) == 1

    separating_probe = replace(
        fixture.probes[0],
        probe_id="separating_hidden_label",
        atom="zh_nonbank_ordinary",
        proposition="HIDDEN_IMPLEMENTATION_LABEL",
    )
    assert (
        semantic_class_count([glued, hidden_alias], (*fixture.probes, separating_probe))
        == 2
    )


def test_emergency_defeater_beats_general_permission():
    fixture = load_fixture(FIXTURE)
    derived = infer(fixture).as_mapping()

    emergency = derived["zh_bank_emergency"]
    assert "OBLIGATORY_REPORT" in emergency
    assert "NOT_PERMITTED_ADMIN_DELAY" in emergency
    assert "PERMITTED_ADMIN_DELAY" not in emergency


def test_fixture_emits_certified_machine_readable_result():
    fixture = load_fixture(FIXTURE)
    payload = certify(fixture, "U").to_dict()

    assert payload == {
        "status": "CERTIFIED",
        "cover_valid": True,
        "matching_family": True,
        "gluing_exists": True,
        "gluing_unique": True,
        "semantic_classes": 1,
        "provenance_complete": True,
        "conflicts": [],
        "missing_atoms": [],
    }
