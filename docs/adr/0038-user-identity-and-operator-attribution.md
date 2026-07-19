# ADR-0038: User identity, roles, and genuine operator attribution

Status: Accepted
Date: 2026-07-19
Deciders: Platform / Security
Supersedes: ADR-0020 (API authentication — extended, not replaced; its service-to-service
API-key layer is retained verbatim)
Related: ADR-0029 (self-hosted Hetzner runtime), ADR-0030 (acquisition provider enablement
lifecycle — the two-key lock), ADR-0033 (agentic legal reasoning — the coverage loop),
ADR-0034 (generated platform-control contract), ADR-0035 (operator-reachable blueprint
enablement), ADR-0036 (Nessie/Trino lakehouse — the self-hosted-OSS precedent), #628
(M13), #632, #634

## Context

### What exists today

There is no user authentication anywhere in Evidara. Verified, at the commit this ADR
was written against:

- **No login, no session, no `User` table** on either frontend. Neither
  `legal-search/frontend` nor `platform-control/admin` has an auth route, a session
  store, or a sign-in surface.
- **Both UIs are public on the internet**, behind exactly one shared Traefik BasicAuth
  password: `infra/hetzner/auth/ingress-tls.yaml` and
  `infra/hetzner/auth/basicauth-middleware.yaml`, provisioned once by
  `infra/hetzner/deploy-stage5.sh:36-50` into the `evidara-basicauth` Secret. One
  password, shared by every human who has ever been shown the demo.
- **The BFF pattern hides the browser from the API.** Both middlewares inject a
  server-held key and strip the browser from the trust path:
  `legal-search/frontend/src/middleware.ts:34` and
  `platform-control/admin/src/middleware.ts:33` each set `X-API-Key`. The browser is
  never authenticated to anything; the *deployment* is.
- **`Principal` exists but is key-shaped.**
  `platform-control/src/platform_control/auth.py:158-172` defines a real
  `Principal`/`Operator` concept, but `_resolve_auth_principal`
  (`auth.py:176-188`) derives `auth_principal` from *which key slot matched*, not from
  who presented it. `alembic/versions/20260426_0016_operators.py:52-79` seeds exactly
  three rows — `op_local_dev`, `op_scoped_operator_key`, `op_legacy_full_access`. Every
  human sharing the operator key is one row.
- **Roles are client-side theatre.** React-admin's `authProvider` slot is empty
  (`platform-control/admin/src/app/AdminApp.tsx` constructs `<Admin>` with a
  `dataProvider` and no `authProvider`); `platform-control/admin/src/lib/admin/accessControl.ts:16-22`
  reads the user's role out of `window.localStorage`; legal-search decides whether to
  show the control-plane entry point from an unsigned cookie that defaults to `"admin"`
  (`legal-search/frontend/src/lib/control-plane-entry.ts:24-40`). All of it is a
  rendering hint an end user can set themselves.
- **`docs/architecture/security-and-tenancy.md:30` describes JWT verification in
  `legal-search/api` that does not exist.** There is no JWT verification anywhere in
  that service; the only guard is `ApiKeyGuard`. That line is aspirational and is
  corrected by this ADR.

