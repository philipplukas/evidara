from __future__ import annotations


class PlatformControlError(Exception):
    """Base domain error."""


class NotFoundError(PlatformControlError):
    """Requested entity does not exist."""


class ConflictError(PlatformControlError):
    """Resource already exists or conflicts with current state."""


class InvalidStateTransitionError(PlatformControlError):
    """Raised when a state transition is invalid."""


class ProviderConfigurationError(PlatformControlError):
    """Raised when an external provider is not configured correctly."""


class BlueprintTemplateNotEnabledError(PlatformControlError):
    """Raised when a run targets a blueprint template that is not enabled.

    Config-owner key of the two-key lock (ADR-0030): a source version created
    from a `source_blueprints.yaml` template may only launch live runs while
    that template carries `enabled: true`. Absent/false means the operator has
    not accepted it for live acquisition yet (no acceptance-run evidence), so
    the run-launch path refuses to dispatch.
    """


class SignatureVerificationError(PlatformControlError):
    """Raised when a webhook signature cannot be verified."""


class WebhookRetryableError(PlatformControlError):
    """Raised when a webhook was received but could not be applied to any local state.

    The delivery is persisted *unprocessed* (``webhook_receipts.processed_at IS NULL``)
    and the sender is asked to redeliver (non-2xx) rather than being told the event was
    accepted. The invariant this protects: a delivery we did not apply never spends its
    dedupe key. Answering 202 instead would let the identical retry be deduped away, so
    the event would be dropped forever — see #558.
    """


class IntegrationConfigurationError(PlatformControlError):
    """Raised when storage or event integrations are misconfigured."""


class DispatchPublishError(PlatformControlError):
    """Raised when acquisition succeeded but the downstream handoff did not publish.

    The gap this closes (#707): artifacts were fetched and durably stored, the run
    was already committed COMPLETED, and then the publish to the broker failed. The
    exception escaped uncaught, so the caller got a bare HTTP 500 while the run row
    read ``status: completed, failure_reason: null`` over a pipeline that delivered
    **zero** documents to document-intelligence.

    That is the #628 signature in the single most load-bearing field in the loop: an
    operator following the documented flow would capture that run as acceptance
    evidence and flip ``enabled: true`` on a template that indexed nothing. The
    evidence gate would have certified its own failure as success.

    So this is not just a nicer error message. The run is rewritten to terminal
    FAILED with a reason naming the cause *before* this propagates, exactly as
    ``_record_refused_run`` does for a two-key-lock refusal (#634/#681): a failed run
    must leave an honest trace. The API maps it to 502 — the request was well-formed
    and acquisition worked; the downstream broker is what did not accept the handoff.
    """


class OrchestrationError(PlatformControlError):
    """Raised when an orchestration backend (e.g. Temporal) cannot complete the action."""
