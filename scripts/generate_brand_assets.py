#!/usr/bin/env python3
"""Generate Evidara's icon assets from the BrandMark lattice geometry.

The geometry here is the SAME as `styles/shell/BrandMark.tsx` — this script is the
one place it is duplicated, because a static file cannot use `currentColor` or read
a CSS custom property. `scripts/tests/test_generate_brand_assets.py` asserts the two
stay in sync, so a change to the component that is not mirrored here fails the build.

Why a navy badge and not the bare lattice
-----------------------------------------
In the header the mark is transparent and inherits its colour from the surface. An
icon cannot: a navy-on-transparent favicon vanishes on a dark browser tab, and iOS
composites `apple-icon` on whatever it likes. So the icon is an opaque badge —
white lattice on brand navy, which is exactly the lockup admin's own header already
uses. It reads on any tab colour.

The accent node is `#a6a3f0`, the sRGB result of the same
`color-mix(in oklab, var(--accent-core) 52%, var(--admin-on-brand))` admin applies:
the workspace violet is too dark to carry on navy.

Requires: `rsvg-convert` (librsvg) and Pillow.

    uv run --with pillow python scripts/generate_brand_assets.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BRAND_NAVY = "#0f4c81"
ON_BRAND = "#ffffff"
# color-mix(in oklab, #6246D9 52%, #ffffff) — see module docstring.
ACCENT_ON_NAVY = "#a6a3f0"

# ── Geometry, mirrored from styles/shell/BrandMark.tsx (32x32 grid) ──
FRAME = "M16 2 L30 16 L16 30 L2 16 Z"
DIAGONALS = ("M9 9 L23 23", "M23 9 L9 23")
HIT = (23, 9)

# BrandMarkCompact: silhouette + the two diagonals that carry the hit. The full
# lattice is unreadable at 16px, which is precisely the size an icon must survive.
COMPACT_STROKE = 2.4
COMPACT_CENTRE_R = 2.0
COMPACT_HIT_R = 4.2

# Icon artboard: 64x64 rounded badge.
ARTBOARD = 64
BADGE_RADIUS = 14


def _physical_stroke(width: float, scale: float, rendered_px: int) -> float:
    """Stroke width in ACTUAL pixels once the badge is rasterised.

    This is the number that decides whether an icon is a shape or a smudge. The
    mark is authored on a 32-grid, scaled by `scale` onto a 64-unit artboard, then
    the whole badge is rendered at `rendered_px`.
    """
    return width * scale * rendered_px / ARTBOARD


# Standard badge — 32px and up. Roomy inset, the compact lattice as the component
# draws it.
STANDARD = {
    "scale": 1.375,
    "stroke": COMPACT_STROKE,
    "diagonals": True,
    "centre": True,
    "hit_r": COMPACT_HIT_R,
}

# 16px badge. The standard geometry renders a 0.83-PHYSICAL-pixel stroke here and
# turns to mush — the same sub-pixel failure the full lattice hits in the header.
#
# 16 therefore gets its own geometry: the mark pushed out to 85% of the badge, a much
# heavier stroke (1.70 real pixels, up from 0.82), and BOTH the diagonals and the
# centre node dropped. Rendered and compared side by side, keeping the diagonals at
# this size produced a busy smudge; the bare diamond plus the violet hit is crisp and
# still carries the two things that identify the brand — the silhouette and the
# off-centre node. Nobody reads a citation graph in a browser tab.
#
# An .ico carries a separate frame per size, so none of this costs the larger icons
# anything.
MICRO = {"scale": 1.7, "stroke": 4.0, "diagonals": False, "centre": False, "hit_r": 4.8}


def icon_svg(spec: dict = STANDARD) -> str:
    scale = spec["scale"]
    offset = (ARTBOARD - 32 * scale) / 2
    shapes = (FRAME, *DIAGONALS) if spec["diagonals"] else (FRAME,)
    paths = "\n      ".join(f'<path d="{d}" />' for d in shapes)
    centre = (
        f'\n    <circle cx="16" cy="16" r="{COMPACT_CENTRE_R}" fill="{ON_BRAND}" />'
        if spec["centre"]
        else ""
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{ARTBOARD}" height="{ARTBOARD}" viewBox="0 0 {ARTBOARD} {ARTBOARD}" role="img" aria-label="Evidara">
  <rect width="{ARTBOARD}" height="{ARTBOARD}" rx="{BADGE_RADIUS}" fill="{BRAND_NAVY}" />
  <g transform="translate({offset},{offset}) scale({scale})">
    <g fill="none" stroke="{ON_BRAND}" stroke-width="{spec["stroke"]}" stroke-linejoin="round">
      {paths}
    </g>{centre}
    <circle cx="{HIT[0]}" cy="{HIT[1]}" r="{spec["hit_r"]}" fill="{ACCENT_ON_NAVY}" />
  </g>
</svg>
"""


def rasterize(svg_path: Path, out: Path, size: int) -> None:
    subprocess.run(
        [
            "rsvg-convert",
            "--width", str(size),
            "--height", str(size),
            "--output", str(out),
            str(svg_path),
        ],
        check=True,
    )


ICO_SIZES = (16, 32, 48)


def build_ico(png_dir: Path, out: Path) -> None:
    from PIL import Image

    # A .ico carries several sizes; browsers and Windows pick per context. Pillow
    # derives every listed size from the image it is given, so hand it the LARGEST
    # render — seeding from the 16px frame would upscale a blurry 16 into 32 and 48.
    # Each frame is rasterised from its OWN size-tuned SVG, so append them rather
    # than letting Pillow resample one image into all three — the 16px frame is
    # deliberately not a scaled-down 48.
    frames = [Image.open(png_dir / f"ico-{s}.png").convert("RGBA") for s in ICO_SIZES]
    frames[-1].save(
        out,
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=frames[:-1],
    )


SURFACES = (
    REPO_ROOT / "legal-search/frontend/src/app",
    REPO_ROOT / "platform-control/admin/src/app",
)


def main() -> int:
    if not shutil_which("rsvg-convert"):
        print("ERROR: rsvg-convert not found (install librsvg).", file=sys.stderr)
        return 1

    scratch = REPO_ROOT / ".brand-assets-tmp"
    scratch.mkdir(exist_ok=True)
    source = scratch / "icon.svg"
    source.write_text(icon_svg(), encoding="utf-8")

    micro = scratch / "icon-micro.svg"
    micro.write_text(icon_svg(MICRO), encoding="utf-8")

    for size in ICO_SIZES:
        # 16 gets the micro geometry; 32/48 use the standard badge.
        src = micro if size == 16 else source
        rasterize(src, scratch / f"ico-{size}.png", size)

    for app_dir in SURFACES:
        app_dir.mkdir(parents=True, exist_ok=True)

        # Next's App Router picks these up by filename and emits the <link> tags.
        (app_dir / "icon.svg").write_text(icon_svg(), encoding="utf-8")
        rasterize(source, app_dir / "apple-icon.png", 180)
        build_ico(scratch, app_dir / "favicon.ico")

        print(f"  {app_dir.relative_to(REPO_ROOT)}: icon.svg, apple-icon.png, favicon.ico")

    for leftover in scratch.iterdir():
        leftover.unlink()
    scratch.rmdir()

    print("\nBrand icons generated from the BrandMark lattice geometry.")
    return 0


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


if __name__ == "__main__":
    raise SystemExit(main())