ADR-0020 is not wrong about any of this — it is a *service-to-service* auth policy and
it says so ("legal-search remains single-tenant, single-role"; "Multi-tenant RBAC beyond
this split is still deferred"). Its own Future Work names the gap and names Google
Identity Platform as the likely answer. This ADR takes that Future Work item and decides it.

### Tenancy is declared but not enforced

The scope of this ADR is authentication, authorization, **and tenancy**, so the third one
deserves its own honest baseline.

`tenant_id` and `scope_type` exist as columns on `Corpus`
(`platform_control/models/corpus.py:33-39`, with `scope_type` constrained to
`global_public` / `tenant_private` / `tenant_shared`) and appear across several schemas.
**There is no `tenants` table anywhere** — not in the models, not in any migration. Nothing
resolves a `tenant_id` to an entity, nothing validates one, and no query filters by one:
they are data labels a writer sets and a reader ignores.
`docs/architecture/security-and-tenancy.md` describes them as an enforced boundary
("Must not leak tenant-private configuration across tenants"; "Every search and
document-detail path must apply tenant and corpus filters derived from authenticated
identity"). That enforcement does not exist, and it cannot exist while there is no
authenticated identity to derive it from — which is the dependency this ADR unblocks.

Enforcing tenancy is **not** in this ADR's scope; it is a larger piece of work with its own
data-model questions. What is in scope is not painting ourselves into a corner: the
identity backend chosen in §2 must have a credible organization/tenant concept to map onto
`tenant_id` later, so that the eventual enforcement work is a mapping rather than an
invention. That requirement materially shapes §2's recommendation.

### Why this is in scope for M13, not after it

The strict reading of #628 is that M13 is about the coverage loop, not about auth, and
that user login can wait. The attribution half cannot, and the reason is structural:

**#628's loop is evidence-gated.** Its acceptance criterion is that the corpus be
assembled *through the platform* — "blueprint → source version → acceptance run →
evidence → `enabled: true` → approval." Every one of those arrows except the first is a
human decision that the platform is supposed to record.

**ADR-0035 built the recording surface and it records nobody.** ADR-0035 moved the
config-owner key into `blueprint_template_overrides` with `enabled`, `note`,
`updated_by`, `updated_at` — explicitly "the audit trail: who turned the key, when, and
why" (`platform_control/models/blueprint_template_override.py:26`). The actor threads
through `BlueprintEnablementService.set_enabled(..., actor=...)`
(`services/blueprint_enablement.py:121-148`). But the actor it receives resolves, in
every deployed configuration, to the single string `op_scoped_operator_key`. The column
is real; the value is a constant.

So the loop's terminal step produces a record that says *a key was used*. An approval
nobody can be held to is not evidence — it is a log line. #632 and #634 are about making
the lock **reachable** and **visible**; this ADR is about making the flip **attributable**.
Without it, M13 can demonstrate the mechanics of the loop and still not produce the
artifact the loop exists to produce.

Login on both apps is the larger, later half. Per-person operator identity behind the
existing admin app is the half M13 needs, and it is the half this ADR sequences first.

### The second reason: demo accounts on a live control plane

Both UIs share one BasicAuth password today, so *any* demo viewer has, transitively, the
admin app's server-held operator key. That key can dispatch runs and — after ADR-0035 —
flip the ADR-0030 two-key lock. A demo account that can trip the lock is a live-fire
hazard: it turns a sales demo into an unreviewed production write against a real corpus.

## Decision

### 1. Scope

Real login on **both** applications, plus real per-person operator identity, roles, and
genuine attribution on runs and approvals. This ADR covers the design; implementation is
sequenced in §8 and is deliberately not part of the change that introduces this file.

### 2. Identity backend: self-hosted open source — **Zitadel**

We do not build password storage, reset flows, MFA, or session revocation. We also do not
*rent* them. We run an OIDC provider on the node we already own, and treat it as
replaceable.

**Why not managed SaaS at all.** The first draft of this ADR recommended WorkOS AuthKit
over Google Identity Platform on the grounds that ADR-0029 is in the middle of
`terraform destroy`-ing the GCP runtime, and "do not re-open the door you are closing."
That argument was right and stopped one step short: it generalises past GCP to **managed
identity as a category**. Every other technology in this runtime is self-hosted OSS —
k3s on a dedicated Hetzner box (ADR-0029), MinIO, NATS JetStream, OpenSearch, Postgres
via CloudNativePG, Nessie/Trino (ADR-0036). A managed IdP would be the **sole SaaS
dependency in the runtime path**, and its per-connection enterprise-SSO pricing is
exactly the lock-in shape the rest of the architecture exists to avoid. Self-hosting also
makes the demo-account question free: no per-seat or per-MAU cost for accounts whose
entire purpose is to be handed out (§5).

#### Candidates

| | Zitadel | Keycloak | Authentik | Ory (Kratos+Hydra) | Dex |
|---|---|---|---|---|---|
| Licence / language | Apache 2.0, Go | Apache 2.0, Java/Quarkus | MIT, Python/Django | Apache 2.0, Go | Apache 2.0, Go |
| Datastore | **Postgres** | Postgres (or others) | Postgres + **Redis** | Postgres (×2 services) | Postgres/CRDs |
| Idle RSS, single instance | ~150–300 MB | **~700 MB–1 GB+** (JVM) | ~400–600 MB across web/worker/redis | ~150 MB × 2 services | ~50 MB |
| Multi-tenancy | **Organizations, first-class** — every user belongs to an org, one instance serves many | Realms — strong isolation, but a realm is heavyweight and cross-realm admin is awkward | Tenants exist, less mature | Build it yourself in your own schema | none |
| Protocols | OIDC, OAuth2, SAML, SCIM | OIDC, OAuth2, SAML, SCIM | OIDC, OAuth2, SAML, SCIM | OIDC/OAuth2 (Hydra) | OIDC federation only |
| Login UI | shipped, themeable | shipped, themeable | shipped, good UX | **you build it** | none |
| Local user store | yes | yes | yes | yes (Kratos) | **no — federation only** |
| Ops burden, solo operator | moderate | high (JVM tuning, realm/version migrations) | moderate | high (two services + your own UI) | low but insufficient |
| Maturity / ecosystem | good, growing | **highest** | moderate | good, niche | high but narrow |

**Dex is disqualified outright, not merely ranked last.** It is a federation proxy with
**no local identity store**. It can only delegate to an upstream IdP, so it cannot satisfy
the demo-account requirement — there is nothing to seed a demo `viewer` *into*, and the
whole point of a demo account is that it does not belong to a corporate directory. Any
Dex design implies a second IdP behind it, at which point Dex is an extra hop rather than
the decision. Listed here so it is not proposed again.

**Ory** is the most composable and the most work: Kratos and Hydra are two services and
neither ships a login UI, so a demo timeline would be spent building screens we would
otherwise get for free. Correct choice for a team that wants identity as a library;
wrong choice for a solo operator with a milestone.

**Authentik** is pleasant at small scale and would work, but it adds a **Redis**
dependency this runtime does not otherwise have, runs a heavier Python/Django footprint
than Zitadel's Go binary, and is the least proven of the three viable options in
enterprise settings — which matters because §"what we are optimising for" below is
partly about the first law-firm deal.

**Keycloak is the serious alternative** and the honest runner-up. It is the most mature,
has the widest ecosystem, and nobody was ever fired for choosing it. Two things cost it
the recommendation, both specific to *this* deployment rather than to Keycloak:

1. **Footprint on a single shared node.** The whole runtime — Postgres, OpenSearch, NATS,
   MinIO, Nessie, Trino, both apps, both BFFs, and the CI runners (`infra/hetzner/README.md`
   notes ARC runners share this "near-idle" node) — lives on one dedicated server. A JVM
   idling at ~1 GB is a real fraction of that budget, spent on the least
   differentiated component in the stack.
2. **Upgrade ergonomics for one person.** Keycloak's realm/version migrations are the part
   operators complain about, and there is exactly one operator here.

**Recommendation: Zitadel.** Three reasons, in order of weight:

1. **Multi-tenancy is the shape of the problem, and Zitadel's organizations are the
   closest fit.** `tenant_id` and `scope_type` already exist as *unenforced data labels*
   (`models/corpus.py:33-39`) with **no `tenants` table anywhere** — the tenancy model is
   currently a naming convention. Zitadel's organizations give us an identity-side notion
   of "which org does this human belong to" that platform-control can map onto `tenant_id`
   when it becomes enforced, without inventing a bespoke user↔tenant join first, and
   without Keycloak's per-realm heaviness (a realm per law firm is a lot of realm).
2. **It reuses the datastore we already run.** `infra/hetzner/postgres-cluster.yaml` is a
   CloudNativePG `Cluster`, and it **already hosts a second database for Nessie** —
   the file documents `CREATE DATABASE nessie OWNER platform_control` as the pattern.
   Zitadel gets a `zitadel` database in the same instance by the same precedent: no new
   stateful component, no new backup target, no new failure mode. Authentik would add
   Redis; Keycloak would add a JVM.
3. **Cost per unit of ops.** A single Go binary with a shipped, themeable login UI, OIDC +
   OAuth2 + SAML + SCIM, and a usable admin console is the most capability per megabyte
   and per operator-hour on this list.

**When to revisit.** Choose Keycloak instead if (a) an enterprise customer requires an
identity integration only Keycloak's ecosystem has, or (b) the node grows enough that the
JVM footprint stops mattering and ecosystem maturity dominates. Reconsider managed SaaS
only if operating the IdP demonstrably costs more attention than it saves — see
§2b, which is the honest bill for this decision.

### 2b. What self-hosting costs us

OSS is not free; it is differently priced. Stated plainly rather than buried:

- **A login outage takes down both apps.** Today there is no login, so there is nothing
  to be down. After this ADR, Zitadel is on the critical path for every human session on
  both `admin.` and `search.`. A managed IdP would have someone else's on-call rota
  behind it; this one has ours.
- **It is now our patch problem.** An IdP is a high-value target and a CVE in it is a
  credential-compromise event, not a degraded feature. Somebody has to actually watch
  releases and apply them — which, on a one-person team, is the commitment most likely to
  quietly lapse. This is the single strongest argument for the managed option, and it is
  the one being knowingly accepted.
- **It is now our backup problem.** The `zitadel` database joins `platform_control` as
  data whose loss is unrecoverable-by-rebuild: losing it means every user, org, and
  credential is gone. It must be in the same backup and *restore-tested* path as
  platform-control's database, not merely in the same Postgres instance. Sharing the
  CNPG cluster helps here — one backup story, not two — but only if that story is
  exercised.
- **Single-node availability is the real ceiling.** One CNPG instance
  (`postgres-cluster.yaml:9` — `instances: 1`) on one dedicated server means the IdP
  inherits exactly the availability of everything else. That is acceptable for the
  current stage and would not be for a paying enterprise tenant; note it before promising
  anyone an SLA.
- **Upgrades can break login specifically.** A bad platform-control deploy degrades a
  feature; a bad IdP deploy locks everyone out of both apps, including the operator who
  needs to fix it. Keep a break-glass path (direct DB/admin access, or the ability to
  re-enable the API key path) documented in the runbook before the first upgrade.

The counterweight: no per-seat cost, no per-connection SSO pricing, no vendor able to
change terms on a product that gates all human access, no third party holding the
credentials of a legal-research corpus, and full control of the demo-account lifecycle.
For a self-hosted-everything runtime with one operator and no external users yet, that
trade is worth taking — but it is a trade, not a free win.

### 3. App-side layer: Auth.js (NextAuth v5) in both Next.js frontends

Both frontends are already Next.js with a `middleware.ts` doing server-side header
injection, which is exactly the shape Auth.js expects. Auth.js gives us the OIDC dance,
an encrypted `httpOnly` session cookie, and `auth()` in server components and middleware.

This layer is **IdP-independent**: Auth.js talks plain OIDC to Zitadel via its generic
OIDC provider, and would talk the same plain OIDC to Keycloak, Authentik, or a managed
vendor. That is what keeps §2 a reversible decision rather than a one-way door — swapping
the IdP is an issuer URL, a client ID, and a re-seed, not a re-platform.

- Session cookie: encrypted JWT (Auth.js default), `httpOnly`, `Secure`, `SameSite=Lax`.
- No session data is trusted from the client. Roles are **not** stored in the session
  cookie as an authorization input (see §4.3).
- `platform-control/admin` additionally implements React-admin's `authProvider` against
  Auth.js, replacing the `localStorage` role read at
  `lib/admin/accessControl.ts:16` — which stays only as a *rendering* hint and is never
  the enforcement point.

### 4. The seam: how a verified user identity reaches the backends

This is the crux of the design, and it is the part most likely to be got wrong.

#### 4.1 The API key does not change roles

`X-API-Key` stays exactly what ADR-0020 made it: **service-to-service auth**. It answers
"is this caller a deployed Evidara component?" It never answers "who is the human?" It is
not removed, not weakened, and not overloaded.

#### 4.2 The BFF additionally forwards a signed user assertion

Alongside `X-API-Key`, the BFF mints a short-lived assertion and sends it as
`X-Evidara-User`:

- **Format:** compact JWS, **EdDSA / Ed25519**. Not HMAC — a shared symmetric secret would
  let any verifier also mint, which defeats the point of having two BFFs.
- **Claims:**

  ```json
  {
    "iss": "bff:platform-control-admin",
    "sub": "zitadel|298734569872345",
    "aud": "platform-control",
    "email": "operator@evidara.example",
    "name": "A. Operator",
    "iat": 1753000000,
    "exp": 1753000060,
    "jti": "01J..."
  }
  ```

- **`exp` is 60 seconds.** The assertion is minted per outbound request, not per session.
- **There is no `roles` claim.** Deliberately — see §4.3.
- **Signing key:** one Ed25519 private key per BFF, in the `evidara-auth` Secret. Each
  backend is configured with the *public* keys of the BFFs allowed to address it, keyed by
  `iss`. Two issuers and two verifiers is small enough that a static public-key map beats
  running a JWKS endpoint; revisit if the mesh grows.

**Backend verification (`platform-control`), in order, all mandatory:**

1. `X-API-Key` passes the existing ADR-0020 guard. Unchanged, still first.
2. `X-Evidara-User` present → parse as JWS. **Absent → the request is service-scoped, and
   no user principal exists.** An absent assertion must never be treated as "trusted
   local caller".
3. Signature verifies against the public key registered for the token's `iss`. Unknown
   `iss` → 401.
4. `aud` equals this service's own identifier → else 401. (Stops an assertion minted for
   legal-search being replayed at platform-control.)
5. `exp` in the future, `iat` not more than 60s in the past, ±30s clock skew → else 401.
6. `sub` resolves to an **enabled** `operators` row → else 403. This replaces
   `_resolve_auth_principal`'s key-slot lookup (`auth.py:176-188`) for user-bearing
   requests; the key-slot path remains for service-only callers.
7. The resulting `Principal` carries `operator_id`, `auth_principal` (`oidc:<iss>:<sub>`),
   `display_name`, **and `role`, read from the database row.**

`legal-search/api` performs steps 2-5 identically and stops there — it has no operator
table and needs identity only for logging and for tenant/corpus scoping later.

#### 4.3 Roles are looked up server-side, never carried in the assertion

The assertion asserts **identity only**. Authorization is a database read in
platform-control against the `operators` row for that `sub`.

This is not incidental — it is what bounds the blast radius of §4.4. A compromised BFF can
mint an assertion for any `sub` and impersonate a user. It **cannot invent a role**,
because the role is not in the token it signs. Promotion to `operator` or `admin` requires
a write to platform-control's database by an existing `admin`, through an audited route.

#### 4.4 Honest limits of a BFF-signed header

A BFF-signed header is only as trustworthy as the network path and the BFF itself. Stated
plainly, because this is the part that gets glossed:

- **The signature proves the BFF minted it. It does not prove the user consented to this
  particular request.** There is no proof-of-possession binding the assertion to the
  browser session. A compromised or buggy BFF can mint an assertion for any user at any
  time. We accept this: the BFF already holds the operator API key, so a compromised BFF
  is already a full control-plane compromise. The assertion does not widen that blast
  radius — but neither does it narrow it, and it must not be described as if it does.
- **`X-Evidara-User` must be stripped at the ingress for every inbound request.** A Traefik
  middleware must delete the header on requests entering the cluster, so an external
  caller who somehow obtains an API key still cannot inject an identity. Header-stripping
  is defence in depth on top of signature verification, not a substitute for it. Verifying
  the signature is what actually stops forgery; stripping stops the failure mode where
  someone later adds an "unsigned assertions allowed in dev" branch and it reaches prod.
- **There is no mTLS between Traefik and the services today** (ADR-0029's runtime is plain
  cluster networking). Anything with pod-network access and a valid API key can talk to
  platform-control. It still cannot forge an identity without the Ed25519 private key.
  That is the property the signature buys, and it is the only one it buys.
- **Never fall back to trusting an unsigned header.** Under no configuration — including
  local development — may a bare, unsigned `X-Evidara-User` be honoured. The local-dev
  path uses a *locally signed* assertion with a dev keypair, or no assertion at all.

#### 4.5 Alternative considered: forward the IdP's own ID token

Cleanest on paper: pass the OIDC ID token through, have backends verify it against the
IdP's JWKS. It removes the "BFF can mint anything" property entirely.

Rejected for now, on three grounds: Auth.js does not silently refresh ID tokens, so a
session outliving the token's ~1h lifetime would start failing mid-work unless we build
refresh handling; the ID token's audience is the frontend client, not the backends, so
using it as a backend credential is an audience confusion we would have to paper over;
and it couples every backend to IdP-specific JWKS rotation and availability. **This is the
right end state** and the assertion format above is deliberately shaped like an ID token
so the swap is mechanical. Revisit once sessions and refresh are proven in production.

### 5. Roles: `viewer` / `operator` / `admin`

| Role | May |
|---|---|
| `viewer` | Read everything it is scoped to. **No state-changing request, ever.** |
| `operator` | Everything `viewer` may, plus: create sources and versions, dispatch runs, record review decisions, flip ADR-0030/ADR-0035 blueprint enablement, approve source versions. |
| `admin` | Everything `operator` may, plus: manage operators and roles, rotate keys, edit reference data. |

Enforcement is a FastAPI dependency in platform-control —
`require_role(Role.OPERATOR)` composed onto the routers that already carry
`Depends(require_control_plane_operator)` in `main.py:116-128`. It is **server-side and
route-level**. The admin UI's role check remains a rendering hint only.

**Demo accounts are `viewer`, hard-scoped read-only.** Two independent mechanisms, because
one is not enough for something that will be handed to strangers:

1. The role itself grants no write capability.
2. A separate `is_demo` flag on the operator row causes **any non-idempotent HTTP method
   (POST/PUT/PATCH/DELETE) to be rejected with 403 before routing**, regardless of what
   the role says. This survives a future role-table bug or a mis-click promoting a demo
   account.

The property this protects is specific: a demo account must not be able to dispatch a run
or flip the ADR-0030/ADR-0035 two-key lock. Those are the two actions that turn a demo
into a real, unreviewed write against the corpus.

**Self-hosting makes this cheap, which is a genuine point in its favour (§2).** Demo
accounts cost nothing per seat and nothing per MAU, so there is no commercial pressure to
share one demo login among many prospects — which is precisely the shared-credential
anti-pattern this ADR exists to end, and which a per-seat price list would quietly
reintroduce. Each demo gets its own identity, in its own Zitadel organization, disposable
on a schedule.

**Seeding.** Demo accounts are created in a dedicated `demo` organization via Zitadel's
management API from a script, with `is_demo = true` set on the corresponding
platform-control operator row at JIT-provision time (§6.4) based on that organization.
The org boundary is what makes "delete every demo account" a one-liner rather than an
audit.

### 6. Migration from the three key-shaped `Operator` rows

The three seeded rows (`20260426_0016_operators.py:52-79`) are referenced by existing
audit data — `blueprint_template_overrides.updated_by` and corrections'
`operator_id`. The migration must not orphan them.

1. **Keep all three rows. Do not delete, do not renumber.** Foreign audit references keep
   resolving.
2. **Add `kind` (`service_key` | `person`)** and mark the three existing rows
   `service_key`. Add `subject`, `email`, `role`, `is_demo`, and `idp_org_id` — the
   Zitadel organization the person belongs to, recorded but **not yet enforced**, so that
   the eventual tenancy work has the mapping it needs without a backfill (see Context).
   `auth_principal` remains the unique key; for people it becomes `oidc:<iss>:<sub>`.
3. **Relabel, don't rewrite.** `op_scoped_operator_key`'s `display_name` becomes
   *"Shared operator key (pre-identity)"* so the admin UI stops rendering a key as if it
   were a person. The identifier is untouched.
4. **Per-person rows are created just-in-time on first successful login**, with
   `role = viewer` always — never `operator`, never inherited from the key. `is_demo` is
   set from the IdP organization (the `demo` org, §5); `idp_org_id` is recorded. An
   existing `admin` promotes. The first `admin` is seeded out-of-band by whoever runs the
   deployment, exactly once.
5. **Once at least one person holds `admin`, set `disabled_at` on the three
   `service_key` rows** so they cannot back new writes. `get_current_principal` already
   filters on `disabled_at IS NULL` (`auth.py:207-210`), so this is a data change, not a
   code change. Historical rows still resolve for display because display lookups do not
   filter on `disabled_at`.
6. **Do not backfill.** Old `updated_by = 'op_scoped_operator_key'` values stay as they
   are. Reattributing them to a person would be fabricating evidence, which is precisely
   the failure this ADR exists to end. "We do not know who did this" is the correct,
   honest value for every write made before per-person identity existed.

This needs one Alembic migration. It is specified here and deliberately not written in the
change that adds this ADR.

### 7. Documentation corrections

- `docs/architecture/security-and-tenancy.md:30` claims JWT verification keys are
  configured for the BFF. **No JWT verification exists in `legal-search/api` today.** The
  line is corrected to name it as aspirational and point here.
- ADR-0020 has no `Status` header at all, unlike its peers. It gets one, and a pointer to
  this ADR. Its service-to-service content stands; this ADR extends rather than deletes it.

### 8. Sequencing

Ordered by what M13 actually needs, not by what is most visible:

1. **Fail-closed auth + real `reviewed_by` derivation.** Independent of this design; can
   and should land immediately. *(Separate change; see the companion PR.)*
2. **Stand up Zitadel** on the k3s node: a `zitadel` database in the existing CNPG
   cluster (the Nessie precedent in `postgres-cluster.yaml`), an Ingress under the
   existing cert-manager issuer, backups joined to the platform-control database's
   path and *restore-tested once* before anything depends on it (§2b), and a documented
   break-glass procedure. Nothing else in this list can start until this is boring.
3. **Operator table extension + per-person schema** (§6 steps 1-3).
4. **The assertion seam** (§4) — mint in both BFFs, verify in both backends, strip at
   ingress. Roles read from the DB.
5. **Auth.js login on `platform-control/admin`** (§3) — this is where attribution starts
   producing real values.
6. **Role enforcement + demo hard-scoping** (§5).
7. **Auth.js login on `legal-search/frontend`**, retire the shared BasicAuth front door.
8. **ID-token pass-through** (§4.5) when sessions are proven.

Steps 2-5 are what makes an ADR-0035 approval attributable. That is the M13-relevant
subset. Step 1 is independent of all of it and should not wait.

## Consequences

### Positive

- An approval in the coverage loop names a person. #628's evidence gate produces evidence.
- The shared BasicAuth password stops being the only thing between the internet and a
  control plane that can dispatch runs.
- Demo accounts become safe to hand out.
- ADR-0020's Future Work items (RBAC, OIDC) are closed rather than perpetually deferred.
- The runtime stays entirely self-hosted OSS (ADR-0029, ADR-0036). No vendor sits on the
  path between a user and a legal corpus, and no per-seat price list shapes how we hand
  out demo accounts.
- Zitadel organizations give the currently-unenforced `tenant_id` / `scope_type` labels
  (`models/corpus.py:33-39`) an identity-side counterpart to be mapped onto when tenancy
  becomes enforced, rather than requiring a bespoke user↔tenant model invented first.

### Negative / accepted

- **We now operate an IdP.** Its uptime, patching, and backups are ours, and a login
  outage takes down both apps. §2b is the full bill; it is accepted deliberately, not
  overlooked. Mitigated only by the fact that Auth.js sessions outlive brief outages —
  an existing session survives a Zitadel restart; a new login does not.
- The BFF becomes a signing authority (§4.4). Its compromise is a user-impersonation
  compromise — bounded, but real, and worse than today only in that it is now *possible to
  impersonate a specific named person* rather than merely act as the key.
- More moving parts in local development. The dev path must be explicit and must not be
  an "if unset, trust everything" branch — that is the exact class of bug the companion
  hardening change fixes.
- One Alembic migration and a role check on every write route.

### Neutral

- `X-API-Key` and ADR-0020's scoped-key model are unchanged. This is additive.
