#!/usr/bin/env python3
"""Promote CH municipalities into platform-control jurisdiction seed rows.

Reads ``country-overlays/ch/municipalities.yaml`` (the BFS Gemeindeverzeichnis
overlay populated by ``scripts/load_ch_gemeindeverzeichnis.py``) and emits a
first-class ``JurisdictionSeed`` row for every active municipality into
``platform-control/src/platform_control/seeds/reference/jurisdictions.yaml``.

ID convention (see issue #424):
    jur_ch_gemeinde_<bfs_number>     e.g. jur_ch_gemeinde_261 (Zürich)
    slug = "ch-gemeinde-<bfs_number>"

Parent linkage:
    parent_id = the canton jurisdiction ID carried by the overlay row
    (canton_jurisdiction_id, e.g. jur_ch_zh).

Behavior:
    1. Reads the municipalities overlay.
    2. Reads the existing jurisdictions.yaml (preserves all non-municipality
       rows verbatim — federal, country, cantons, AT/DE/FR/IT/EU rows).
    3. Replaces the contiguous block of ``jur_ch_gemeinde_*`` rows with a
       freshly-sorted, deterministic list derived from the overlay.
    4. Validates that every generated row's parent_id resolves against an
       existing canton row in the same file. Fails loud if not.
    5. Sorts deterministically (by BFS id ascending) so re-runs produce no
       diff noise.

The script is intentionally re-runnable. Hand-edits to non-municipality rows
(jur_ch, jur_ch_federal, cantons, other countries) are preserved.

Usage:
    python scripts/generate_ch_municipality_jurisdictions.py
    python scripts/generate_ch_municipality_jurisdictions.py --check
    python scripts/generate_ch_municipality_jurisdictions.py --dry-run

``--check`` exits non-zero if regeneration would change the target file
(use this in CI). ``--dry-run`` prints a summary and writes nothing.

Constraints:
    - Never touches jur_ch_federal or auth_fedlex (the canary fast-loop
      script ``scripts/ch-fedlex-fast-loop.sh`` hardcodes both).
    - Skips municipalities lacking a canton_jurisdiction_id and reports them.
    - Skips municipalities whose canton_jurisdiction_id does not resolve
      against an existing canton row, reports them, and exits non-zero so
      CI catches the inconsistency.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MUNICIPALITIES_YAML = REPO_ROOT / "country-overlays" / "ch" / "municipalities.yaml"
JURISDICTIONS_YAML = (
    REPO_ROOT
    / "platform-control"
    / "src"
    / "platform_control"
    / "seeds"
    / "reference"
    / "jurisdictions.yaml"
)

# Marker comment block that brackets the generated section. The regenerator
# rewrites only the lines between (exclusive) BEGIN_MARKER and END_MARKER, so
# hand-edited rows above/below survive untouched. Marker text is stable so
# the script can be re-run idempotently.
BEGIN_MARKER = "  # ─── BEGIN generated CH municipalities (do not hand-edit) ───"
END_MARKER = "  # ─── END generated CH municipalities ───"
GENERATOR_NOTE = (
    "  # Regenerate with: python scripts/generate_ch_municipality_jurisdictions.py\n"
    "  # Source: country-overlays/ch/municipalities.yaml (BFS Gemeindeverzeichnis)\n"
    "  # Issue: #424"
)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return data


def _yaml_quote(value: str) -> str:
    """Return YAML-safe form of *value* for the ``name:`` field.

    The seed file uses unquoted plain scalars wherever safe; we mirror
    PyYAML's default flow-style quoting decision via a tiny helper. We avoid
    a full PyYAML dump here because we want byte-for-byte stable output and
    PyYAML's emitter inserts unwanted line breaks for long strings.
    """
    needs_quote = (
        not value
        or value.strip() != value
        or value[0] in "!&*[{|>%@`#,?"
        or any(ch in value for ch in (":", "#"))
        or value.lower() in ("true", "false", "null", "yes", "no", "on", "off", "~")
    )
    if not needs_quote:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _municipality_id(bfs_id: int) -> str:
    return f"jur_ch_gemeinde_{bfs_id}"


def _municipality_slug(bfs_id: int) -> str:
    return f"ch-gemeinde-{bfs_id}"


def _municipality_name(raw: str) -> str:
    """Compose the display name used in the seed row.

    We keep the BFS official name so seed rows are independently grep-able
    against the source registry; we do NOT prefix with "Gemeinde " because
    the ID itself encodes the kind (jur_ch_gemeinde_*).
    """
    return raw


def _generate_rows(
    municipalities: list[dict[str, Any]],
    canton_ids: set[str],
) -> tuple[list[str], list[tuple[int, str]], list[tuple[int, str, str]]]:
    """Return (yaml_lines, skipped_no_canton, unresolved_parent).

    yaml_lines is the rendered block of jurisdiction items (each item is one
    ``- jurisdiction_id`` block as a multi-line string fragment).
    skipped_no_canton is [(bfs_id, name)] for rows missing canton_jurisdiction_id.
    unresolved_parent is [(bfs_id, name, parent_id)] for rows whose
    canton_jurisdiction_id does not resolve in jurisdictions.yaml.
    """
    skipped_no_canton: list[tuple[int, str]] = []
    unresolved_parent: list[tuple[int, str, str]] = []
    rendered: list[str] = []

    # Deterministic order: ascending BFS id.
    sorted_munis = sorted(municipalities, key=lambda m: int(m["bfs_id"]))

    for entry in sorted_munis:
        bfs_id = int(entry["bfs_id"])
        name = entry.get("name") or ""
        canton = entry.get("canton_jurisdiction_id")
        if not canton:
            skipped_no_canton.append((bfs_id, name))
            continue
        if canton not in canton_ids:
            unresolved_parent.append((bfs_id, name, canton))
            continue

        jur_id = _municipality_id(bfs_id)
        slug = _municipality_slug(bfs_id)
        display = _municipality_name(name)

        block = (
            f"  - jurisdiction_id: {jur_id}\n"
            f"    slug: {slug}\n"
            f"    name: {_yaml_quote(display)}\n"
            f"    parent_id: {canton}\n"
        )
        rendered.append(block)

    return rendered, skipped_no_canton, unresolved_parent


def _existing_canton_ids(jurisdictions: dict[str, Any]) -> set[str]:
    """Return jurisdiction IDs that look like CH cantons (parent jur_ch, not federal/gemeinde)."""
    canton_ids: set[str] = set()
    for item in jurisdictions.get("items") or []:
        if not isinstance(item, dict):
            continue
        jid = item.get("jurisdiction_id")
        parent = item.get("parent_id")
        if not jid or not isinstance(jid, str):
            continue
        if not jid.startswith("jur_ch_"):
            continue
        if jid == "jur_ch_federal":
            continue
        if jid.startswith("jur_ch_gemeinde_"):
            continue
        if parent != "jur_ch":
            continue
        canton_ids.add(jid)
    return canton_ids


def _strip_existing_block(text: str) -> tuple[str, bool]:
    """Remove a previously-generated CH municipality block from *text*.

    Returns (stripped_text, had_block). The block is bracketed by
    BEGIN_MARKER and END_MARKER lines (inclusive). Anything outside that
    block is preserved verbatim.

    If the markers are absent (first run), the original text is returned
    unchanged with had_block=False.
    """
    lines = text.splitlines(keepends=True)
    begin_idx: int | None = None
    end_idx: int | None = None
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n").rstrip("\r")
        if begin_idx is None and stripped == BEGIN_MARKER:
            begin_idx = i
        elif begin_idx is not None and stripped == END_MARKER:
            end_idx = i
            break
    if begin_idx is None or end_idx is None:
        return text, False
    new_lines = lines[:begin_idx] + lines[end_idx + 1 :]
    return "".join(new_lines), True


def _ensure_trailing_newline(text: str) -> str:
    if not text.endswith("\n"):
        return text + "\n"
    return text


def _build_block(rendered_rows: list[str]) -> str:
    body = "".join(rendered_rows)
    return f"{BEGIN_MARKER}\n{GENERATOR_NOTE}\n{body}{END_MARKER}\n"


def _insert_block(text: str, block: str) -> str:
    """Append the generated block to the items list.

    The CH country/canton rows live near the top of items: list, followed by
    AT/DE/.../EU rows. We insert the generated CH municipality block at the
    very end of the items: list (i.e. as the last entries) to avoid disrupting
    the existing visual grouping by country.
    """
    text = _ensure_trailing_newline(text)
    # Append at end of file (items: is the only top-level list).
    return text + block


def regenerate(
    municipalities_path: Path,
    jurisdictions_path: Path,
) -> tuple[str, dict[str, Any]]:
    """Return (new_text, summary) for the regenerated jurisdictions.yaml.

    Does not write to disk. Raises ValueError if any parent_id is unresolved.
    """
    overlay = _load_yaml(municipalities_path)
    municipalities = overlay.get("municipalities") or []
    if not isinstance(municipalities, list):
        raise ValueError(f"{municipalities_path}: expected `municipalities:` to be a list")

    jurisdictions = _load_yaml(jurisdictions_path)
    canton_ids = _existing_canton_ids(jurisdictions)
    if not canton_ids:
        raise ValueError(
            f"{jurisdictions_path}: no CH canton rows found — refusing to "
            "generate municipality rows that would have unresolved parents."
        )

    rendered, skipped_no_canton, unresolved = _generate_rows(municipalities, canton_ids)

    if unresolved:
        details = ", ".join(
            f"BFS {bfs} ({name}) -> {parent}" for bfs, name, parent in unresolved[:10]
        )
        raise ValueError(
            f"{len(unresolved)} municipality row(s) reference unknown canton parent_id "
            f"(showing first 10): {details}"
        )

    original_text = jurisdictions_path.read_text(encoding="utf-8")
    stripped_text, _ = _strip_existing_block(original_text)
    block = _build_block(rendered)
    new_text = _insert_block(stripped_text, block)

    summary = {
        "generated": len(rendered),
        "skipped_no_canton": skipped_no_canton,
        "canton_count": len(canton_ids),
    }
    return new_text, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--municipalities",
        type=Path,
        default=MUNICIPALITIES_YAML,
        help=f"Source overlay (default: {MUNICIPALITIES_YAML.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--jurisdictions",
        type=Path,
        default=JURISDICTIONS_YAML,
        help=f"Target seed file (default: {JURISDICTIONS_YAML.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if regeneration would change the target file (CI gate).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary and exit without writing.",
    )
    args = parser.parse_args()

    try:
        new_text, summary = regenerate(args.municipalities, args.jurisdictions)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    current_text = args.jurisdictions.read_text(encoding="utf-8")
    changed = new_text != current_text

    print(f"Generated {summary['generated']} CH municipality jurisdiction rows", file=sys.stderr)
    print(f"Validated {summary['canton_count']} CH canton parents", file=sys.stderr)
    if summary["skipped_no_canton"]:
        print(
            f"Skipped {len(summary['skipped_no_canton'])} municipalities lacking "
            "canton_jurisdiction_id:",
            file=sys.stderr,
        )
        for bfs, name in summary["skipped_no_canton"]:
            print(f"  - BFS {bfs}: {name}", file=sys.stderr)

    if args.check:
        if changed:
            print(
                "ERROR: jurisdictions.yaml is out of sync with municipalities.yaml. "
                "Run: python scripts/generate_ch_municipality_jurisdictions.py",
                file=sys.stderr,
            )
            return 1
        print("OK: jurisdictions.yaml is in sync.", file=sys.stderr)
        return 0

    if args.dry_run:
        print("Dry-run: not writing.", file=sys.stderr)
        return 0

    if not changed:
        print("No changes — file already up to date.", file=sys.stderr)
        return 0

    args.jurisdictions.write_text(new_text, encoding="utf-8")
    print(f"Wrote {args.jurisdictions}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
