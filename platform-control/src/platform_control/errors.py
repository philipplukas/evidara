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


class OrchestrationError(PlatformControlError):
    """Raised when an orchestration backend (e.g. Temporal) cannot complete the action."""
