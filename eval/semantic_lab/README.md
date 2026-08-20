# Evidara Semantic Laboratory v0.8

A read-only, dependency-free reference implementation for testing whether
contextual legal information can be composed coherently before any semantic
reasoning is promoted into Evidara's runtime.

This is an **evaluation instrument**, not a production legal reasoner. It does
not write canonical truth and it does not expose a product API.

## v0.5 baseline

The frozen toy fixture intentionally mirrors Evidara's canonical boundary:
documents and sections are evidence anchors; semantic sections and rules are
derived objects.

The baseline checks:

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

The expected certificate for the frozen v0.5 fixture is `CERTIFIED`.

## What exact gluing means in the baseline

Let `U` be a legal context covered by local contexts `U_i`. A local semantic
section `s_i` assigns a finite set of propositions to every atomic context in
`U_i`.

The family is *matching* when every pair agrees wherever the scopes overlap:

```text
restrict(s_i, U_i ∩ U_j) == restrict(s_j, U_i ∩ U_j)
```

For the finite function-valued baseline, gluing is then the compatible union:

```text
s(atom) = s_i(atom)  for any U_i containing atom
```

This is well-defined because overlap agreement makes the choice of `i`
irrelevant. The cover must contain every atom of `U`; otherwise gluing fails
with `COVERAGE_INCOMPLETE`. If two locals disagree on an overlap, gluing fails
with `COHERENCE_FAILURE`.

## v0.8: finite legal semantic diagrams

`diagram.py` generalizes gluing beyond function-valued sections. A query can be
compiled into a finite typed diagram `D` whose nodes include ordinary legal
contexts, relation cells, provenance cells, or other semantic locations.

Each node `v` has a finite admissible state set `F(v)`. Each arrow
`a: v -> w` has a total typed projection/restriction map `F(a)`. A global legal
state is a compatible assignment

```text
x_v in F(v) for every node v
```

such that

```text
F(a)(x_source(a)) == x_target(a)
```

for every arrow. Therefore the global state space is the finite limit

```text
Gamma(D) = lim F.
```

The reference implementation enumerates this limit exactly. A production
implementation may compile the same semantics to SAT/SMT/CSP.

### Existence, uniqueness, and semantic identifiability

For a declared probe family `P`, two global states are semantically equivalent
when every active probe observes them identically.

The v0.8 certificate distinguishes:

- `INCONSISTENT`: `Gamma(D)` is empty;
- `UNIQUE`: exactly one global section exists;
- `IDENTIFIED_MODULO_PROBES`: several formal sections exist but all have one
  declared probe signature;
- `AMBIGUOUS`: more than one probe-distinguishable global state survives.

The probe family is always part of the certificate. The lab does not claim
absolute semantic uniqueness from a finite observation family.

### Descent-cover validation

For proposed observed nodes `U_1, ..., U_n`, let `Match(U)` be the set of local
families satisfying all incidence constraints visible inside the proposed
subdiagram. Restriction induces

```text
r: Gamma(D) -> Match(U).
```

The cover/subdiagram has **exact descent** precisely when `r` is bijective:

- surjectivity: every matching local family has a global gluing;
- injectivity/separation: every matching family has at most one global gluing.

`analyze_descent()` reports these failures separately.

The v0.8 fixture deliberately shows why relation cells can be necessary. With
only local nodes `A` and `B`, four local families are overlap-compatible, but
two have no global completion and one has two distinct global completions. The
vertex-only cover therefore fails both existence and uniqueness of descent.
Adding the relation cell `R_AB` yields three matching families, all realized by
exactly one global section, so the enriched diagram has exact descent.

This is the intended validation principle: **do not stipulate a legal topology
or cover class in advance. Test whether the proposed local observations really
support existence and unique descent for the semantic structure being modeled.**

## Well-posedness conditions of the finite reference model

Before a diagram is solved, v0.8 requires:

1. every node has a non-empty finite state set;
2. every arrow is typed between known nodes;
3. every arrow map exists and is total on its source state set;
4. every projected state belongs to the target state set;
5. probe identifiers are unique.

These conditions make the finite global-section problem well-defined and
decidable. They do **not** establish that the chosen states, arrows, or probes
are legally adequate; adequacy remains a separate empirical/model-validation
question.

## Deliberate non-goals

- no LLM extraction;
- no writes to `document-intelligence`, `platform-control`, or `legal-search`;
- no claim that legal meaning is globally an ordinary sheaf;
- no automatic promotion of a passing toy certificate to legal correctness;
- no approximate/metric gluing yet.

The next rung should compile a frozen canonical Evidara fixture into this finite
diagram representation and mutation-test state spaces, relation cells,
provenance projections, probe sufficiency, and descent validity before any
runtime integration.
