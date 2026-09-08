"""OpenAPI document metadata and the operation-id policy for platform-control.

``contracts/api/platform-control.openapi.yaml`` is **generated from this app** by
``scripts/generate_platform_control_contract.py`` and gated for drift by
``scripts/check-platform-control.sh``. It used to be hand-maintained, and it
described less than the code did: 4 of 11 acquisition provider variants, no
``execution_mode``, list responses without their ``{data, limit, offset, total}``
envelope, and an ``Authorization: Bearer <JWT>`` security scheme this service has
never implemented. Consumers that believed it shipped bugs (#614, #616); #617
could not derive the admin provider list from it precisely because it lied. See
#618.

Everything an OpenAPI document needs that the routes and Pydantic models cannot
supply themselves lives here, so that ``/openapi.json`` and the committed
contract are the same document. There is deliberately **no overlay applied at
generation time**: an overlay is a second source of truth, and a second source of
truth is where drift lives.

Two things are consciously *not* declared here:

``servers``
    The base URL is per-deployment (Cloud Run URLs in ``infra/env/*``, a
    ``REPLACE_ME`` ingress host in ``k8s/gitops/``), and the app cannot know it.
    Declaring one would also aim Swagger UI's "Try it out" at that URL on every
    deployment. With no ``servers``, both the docs UI and generated clients
    resolve against wherever the document was served, which is the truth.

``bearerAuth``
    Not a loss — a correction. Auth is the ``X-API-Key`` header
    (:mod:`platform_control.auth`), which FastAPI emits as the ``APIKeyHeader``
    scheme from the route dependencies.
"""

from __future__ import annotations

from typing import Any

from fastapi.routing import APIRoute

API_TITLE = "Platform Control API"

# Must equal `apis.platform_control.version` in contracts/manifest.yaml —
# scripts/check_contract_manifest.py compares the manifest against the generated
# contract's info.version, and the drift gate compares the contract against this
# app. Bump both together, per contracts/manifest.yaml compatibility_policy
# (additive -> minor, breaking -> major).
# 0.9.0: additive — new blueprint-template enablement endpoint + `enabled`/
# `live_ready`/`launchable`/`notes` on blueprint responses (#632, #634).
# 0.10.0: additive — routes now declare the 4xx/5xx their exception handlers
# really return, with the shared `ErrorResponse` body (#627).
# 0.11.0: additive — `refused` on run responses + `?refused=` filter on the run
# collection, and `plan_notes` on blueprint-preview (#634).
# 0.13.0: additive — blueprint coverage inventory fields on source responses,
# so the admin can show which blueprints are enabled and which are not (#668).
# 0.15.0: additive — `acquisition_readiness` on blueprint responses and a new
# `acceptance` RunMode. The ADR-0030 code key became three-state so a provider
# that is built but has no acceptance evidence is no longer reported as a
# scaffold needing engineering (#743), and so it can run the acceptance loop
# that produces its own evidence (#735). `live_ready` is retained as the boolean
# projection (true only for `live`), so this is additive, not breaking.
# 0.16.0: additive — pagination on the reference-data collections. Jurisdictions
# and authorities now accept `limit`/`offset` and return a real `total`, so the
# admin can page 2,169 jurisdictions instead of receiving them all in one array
# and windowing client-side (#616).
# 0.17.0: additive — `blueprint_overrides` on the source-create, version-create
# and blueprint-preview requests. A source version may now carry the template's
# spec with operator-chosen seeds, fenced to the template's own origins, instead
# of forcing a hand-written `acquisition_spec` that loses the ADR-0030 config key
# (#710, ADR-0046).
# 0.20.0: additive -- `GET /v1/acquisition-coverage`, the platform-control half of
# the ADR-0042 SS4 split: expected -> discovered -> acquired -> processed per
# jurisdiction, with a denominator tier. Deliberately carries no percentage or
# completeness score (ADR-0042 rejected those outright), and names `indexed` as
# unmeasured because it lives in legal-search's index (#816).
# 0.21.0: additive — `published_artifacts_count` and `publication_withheld` on the
# run detail and run list responses. A FAILED dispatch no longer publishes what it
# captured (#853), so captured and published are now different numbers and the read
# model must carry both: rendering `artifacts_count` alone would claim a delivery
# that did not happen, and rendering `0` would hide the capture. Touches the locked
# `/v1/runs` and `/v1/runs/{run_id}` paths, but only by adding response fields.
# 0.22.0: additive — `quarantined` joins the document processing-status enum on
# `/v1/runs/{run_id}/processing-status`. ADR-0047 gives DI a verdict between
# processed and failed for a manifestation whose text is not law; without the
# value the endpoint rejected the very status it must record, and the run read
# as still-in-flight forever (#731). Additive: an existing writer never sends it.
# 0.23.0: additive — the wizard human gate's terminal states. An expired gate now
# resolves to a recorded outcome instead of hanging with no timeout, no
# notification and no way to end (#560), so the gate decision is readable as a
# claim rather than inferred from a run that never moves.
# 0.24.0: additive -- the ADR-0030 config-key flip guard moved server-side (#854).
# `PUT /v1/sources/blueprint-templates/{overlay}/{template}/enablement` now accepts
# `evidence_run_id` and the two ADR-0030 acknowledgements, answers 409 with
# machine-readable `refusals[].code` when it will not move the key, and reports
# `applied` / `needs_human` / `evidence_binding` on success. Additive on the wire, but
# a caller that sent `{enabled, note}` alone can no longer arm a key — which is the
# point: the admin panel was the soft path around the guard the CLI enforced.
# 0.30.0: BREAKING for anyone who called it -- `POST /webhooks/slack/interactions`
# and the `slack` tag are removed (#852). The route was mounted unauthenticated and
# was never signature-verified: it read `workflow_id` out of the request body and
# signalled approve/reject to it, bypassing `WizardService` and its state guards.
# Nothing in this service ever posted the Slack buttons it claimed to receive -- the
# only sender in the repo is `infra/coordinator`, which owns the Slack signing secret
# and receives its own buttons at its own verified endpoint. Minor rather than major
# because the endpoint had no caller and, with `wizard_orchestrator_backend` at
# `in_memory` everywhere (ADR-0031), no effect. The gate's real path is unchanged:
# `POST /v1/wizard/runs/{run_id}/approve` and `.../reject`.
API_VERSION = "0.30.0"

