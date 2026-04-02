from __future__ import annotations


class PlatformControlError(Exception):
    """Base domain error."""


class NotFoundError(PlatformControlError):
    """Requested entity does not exist."""


class InvalidStateTransitionError(PlatformControlError):
    """Raised when a state transition is invalid."""


class ProviderConfigurationError(PlatformControlError):
    """Raised when an external provider is not configured correctly."""


class SignatureVerificationError(PlatformControlError):
    """Raised when a webhook signature cannot be verified."""


class IntegrationConfigurationError(PlatformControlError):
    """Raised when storage or event integrations are misconfigured."""
