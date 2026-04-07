"""Resolve pipeline policy sets from document metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_POLICY_DIR = Path(__file__).parent


@dataclass(frozen=True)
class PolicySet:
    policy_set_id: str
    description: str
    ingestion_policy: str
    canonicalization_policy: str
    identity_policy: str
    parsing_policy: str
    nlp_policy: str
    serving_policy: str


class PolicyResolver:
    def __init__(
        self,
        registry_path: Path | None = None,
        sets_path: Path | None = None,
    ) -> None:
        registry_path = registry_path or _POLICY_DIR / "policy_registry.yml"
        sets_path = sets_path or _POLICY_DIR / "policy_sets.yml"

        with open(registry_path) as f:
            self._registry = yaml.safe_load(f)
        with open(sets_path) as f:
            self._sets_data = yaml.safe_load(f)

        self._policy_sets: dict[str, PolicySet] = {}
        for ps_id, ps_config in (self._sets_data.get("policy_sets") or {}).items():
            if not isinstance(ps_config, dict):
                continue
            self._policy_sets[ps_id] = PolicySet(
                policy_set_id=ps_id,
                description=ps_config.get("description", ""),
                ingestion_policy=ps_config.get("ingestion_policy", ""),
                canonicalization_policy=ps_config.get("canonicalization_policy", ""),
                identity_policy=ps_config.get("identity_policy", ""),
                parsing_policy=ps_config.get("parsing_policy", ""),
                nlp_policy=ps_config.get("nlp_policy", ""),
                serving_policy=ps_config.get("serving_policy", ""),
            )

    def resolve(
        self,
        *,
        source_system: str | None = None,
        document_class: str | None = None,
        jurisdiction: str | None = None,
    ) -> PolicySet:
        """Return the first matching policy set, or the default fallback."""
        for rule in self._registry.get("policies") or []:
            match_spec = rule.get("match") or {}
            if self._matches(match_spec, source_system, document_class, jurisdiction):
                ps_id = rule["policy_set"]
                if ps_id in self._policy_sets:
                    return self._policy_sets[ps_id]

        if "default_v1" in self._policy_sets:
            return self._policy_sets["default_v1"]
        raise ValueError("No matching policy set and no default_v1 fallback defined")

    def get_concrete_policy(self, policy_type: str, policy_id: str) -> dict[str, Any]:
        """Look up a concrete policy definition (e.g. parsing_policies.docling_structured_v1)."""
        section_key = f"{policy_type}_policies"
        section = self._sets_data.get(section_key) or {}
        return dict(section.get(policy_id) or {})

    @staticmethod
    def _matches(
        match_spec: dict[str, str],
        source_system: str | None,
        document_class: str | None,
        jurisdiction: str | None,
    ) -> bool:
        if not match_spec:
            return True
        if "source_system" in match_spec and match_spec["source_system"] != source_system:
            return False
        if "document_class" in match_spec and match_spec["document_class"] != document_class:
            return False
        if "jurisdiction" in match_spec and match_spec["jurisdiction"] != jurisdiction:
            return False
        return True
