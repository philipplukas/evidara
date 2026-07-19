# ADR-0038: User identity, roles, and genuine operator attribution

Status: Proposed
Date: 2026-07-19
Deciders: Platform / Security
Supersedes: ADR-0020 (API authentication — extended, not replaced; its service-to-service
API-key layer is retained verbatim)
Related: ADR-0029 (self-hosted Hetzner runtime), ADR-0030 (acquisition provider enablement
lifecycle — the two-key lock), ADR-0033 (agentic legal reasoning — the coverage loop),
ADR-0034 (generated platform-control contract), ADR-0035 (operator-reachable blueprint
enablement), #628 (M13), #632, #634

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

### 2. Identity backend: managed OIDC — **WorkOS AuthKit**

We do not build password storage, reset flows, MFA, or session revocation. We buy an
OIDC provider and treat it as replaceable.

| | Google Identity Platform | WorkOS AuthKit |
|---|---|---|
| Protocol | OIDC (+ Firebase-flavoured SDKs) | OIDC, standards-first |
| Cost at our scale (<20 humans + demo accounts) | $0 (free MAU tier) | $0 (free MAU tier) |
| Cost at 10k MAU | low single-digit $/1k MAU beyond the free tier | free MAU tier is generous; enterprise SSO/SCIM is priced **per connection**, which is the real cost driver |
| Enterprise SSO (SAML) / SCIM directory sync | build it or bolt on | first-class, the product's core |
| Runtime coupling | **requires a GCP project and billing account** | none — HTTPS to a third party |
| Lock-in | moderate; Firebase-flavoured client SDKs pull you off plain OIDC | low; plain OIDC in, plain OIDC out |

*(Pricing tiers move. Both vendors' current published rates must be re-checked before the
implementation PR; the ranking below does not depend on the exact numbers, because at
Evidara's headcount both are free.)*

**Recommendation: WorkOS AuthKit.** Three reasons, in order of weight:

1. **ADR-0029 just spent a milestone removing GCP.** It retires Cloud Run, Cloud SQL and
   the rest for self-hosted Hetzner k3s, and its wind-down plan ends in
   `terraform destroy` of the GCP runtime stack. Adopting Google Identity Platform
   re-introduces a live GCP project, billing account, and IAM surface that we are in the
   middle of destroying. That is not a cost argument — it is a "do not re-open the door
   you are closing" argument, and it is why ADR-0020's Future Work suggestion should not
   simply be inherited: it was written when GCP was the runtime.
2. **Evidara sells to law firms.** SAML SSO and SCIM deprovisioning are table stakes in
   that segment and are the exact thing WorkOS exists to sell. Choosing it now avoids a
   re-platform at the first enterprise deal.
3. **Lower lock-in in practice.** Both are OIDC on paper; only one is OIDC in its
   idiomatic client path. Because the app-side layer is Auth.js (§3), the IdP is a
   provider-config swap.

**Cost and lock-in noted honestly:** WorkOS's per-connection enterprise SSO pricing is
materially more expensive than Google's per-MAU pricing *if* we ever end up with many
small tenants each wanting their own SSO connection. That is the scenario in which this
decision should be revisited. Google Identity Platform remains the correct fallback and
should be reconsidered if (a) GCP re-enters the runtime for other reasons, or (b) the
product turns out to be B2C-shaped with a large low-value MAU tail.

### 3. App-side layer: Auth.js (NextAuth v5) in both Next.js frontends

Both frontends are already Next.js with a `middleware.ts` doing server-side header
injection, which is exactly the shape Auth.js expects. Auth.js gives us the OIDC dance,
an encrypted `httpOnly` session cookie, and `auth()` in server components and middleware.

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
    "sub": "workos|user_01J...",
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

### 6. Migration from the three key-shaped `Operator` rows

The three seeded rows (`20260426_0016_operators.py:52-79`) are referenced by existing
audit data — `blueprint_template_overrides.updated_by` and corrections'
`operator_id`. The migration must not orphan them.

1. **Keep all three rows. Do not delete, do not renumber.** Foreign audit references keep
   resolving.
2. **Add `kind` (`service_key` | `person`)** and mark the three existing rows
   `service_key`. Add `subject`, `email`, `role`, `is_demo`.
   `auth_principal` remains the unique key; for people it becomes `oidc:<iss>:<sub>`.
3. **Relabel, don't rewrite.** `op_scoped_operator_key`'s `display_name` becomes
   *"Shared operator key (pre-identity)"* so the admin UI stops rendering a key as if it
   were a person. The identifier is untouched.
4. **Per-person rows are created just-in-time on first successful login**, with
   `role = viewer` always — never `operator`, never inherited from the key. An existing
   `admin` promotes. The first `admin` is seeded out-of-band by whoever runs the
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
2. **Operator table extension + per-person schema** (§6 steps 1-3).
3. **The assertion seam** (§4) — mint in both BFFs, verify in both backends, strip at
   ingress. Roles read from the DB.
4. **Auth.js login on `platform-control/admin`** (§3) — this is where attribution starts
   producing real values.
5. **Role enforcement + demo hard-scoping** (§5).
6. **Auth.js login on `legal-search/frontend`**, retire the shared BasicAuth front door.
7. **ID-token pass-through** (§4.5) when sessions are proven.

Steps 2-4 are what makes an ADR-0035 approval attributable. That is the M13-relevant
subset.

## Consequences

### Positive

- An approval in the coverage loop names a person. #628's evidence gate produces evidence.
- The shared BasicAuth password stops being the only thing between the internet and a
  control plane that can dispatch runs.
- Demo accounts become safe to hand out.
- ADR-0020's Future Work items (RBAC, OIDC) are closed rather than perpetually deferred.

### Negative / accepted

- A third-party dependency on the login path. If WorkOS is down, nobody logs in. Mitigated
  only by the fact that sessions outlive brief outages.
- The BFF becomes a signing authority (§4.4). Its compromise is a user-impersonation
  compromise — bounded, but real, and worse than today only in that it is now *possible to
  impersonate a specific named person* rather than merely act as the key.
- More moving parts in local development. The dev path must be explicit and must not be
  an "if unset, trust everything" branch — that is the exact class of bug the companion
  hardening change fixes.
- One Alembic migration and a role check on every write route.

### Neutral

- `X-API-Key` and ADR-0020's scoped-key model are unchanged. This is additive.
