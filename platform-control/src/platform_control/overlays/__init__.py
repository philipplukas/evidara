"""Country-overlay loader package.

See docs/architecture/vocabulary-standards.md for the single-source-of-truth
rules. The loader exposes functions that deep-merge shared defaults with
per-country overrides and substitute the `{country_code}` placeholder.
"""

from platform_control.overlays.loader import (
    OverlayLoadError,
    load_operator_content,
    load_overlay,
    load_reference_data,
    load_user_content,
)

__all__ = [
    "OverlayLoadError",
    "load_operator_content",
    "load_overlay",
    "load_reference_data",
    "load_user_content",
]
