from eval.semantic_lab.diagram import (
    DiagramArrow,
    DiagramError,
    FiniteLegalDiagram,
    SemanticProbe,
)


A_SYS = ("A=1d", "proof=systemic")
A_LOC = ("A=1d", "proof=local")
B_SYS = ("B=1d", "proof=systemic")
B_LOC = ("B=1d", "proof=local")

R_STATUTE = ("R=systemic_AB", A_SYS, B_SYS, "basis=statute")
R_TREATY = ("R=systemic_AB", A_SYS, B_SYS, "basis=treaty")
R_LOCAL = ("R=independent_local", A_LOC, B_LOC, "basis=local")


def make_diagram(*, rich_probe: bool = False) -> FiniteLegalDiagram:
    probes = [
        SemanticProbe("A_conclusion", lambda section: section["A"][0]),
        SemanticProbe("B_conclusion", lambda section: section["B"][0]),
    ]
    if rich_probe:
        probes.append(
            SemanticProbe(
                "relational_legal_basis",
                lambda section: section["R_AB"][3],
            )
        )

    return FiniteLegalDiagram(
        state_sets={
            "A": [A_SYS, A_LOC],
            "B": [B_SYS, B_LOC],
            "R_AB": [R_STATUTE, R_TREATY, R_LOCAL],
        },
        arrows=[
            DiagramArrow("R_to_A", "R_AB", "A", "pi_A"),
            DiagramArrow("R_to_B", "R_AB", "B", "pi_B"),
        ],
        maps={
            "pi_A": lambda relation: relation[1],
            "pi_B": lambda relation: relation[2],
        },
        probes=probes,
    )


def test_global_sections_are_the_finite_limit():
    diagram = make_diagram()
    sections = diagram.global_sections()
    assert len(sections) == 3
    assert all(diagram.compatible(section) for section in sections)


def test_identifiability_is_relative_to_probe_family():
    local = make_diagram(rich_probe=False).certify()
    rich = make_diagram(rich_probe=True).certify()

    assert local.status == "IDENTIFIED_MODULO_PROBES"
    assert local.global_sections == 3
    assert local.semantic_classes == 1

    assert rich.status == "AMBIGUOUS"
    assert rich.global_sections == 3
    assert rich.semantic_classes == 3


def test_vertex_only_cover_fails_existence_and_uniqueness_of_descent():
    analysis = make_diagram(rich_probe=True).analyze_descent(["A", "B"])
    cert = analysis.certificate

    assert cert.matching_families == 4
    assert cert.realized_families == 2
    assert cert.families_without_gluing == 2
    assert cert.families_with_nonunique_gluing == 1
    assert not cert.descent_surjective
    assert not cert.separating
    assert not cert.exact_descent


def test_relation_cell_restores_exact_descent():
    cert = make_diagram(rich_probe=True).analyze_descent(
        ["R_AB", "A", "B"]
    ).certificate

    assert cert.matching_families == 3
    assert cert.realized_families == 3
    assert cert.families_without_gluing == 0
    assert cert.families_with_nonunique_gluing == 0
    assert cert.exact_descent


def test_malformed_projection_is_rejected():
    try:
        FiniteLegalDiagram(
            state_sets={"R": ["r"], "A": ["a"]},
            arrows=[DiagramArrow("bad", "R", "A", "bad_map")],
            maps={"bad_map": lambda _value: "not-an-A-state"},
        )
    except DiagramError as exc:
        assert "not well typed" in str(exc)
    else:
        raise AssertionError("expected DiagramError")


def test_missing_map_is_rejected():
    try:
        FiniteLegalDiagram(
            state_sets={"R": ["r"], "A": ["a"]},
            arrows=[DiagramArrow("bad", "R", "A", "missing")],
            maps={},
        )
    except DiagramError as exc:
        assert "missing map" in str(exc)
    else:
        raise AssertionError("expected DiagramError")
