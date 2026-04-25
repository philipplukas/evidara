"""Cross-check downstream consumers against canonical seed IDs.

Enforces the invariant that every `authority_id` / `jurisdiction_id`
referenced anywhere in the repo (contract examples, golden datasets,
fixtures, scripts, workflows, DI jurisdiction resolver) resolves to a
row in `platform-control/src/platform_control/seeds/reference/{authorities,jurisdictions}.yaml`.

This catches the #241-class drift where a seed rename landed without
updating the ~20 downstream callers. See issue #264 for the naming policy.

If this test fails, the fix is one of:
  - add the missing ID to the seed (if the caller is using a legitimate ID
    that the seed just doesn't know about yet), or
  - rename the seed back to match the caller (if the seed is the outlier),
    in a dedicated `ids-migration`-labeled PR per policy.
Do not "fix" the test by adding a skip — the whole point is that the test
is the gate.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]

_SEEDS_DIR = REPO_ROOT / "platform-control" / "src" / "platform_control" / "seeds" / "reference"
_AUTHORITIES_YAML = _SEEDS_DIR / "authorities.yaml"
_JURISDICTIONS_YAML = _SEEDS_DIR / "jurisdictions.yaml"

# File globs whose ID references are considered part of the durable contract.
# Adding a new surface here is cheap — loosening the check by removing a
# surface should require explicit review.
_SCAN_GLOBS: tuple[tuple[str, str], ...] = (
    ("contracts/examples", "*.json"),
    ("document-intelligence/tests/golden", "*.json"),
    ("platform-control/tests/fixtures", "*.json"),
    ("scripts", "*.sh"),
    (".github/workflows", "*.yml"),
    (".github/workflows", "*.yaml"),
)

# Regexes for ID references we care about. Intentionally narrow: only match
# `"authority_id": "..."` / `authority_id: "..."` / `authority_id="..."`
# shapes, since bare identifiers in prose are out of scope.
_AUTH_ID_RE = re.compile(r'authority_id["\']?\s*[:=]\s*["\']([a-z0-9_]+)["\']')
_JUR_ID_RE = re.compile(r'jurisdiction_id["\']?\s*[:=]\s*["\']([a-z0-9_]+)["\']')

# Known pre-existing drift between downstream callers and the seed files.
# Each entry MUST point at a tracking issue. New drift is NOT allowed —
# remove entries from these sets as the underlying issue is fixed; never
# extend them without opening a matching tracking issue first.
#
# Per policy in issue #264: ID renames go through a dedicated
# `ids-migration`-labeled PR, not buried in a feature PR.
_KNOWN_MISSING_AUTHORITY_IDS: frozenset[str] = frozenset(
    {
        # AT drift: seed has auth_at_ris / auth_at_ogh / auth_at_vfgh /
        # auth_at_vwgh (prefixed), downstream consumers use the flat form.
        # See #264 + follow-up AT reconciliation (to be filed).
        "auth_ris",
        "auth_vfgh",
        "auth_vwgh",
        # Generic placeholder authority IDs used only in scraping-baseline
        # test fixtures. These don't represent real publishers — the
        # fixtures test pipeline plumbing, not ID resolution. Fixture
        # rewrites are tracked as a separate cleanup and can remove these.
        "auth_parliament",
        "auth_commentary_publisher",
        "auth_federal_admin",
        "auth_federal_assembly",
        "auth_federal_chancellery",
        "auth_federal_court",
        "auth_federal_procurement",
        "auth_gesetze_im_internet",
    }
)
_KNOWN_MISSING_JURISDICTION_IDS: frozenset[str] = frozenset(
    {
        # AT/DE federal scope: same drift class as CH's (fixed in this PR).
        # Follow-up AT + DE reconciliation tracked separately.
        "jur_at_federal",
        "jur_de_federal",
        # LI (Liechtenstein) referenced by the DI canonical resolver but not
        # yet part of the five-country rollout scope.
        "jur_li",
    }
)


def _load_seed_ids() -> tuple[set[str], set[str]]:
    with _AUTHORITIES_YAML.open(encoding="utf-8") as handle:
        authorities = yaml.safe_load(handle)
    with _JURISDICTIONS_YAML.open(encoding="utf-8") as handle:
        jurisdictions = yaml.safe_load(handle)
    auth_ids = {
        item["authority_id"]
        for item in authorities.get("items", [])
        if isinstance(item, dict) and "authority_id" in item
    }
    jur_ids = {
        item["jurisdiction_id"]
        for item in jurisdictions.get("items", [])
        if isinstance(item, dict) and "jurisdiction_id" in item
    }
    return auth_ids, jur_ids


def _scan_file_for_ids(path: Path) -> tuple[set[str], set[str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return set(_AUTH_ID_RE.findall(text)), set(_JUR_ID_RE.findall(text))


def _collect_consumer_ids() -> tuple[dict[str, set[Path]], dict[str, set[Path]]]:
    """Return mappings of id -> files that reference it, for both kinds."""
    auth_refs: dict[str, set[Path]] = {}
    jur_refs: dict[str, set[Path]] = {}
    for rel_dir, pattern in _SCAN_GLOBS:
        base = REPO_ROOT / rel_dir
        if not base.exists():
            continue
        for path in base.rglob(pattern):
            if not path.is_file():
                continue
            auths, jurs = _scan_file_for_ids(path)
            for aid in auths:
                auth_refs.setdefault(aid, set()).add(path)
            for jid in jurs:
                jur_refs.setdefault(jid, set()).add(path)

    # DI jurisdiction resolver carries an explicit canonical map. Pick up
    # every jur_* literal in that file too.
    resolver = (
        REPO_ROOT
        / "document-intelligence"
        / "src"
        / "document_intelligence"
        / "canonical"
        / "jurisdiction.py"
    )
    if resolver.exists():
        text = resolver.read_text(encoding="utf-8")
        for jid in re.findall(r'["\'](jur_[a-z0-9_]+)["\']', text):
            jur_refs.setdefault(jid, set()).add(resolver)

    return auth_refs, jur_refs


class TestSeedIdConsistency(unittest.TestCase):
    """Every authority_id / jurisdiction_id used downstream must exist in seeds.

    This is the contract enforcement — see issue #264.
    """

    def test_every_consumer_authority_id_resolves_in_seeds(self) -> None:
        seed_auth_ids, _ = _load_seed_ids()
        auth_refs, _ = _collect_consumer_ids()
        missing = {
            aid: refs
            for aid, refs in auth_refs.items()
            if aid not in seed_auth_ids and aid not in _KNOWN_MISSING_AUTHORITY_IDS
        }
        if missing:
            lines = [
                "authority_id values referenced downstream but missing from seeds",
                "(and not on the known-drift allowlist — new drift is not allowed,",
                "see issue #264 for policy):",
            ]
            for aid in sorted(missing):
                files = sorted(str(p.relative_to(REPO_ROOT)) for p in missing[aid])
                suffix = "…" if len(files) > 5 else ""
                lines.append(f"  {aid}  (referenced by: {', '.join(files[:5])}{suffix})")
            self.fail("\n".join(lines))

        # Ratchet: fail if a known-drift entry is no longer actually missing
        # (i.e. someone fixed it but forgot to remove the allowlist entry).
        stale = {aid for aid in _KNOWN_MISSING_AUTHORITY_IDS if aid in seed_auth_ids}
        if stale:
            self.fail(
                "known-drift allowlist entries are now present in seeds; "
                f"remove them from _KNOWN_MISSING_AUTHORITY_IDS: {sorted(stale)}"
            )

    def test_every_consumer_jurisdiction_id_resolves_in_seeds(self) -> None:
        _, seed_jur_ids = _load_seed_ids()
        _, jur_refs = _collect_consumer_ids()
        missing = {
            jid: refs
            for jid, refs in jur_refs.items()
            if jid not in seed_jur_ids and jid not in _KNOWN_MISSING_JURISDICTION_IDS
        }
        if missing:
            lines = [
                "jurisdiction_id values referenced downstream but missing from seeds",
                "(and not on the known-drift allowlist — new drift is not allowed,",
                "see issue #264 for policy):",
            ]
            for jid in sorted(missing):
                files = sorted(str(p.relative_to(REPO_ROOT)) for p in missing[jid])
                suffix = "…" if len(files) > 5 else ""
                lines.append(f"  {jid}  (referenced by: {', '.join(files[:5])}{suffix})")
            self.fail("\n".join(lines))

        stale = {jid for jid in _KNOWN_MISSING_JURISDICTION_IDS if jid in seed_jur_ids}
        if stale:
            self.fail(
                "known-drift allowlist entries are now present in seeds; "
                f"remove them from _KNOWN_MISSING_JURISDICTION_IDS: {sorted(stale)}"
            )

    def test_seed_authority_jurisdictions_resolve(self) -> None:
        """Every authority row's jurisdiction_id must resolve in jurisdictions.yaml."""
        seed_auth_ids, seed_jur_ids = _load_seed_ids()
        with _AUTHORITIES_YAML.open(encoding="utf-8") as handle:
            authorities = yaml.safe_load(handle)
        orphans = [
            item["authority_id"]
            for item in authorities.get("items", [])
            if isinstance(item, dict) and item.get("jurisdiction_id") not in seed_jur_ids
        ]
        self.assertFalse(
            orphans,
            msg=(
                f"Authority rows reference jurisdiction_ids missing from "
                f"jurisdictions.yaml: {orphans}"
            ),
        )

    def test_seed_jurisdiction_parents_resolve(self) -> None:
        """Every jurisdiction row's parent_id must resolve to a sibling row.

        Catches the failure mode where a child jurisdiction (canton,
        Land, municipality) is added with a typo'd or stale `parent_id`
        — silently breaking hierarchy queries with no API surface error.
        """
        with _JURISDICTIONS_YAML.open(encoding="utf-8") as handle:
            jurisdictions = yaml.safe_load(handle)
        items = [item for item in jurisdictions.get("items", []) if isinstance(item, dict)]
        seed_ids = {item["jurisdiction_id"] for item in items if "jurisdiction_id" in item}
        orphans = [
            (item["jurisdiction_id"], item["parent_id"])
            for item in items
            if item.get("parent_id") and item["parent_id"] not in seed_ids
        ]
        self.assertFalse(
            orphans,
            msg=(
                f"Jurisdiction rows reference parent_ids missing from the same seed file: {orphans}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
