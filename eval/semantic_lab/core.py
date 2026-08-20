"""Finite reference semantics for Evidara Semantic Laboratory v0.5.

This module is deliberately dependency-free. It is a small executable
specification, not a production legal reasoner.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Iterable, Mapping, Sequence


class SemanticLabError(ValueError):
    """Raised when a semantic-lab fixture is structurally invalid."""


@dataclass(frozen=True)
class EvidenceRef:
    document_id: str
    section_id: str | None = None


@dataclass(frozen=True)
class Context:
    context_id: str
    atoms: frozenset[str]


@dataclass(frozen=True)
class Section:
    """A local semantic section: atom -> finite set of propositions."""

    context_id: str
    values: tuple[tuple[str, tuple[str, ...]], ...]
    evidence_refs: tuple[EvidenceRef, ...]

    def as_mapping(self) -> dict[str, frozenset[str]]:
        return {atom: frozenset(values) for atom, values in self.values}

    @classmethod
    def from_mapping(
        cls,
        context_id: str,
        values: Mapping[str, Iterable[str]],
        evidence_refs: Sequence[EvidenceRef] = (),
    ) -> "Section":
        frozen = tuple(
            sorted((atom, tuple(sorted(set(props)))) for atom, props in values.items())
        )
        return cls(context_id=context_id, values=frozen, evidence_refs=tuple(evidence_refs))


@dataclass(frozen=True)
class Rule:
    rule_id: str
    premises: frozenset[str]
    conclusion: str
    atoms: frozenset[str]
    priority: int = 0
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class Probe:
    probe_id: str
    atom: str
    proposition: str

    def observe(self, section: Section) -> bool:
        values = section.as_mapping()
        return self.proposition in values.get(self.atom, frozenset())


@dataclass(frozen=True)
class GlueResult:
    exists: bool
    unique: bool
    section: Section | None
    conflicts: tuple[str, ...] = ()
    missing_atoms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Certificate:
    status: str
    cover_valid: bool
    matching_family: bool
    gluing_exists: bool
    gluing_unique: bool
    semantic_classes: int
    provenance_complete: bool
    conflicts: tuple[str, ...]
    missing_atoms: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cover_valid": self.cover_valid,
            "matching_family": self.matching_family,
            "gluing_exists": self.gluing_exists,
            "gluing_unique": self.gluing_unique,
            "semantic_classes": self.semantic_classes,
            "provenance_complete": self.provenance_complete,
            "conflicts": list(self.conflicts),
            "missing_atoms": list(self.missing_atoms),
        }


@dataclass(frozen=True)
class Fixture:
    contexts: dict[str, Context]
    covers: dict[str, tuple[str, ...]]
    sections: dict[str, Section]
    rules: tuple[Rule, ...]
    facts: dict[str, frozenset[str]]
    probes: tuple[Probe, ...]
    document_ids: frozenset[str]
    section_ids: frozenset[str]


def _refs(raw: Sequence[Mapping[str, Any]] | None) -> tuple[EvidenceRef, ...]:
    return tuple(
        EvidenceRef(
            document_id=str(item["document_id"]),
            section_id=(str(item["section_id"]) if item.get("section_id") else None),
        )
        for item in (raw or ())
    )


def load_fixture(path: str | Path) -> Fixture:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    documents = raw.get("documents", [])
    sections_raw = raw.get("canonical_sections", [])
    document_ids = frozenset(str(item["document_id"]) for item in documents)
    section_ids = frozenset(str(item["section_id"]) for item in sections_raw)

    contexts = {
        str(item["id"]): Context(
            context_id=str(item["id"]),
            atoms=frozenset(str(atom) for atom in item["atoms"]),
        )
        for item in raw["contexts"]
    }

    covers = {
        str(parent): tuple(str(child) for child in children)
        for parent, children in raw.get("covers", {}).items()
    }

    sections: dict[str, Section] = {}
    for item in raw.get("local_sections", []):
        context_id = str(item["context"])
        sections[context_id] = Section.from_mapping(
            context_id=context_id,
            values={
                str(atom): tuple(str(p) for p in propositions)
                for atom, propositions in item["values"].items()
            },
            evidence_refs=_refs(item.get("evidence_refs")),
        )

    rules = tuple(
        Rule(
            rule_id=str(item["id"]),
            premises=frozenset(str(p) for p in item.get("premises", [])),
            conclusion=str(item["conclusion"]),
            atoms=frozenset(str(atom) for atom in item["atoms"]),
            priority=int(item.get("priority", 0)),
            evidence_refs=_refs(item.get("evidence_refs")),
        )
        for item in raw.get("rules", [])
    )

    facts = {
        str(atom): frozenset(str(p) for p in propositions)
        for atom, propositions in raw.get("facts", {}).items()
    }

    probes = tuple(
        Probe(
            probe_id=str(item["id"]),
            atom=str(item["atom"]),
            proposition=str(item["proposition"]),
        )
        for item in raw.get("probes", [])
    )

    fixture = Fixture(
        contexts=contexts,
        covers=covers,
        sections=sections,
        rules=rules,
        facts=facts,
        probes=probes,
        document_ids=document_ids,
        section_ids=section_ids,
    )
    validate_fixture(fixture)
    return fixture


def validate_fixture(fixture: Fixture) -> None:
    all_atoms = set().union(*(ctx.atoms for ctx in fixture.contexts.values()))

    for parent, children in fixture.covers.items():
        if parent not in fixture.contexts:
            raise SemanticLabError(f"cover parent {parent!r} is not a context")
        for child in children:
            if child not in fixture.contexts:
                raise SemanticLabError(f"cover child {child!r} is not a context")
            if not fixture.contexts[child].atoms <= fixture.contexts[parent].atoms:
                raise SemanticLabError(f"{child!r} is not a refinement of {parent!r}")

    for context_id, section in fixture.sections.items():
        if context_id not in fixture.contexts:
            raise SemanticLabError(f"section context {context_id!r} is unknown")
        if not set(section.as_mapping()) <= fixture.contexts[context_id].atoms:
            raise SemanticLabError(f"section {context_id!r} assigns outside its context")

    for atom in fixture.facts:
        if atom not in all_atoms:
            raise SemanticLabError(f"fact atom {atom!r} is unknown")

    for rule in fixture.rules:
        if not rule.atoms <= all_atoms:
            raise SemanticLabError(f"rule {rule.rule_id!r} uses an unknown atom")

    for probe in fixture.probes:
        if probe.atom not in all_atoms:
            raise SemanticLabError(f"probe {probe.probe_id!r} uses an unknown atom")

    for ref in _all_refs(fixture):
        if ref.document_id not in fixture.document_ids:
            raise SemanticLabError(
                f"evidence ref points to unknown document {ref.document_id!r}"
            )
        if ref.section_id is not None and ref.section_id not in fixture.section_ids:
            raise SemanticLabError(
                f"evidence ref points to unknown section {ref.section_id!r}"
            )


def _all_refs(fixture: Fixture) -> Iterable[EvidenceRef]:
    for section in fixture.sections.values():
        yield from section.evidence_refs
    for rule in fixture.rules:
        yield from rule.evidence_refs


def restrict(section: Section, target: Context) -> Section:
    values = section.as_mapping()
    return Section.from_mapping(
        context_id=target.context_id,
        values={atom: values[atom] for atom in target.atoms if atom in values},
        evidence_refs=section.evidence_refs,
    )


def cover_is_valid(fixture: Fixture, parent_id: str) -> bool:
    children = fixture.covers.get(parent_id, ())
    if not children:
        return False
    parent = fixture.contexts[parent_id].atoms
    union = set().union(*(fixture.contexts[child].atoms for child in children))
    return union == set(parent)


def matching_family(fixture: Fixture, parent_id: str) -> tuple[bool, tuple[str, ...]]:
    children = fixture.covers.get(parent_id, ())
    conflicts: list[str] = []
    for index, left_id in enumerate(children):
        left = fixture.sections[left_id].as_mapping()
        left_atoms = fixture.contexts[left_id].atoms
        for right_id in children[index + 1 :]:
            right = fixture.sections[right_id].as_mapping()
            overlap = left_atoms & fixture.contexts[right_id].atoms
            for atom in overlap:
                if left.get(atom, frozenset()) != right.get(atom, frozenset()):
                    conflicts.append(
                        f"{left_id}/{right_id} disagree on {atom}: "
                        f"{sorted(left.get(atom, frozenset()))} != "
                        f"{sorted(right.get(atom, frozenset()))}"
                    )
    return not conflicts, tuple(conflicts)


def glue(fixture: Fixture, parent_id: str) -> GlueResult:
    """Glue named local sections over a finite cover.

    For this reference sheaf, a section is a function from atoms to proposition
    sets. Gluing means: every parent atom is covered, local sections agree on
    overlaps, and the compatible local assignments are unioned. Function
    extensionality makes that union unique.
    """

    if not cover_is_valid(fixture, parent_id):
        parent_atoms = fixture.contexts[parent_id].atoms
        children = fixture.covers.get(parent_id, ())
        covered = (
            set().union(*(fixture.contexts[c].atoms for c in children))
            if children
            else set()
        )
        missing = tuple(sorted(parent_atoms - covered))
        return GlueResult(
            exists=False,
            unique=False,
            section=None,
            missing_atoms=missing,
        )

    matches, conflicts = matching_family(fixture, parent_id)
    if not matches:
        return GlueResult(
            exists=False,
            unique=False,
            section=None,
            conflicts=conflicts,
        )

    merged: dict[str, frozenset[str]] = {}
    refs: list[EvidenceRef] = []
    for child_id in fixture.covers[parent_id]:
        local = fixture.sections[child_id]
        refs.extend(local.evidence_refs)
        for atom, propositions in local.as_mapping().items():
            merged[atom] = propositions

    section = Section.from_mapping(
        context_id=parent_id,
        values=merged,
        evidence_refs=tuple(dict.fromkeys(refs)),
    )
    return GlueResult(exists=True, unique=True, section=section)


def infer(
    fixture: Fixture,
    *,
    atoms: Iterable[str] | None = None,
) -> Section:
    """Compute a finite prioritized forward-chaining closure.

    The highest-priority rule wins against an explicit contrary `NOT_<p>`.
    Equal top priorities retain neither proposition, representing unresolved
    conflict in this deliberately tiny reference semantics.
    """

    selected = set(atoms) if atoms is not None else set(fixture.facts)
    states: dict[str, set[str]] = {
        atom: set(fixture.facts.get(atom, frozenset())) for atom in selected
    }

    changed = True
    while changed:
        changed = False
        for atom in selected:
            candidates: dict[str, tuple[int, str]] = {}
            for rule in fixture.rules:
                if atom not in rule.atoms:
                    continue
                if not rule.premises <= states[atom]:
                    continue
                old = candidates.get(rule.conclusion)
                if old is None or rule.priority > old[0]:
                    candidates[rule.conclusion] = (rule.priority, rule.rule_id)

            handled: set[str] = set()
            for proposition, (priority, _rule_id) in candidates.items():
                if proposition in handled:
                    continue
                contrary = (
                    proposition[4:]
                    if proposition.startswith("NOT_")
                    else f"NOT_{proposition}"
                )
                handled.add(proposition)
                handled.add(contrary)
                opposite = candidates.get(contrary)
                if opposite is None:
                    if proposition not in states[atom]:
                        states[atom].add(proposition)
                        changed = True
                elif priority > opposite[0]:
                    if contrary in states[atom]:
                        states[atom].remove(contrary)
                        changed = True
                    if proposition not in states[atom]:
                        states[atom].add(proposition)
                        changed = True
                elif opposite[0] > priority:
                    if proposition in states[atom]:
                        states[atom].remove(proposition)
                        changed = True
                    if contrary not in states[atom]:
                        states[atom].add(contrary)
                        changed = True
                else:
                    if proposition in states[atom]:
                        states[atom].remove(proposition)
                        changed = True
                    if contrary in states[atom]:
                        states[atom].remove(contrary)
                        changed = True

    context_atoms = frozenset(selected)
    context_id = next(
        (
            ctx.context_id
            for ctx in fixture.contexts.values()
            if ctx.atoms == context_atoms
        ),
        "derived",
    )
    refs = tuple(dict.fromkeys(ref for rule in fixture.rules for ref in rule.evidence_refs))
    return Section.from_mapping(context_id=context_id, values=states, evidence_refs=refs)


def probe_signature(section: Section, probes: Sequence[Probe]) -> tuple[bool, ...]:
    return tuple(probe.observe(section) for probe in probes)


def semantic_class_count(
    sections: Sequence[Section],
    probes: Sequence[Probe],
) -> int:
    return len({probe_signature(section, probes) for section in sections})


def provenance_complete(fixture: Fixture) -> bool:
    """Every formal rule and supplied local section must have evidence."""
    return all(section.evidence_refs for section in fixture.sections.values()) and all(
        rule.evidence_refs for rule in fixture.rules
    )


def certify(fixture: Fixture, parent_id: str) -> Certificate:
    cover_valid = cover_is_valid(fixture, parent_id)
    matches, conflicts = (
        matching_family(fixture, parent_id) if cover_valid else (False, ())
    )
    glued = glue(fixture, parent_id)

    semantic_classes = (
        semantic_class_count([glued.section], fixture.probes)
        if glued.section is not None
        else 0
    )
    provenance_ok = provenance_complete(fixture)

    if not cover_valid:
        status = "COVERAGE_INCOMPLETE"
    elif not matches:
        status = "COHERENCE_FAILURE"
    elif not glued.exists:
        status = "NO_GLOBAL_SECTION"
    elif not provenance_ok:
        status = "UNPROVEN"
    else:
        status = "CERTIFIED"

    return Certificate(
        status=status,
        cover_valid=cover_valid,
        matching_family=matches,
        gluing_exists=glued.exists,
        gluing_unique=glued.unique,
        semantic_classes=semantic_classes,
        provenance_complete=provenance_ok,
        conflicts=conflicts or glued.conflicts,
        missing_atoms=glued.missing_atoms,
    )
