# ADR-0045: A Blueprint Template Takes Operator Seeds, and Nothing Else

## Status

Proposed

## Date

2026-07-21

## Context

A source version's acquisition spec could be composed in exactly two ways, and
the schema enforced the exclusive-or at
`platform-control/src/platform_control/schemas/source.py:319` and `:352`:

```
Provide either acquisition_spec or overlay_id/provider_template_id, not both.
```

Either the version *is* a `source_blueprints.yaml` template, verbatim, or the
operator hand-writes the whole spec. #628 measures the cost of the Nth source and
treats the reuse ladder as the number that must trend down. That ladder had no
middle rung:

| Rung | Operator cost | Blueprint provenance | Available |
|---|---|---|---|
| 1 — template as-is | minutes, zero code | yes | yes |
| 2 — template + operator seeds | — | — | **no** |
| 3 — full hand-written spec | ~13 fields, by hand | **discarded** | yes |

On 2026-07-21 the federal animal-protection layer (TSchG SR 455 / TSchV SR 455.1)
had to enter the corpus for ADR-0033's dog question. The work required was
exactly *the existing `fedlex_sparql_federal_law_batch_de` shape with two
different `seed_urls`*. Every other field — `sparql_endpoint`, `query_mode`,
`preferred_languages`, `extractor_profile_id`, `scope_type`, `trust_tier`,
`document_type_hint` — was already correct.

Rung 2 not existing made that a **repo edit, an image rebuild and a redeploy**
(#736) for two URLs. Rung 3 was worse than it looks: because
`_blueprint_provenance` clears `overlay_id`/`provider_template_id` whenever an
explicit spec is supplied, a hand-written spec is a version the ADR-0030 config
key **never gates** — `run_service._assert_launchable` only consults the
enablement service when both provenance fields are set. The cheap escape hatch
was also the one that left the lock behind.

"Same provider, same settings, different documents" is the common shape as
coverage extends along an axis. It is the one thing the platform should make
trivial, and it was the one thing it forbade.

## Decision

A source version may name a blueprint template **and** supply
`blueprint_overrides`. The override vocabulary is exactly two keys:

```json
{ "overlay_id": "ch",
  "provider_template_id": "fedlex_sparql_federal_law_batch_de",
  "blueprint_overrides": { "seed_urls": ["…/eli/cc/2008/414", "…/eli/cc/2008/416"] } }
```

Three rules make this safe:

1. **Seeds only.** `blueprint_overrides` is a closed schema (`extra="forbid"`)
   with `seed_url` and `seed_urls` and nothing else. It is not a merge facility.
2. **Same origin.** Every supplied seed must sit on a `(scheme, host)` the
   template's own seeds already reach. A template with no seeds of its own
   (`ris_ogd`, `legifrance`) cannot take an override at all.
3. **Provenance is kept, not dropped.** A template-plus-seeds version records
   `overlay_id`/`provider_template_id` exactly as a verbatim one does, so the
   two-key lock applies to it unchanged.

### What is deliberately *not* overridable, and why

The XOR was load-bearing. A template is not a convenience macro; it is a set of
assertions that an enablement decision was made *about*. Each of these stays the
blueprint's:

| Field(s) | What an override would let an operator do |
|---|---|
| `provider` | Judge the run against a different provider's code key — launder one template's enablement onto another provider's readiness |
| `tenant_id`, `corpus_id`, `scope_type` | Redirect where documents land and who can see them; write tenant-private material into a public corpus, or vice versa |
| `trust_tier`, `source_origin_kind` | Assert a stronger evidentiary claim over every artifact than the source supports |
| `sparql_endpoint`, `base_url`, `canton_code`, `bfs_number`, `bundesland`, `regione` | Point an enabled template at an unvetted portal — the same attack rule 2 blocks for seeds, by a different field |
| everything else (limits, timeouts, formats, languages) | No motivating case; excluded by default rather than by argument |

Rule 2 is the non-obvious one and it carries the security weight. Without it,
"seeds only" is still a general-purpose crawl licence: `seed_urls` are fetch
targets for `deterministic_http` and `firecrawl`, so an enabled template would
become permission to fetch anything. The acceptance-run evidence behind a config
key is evidence about **one portal's** robots posture, licence terms, and
document shape. Confining overrides to the template's own origins is what keeps
that evidence meaningful. The portal-keyed providers (`canton_http`,
`gemeinde_http`, `bundesland_http`, `regione_http`) already allow-list a host per
subdivision code; rule 2 gives the rest of the providers the same property.

### Consequence for the #619 provenance rule

`_blueprint_provenance_for_spec` decided provenance by exact equality against
the template's output. With rung 2 that test is wrong in the dangerous
direction: every template-plus-seeds version would read as hand-written, and
would therefore lose its config-key gate. The rule is widened to match the new
definition of "is this template's output" — non-seed fields must still match
exactly, and the seeds must still lie within the template's origins. Seeds that
leave the portal still clear provenance, as before.

## Consequences

- Adding a source on a portal the platform already reaches is an API call, not a
  deploy. That is the #628 metric moving.
- Rung 2 is now *strictly better governed* than rung 3: it keeps the lock, while
  a hand-written spec still bypasses the config key entirely. The cheap path and
  the safe path are the same path, which is the point.
- `source_blueprints.yaml` keeps its meaning: it is the list of portals the
  platform is allowed to reach, and only a repo change adds one.
- A template that genuinely needs different non-seed settings is still a
  template. That is correct — it is a different assertion, and it should be
  reviewed as one.
- The admin panel's source-create form does not yet expose the field; the API
  and CLI do. Surfacing it in the wizard is follow-up work.

## Alternatives considered

**A general sparse merge over the whole spec.** What the issue originally
suggested. Rejected: it makes every guarantee in the table above operator-
revocable, and the motivating case needs none of it.

**Store the override in a new column for provenance.** Rejected as unnecessary
state: the persisted `acquisition_spec` already carries the seeds and the row
already carries the template id, so the override is exactly their difference.

**Generate templates from a parameterised YAML macro.** Rejected: it keeps the
deploy in the loop, which is the cost being removed.

## References

- #710 (this ADR), #736 (the redeploy this avoids), #628 (the metric)
- ADR-0030 — acquisition provider enablement lifecycle (the two-key lock)
- ADR-0033 — agentic legal reasoning (the dog question driving the axis)
- #619 / #655 — blueprint provenance on a source version
