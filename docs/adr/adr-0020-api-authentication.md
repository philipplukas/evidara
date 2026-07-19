# ADR-0020: API Authentication & Authorization Policy

Status: Accepted — service-to-service scope only. Extended by
[ADR-0038](0038-user-identity-and-operator-attribution.md) (Proposed), which decides the
"RBAC" and "OAuth2 / OIDC" items in this ADR's Future Work and adds per-person operator
identity. The API-key model below is retained unchanged by ADR-0038.

> Security Architecture — Trust Boundaries & Access Control

## Overview

All Evidara HTTP surfaces enforce API-key authentication. Health/liveness
endpoints are explicitly excluded so Cloud Run and load balancers can probe
without credentials.

## Trust Model

```
┌─────────────────────────────────────────────────────────┐
│  Trusted Zone (GCP VPC)                                 │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ platform-    │  │ legal-search │  │ document-    │  │
│  │ control API  │  │ API (BFF)    │  │ intelligence │  │
│  │              │  │              │  │ consumer     │  │
│  │ X-API-Key    │  │ X-API-Key    │  │ (no HTTP)    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         ▲                 ▲                              │
│         │                 │                              │
│    Cloud Run              │  Cloud Run                   │
│    Invoker IAM            │  Invoker IAM                 │
│         │                 │                              │
└─────────┼─────────────────┼──────────────────────────────┘
          │                 │
    ┌──────────────┐    ┌──────────────┐
    │ React-admin  │    │  Frontend    │
    │    (ops)     │    │  (Next.js)   │
    └──────────────┘    └──────────────┘
```

## Authentication Mechanisms

### API Key (X-API-Key header)

| Service | Config Var | Guard |
|---------|-----------|-------|
| platform-control | `PLATFORM_CONTROL_API_KEY` (optional legacy full-access), `PLATFORM_CONTROL_OPERATOR_API_KEY`, `PLATFORM_CONTROL_SERVICE_API_KEY` | `auth.require_control_plane_operator` / `auth.require_control_plane_service` (FastAPI `Depends`) |
| legal-search API | `API_KEY` | `ApiKeyGuard` (NestJS global APP_GUARD) |
| both (dev only) | `PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED` / `AUTH_DEV_ALLOW_UNAUTHENTICATED` | Explicit opt-in to the keyless local path; without it a keyless process serves 503s |

**Behavior (platform-control):**

- When **no** platform-control API key env vars are **set**: every protected route
  **fails closed with 503** and the app logs a `CRITICAL` line at startup. This was
  previously "authentication is disabled (local development default)" — a fail-**open**
  default, which meant a deployment whose key Secret failed to mount served the entire
  control plane unauthenticated and looked exactly like a working one.
  The keyless local-development path is preserved but must be opted into by name:
  `PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED=1`. The flag is ignored once any key
  is configured, so it cannot be used as a backdoor. `legal-search` behaves the same way
  via `AUTH_DEV_ALLOW_UNAUTHENTICATED`. Health endpoints stay unauthenticated either way,
  so an unconfigured pod remains diagnosable.
- **Legacy:** only `PLATFORM_CONTROL_API_KEY` is set — same as before: every
  protected route requires that key (401 if missing/invalid).
- **Scoped:** `PLATFORM_CONTROL_OPERATOR_API_KEY` and/or
  `PLATFORM_CONTROL_SERVICE_API_KEY` is set — operator (admin / control-plane)
  routes require an operator-capable key; pipeline ingest routes (`/v1/di/events/*`,
  `POST /v1/firecrawl/webhooks`) accept the service key, operator key, or legacy
  `PLATFORM_CONTROL_API_KEY`. A valid **service-only** key on an operator route
  receives **403 Forbidden**.
- Key comparison uses **timing-safe** algorithms (`hmac.compare_digest` /
  `crypto.timingSafeEqual`) to prevent side-channel attacks.

### Cloud Run IAM (infrastructure layer)

In production, Cloud Run services are deployed with `--no-allow-unauthenticated`.
Only principals with the **Cloud Run Invoker** role can reach the HTTP endpoint.
This provides a second trust boundary independent of the API key.

## Authorization Model

**legal-search** remains **single-tenant, single-role** for its API key.

**platform-control** supports a coarse **operator vs service** split when scoped
keys are configured (see table above). Multi-tenant RBAC beyond this split is
still deferred.

## Excluded Endpoints (Public)

| Service | Path | Reason |
|---------|------|--------|
| platform-control | `GET /health`, `GET /ready` | Cloud Run liveness/readiness probes |
| legal-search API | `GET /health`, `GET /health/ready` | Cloud Run liveness/readiness probes |

## Webhook Authentication

| Endpoint | Method |
|----------|--------|
| `POST /v1/firecrawl/webhooks` | HMAC signature verification (`firecrawl_webhook_secret`) when configured; `X-API-Key` still enforced when platform-control keys are set (service-scope) |

## Threat Assumptions

1. **Network**: GCP VPC + Cloud Run IAM prevents external access. API keys
   protect against compromised internal callers.
2. **Key rotation**: Set new `PLATFORM_CONTROL_*` / `API_KEY` values and
   redeploy. No session invalidation needed (stateless).
3. **Secrets storage**: on the live Hetzner runtime (ADR-0029) the keys live in the
   `evidara-auth` Kubernetes Secret, created by `infra/hetzner/deploy-stage5.sh` and
   consumed as a **required** secret ref — a pod without it refuses to start. The GCP
   Secret Manager / Cloud Run path described here belongs to the retired stack. Never
   committed to source control.
4. **Logging**: Auth failures are logged at WARN level. API keys are NOT logged.

## Future Work

- ~~**RBAC**: Finer roles (viewer vs editor) beyond operator vs service.~~ — decided by
  ADR-0038 (`viewer` / `operator` / `admin`).
- ~~**OAuth2 / OIDC**: Integrate Google Identity Platform if frontend users need
  per-identity authentication.~~ — decided by ADR-0038, which recommends **WorkOS
  AuthKit** rather than Google Identity Platform, because ADR-0029 retires the GCP
  runtime this suggestion assumed.
- **Mutual TLS**: Consider mTLS for service-to-service communication if
  the mesh grows beyond 3 services.
