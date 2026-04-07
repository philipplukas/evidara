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


class SignatureVerificationError(PlatformControlError):
    """Raised when a webhook signature cannot be verified."""


class IntegrationConfigurationError(PlatformControlError):
    """Raised when storage or event integrations are misconfigured."""


class OrchestrationError(PlatformControlError):
    """Raised when an orchestration backend (e.g. Temporal) cannot complete the action."""
