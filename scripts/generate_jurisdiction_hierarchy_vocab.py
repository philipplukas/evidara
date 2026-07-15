#!/usr/bin/env python3
"""Export the jurisdiction hierarchy from platform-control's seed into contracts.

platform-control owns the jurisdiction tree (ADR-0004: contracts are the shared,
build-time surface; the seed is the source of truth). legal-search needs that
tree to answer `norm_hierarchy(jurisdiction_id)` and to stamp a `level` onto
every document projection — but legal-search must not read platform-control's
database or call it at request time for reference data that never changes
between deploys.

So the tree is exported, generated-not-handwritten, into
`contracts/vocabularies/jurisdiction-hierarchy.json`, which legal-search loads
at module init exactly like the other vocabularies. This script is the export;
`--check` is the CI drift guard.

The export carries only what the hierarchy walk needs — id, name, slug, level,
parent — deliberately NOT the compliance policy or any other operational
attribute, so this does not become a second copy of the seed.

Usage:
    python3 scripts/generate_jurisdiction_hierarchy_vocab.py            # write
    python3 scripts/generate_jurisdiction_hierarchy_vocab.py --check    # CI drift guard
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = (
    REPO_ROOT
    / "platform-control"
    / "src"
    / "platform_control"
    / "seeds"
    / "reference"
    / "jurisdictions.yaml"
)
VOCAB_PATH = REPO_ROOT / "contracts" / "vocabularies" / "jurisdiction-hierarchy.json"
NORM_LEVEL_PATH = REPO_ROOT / "contracts" / "vocabularies" / "norm-level.json"

DESCRIPTION = (
    "Single source of truth for the jurisdiction tree as legal-search sees it: "
    "which jurisdictions exist, which level of the hierarchy of norms each one "
    "legislates at (see contracts/vocabularies/norm-level.json), and which "
    "jurisdiction contains it. GENERATED from "
    "platform-control/src/platform_control/seeds/reference/jurisdictions.yaml by "
    "scripts/generate_jurisdiction_hierarchy_vocab.py — do not hand-edit; edit "
    "the seed and regenerate. Consumers derive the governing chain (`what governs "
    "this place, at each level`) from `parent` + `level` rather than storing it, "
    "because the chain is a function of the tree: the scopes that govern J are "
    "J's ancestors, plus each ancestor's same-level children (which is how "
    "jur_ch_federal — a federal-level child of the federal-level container jur_ch "
    "— governs a canton that is only jur_ch's child)."
)


def load_seed_entries(seed_path: Path) -> list[dict[str, object]]:
    data = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError(f"{seed_path} must contain an `items` list")
    return [item for item in data["items"] if isinstance(item, dict)]


def load_norm_levels(norm_level_path: Path) -> dict[str, int]:
    data = json.loads(norm_level_path.read_text(encoding="utf-8"))
    values = data.get("values")
    if not isinstance(values, dict):
        raise ValueError(f"{norm_level_path} must contain a `values` object")
    return {key: entry["rank"] for key, entry in values.items()}


def render_vocabulary(
    entries: list[dict[str, object]],
    known_levels: dict[str, int],
) -> dict[str, object]:
    """Build the vocabulary document. Entries are emitted in seed order."""
    values: dict[str, object] = {}
    for entry in entries:
        jurisdiction_id = entry.get("jurisdiction_id")
        level = entry.get("level")
        if not isinstance(jurisdiction_id, str):
            raise ValueError(f"Seed entry without a jurisdiction_id: {entry!r}")
        if not isinstance(level, str) or level not in known_levels:
            raise ValueError(
                f"Jurisdiction {jurisdiction_id} has level {level!r}, which is not one of "
                f"{sorted(known_levels)} (see contracts/vocabularies/norm-level.json)."
            )
        values[jurisdiction_id] = {
            "name": entry.get("name"),
            "slug": entry.get("slug"),
            "level": level,
            "parent": entry.get("parent_id"),
        }

    # A parent that is not itself a seeded jurisdiction would break every
    # hierarchy walk that passes through it — fail loudly at generation time
    # rather than returning a silently truncated chain at request time.
    for jurisdiction_id, value in values.items():
        parent = value["parent"]  # type: ignore[index]
        if parent is not None and parent not in values:
            raise ValueError(
                f"Jurisdiction {jurisdiction_id} has parent {parent!r}, which is not seeded."
            )

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://evidara.dev/vocabularies/jurisdiction-hierarchy",
        "title": "Jurisdiction Hierarchy Vocabulary",
        "description": DESCRIPTION,
        "vocabulary": "jurisdiction-hierarchy",
        "values": values,
    }


def render_json(document: dict[str, object]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the committed vocabulary differs from the seed.",
    )
    args = parser.parse_args()

    entries = load_seed_entries(SEED_PATH)
    known_levels = load_norm_levels(NORM_LEVEL_PATH)
    rendered = render_json(render_vocabulary(entries, known_levels))

    if args.check:
        current = VOCAB_PATH.read_text(encoding="utf-8") if VOCAB_PATH.exists() else ""
        if current != rendered:
            print(
                f"❌ {VOCAB_PATH} is out of sync with {SEED_PATH}.\n"
                "   Run: python3 scripts/generate_jurisdiction_hierarchy_vocab.py",
                file=sys.stderr,
            )
            return 1
        print(f"✅ {VOCAB_PATH} is in sync with {SEED_PATH}.")
        return 0

    VOCAB_PATH.write_text(rendered, encoding="utf-8")
    print(f"✅ Wrote {len(entries)} jurisdictions to {VOCAB_PATH}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
