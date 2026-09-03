# ADR-0050: One rule, one enforcement point

## Status

Proposed

## Date

2026-09-03

## Context

### The same rule, written twice, and the weaker copy won

On 2026-09-03 the ADR-0030 config key — the one an operator turns to point production
traffic at a live government portal — could be armed two ways, and the two ways did not
agree.

| Path | What it required to arm the key |
|---|---|
| Admin panel | a non-empty free-text note (`platform-control/admin/src/resources/blueprints/BlueprintEnablementDialog.tsx:62-63`) |
| `evidara workflow coverage enable` | a cited acceptance run, a re-derived ADR-0030 verdict, a provider match, and two explicit acknowledgements — refusing with eight named codes (`tools/evidara-cli/src/evidara_cli/coverage.py:447-454`, `:502-552`) |
| The server both go through | that the template exists (`platform-control/src/platform_control/services/blueprint_enablement.py:128-159`) |

`set_enabled` runs one check — `is_source_blueprint_default_enabled` raises for an unknown
template — and then writes. `note` is `str | None = None`. Turning the key **off** required
nothing at all from either client.

So the eight refusals were not policy. They were a courtesy the CLI extended to anyone who
happened to use the CLI, and the panel is the easier path. **Where a rule is enforced in
two clients, the weaker path is the real policy**, because it is the one under the least
friction and there is no mechanism that makes the stronger one binding.

### The same shape, four more times

