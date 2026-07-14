from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "generate_brand_assets.py"
SPEC = importlib.util.spec_from_file_location("generate_brand_assets", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

REPO_ROOT = Path(__file__).resolve().parents[2]
BRAND_MARK = (REPO_ROOT / "styles/shell/BrandMark.tsx").read_text(encoding="utf-8")


class GeometrySyncTests(unittest.TestCase):
    """The icon geometry is duplicated in the generator, because a static file cannot
    use `currentColor` or read a CSS custom property. Duplication is only safe if it
    cannot silently drift, so pin it here: change the component without changing the
    generator and this fails."""

    def test_frame_path_matches_the_component(self) -> None:
        self.assertIn(f'const FRAME = "{MODULE.FRAME}"', BRAND_MARK)

    def test_diagonals_match_the_component(self) -> None:
        for diagonal in MODULE.DIAGONALS:
            self.assertIn(f'"{diagonal}"', BRAND_MARK)

    def test_hit_node_matches_the_component_and_stays_off_centre(self) -> None:
        cx, cy = MODULE.HIT
        self.assertIn(f"const HIT: readonly [number, number] = [{cx}, {cy}];", BRAND_MARK)
        # The asymmetry IS the idea — a centred hit would make it a snowflake.
        self.assertNotEqual((cx, cy), (16, 16))

    def test_compact_stroke_and_radii_match_the_component(self) -> None:
        compact = BRAND_MARK.split("export function BrandMarkCompact", 1)[1]
        self.assertIn(f"strokeWidth={{{MODULE.COMPACT_STROKE}}}", compact)
        self.assertIn(f"r={{{MODULE.COMPACT_HIT_R}}}", compact)


class LegibilityTests(unittest.TestCase):
    """The 16px favicon is the size that decides an icon. Guard the arithmetic that
    got it there, so a well-meaning tweak cannot quietly push it back under a pixel."""

    def test_the_16px_stroke_clears_one_physical_pixel(self) -> None:
        stroke_px = MODULE._physical_stroke(
            MODULE.MICRO["stroke"], MODULE.MICRO["scale"], 16
        )
        # The original geometry rendered 0.82px here and turned to mush.
        self.assertGreater(stroke_px, 1.5, f"16px stroke is {stroke_px:.2f}px — sub-pixel mush")

    def test_the_micro_badge_drops_the_diagonals(self) -> None:
        # Rendered side by side, keeping them at 16px produced a smudge.
        self.assertFalse(MODULE.MICRO["diagonals"])
        self.assertFalse(MODULE.MICRO["centre"])

    def test_the_standard_badge_keeps_the_lattice(self) -> None:
        self.assertTrue(MODULE.STANDARD["diagonals"])


class SvgOutputTests(unittest.TestCase):
    def test_the_icon_is_an_opaque_navy_badge(self) -> None:
        svg = MODULE.icon_svg()
        # A navy-on-transparent favicon vanishes on a dark browser tab.
        self.assertIn(f'fill="{MODULE.BRAND_NAVY}"', svg)
        self.assertIn(f'stroke="{MODULE.ON_BRAND}"', svg)

    def test_the_accent_node_is_the_lifted_violet(self) -> None:
        # The workspace violet is too dark to carry on navy; admin lifts it and so
        # must the icon, or the hit node disappears into the badge.
        self.assertIn(f'fill="{MODULE.ACCENT_ON_NAVY}"', MODULE.icon_svg())
        self.assertNotIn("#6246D9", MODULE.icon_svg())

    def test_the_icon_carries_no_other_colour(self) -> None:
        colours = set(re.findall(r"#[0-9a-fA-F]{6}", MODULE.icon_svg()))
        self.assertEqual(
            colours,
            {MODULE.BRAND_NAVY, MODULE.ON_BRAND, MODULE.ACCENT_ON_NAVY},
            "a fourth colour would break the single-accent rule",
        )


if __name__ == "__main__":
    unittest.main()
