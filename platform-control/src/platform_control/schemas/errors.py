"""The error body every platform-control failure returns, and how routes declare it.

`platform_control.main` maps the domain errors onto status codes in one place
(`NotFoundError` -> 404, `ConflictError`/`InvalidStateTransitionError` -> 409,
`SignatureVerificationError` -> 401, `WebhookRetryableError` -> 503, every other
`PlatformControlError` -> 400) and renders all of them through one payload
builder. :class:`ErrorResponse` *is* that payload — `_error_payload` constructs
it — so the contract cannot describe an error shape the service does not send.

The routes still have to say which of those they can produce: the contract is
generated from the app (#618, ADR-0034) and an export cannot invent a response
the route never declared. That is what #627 fixed, via :func:`error_responses`.

Declare only what the route can *actually* raise. Blanket-applying `404` at the
router level would document a 404 on `GET /v1/sources`, which cannot 404 — a
response that cannot happen is the same class of lie #618 exists to end.
Under-documenting is safe; over-documenting is not.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Uniform error body. `correlation_id` echoes `X-Correlation-Id` when present."""

    detail: str = Field(description="Human-readable explanation of the failure.")
    correlation_id: str | None = Field(
        default=None,
        description="Correlation id for the request, echoed as the X-Correlation-Id header.",
    )


#: What each declared status code means for *this* service. Keyed by the status
#: code so a route says `error_responses(404, 409)` and gets consistent prose.
ERROR_DESCRIPTIONS: dict[int, str] = {
    400: "A domain rule rejected the request (misconfigured provider, orchestration failure, "
    "or a blueprint template that is not enabled for live acquisition).",
    401: "Webhook signature missing or could not be verified.",
    404: "A referenced entity does not exist.",
    409: "The request conflicts with the current state of the resource.",
    503: "A dependency is unavailable; the caller should retry.",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Build the `responses=` mapping for the error codes a route can produce."""
    return {
        code: {"model": ErrorResponse, "description": ERROR_DESCRIPTIONS[code]}
        for code in status_codes
    }


#: 422 for routes that validate a *raw* body themselves rather than through a
#: typed request model, so FastAPI never documents one for them: the three
#: `/v1/di/events/*` receivers read `Request` (the body may be a Pub/Sub push
#: envelope) and re-raise the pydantic failure as `HTTPException(422, detail=
#: error.errors())`. That body is a list of validation errors, not this module's
#: `{detail: str}` — it is the same shape FastAPI's own validation handler sends,
#: so this points at the component FastAPI already emits instead of adding a
#: near-duplicate schema for it.
VALIDATION_ERROR_RESPONSE: dict[int | str, dict[str, Any]] = {
    422: {
        "description": "The event payload failed schema validation.",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/HTTPValidationError"}}
        },
    }
}
