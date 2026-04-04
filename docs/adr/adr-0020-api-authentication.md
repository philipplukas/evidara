# Security Architecture — Trust Boundaries & Access Control

> ADR-0020: API Authentication & Authorization Policy

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
    ┌─────┴─────┐    ┌──────┴─────┐
    │  Retool   │    │  Frontend  │
    │  (ops)    │    │  (Next.js) │
    └───────────┘    └────────────┘
```

## Authentication Mechanisms

### API Key (X-API-Key header)

| Service | Config Var | Guard |
|---------|-----------|-------|
| platform-control | `PLATFORM_CONTROL_API_KEY` | `auth.require_api_key` (FastAPI Depends) |
| legal-search API | `API_KEY` | `ApiKeyGuard` (NestJS global APP_GUARD) |

**Behavior:**

- When the env var is **set**: All non-health endpoints reject requests
  without a valid `X-API-Key` header (401 Unauthorized).
- When the env var is **unset**: Authentication is disabled (development mode).
- Key comparison uses **timing-safe** algorithms (`hmac.compare_digest` /
  `crypto.timingSafeEqual`) to prevent side-channel attacks.

### Cloud Run IAM (infrastructure layer)

In production, Cloud Run services are deployed with `--no-allow-unauthenticated`.
Only principals with the **Cloud Run Invoker** role can reach the HTTP endpoint.
This provides a second trust boundary independent of the API key.

## Authorization Model

Current model is **single-tenant, single-role**: any valid API key grants full
access to all endpoints on that service. Role-based access control (RBAC) is
deferred until multi-tenant requirements materialize.

## Excluded Endpoints (Public)

| Service | Path | Reason |
|---------|------|--------|
| platform-control | `GET /health`, `GET /health/ready` | Cloud Run liveness/readiness probes |
| legal-search API | `GET /health`, `GET /health/ready` | Cloud Run liveness/readiness probes |

## Webhook Authentication

| Endpoint | Method |
|----------|--------|
| `POST /v1/firecrawl/webhook` | HMAC signature verification (`firecrawl_webhook_secret`) |

## Threat Assumptions

1. **Network**: GCP VPC + Cloud Run IAM prevents external access. API keys
   protect against compromised internal callers.
2. **Key rotation**: Set a new `PLATFORM_CONTROL_API_KEY` / `API_KEY` value and
   redeploy. No session invalidation needed (stateless).
3. **Secrets storage**: API keys stored in Google Secret Manager, mounted as
   Cloud Run env vars. Never committed to source control.
4. **Logging**: Auth failures are logged at WARN level. API keys are NOT logged.

## Future Work

- **RBAC**: Add role claims when multi-tenant or operator-vs-viewer
  distinction is needed.
- **OAuth2 / OIDC**: Integrate Google Identity Platform if frontend users need
  per-identity authentication.
- **Mutual TLS**: Consider mTLS for service-to-service communication if
  the mesh grows beyond 3 services.
