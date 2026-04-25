"""CH municipality seed integrity.

The 2110 `jur_ch_gemeinde_*` rows in `jurisdictions.yaml` are generated
from `country-overlays/ch/municipalities.yaml` via
`scripts/generate_ch_municipality_seeds.py`. This module pins three
invariants:

1. The generator output matches the on-disk seed (no drift).
2. Every generated row's `parent_id` resolves to a canton already in
   the seed file.
3. The historical IDs `jur_ch_federal` and `auth_fedlex` survive
   regeneration unchanged — they're hardcoded by the canary script
   `scripts/ch-fedlex-fast-loop.sh` (see issue #264 / CLAUDE.md).
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_ch_municipality_seeds.py"
SEED_PATH = (
    REPO_ROOT
    / "platform-control"
    / "src"
    / "platform_control"
    / "seeds"
    / "reference"
    / "jurisdictions.yaml"
)


def _load_generator():
    """Load the generator module by file path (lives outside the package)."""
    spec = importlib.util.spec_from_file_location("_gen_ch_seeds", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("_gen_ch_seeds", module)
    spec.loader.exec_module(module)
    return module


class TestChMunicipalitySeeds(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gen = _load_generator()
        with SEED_PATH.open(encoding="utf-8") as handle:
            cls.seed_data = yaml.safe_load(handle)

    def test_seed_in_sync_with_overlay(self) -> None:
        """`generate_ch_municipality_seeds.py --check` must pass."""
        ok = self.gen.check_drift()
        self.assertTrue(
            ok,
            msg=(
                "jurisdictions.yaml CH municipality block is out of sync with "
                "country-overlays/ch/municipalities.yaml. "
                "Run scripts/generate_ch_municipality_seeds.py to regenerate."
            ),
        )

    def test_every_municipality_parent_is_a_canton(self) -> None:
        """Every `jur_ch_gemeinde_*` row's `parent_id` must be a canton seed row."""
        items = [item for item in self.seed_data.get("items", []) if isinstance(item, dict)]
        all_ids = {item["jurisdiction_id"] for item in items if "jurisdiction_id" in item}
        canton_ids = {
            item["jurisdiction_id"]
            for item in items
            if item.get("jurisdiction_id", "").startswith("jur_ch_")
            and not item.get("jurisdiction_id", "").startswith("jur_ch_gemeinde_")
            and item["jurisdiction_id"] != "jur_ch"
        }
        gemeinde_rows = [
            item for item in items if item.get("jurisdiction_id", "").startswith("jur_ch_gemeinde_")
        ]
        # Sanity: 2110 known active municipalities per BFS 01.01.2026.
        self.assertEqual(
            len(gemeinde_rows),
            2110,
            msg=f"Expected 2110 jur_ch_gemeinde_* rows, got {len(gemeinde_rows)}",
        )
        orphans = [
            (row["jurisdiction_id"], row.get("parent_id"))
            for row in gemeinde_rows
            if row.get("parent_id") not in canton_ids
        ]
        self.assertFalse(
            orphans,
            msg=(
                "Municipality rows reference parent_ids that aren't canton seeds: "
                f"{orphans[:5]}{'…' if len(orphans) > 5 else ''}"
            ),
        )
        # Defensive: parent_ids must also resolve in all_ids (covers any future
        # rename that drops the canton from seeds).
        unresolved = [
            (row["jurisdiction_id"], row.get("parent_id"))
            for row in gemeinde_rows
            if row.get("parent_id") not in all_ids
        ]
        self.assertFalse(unresolved, msg=f"Unresolved parents: {unresolved[:5]}")

    def test_canary_ids_unchanged(self) -> None:
        """`jur_ch_federal` and `auth_fedlex` must survive — see CLAUDE.md / #264."""
        items = [item for item in self.seed_data.get("items", []) if isinstance(item, dict)]
        seed_ids = {item.get("jurisdiction_id") for item in items}
        self.assertIn(
            "jur_ch_federal",
            seed_ids,
            msg=(
                "jur_ch_federal disappeared from jurisdictions.yaml — this ID is "
                "hardcoded by scripts/ch-fedlex-fast-loop.sh and ~15 other "
                "downstream consumers."
            ),
        )


if __name__ == "__main__":
    unittest.main()
