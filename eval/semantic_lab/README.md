# Evidara Semantic Laboratory v0.5

A read-only, dependency-free reference implementation for testing whether
contextual legal information can be composed coherently before any semantic
reasoning is promoted into Evidara's runtime.

This is an **evaluation instrument**, not a production legal reasoner. It does
not write canonical truth and it does not expose a product API.

## What v0.5 tests

The frozen toy fixture intentionally mirrors Evidara's canonical boundary:
documents and sections are evidence anchors; semantic sections and rules are
derived objects.

The reference implementation checks:

1. context/refinement typing;
2. evidence-reference integrity;
3. finite prioritized inference with an explicit defeater;
4. cover completeness;
5. matching-family compatibility on overlaps;
6. exact gluing to a global section;
7. semantic equivalence modulo declared probes;
8. a machine-readable fail-closed certificate.

Run:

```bash
python -m pytest eval/semantic_lab
python -m eval.semantic_lab.run
```

The expected certificate for the frozen fixture is `CERTIFIED`.

## What "gluing" means here

Let `U` be a legal context covered by local contexts `U_i`. A local semantic
section `s_i` assigns a finite set of propositions to every atomic context in
`U_i`.

The family is *matching* when every pair agrees wherever the scopes overlap:

```text
restrict(s_i, U_i ∩ U_j) == restrict(s_j, U_i ∩ U_j)
```

For this finite function-valued reference sheaf, gluing is then the compatible
union:

```text
s(atom) = s_i(atom)  for any U_i containing atom
```

This is well-defined because overlap agreement makes the choice of `i`
irrelevant. The cover must contain every atom of `U`; otherwise gluing fails
with `COVERAGE_INCOMPLETE`. If two locals disagree on an overlap, gluing fails
with `COHERENCE_FAILURE`.

In a richer Evidara model a "section" may instead be a *set of admissible legal
models*. Then gluing becomes a constraint problem:

```text
find global model M
such that restrict(M, U_i) is admissible in every U_i
```

No solution is a global obstruction; several non-equivalent solutions are
genuine ambiguity; several solutions with one probe signature are unique only
modulo the declared semantic observations. Approximate gluing will later replace
exact equality by a residual/minimization problem, but v0.5 stays exact so its
failure modes are auditable.

## Deliberate non-goals

- no LLM extraction;
- no writes to `document-intelligence`, `platform-control`, or `legal-search`;
- no claim that legal meaning is globally a sheaf;
- no automatic promotion of a `CERTIFIED` toy result to legal correctness.

The next rung should consume frozen canonical Evidara fixtures and mutation-test
the same gates before any runtime integration.
