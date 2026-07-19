# ADR-0043: A Source's Scope Is a Measurement, Not an Assumption

## Status

Proposed

## Date

2026-07-19

## Context

`fedlex_sparql` shipped with a `canton_discovery` mode. It discovered Swiss
cantonal legislation by querying a `jolux:CantonOfOrigin` predicate, and it came
with three blueprint templates (`fedlex_sparql_canton_zh` / `_be` / `_bs`), a
schema (`scope_kind` / `canton` / `max_works`), an overlay validation branch, a
vocabulary token in `contracts/vocabularies/subdivisions.json`, eight unit
tests, and three documentation sections describing what it covered.

None of it could ever have worked. Measured against
`https://fedlex.data.admin.ch/sparqlendpoint` on 2026-07-19 (#716):

| Probe | Result |
|---|---|
| `SELECT (COUNT(*)) WHERE { ?s ?p ?o }` | 56,238,852 triples — endpoint live, so the negatives are real |
| `SELECT DISTINCT ?p` | 426 predicates, **zero** containing `anton` (covers `Canton` and `Kanton`) |
| `ASK` on six spellings of the predicate | all `false` |
| `GET /vocabulary/canton/ZH` | 404 (control `/vocabulary/legal-institution/3525` → 200) |
| `SELECT DISTINCT ?t WHERE { ?s a ?t }` | 133 classes, none cantonal; `jolux:Country` exists |
| ELI collection segments | only `fga` (BBl), `oc` (AS), `cc` (SR) — all federal |

Fedlex is the Federal Chancellery platform for **Bundesrecht**. Cantonal law is
out of scope by design; each canton runs its own systematic collection. The
inter-cantonal concordats Fedlex *does* carry are modelled as AS-collection
publications carrying no cantonal attribution whatsoever — so the mode could not
have been repaired by correcting the predicate name either. There was nothing to
filter on.

Two things make this an architectural problem rather than one bad commit.

**First, the failure is silent and confident.** Zero SPARQL bindings is not an
exception. The mode would have returned `captured=0` with no cause attributable
to the missing predicate — an operator would have seen an empty run, not a
broken one, from a provider marked `live_ready: true` against templates the
blueprint coverage inventory (#693) presents as operator-actionable. That is the
confident-fabrication failure ADR-0033 exists to prevent, displaced one layer up
from the answer to the corpus the answer is drawn from.

**Second, every artifact that could have falsified the premise restated it
instead.** `test_build_canton_discovery_query_shape` asserted
`"jolux:CantonOfOrigin" in query` — a tautology over a string we generate. The
test double intercepted on a substring of our own query text and returned a
hand-written binding whose work URI was `eli/cc/1999/404`: the *federal*
Bundesverfassung. The docs described the coverage the code claimed. The code
comment said the helper was "isolated so it can be unit-tested **without** a
live endpoint" — the opposite of the "VERIFIED against the live endpoint" note
carried by the genuinely verified predicates in the same file. Under ADR-0040's
framing, this is a whole subsystem's worth of tests that converted "I do not
know" into "pass".

Two smells were available for free, with no network call: `CantonOfOrigin` is
PascalCase, which RDF reserves for classes while every other predicate in the
file is lowerCamelCase; and the runbook item tracking this work already listed
the live acceptance run as *Still needed*. The repo had recorded its own
uncertainty and then built on top of it anyway.

## Decision

**1. A provider's claimed scope must be established by measurement against the
live source before the capability ships, not before it is enabled.**

An `enabled: false` default is not a substitute.
`test_enabled_templates_only_reference_live_ready_providers` only guards
templates whose *provider* is not
`live_ready` — a `live_ready: true` provider's disabled template is one YAML
edit from a guaranteed-zero production run. Scope claims are load-bearing at
authoring time.

**2. Every external identifier a provider depends on — predicate, vocabulary
IRI, endpoint path, parameter name — carries a comment recording the date and
query that verified it against the live source.**

This already existed as local practice in `fedlex_sparql_provider.py` for
`jolux:dateApplicability` and `jolux:inForceStatus`. It is now the rule. An
unverified identifier is a hypothesis and must be labelled as one.

**3. A test may not assert a property of a string the code under test
generated.** Asserting our own constant back to ourselves proves the constant
was interpolated, never that it is correct. Where the truth lives outside the
process, the test's honest scope is the transformation, and correctness of the
external identifier is established by (2), not by the unit test.

**4. Jurisdictional scope follows the publisher, not the geography.** A provider
for a federal source acquires federal law. Sub-federal coverage is a separate
per-jurisdiction provider against that jurisdiction's own publisher — never a
mode, flag, or filter bolted onto a federal provider. The abstraction that
looked appealing ("one provider, parameterised by canton") is precisely what
made an impossible capability look like a small configuration surface.

**5. A capability found to rest on a false premise is removed, not left
inert.** Dormant code with operator-visible templates is a latent
zero-result run wearing the same UI affordances as a working one.

## Consequences

- The `canton_discovery` mode, its three templates, its schema fields, its
  overlay branch, its `fedlex_sparql_canton` vocabulary token, and its eight
  tests are removed (#716). `fedlex_sparql`'s federal seed mode — the live CH
  legislation path exercised by `scripts/ch-fedlex-fast-loop.sh` — is untouched.
- `FedlexSparqlAcquisitionSpec` loses `scope_kind` / `canton` / `max_works`.
  Because acquisition specs are `extra="forbid"`, a stored spec carrying those
  fields now fails validation loudly rather than running a query that cannot
  succeed. This is the intended behaviour: contract version `0.14.0`.
- CH cantonal coverage is unclaimed. It requires a per-canton provider against
  each canton's systematic collection. The ZH Hundegesetz — ADR-0033's
  acceptance target — is at ZH-Lex LS 554.5 on `zh.ch`, and the only
  "Hundegesetz" in Fedlex is a federal 2009 *draft* that was never enacted. A
  separate lane is scoping what ZH actually publishes; note that `zh.ch` erlass
  pages are a JavaScript shell (the #631 failure mode), with the authoritative
  text behind a `notes.zh.ch/…OpenAttachment` PDF link.
- Rule (2) applies to existing providers on next touch, not as a sweep. Rules
  (1) and (4) bind new provider work immediately.

## Alternatives considered

**Retarget the mode at concordats.** Rejected: concordats carry no cantonal
attribution, so the best achievable filter is by collection, which is not
cantonal discovery and does not serve ADR-0033's target.

**Leave the templates disabled and fix later.** Rejected under decision (5) —
this is what let the false premise survive from #531 to #716.

**Record it in the coverage doc without an ADR.** Rejected: the coverage doc
records *what* is covered. The generalisable rules — measure before shipping,
never assert a generated string, scope follows publisher — bind future provider
design and belong where provider authors look.

## Related

- ADR-0030 — acquisition provider enablement lifecycle (the two keys this
  bypasses)
- ADR-0033 — agentic legal reasoning (the fabrication this prevents)
- ADR-0040 — what makes a test result trustworthy (the tautological-assert
  mechanism)
- #716 — the investigation and removal
- `docs/architecture/ch-acquisition-coverage-status.md` — corrected CH coverage
- `docs/runbooks/country-rollout-drift-prevention-backlog.md` §4.4 — closed
