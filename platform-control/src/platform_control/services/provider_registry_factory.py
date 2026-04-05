from __future__ import annotations

from platform_control.config import Settings
from platform_control.services.deterministic_http_provider import DeterministicHttpProvider
from platform_control.services.firecrawl_provider import FirecrawlProvider
from platform_control.services.provider_registry import ProviderRegistry


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(FirecrawlProvider(settings))
    registry.register(DeterministicHttpProvider())
    return registry
