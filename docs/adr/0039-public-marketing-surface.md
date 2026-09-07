# ADR-0039: A Third Frontend Surface — the Public Marketing Page

## Status

Proposed

## Date

2026-07-19

## Context

Evidara has two frontend surfaces today, and ADR-0027 ("two products, shared
brand") records the stance that governs them:

- **Workspace** (`legal-search/frontend`) — the reading experience for lawyers.
- **Admin** (`platform-control/admin`) — the operator control plane UI.

Both are **private**. They sit behind a single shared BasicAuth password
applied per-Ingress in `infra/hetzner/auth/ingress-tls.yaml`, and there is no
end-user authentication anywhere in the system: `legal-search/frontend` has no
login route and no session, and both APIs fail closed on a shared service key
(#680). User identity is ADR-0038 (#676, Proposed).

There is currently **no public artifact** describing what Evidara is. Anyone
who hears about the project has nothing to read and no way to register
interest. That is the gap this ADR closes.

### Why this is an architecture decision and not just a new page

Under AGENTS.md's change classification, adding a surface is
`architecture-change`: it introduces a new deployable container, a new
publicly-reachable ingress, a new trust boundary, and a new consumer of the
shared design tokens. It therefore requires an ADR and a `structurizr/workspace.dsl`
update. Both are part of this change.

The trust-boundary point is the substantive one. Every existing surface is
behind the shared password. This one is not — by design. That makes it the
first component in the system whose threat model includes anonymous internet
traffic, and it deserves to be reasoned about explicitly rather than
introduced as a folder.

### The constraint that shapes everything else

**The page must not link to a live product demo.** This is a decision, not an
omission:

- Search has three unmerged correctness fixes: deep-linked searches return "no
  results" (#672), `official_only=false` silently narrows results (#673), and
  facets come back empty (#675). A visitor who follows a demo link today gets
  wrong answers presented as right ones — the exact failure mode ADR-0033
  argues is worse than no product at all.
- There is no user authentication. "Letting someone try it" currently means
  giving them the shared BasicAuth password that also opens the admin control
  plane.

Design-partner and pilot flows come later, gated on ADR-0038. The page must be
built so that path can be added without a rewrite.

## Decision

### D1 — A new top-level surface at `marketing/`

The page lives at `marketing/` at the repo root: **one npm package, installed
and gated on its own**, exactly like `legal-search/frontend`,
`legal-search/api`, and `platform-control/admin`.

Two rejected alternatives, and why:

- **Inside `legal-search/`.** Rejected. `legal-search/` is a plain directory
  holding independent packages and deliberately has no root `package.json`;
  the vestigial one that used to live there ERESOLVEd on install and shadowed
  the real surfaces (#588). Marketing is also not part of the search product —
  it has a different audience, a different lifecycle, and must be public while
  everything under `legal-search/` is private.
- **A container directory (`marketing/www/`).** Rejected as premature. There
  is one package. A container directory with a single child is the shape that
  invited the `legal-search/package.json` mistake in the first place. If a
  second marketing artifact ever appears, promoting to a container directory
  is a rename.

The surface follows every existing convention: Biome for lint/format, Vitest
for tests, `npm run check` (typecheck + lint + test) as the gate, Node pinned
via the root `.nvmrc`, and its own `node_modules` installed with `npm ci`.

It consumes the shared `styles/` modules (`@evidara/tokens`, `@evidara/shell`)
and therefore reproduces all three resolution mechanisms the other React
surfaces use — `tsconfig` `paths`, Vitest `resolve.dedupe`, and Turbopack
`resolveAlias` — because the shared modules live outside any npm package and
resolving them from the wrong root yields a second React instance (#588).
`scripts/check-js-workspace-hygiene.sh` is extended to assert this for the new
surface, so the invariant is enforced rather than remembered.

### D2 — Statically exported; no server runtime

`output: "export"`. The build emits plain HTML, CSS and JS; the container is a
static file server.

This is a security decision as much as a simplicity one. The only publicly
reachable surface in the system is the one that **cannot execute server code,
cannot hold a secret, and has no network path to any other container**. In the
Structurizr model, `marketing` has no outbound relationship to anything. That
empty arrow list is the design.

It also means the marketing page cannot break when the product does, and does
not need to be in the deploy blast radius of a platform change.

### D3 — No email storage in this change; when it lands, Listmonk

The page ships with a complete, accessible, tested waitlist form and **no
storage behind it**. `src/lib/waitlist.ts` is a single seam: point
`NEXT_PUBLIC_WAITLIST_ENDPOINT` at a store and the form works, with no
component changes. Until then the UI states plainly that signups are not open
yet — it does not fake success.

Two options were compared.

**Option A — a `waitlist` table plus a minimal public endpoint on
platform-control.** Rejected, and the reasoning generalises beyond this
feature:

- platform-control is the **operator control plane**. It holds source
  lifecycle, approvals, and compliance policies, and #680 deliberately made it
  fail closed when no API key is configured. Adding a public, unauthenticated
  write path to that service directly contradicts the posture it was just
  given.
- The isolation loss is real, not theoretical. A public endpoint on
  platform-control shares a process, a connection pool, and a database role
  with the approvals system. A resource-exhaustion or injection bug on the
  least-trusted path in the system becomes a control-plane incident.
- Once you accept that it must therefore be a *separate* service, Option A has
  lost its only advantage. A new standalone write service is comparable
  operational work to Listmonk while providing none of Listmonk's features.
- Hand-rolling storage also means hand-rolling the parts that actually matter
  for collecting an email address in the EU: consent capture, double opt-in,
  unsubscribe, bounce handling, and an erasure path. That is the real work,
  and doing it badly is a compliance problem rather than a bug.

**Option B — self-hosted Listmonk on the existing CNPG cluster.** Selected as
the *eventual* target, deferred until there is a reason to collect addresses.
The precedent is established: `infra/hetzner/postgres-cluster.yaml` already
documents hosting a second database in the same instance
(`CREATE DATABASE nessie OWNER platform_control`), and ADR-0038 proposes the
same pattern for Zitadel. Listmonk ships a public subscription API designed
for exactly this, so the page posts **directly to Listmonk** and
platform-control is never in the request path.

Whenever it is implemented, the following are requirements, not options:

- **Its own database and its own role** — `CREATE DATABASE listmonk OWNER
  listmonk`, not `OWNER platform_control`. Sharing the Postgres *instance* is
  the accepted precedent; sharing the *role* is not.
- **Rate limiting at the ingress** (Traefik middleware), not in application
  code, so the limit holds regardless of what is behind it.
- **Honeypot** — already implemented client-side (`HONEYPOT_FIELD`), rejected
  before any network call. Must be re-checked server-side.
- **Double opt-in**, so an address cannot be added by someone who does not
  control it.
- **Duplicate submission is not an error.** It returns success. Telling an
  anonymous caller whether an address is already on the list is an
  address-enumeration oracle; the client already normalises `409` to success
  for this reason.

### D4 — Host `evidara.veyo.dev`, public, requiring a reviewed ingress change

Proposed host: **`evidara.veyo.dev`** — the apex of the existing umbrella,
with `search.` and `admin.` remaining as the private subdomains. The marketing
page is the front door; the products are rooms behind it.

The ingress manifest is provided at
`infra/hetzner/marketing/ingress-tls.yaml` and is **deliberately not applied**.
It requires human review and an explicit `kubectl apply`, because:

- It is the first Ingress in this cluster that intentionally **omits** the
  `traefik.ingress.kubernetes.io/router.middlewares:
  evidara-evidara-basicauth@kubernetescrd` annotation.
- BasicAuth in this cluster is **opt-in per Ingress**, not a cluster default.
  That is correct for this page and worth stating out loud as a hazard for
  every *other* Ingress: the default posture is public, so protection is
  something you must remember to add. A reviewer should confirm the omission
  here is the only one.
- A new DNS A record (`evidara.veyo.dev` → `88.99.26.120`) must exist and
  resolve *before* apply, or the cert-manager HTTP-01 challenge fails and may
  consume Let's Encrypt rate limit.

Nothing in this change deploys. The manifest is a reviewed artifact.

> **Status of D4 as of 2026-09-07 (#884).** The decision stands; three of the
> facts above no longer describe the cluster, and the gap between them is the
> defect #884 records.
>
> - The Ingress **is** applied, declaratively — `infra/hetzner/marketing/` is a
>   base under `infra/hetzner/apps/kustomization.yaml`, so Argo CD owns it. The
>   "explicit `kubectl apply` after human review" gate was real but had no
>   mechanism behind it: what actually happened is that the Deployment and Service
>   were applied on 2026-09-04 and the Ingress never was.
> - It does **not** omit the BasicAuth middleware. It carries it, as a deliberate
>   and temporary decision by the repo owner (2026-09-04) — documented at length in
>   the header of `ingress-tls.yaml`, which remains the authority. **The page is
>   therefore not yet public, and D4's central commitment is not yet met.** Every
>   day the annotation stays, the surface is deployed and cannot do the one job
>   this ADR gave it.
> - The DNS A record now exists (`evidara.veyo.dev` → `88.99.26.120`), created at
>   the registrar on 2026-09-07. Until then the page was deployed and unreachable —
>   healthy pod, no route, no name — and no signal in the repo or the cluster was
>   red about it.
>
> Removing the BasicAuth annotation is the change that satisfies D4. Before making
> it, re-read D3: a submission endpoint going live is the point at which the
> Traefik rate-limit middleware stops being optional.

## Consequences

### Positive

- Evidara has a public description grounded in verified capability, and a way
  to register interest, without exposing an unauthenticated product.
- The public attack surface is a static file server with no outbound
  dependencies — the smallest possible footprint for the job.
- The waitlist seam means adding storage later is configuration, not a
  rewrite; and the ADR-0038 design-partner path can be added as a new section
  without restructuring the page.
- Copy integrity is mechanical rather than cultural: every claim carries a
  code-path citation in `src/lib/content.ts`, and `content.test.ts` fails the
  build on a claim without evidence, on a capability card that hedges into the
  future, and on copy that implies an AI agent or semantic search.

### Negative

- A third surface is a third `node_modules`, a third CI job, and a third place
  the shared token contract can drift. Mitigated by
  `marketing-token-parity.test.ts` (the same guard admin has) and by extending
  `check-js-workspace-hygiene.sh`.
- The page will go stale as capabilities land. `content.ts` carries a
  verification date; the claims need re-checking whenever the platform's
  capability set changes materially. This is a real maintenance obligation,
  not a one-time cost.
- Marketing copy now has a review dependency on engineering reality. That is
  intended, and it is slower than writing copy freely.

### Neutral

- ADR-0027's stance extends cleanly to a third surface: marketing inherits the
  shared layer (palette, spacing scale, focus ring, accessibility contracts)
  and layers its own typography and density on top, exactly as the other two
  do. No shared-token change was needed.

## Notes on copy, and why they belong in an ADR

This is legal technology. An overclaim on a marketing page is not puffery; it
is a false statement about system capability made to people whose professional
work depends on the answer. Two rules follow, and they are architectural
because they constrain what the code may say:

1. **No claim without a code path.** `src/lib/content.ts` requires an
   `evidence` field on every claim, enforced by test. "It is on the roadmap"
   and "the schema has a field for it" are explicitly not evidence — a field
   that exists but is never populated (`delegates_to`) belongs in the
   limitations list, and is there.
2. **The limitations section is not optional.** It is load-bearing
   positioning: a platform whose architecture argues that refusing correctly
   beats answering fluently and wrongly (ADR-0033 §2) should market itself the
   same way. A test fails if that section is trimmed to a token disclaimer.

Claims were verified against the code on 2026-07-19. That pass found that
ADR-0033's own "status today" table has partly gone stale in the right
direction — the citation graph, temporal validity, and norm hierarchy have
since been built — while its municipal-acquisition gap and its "do not build
the MCP server first" guardrail remain exactly accurate. Both facts are
reflected in the copy.

## References

- [ADR-0027: Workspace ↔ Admin Visual Language — Two Products, Shared Brand](0027-workspace-admin-visual-language.md)
- [ADR-0028: Shared Shell Module](0028-shared-shell-module.md)
- [ADR-0029: Self-Hosted Hetzner Runtime](0029-self-hosted-hetzner-runtime.md)
- [ADR-0033: Agentic Legal Reasoning — RAG to Enter, Graph to Reason](0033-agentic-legal-reasoning.md)
- ADR-0038 — user identity, roles, and operator attribution (Proposed, #676)
- #588 — JS workspace hygiene; why `legal-search/` has no root `package.json`
- #672 / #673 / #675 — the unmerged search correctness fixes behind the
  no-demo-link decision
- #680 — platform-control fails closed; the posture a public write endpoint
  would contradict
