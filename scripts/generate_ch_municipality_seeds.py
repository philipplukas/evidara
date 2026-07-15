#!/usr/bin/env python3
"""Generate CH municipality jurisdiction seed rows from the BFS overlay.

Reads `country-overlays/ch/municipalities.yaml` (the ~2110-entry registry
sourced from BFS Amtliches Gemeindeverzeichnis) and rewrites the
`jur_ch_gemeinde_*` block of
`platform-control/src/platform_control/seeds/reference/jurisdictions.yaml`
to match it 1:1.

Each overlay entry produces one seed row:

    overlay  -> seed
    bfs_id 4001 + canton jur_ch_ag + name "Aarau"
        -> jurisdiction_id: jur_ch_gemeinde_4001
           slug:            ch-gemeinde-4001
           name:            Aarau
           parent_id:       jur_ch_ag

The block lives between two anchor lines that the script identifies and
preserves exactly, so curated content above and below (federal, cantons,
other countries) is not touched. Re-running the script is idempotent.

Usage:
    python3 scripts/generate_ch_municipality_seeds.py            # write
    python3 scripts/generate_ch_municipality_seeds.py --check    # CI drift guard
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
OVERLAY_PATH = REPO_ROOT / "country-overlays" / "ch" / "municipalities.yaml"
SEED_PATH = (
    REPO_ROOT
    / "platform-control"
    / "src"
    / "platform_control"
    / "seeds"
    / "reference"
    / "jurisdictions.yaml"
)

# Anchor comments delimit the generated block. The seed YAML keeps curated
# rows on either side; the generator only rewrites the block between these
# two markers (inclusive of the start marker line, exclusive of the end).
START_MARKER = (
    "  # ─── Swiss municipalities (BFS-keyed, generated; see "
    "scripts/generate_ch_municipality_seeds.py) ───\n"
)
END_MARKER_PREFIX = "  - jurisdiction_id: jur_at"


def _load_overlay_entries(overlay_path: Path) -> list[dict[str, object]]:
    """Return the overlay's `municipalities` list as plain dicts.

    Sorted by `bfs_id` so the generated block is stable across runs.
    """
    with overlay_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{overlay_path} must contain a YAML mapping")
    items = data.get("municipalities", [])
    if not isinstance(items, list):
        raise ValueError(f"{overlay_path} `municipalities` must be a list")
    rows = [m for m in items if isinstance(m, dict)]
    rows.sort(key=lambda row: row["bfs_id"])
    return rows


def render_seed_block(overlay_entries: list[dict[str, object]]) -> str:
    """Render the seed-block YAML chunk for the given overlay entries.

    Output is deterministic: anchor comment, then one block of
    `jurisdiction_id` / `slug` / `name` / `parent_id` / `level` per entry,
    sorted by `bfs_id`.

    Every row in this block is a Swiss commune, so `level` is constant —
    `municipal`, the bottom of the hierarchy of norms (ADR-0033).
    """
    lines: list[str] = [START_MARKER]
    for row in overlay_entries:
        bfs_id = row["bfs_id"]
        name = row["name"]
        parent = row["canton_jurisdiction_id"]
        lines.append(f"  - jurisdiction_id: jur_ch_gemeinde_{bfs_id}\n")
        lines.append(f"    slug: ch-gemeinde-{bfs_id}\n")
        lines.append(f"    name: {name}\n")
        lines.append(f"    parent_id: {parent}\n")
        lines.append("    level: municipal\n")
    return "".join(lines)


def render_updated_seed_file(seed_text: str, generated_block: str) -> str:
    """Splice the generated block into the seed YAML, replacing any prior generated block.

    Locates the line immediately before the END_MARKER_PREFIX line
    (typically `jur_at`), and rewrites everything between START_MARKER
    and that point. If START_MARKER is not present, the block is
    inserted directly above the END_MARKER_PREFIX line.
    """
    end_idx = seed_text.find(END_MARKER_PREFIX)
    if end_idx < 0:
        raise RuntimeError(
            f"Could not locate end marker line ({END_MARKER_PREFIX!r}) in seed YAML; "
            f"refusing to write rather than corrupt the file."
        )
    # Find the START_MARKER if present; otherwise insert just before the end marker.
    start_idx = seed_text.find(START_MARKER)
    if start_idx < 0:
        # First-time insertion: keep everything up to (and including the newline before)
        # the end-marker line.
        prefix = seed_text[:end_idx]
        suffix = seed_text[end_idx:]
    else:
        prefix = seed_text[:start_idx]
        suffix = seed_text[end_idx:]
    return prefix + generated_block + suffix


def write_seed_file(
    *,
    overlay_path: Path = OVERLAY_PATH,
    seed_path: Path = SEED_PATH,
) -> tuple[str, str]:
    """Write the regenerated seed YAML. Returns (old_text, new_text)."""
    entries = _load_overlay_entries(overlay_path)
    block = render_seed_block(entries)
    old_text = seed_path.read_text(encoding="utf-8")
    new_text = render_updated_seed_file(old_text, block)
    if new_text != old_text:
        seed_path.write_text(new_text, encoding="utf-8")
    return old_text, new_text


def check_drift(
    *,
    overlay_path: Path = OVERLAY_PATH,
    seed_path: Path = SEED_PATH,
) -> bool:
    """Return True if the seed file matches what the generator would produce."""
    entries = _load_overlay_entries(overlay_path)
    block = render_seed_block(entries)
    seed_text = seed_path.read_text(encoding="utf-8")
    expected = render_updated_seed_file(seed_text, block)
    return expected == seed_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the seed file would change (CI drift guard).",
    )
    parser.add_argument("--overlay", type=Path, default=OVERLAY_PATH)
    parser.add_argument("--seed", type=Path, default=SEED_PATH)
    args = parser.parse_args()

    if args.check:
        ok = check_drift(overlay_path=args.overlay, seed_path=args.seed)
        if not ok:
            print(
                f"❌ {args.seed} is out of sync with {args.overlay}. "
                f"Run scripts/generate_ch_municipality_seeds.py to regenerate.",
                file=sys.stderr,
            )
            return 2
        print(f"✅ {args.seed} CH municipality block is in sync with {args.overlay}.")
        return 0

    old_text, new_text = write_seed_file(overlay_path=args.overlay, seed_path=args.seed)
    if old_text == new_text:
        print(f"✅ {args.seed} already up-to-date; no changes written.")
    else:
        added = new_text.count("jur_ch_gemeinde_")
        print(f"✅ Wrote {args.seed} with {added} jur_ch_gemeinde_* rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
