"""Source and jurisdiction profile selection registry."""

from dataclasses import dataclass
from typing import Any

_DEFAULT_SOURCE_PROFILE = "default_html_v1"
_DEFAULT_JURISDICTION_PROFILE = "default_jurisdiction_v1"
_DEFAULT_RESOLUTION_POLICY = "default_resolution_v1"

_SOURCE_PROFILE_BY_NORMALIZER = {
    "html_v1": "default_html_v1",
    "xml_v1": "default_xml_v1",
    "pdf_v1": "default_pdf_v1",
    "plain_text_v1": "default_plain_text_v1",
    "docling_v1": "default_docling_v1",
    "docling_fallback_v1": "default_docling_fallback_v1",
}

_JURISDICTION_PROFILE_BY_PREFIX = {
    "jur_ch": "ch_jurisdiction_v1",
    "jur_at": "at_jurisdiction_v1",
    "jur_de": "de_jurisdiction_v1",
    "jur_li": "li_jurisdiction_v1",
}


@dataclass(frozen=True)
class SelectedProfiles:
    source_profile_ref: str
    jurisdiction_profile_ref: str
    resolution_policy_ref: str
    normalization_profile_ref: str | None = None

    def to_dict(self) -> dict[str, str]:
        output = {
            "source_profile_ref": self.source_profile_ref,
            "jurisdiction_profile_ref": self.jurisdiction_profile_ref,
            "resolution_policy_ref": self.resolution_policy_ref,
        }
        if self.normalization_profile_ref:
            output["normalization_profile_ref"] = self.normalization_profile_ref
        return output


def resolve_selected_profiles(
    *,
    source_origin_kind: str,
    trust_tier: str,
    source_defaults: dict[str, Any],
    di_overrides: dict[str, Any],
    normalized_metadata: dict[str, Any],
) -> SelectedProfiles:
    """Resolve profile refs with explicit override precedence."""
    source_profile_ref = str(
        di_overrides.get("source_profile_ref")
        or normalized_metadata.get("source_profile_ref")
        or _source_profile_for_normalizer(normalized_metadata.get("normalizer"))
        or _DEFAULT_SOURCE_PROFILE
    )
    jurisdiction_profile_ref = str(
        di_overrides.get("jurisdiction_profile_ref")
        or _jurisdiction_profile_for_id(source_defaults.get("jurisdiction_id"))
        or _DEFAULT_JURISDICTION_PROFILE
    )
    resolution_policy_ref = str(
        di_overrides.get("resolution_policy_ref")
        or _resolution_policy_for_source(source_origin_kind, trust_tier)
        or _DEFAULT_RESOLUTION_POLICY
    )
    normalization_profile_ref = di_overrides.get("normalization_profile_ref") or normalized_metadata.get(
        "normalization_profile_ref"
    )
    return SelectedProfiles(
        source_profile_ref=source_profile_ref,
        jurisdiction_profile_ref=jurisdiction_profile_ref,
        resolution_policy_ref=resolution_policy_ref,
        normalization_profile_ref=str(normalization_profile_ref) if normalization_profile_ref else None,
    )


def _source_profile_for_normalizer(normalizer: Any) -> str | None:
    if not isinstance(normalizer, str):
        return None
    return _SOURCE_PROFILE_BY_NORMALIZER.get(normalizer.strip().lower())


def _jurisdiction_profile_for_id(jurisdiction_id: Any) -> str | None:
    if not isinstance(jurisdiction_id, str):
        return None
    normalized = jurisdiction_id.strip().lower()
    for prefix, profile_ref in _JURISDICTION_PROFILE_BY_PREFIX.items():
        if normalized.startswith(prefix):
            return profile_ref
    return None


def _resolution_policy_for_source(source_origin_kind: str, trust_tier: str) -> str:
    if source_origin_kind == "official_primary" and trust_tier == "authoritative":
        return "official_primary_resolution_v1"
    return _DEFAULT_RESOLUTION_POLICY