- **The documents index mapping.** `legal-search/api/src/core/opensearch/documents-index.mapping.ts`
  is the declared single source of truth, and `AGENTS.md` records two violations: a drifted
  hand-maintained copy in `scripts/validate-tar89-metadata-local.sh` (#675) and a
  mapping-less `PUT` in the GCP runtime tfvars (#713). Index creation is first-writer-wins,
  so a second creation path does not merely disagree with the canonical one — it *wins*.
- **Registry comments outranking the class they describe** (#833). `lexfind_api_provider.py`
  has been `AcquisitionReadiness.LIVE` since #815, against three acceptance bundles; the
  registry comment beside it still said no operator had captured evidence. A third comment
  still spoke of `live_ready`, the boolean #743 replaced. Prose is a second statement of a
  rule with no build step behind it.
- **Skills against code** (#855, open). A skill draft cited a `--copy-evidence` flag on
  `scripts/ch-fedlex-compose-e2e.sh`; that script's own comment at `:64-65` says it has *"no
  `--copy-evidence` path"*. Caught in review.
- **An ADR against code, in this very series.** ADR-0030 §5 says
  `scripts/ch-fedlex-fast-loop.sh` **and** `scripts/ch-fedlex-compose-e2e.sh` take
  `--url-pattern` and `--corpus-slug`. Only the fast loop does; the compose script says so
  at the line above. Nobody wrote that carelessly — the ADR was true when written and the
  script grew a comment denying it.

### Why the pattern survives review

Each duplicate is individually defensible. A client-side check gives a better error
message. A comment explains a class. A skill saves an agent a round trip. None of them is
wrong on the day it is written. What is wrong is that there are now two places that answer
one question, and only one of them has a build consequence.

## Decision

**A rule that more than one caller can reach is enforced at the join — the last point every
path passes through before the state changes. Clients collect inputs and render refusals;
they do not decide.**

For a write, the join is the server. Five commitments follow.

1. **The enforcement point is the narrowest common ancestor of every path to the effect.**
   PR #864 is the worked instance: the guard moved into
   `platform_control/services/blueprint_enablement_guard.py`, refusals return **409** with
   machine-readable `refusals[].code`, and both the admin dialog and the CLI now render what
   the server returned instead of deriving it.

2. **A client-side copy is deleted, not left beside the server's.** #864 deletes the CLI's
   `flip_refusals`, `verify_flip`, `evidence_binding_strength` and `version_provider`
   outright. A copy retained "as belt and braces" is the state this ADR describes: two
   rules, one of which nobody is checking.

3. **The refusal vocabulary is data, not prose.** Codes, one list, owned by the enforcement
   point and carried in the generated contract (ADR-0034), so a client cannot invent a
   refusal or silently drop one. Spelling and meaning are part of the contract; adding a
   code is an additive contract change, and a code that only ever *adds* a refusal is
   backward-compatible for a client that does not know it.

4. **Exactly one exemption, with a test for it: a check may stay client-side only if it
   would be a tautology at the enforcement point.** The CLI keeps
   `classification_disagrees_with_server`, which compares its own mirror of the two-key lock
   against the server's `launchable`. On the server that *produces* `launchable`, that
   comparison is `x == x`. It is not a crack, because the property it asserts — that the
   client's model of the lock has not drifted from the server's — has no meaning anywhere
   else. The criterion is the question, not the list: *would this check be a tautology at
   the join?* If yes, it belongs in the client. If no, it belongs at the join.

5. **Prose is not an enforcement point.** A comment, ADR, skill or README that states a rule
   cites the code that enforces it, and where it names a flag, field or state it is subject
   to ADR-0052's declared-means-produced gate. #833's comments and #855's flag were both
   found by a human reading two things at once; that is not a mechanism.

**The test that enforces this ADR** is per-rule, and it is two tests, not one: a refusal test
at the enforcement point (#864 mutation-checked all of them — see ADR-0051), and, for each
client, a test that it *consumes* the returned refusal rather than re-deriving it. The second
is what would have caught #854: the admin dialog had a test, and the test asserted the
dialog's own rule.

## Consequences

### What gets better

- Divergence becomes impossible rather than unlikely. The panel and the CLI cannot disagree
  about what arms the key, because neither of them decides.
- The refusal vocabulary is enumerable. An operator asking "what would stop this flip?" has
  one list to read, and the CLI reproduces the server's codes verbatim.
- Adding a rule is one edit. Under the old shape, a new refusal had to be written twice and
  the second writing was optional.

### What gets harder

- **A round trip for a check the client could do locally.** The CLI can no longer refuse
  offline or instantly; it sends inputs and renders what comes back. That is a real
  regression in interactive feel, accepted deliberately.
- **Refusal codes become API surface.** They appear in the generated contract, so renaming
  one is a contract change with a version bump, and a lane touching the guard now contends
  for `contracts/api/platform-control.openapi.yaml`. That is a serialization cost on a file
  several lanes already share.
- **The client's error messages get worse before they get better.** A generic 409 renderer
  is a downgrade on a bespoke inline hint. #864 pays this back by rendering the returned
  codes rather than a generic error, but that work is per-client and is not free.

### Not covered — say these out loud

- **Read-only display derivations may still live client-side**, and two of them can still
  disagree. `classifyTemplate` in the admin and `evidara_cli.coverage.classify_template`
  both derive a class for display; #864 orders the admin's to mirror the CLI's blocker
  priority and mutation-tests both. Two disagreeing display derivations are a legibility
  defect, not a safety one — but #854's display half (a kill switch rendering identically to
  a key nobody ever turned) shows how quickly a legibility defect becomes an operator
  writing over a state they were never shown.
- **This says nothing about rules whose only reachable path is a document.** ADR-0030 §5's
  flag drift has no enforcement point at all today; ADR-0052's gate is the nearest mechanism
  and it covers contract fields, not shell flags.
- **A document's own status is the same class of drift, and this ADR does not fix it.**
  ADR-0042, ADR-0047 and ADR-0048 are all `Proposed` while their subjects ship — ADR-0047's
  quarantine landed in #841, ADR-0042's `/v1/coverage` is deployed (ADR-0048 measures its
  behaviour *in production*), and ADR-0048's drift comparator was scheduled in #824.
  Nothing reconciles a status field with the merge that implemented it, so the field records
  an intention rather than a state. Flagged here because it is the same shape; changing an
  ADR's status is the owner's call and not this ADR's business.
- **It does not amend ADR-0030.** The two-key lock is unchanged: this is about where the
  config key's guard lives, not what it requires. It *does* amend **ADR-0035**, which moved
  the config key to the database and gave it an API route, and put no guard on that route —
  correctly for its scope (§1 was about the key's *home*), and the gap has been open since.

## References

- #854 (the two rules), #846 (evidence binding), #864 (the worked instance, open)
- #675, #713 — the same shape at the documents index; recorded in `AGENTS.md`
- #833 — registry comments outranking their class attributes
- #855 — a skill citing a flag that does not exist (open)
- [ADR-0030](0030-acquisition-provider-enablement-lifecycle.md) §2, §5 — the two-key lock
- [ADR-0034](0034-generated-platform-control-contract.md) — the same argument for contracts:
  an unchecked copy is a lie waiting to be believed
- [ADR-0035](0035-operator-reachable-blueprint-enablement.md) — the route this ADR guards
- [ADR-0051](0051-a-gate-that-cannot-fail-is-not-a-gate.md) — the enforcement point's own
  refusals must be shown to fire