API_DESCRIPTION = """\
API for managing sources, source versions, runs, approvals, and provider webhooks
in the Evidara platform control plane.

This document is generated from the FastAPI application — it is exactly what the
service serves at `/openapi.json`. Do not hand-edit `contracts/api/platform-control.openapi.yaml`;
change the models or routes and run `scripts/generate_platform_control_contract.py`.
"""

API_CONTACT: dict[str, Any] = {"name": "Evidara Team"}

# Tag order drives the render order in Swagger UI and Redoc. Descriptions are
# part of the contract: they carry semantics the schemas cannot.
OPENAPI_TAGS: list[dict[str, Any]] = [
    {"name": "reference-data"},
    {
        "name": "acquisition-coverage",
        "description": (
            "What were we asked to acquire, and did it succeed? Per jurisdiction:\n"
            "``expected -> discovered -> acquired -> processed``, with a\n"
            "``denominator_tier`` recording how trustworthy ``expected`` is.\n\n"
            "This is the platform-control half of the ADR-0042 SS4 split. The other\n"
            "half -- *what does the corpus hold?* -- is legal-search ``GET /v1/coverage``,\n"
            "and the ``indexed`` stage is reported there rather than here, because this\n"
            "service has no dependency on the search index.\n\n"
            "Carries no percentage, ratio or completeness score by design.\n"
        ),
    },
    {"name": "sources"},
    {"name": "source-versions"},
    {"name": "runs"},
    {"name": "schedules"},
    {"name": "wizard"},
    {"name": "reviews"},
    {
        "name": "corpora",
        "description": (
            "First-class corpus and tenant/scope management.  A corpus groups source versions\n"
            "under a shared ``tenant_id`` and ``scope_type`` identity.  Operators create corpora\n"
            "here and reference them by ``corpus_id`` in acquisition configs.\n"
        ),
    },
    {"name": "compliance-policies"},
    {"name": "di-events"},
    {"name": "firecrawl"},
    {
        "name": "corrections",
        "description": (
            "Human-in-the-loop corrections raised against upstream domain entities (source,\n"
            "canonical document, commentary insight). Corrections are the durable audit trail\n"
            "for HITL field edits, annotations, rejections, and rescore requests.\n"
        ),
    },
    {
        "name": "commentary-insights",
        "description": (
            "Operator-facing read surface for commentary insights. Reads are\n"
            "backed by the `commentary_insights` overlay populated by\n"
            "document-intelligence runs and amended by applied corrections;\n"
            "writes flow through `POST /v1/corrections` (no PATCH on\n"
            "commentary-insights — see PR #440 design).\n"
        ),
    },
    {"name": "health"},
    {
        "name": "agent-discovery",
        "description": (
            "Read-only operations commonly used by operators and agents for discovery and "
            "evidence\n"
            "(`evidara openapi tags`, MVP acceptance, smoke matrices). Does not imply mutating "
            "workflow APIs.\n"
        ),
    },
]

# ADR-0022: read-heavy operations carry `agent-discovery` as a secondary tag so
# agents can filter the discovery surface without new endpoints. Apply it in the
# route decorators (`tags=[..., AGENT_DISCOVERY_TAG]`) — a tag that exists only
# in the contract is exactly the drift this module exists to end.
AGENT_DISCOVERY_TAG = "agent-discovery"


def generate_operation_id(route: APIRoute) -> str:
    """Derive a stable camelCase ``operationId`` from the endpoint function name.

    FastAPI's default appends the path and method (``get_run_v1_runs__run_id__get``),
    which is unique but hostile to generated clients. The endpoint function name
    is already the operation's name, so ``get_run`` -> ``getRun``.

    This means **the function name is API surface**: renaming an endpoint function
    renames its ``operationId``, and two endpoint functions may not share a name.
    ``tests/unit/test_openapi_contract.py`` enforces both.
    """
    head, *rest = route.name.split("_")
    return head + "".join(word.capitalize() for word in rest)
