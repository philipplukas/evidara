"""Finite legal semantic diagrams for Evidara Semantic Laboratory v0.8.

The module is deliberately dependency-free. It gives an executable finite
specification of global sections, semantic identifiability, and descent-cover
validation. It is not a production legal reasoner.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from typing import Any, Callable, Hashable, Mapping, Sequence


State = Hashable
Assignment = dict[str, State]
StateMap = Callable[[State], State]
ProbeFn = Callable[[Mapping[str, State]], Hashable]


class DiagramError(ValueError):
    """Raised when a finite legal semantic diagram is structurally invalid."""


@dataclass(frozen=True)
class DiagramArrow:
    arrow_id: str
    source: str
    target: str
    map_id: str


@dataclass(frozen=True)
class SemanticProbe:
    probe_id: str
    observe: ProbeFn


@dataclass(frozen=True)
class DiagramCertificate:
    status: str
    global_sections: int
    semantic_classes: int
    exists: bool
    unique: bool
    identifiable_modulo_probes: bool
    probe_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "global_sections": self.global_sections,
            "semantic_classes": self.semantic_classes,
            "exists": self.exists,
            "unique": self.unique,
            "identifiable_modulo_probes": self.identifiable_modulo_probes,
            "probe_ids": list(self.probe_ids),
        }


@dataclass(frozen=True)
class DescentCertificate:
    observed_nodes: tuple[str, ...]
    matching_families: int
    realized_families: int
    families_without_gluing: int
    families_with_nonunique_gluing: int
    descent_surjective: bool
    separating: bool
    exact_descent: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "observed_nodes": list(self.observed_nodes),
            "matching_families": self.matching_families,
            "realized_families": self.realized_families,
            "families_without_gluing": self.families_without_gluing,
            "families_with_nonunique_gluing": self.families_with_nonunique_gluing,
            "descent_surjective": self.descent_surjective,
            "separating": self.separating,
            "exact_descent": self.exact_descent,
        }


@dataclass(frozen=True)
class DescentAnalysis:
    certificate: DescentCertificate
    missing_families: tuple[tuple[tuple[str, State], ...], ...]
    nonunique_families: tuple[
        tuple[tuple[tuple[str, State], ...], tuple[tuple[tuple[str, State], ...], ...]],
        ...,
    ]


class FiniteLegalDiagram:
    """A finite diagram of legal semantic state spaces.

    ``state_sets[node]`` is the finite set of admissible states at a semantic
    location (ordinary context, relation cell, provenance cell, etc.). Each
    arrow carries a total, typed projection/restriction map from source states
    to target states.

    A global section is a compatible assignment to every node. Therefore
    ``global_sections()`` computes the finite limit of the diagram by exact
    enumeration. Production implementations can replace enumeration with
    SAT/SMT/CSP without changing the semantics.
    """

    def __init__(
        self,
        *,
        state_sets: Mapping[str, Sequence[State]],
        arrows: Sequence[DiagramArrow],
        maps: Mapping[str, StateMap],
        probes: Sequence[SemanticProbe] = (),
    ) -> None:
        if not state_sets:
            raise DiagramError("a diagram must contain at least one node")

        normalized: dict[str, tuple[State, ...]] = {}
        for node, states in state_sets.items():
            unique = tuple(dict.fromkeys(states))
            if not unique:
                raise DiagramError(f"node {node!r} has an empty state set")
            normalized[str(node)] = unique

        self.state_sets = normalized
        self.arrows = tuple(arrows)
        self.maps = dict(maps)
        self.probes = tuple(probes)
        self._validate()

    def _validate(self) -> None:
        node_ids = set(self.state_sets)
        arrow_ids: set[str] = set()

        for arrow in self.arrows:
            if arrow.arrow_id in arrow_ids:
                raise DiagramError(f"duplicate arrow id {arrow.arrow_id!r}")
            arrow_ids.add(arrow.arrow_id)

            if arrow.source not in node_ids or arrow.target not in node_ids:
                raise DiagramError(
                    f"arrow {arrow.arrow_id!r} references an unknown node"
                )
            if arrow.map_id not in self.maps:
                raise DiagramError(
                    f"arrow {arrow.arrow_id!r} references missing map "
                    f"{arrow.map_id!r}"
                )

            allowed_target = set(self.state_sets[arrow.target])
            projection = self.maps[arrow.map_id]
            for source_state in self.state_sets[arrow.source]:
                try:
                    target_state = projection(source_state)
                except Exception as exc:  # pragma: no cover - defensive boundary
                    raise DiagramError(
                        f"map {arrow.map_id!r} is not total on node "
                        f"{arrow.source!r}"
                    ) from exc
                if target_state not in allowed_target:
                    raise DiagramError(
                        f"map {arrow.map_id!r} is not well typed: "
                        f"{source_state!r} maps to {target_state!r}, which is "
                        f"not an admissible state of {arrow.target!r}"
                    )

        probe_ids = [probe.probe_id for probe in self.probes]
        if len(set(probe_ids)) != len(probe_ids):
            raise DiagramError("probe ids must be unique")

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(self.state_sets)

    def compatible(self, assignment: Mapping[str, State]) -> bool:
        if set(assignment) != set(self.state_sets):
            return False
        for arrow in self.arrows:
            projection = self.maps[arrow.map_id]
            if projection(assignment[arrow.source]) != assignment[arrow.target]:
                return False
        return True

    def global_sections(self) -> tuple[Assignment, ...]:
        nodes = self.node_ids
        sections: list[Assignment] = []
        for values in product(*(self.state_sets[node] for node in nodes)):
            assignment = dict(zip(nodes, values, strict=True))
            if self.compatible(assignment):
                sections.append(assignment)
        return tuple(sections)

    def probe_signature(self, assignment: Mapping[str, State]) -> tuple[Hashable, ...]:
        return tuple(probe.observe(assignment) for probe in self.probes)

    def semantic_partition(
        self,
        sections: Sequence[Mapping[str, State]] | None = None,
    ) -> dict[tuple[Hashable, ...], tuple[Mapping[str, State], ...]]:
        selected = tuple(sections) if sections is not None else self.global_sections()
        classes: dict[tuple[Hashable, ...], list[Mapping[str, State]]] = defaultdict(list)
        for section in selected:
            classes[self.probe_signature(section)].append(section)
        return {signature: tuple(items) for signature, items in classes.items()}

    def certify(self) -> DiagramCertificate:
        sections = self.global_sections()
        classes = self.semantic_partition(sections) if sections else {}
        exists = bool(sections)
        unique = len(sections) == 1
        identifiable = exists and len(classes) == 1

        if not exists:
            status = "INCONSISTENT"
        elif unique:
            status = "UNIQUE"
        elif identifiable:
            status = "IDENTIFIED_MODULO_PROBES"
        else:
            status = "AMBIGUOUS"

        return DiagramCertificate(
            status=status,
            global_sections=len(sections),
            semantic_classes=len(classes),
            exists=exists,
            unique=unique,
            identifiable_modulo_probes=identifiable,
            probe_ids=tuple(probe.probe_id for probe in self.probes),
        )

    @staticmethod
    def _signature(
        assignment: Mapping[str, State],
        nodes: Sequence[str],
    ) -> tuple[tuple[str, State], ...]:
        return tuple((node, assignment[node]) for node in nodes)

    def matching_families(self, observed_nodes: Sequence[str]) -> tuple[Assignment, ...]:
        """Enumerate locally compatible families on a proposed cover/subdiagram.

        Only arrows whose source and target are both observed constrain a local
        family. This intentionally exposes when omitted relation cells make a
        proposed cover too weak: disjoint vertex observations may match
        vacuously while failing to extend to any global section.
        """

        nodes = tuple(observed_nodes)
        if not nodes:
            raise DiagramError("observed_nodes cannot be empty")
        if len(set(nodes)) != len(nodes):
            raise DiagramError("observed_nodes must be unique")
        unknown = set(nodes) - set(self.state_sets)
        if unknown:
            raise DiagramError(f"unknown observed nodes: {sorted(unknown)}")

        internal_arrows = tuple(
            arrow
            for arrow in self.arrows
            if arrow.source in nodes and arrow.target in nodes
        )

        families: list[Assignment] = []
        for values in product(*(self.state_sets[node] for node in nodes)):
            assignment = dict(zip(nodes, values, strict=True))
            if all(
                self.maps[arrow.map_id](assignment[arrow.source])
                == assignment[arrow.target]
                for arrow in internal_arrows
            ):
                families.append(assignment)
        return tuple(families)

    def analyze_descent(self, observed_nodes: Sequence[str]) -> DescentAnalysis:
        """Test whether a proposed finite cover/subdiagram has unique descent.

        Let r be restriction from global sections to matching local families.
        Exact descent means r is bijective:
          * surjectivity: every matching family glues;
          * injectivity: every matching family has at most one global gluing.
        """

        nodes = tuple(observed_nodes)
        globals_ = self.global_sections()
        matching = self.matching_families(nodes)

        fibers: dict[
            tuple[tuple[str, State], ...],
            list[tuple[tuple[str, State], ...]],
        ] = defaultdict(list)
        for global_section in globals_:
            local_signature = self._signature(global_section, nodes)
            global_signature = self._signature(global_section, self.node_ids)
            fibers[local_signature].append(global_signature)

        matching_signatures = {
            self._signature(family, nodes) for family in matching
        }
        realized_signatures = set(fibers)

        missing = tuple(sorted(matching_signatures - realized_signatures, key=repr))
        nonunique = tuple(
            sorted(
                (
                    (signature, tuple(completions))
                    for signature, completions in fibers.items()
                    if len(completions) > 1
                ),
                key=repr,
            )
        )

        certificate = DescentCertificate(
            observed_nodes=nodes,
            matching_families=len(matching_signatures),
            realized_families=len(realized_signatures),
            families_without_gluing=len(missing),
            families_with_nonunique_gluing=len(nonunique),
            descent_surjective=not missing,
            separating=not nonunique,
            exact_descent=not missing and not nonunique,
        )
        return DescentAnalysis(
            certificate=certificate,
            missing_families=missing,
            nonunique_families=nonunique,
        )
