#!/usr/bin/env python3
"""Merge law_collection data from a CSV into a country's municipalities.yaml.

Operators research municipality law-collection URLs and record them in a CSV.
This script reads that CSV and merges law_collection blocks into the existing
municipalities.yaml, preserving all other fields.

Usage:
    # Dry-run (preview changes without writing):
    python scripts/merge_municipality_law_collections.py \
        --country CH --input law_collections.csv --dry-run

    # Apply:
    python scripts/merge_municipality_law_collections.py \
        --country CH --input law_collections.csv

CSV columns:
    id          Required. BFS number (CH) or AGS code (DE).
    publisher   Required. Name of the publishing body.
    format      Required. Publication format (html, pdf, etc.).
    url         Optional. URL of the law collection.
    language    Optional. ISO 639-1 language code (de, fr, it, rm).
    note        Optional. Free-text note for operators.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

COUNTRY_CONFIG: dict[str, dict] = {
    "CH": {
        "file": REPO_ROOT / "country-overlays" / "ch" / "municipalities.yaml",
        "id_field": "bfs_id",
    },
    "DE": {
        "file": REPO_ROOT / "country-overlays" / "de" / "municipalities.yaml",
        "id_field": "ags",
    },
}

REQUIRED_CSV_COLUMNS = {"id", "publisher", "format"}
OPTIONAL_CSV_COLUMNS = {"url", "language", "note"}
ALL_CSV_COLUMNS = REQUIRED_CSV_COLUMNS | OPTIONAL_CSV_COLUMNS

# law_collection field order (matches schema declaration)
LC_FIELD_ORDER = ["publisher", "format", "url", "language", "note"]


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


def load_csv(path: Path, *, id_field: str) -> tuple[list[dict], list[str]]:
    """Load the input CSV and return (rows, warnings).

    Each row dict has the municipality id (coerced to match the YAML type)
    and the law_collection fields.
    """
    warnings: list[str] = []
    rows: list[dict] = []

    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            warnings.append("CSV file has no header row")
            return rows, warnings

        header_set = {h.strip().lower() for h in reader.fieldnames}
        missing = REQUIRED_CSV_COLUMNS - header_set
        if missing:
            warnings.append(f"CSV missing required columns: {sorted(missing)}")
            return rows, warnings

        for line_no, raw_row in enumerate(reader, start=2):
            # Normalise keys to lowercase
            row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items()}

            raw_id = row.get("id", "")
            if not raw_id:
                warnings.append(f"CSV line {line_no}: empty id, skipping")
                continue

            # For CH the id is an int; for DE it is a zero-padded string.
            if id_field == "bfs_id":
                try:
                    entry_id: int | str = int(raw_id)
                except ValueError:
                    warnings.append(f"CSV line {line_no}: non-integer id {raw_id!r}, skipping")
                    continue
            else:
                entry_id = raw_id  # AGS stays as string

            publisher = row.get("publisher", "")
            fmt = row.get("format", "")
            if not publisher or not fmt:
                warnings.append(
                    f"CSV line {line_no} (id={raw_id}): publisher and format are required, skipping"
                )
                continue

            lc: dict = {"publisher": publisher, "format": fmt}
            for opt in ("url", "language", "note"):
                val = row.get(opt, "")
                if val:
                    lc[opt] = val

            rows.append({"id": entry_id, "law_collection": lc})

    return rows, warnings


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------


def merge(
    municipalities: list[dict],
    csv_rows: list[dict],
    id_field: str,
) -> tuple[int, int, int, list[str]]:
    """Merge law_collection from CSV rows into municipalities list (in-place).

    Returns (matched, already_had, updated, unmatched_ids).
    """
    # Build index: id -> municipality dict
    index: dict[int | str, dict] = {}
    for m in municipalities:
        key = m.get(id_field)
        if key is not None:
            index[key] = m

    matched = 0
    already_had = 0
    updated = 0
    unmatched_ids: list[str] = []

    for row in csv_rows:
        entry_id = row["id"]
        m = index.get(entry_id)
        if m is None:
            unmatched_ids.append(str(entry_id))
            continue

        matched += 1
        had_lc = "law_collection" in m
        if had_lc:
            already_had += 1

        # Build ordered law_collection dict
        lc_ordered: dict = {}
        for field in LC_FIELD_ORDER:
            if field in row["law_collection"]:
                lc_ordered[field] = row["law_collection"][field]

        m["law_collection"] = lc_ordered
        updated += 1

    return matched, already_had, updated, unmatched_ids


# ---------------------------------------------------------------------------
# YAML round-trip helpers
# ---------------------------------------------------------------------------


def _represent_str(dumper: yaml.Dumper, data: str) -> yaml.Node:
    """Use plain style for simple strings, single-quoted for problematic ones."""
    if any(c in data for c in (":", "#", "'", '"', "{", "}", "[", "]", "&", "*", "?", "|", ">", "!", "%", "@", "`")):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
    if data.lower() in ("true", "false", "null", "yes", "no", "on", "off"):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class _OrderedDumper(yaml.SafeDumper):
    """Dumper that preserves dict insertion order and uses clean formatting."""
    pass


_OrderedDumper.add_representer(str, _represent_str)


def load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_yaml(data: dict, path: Path) -> None:
    """Write YAML preserving the hand-authored style as closely as possible.

    PyYAML's dumper cannot perfectly reproduce the hand-authored formatting
    (canton separator comments, blank lines between entries, etc.), so we
    regenerate the file using the same template approach as
    load_ch_gemeindeverzeichnis.py.
    """
    # We re-use the file's own header (everything before "municipalities:")
    # and regenerate only the municipalities list to keep comments intact.
    original_text = path.read_text(encoding="utf-8")
    header_end = original_text.find("\nmunicipalities:")
    if header_end == -1:
        # Fallback: dump with PyYAML
        path.write_text(
            yaml.dump(data, Dumper=_OrderedDumper, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return

    header = original_text[: header_end + len("\nmunicipalities:")]

    # Detect country from the data
    country_code = data.get("country_code", "CH")
    id_field = "bfs_id" if country_code == "CH" else "ags"

    lines = [header, ""]
    municipalities = data.get("municipalities", [])

    # Group by parent jurisdiction for canton/land separator comments
    current_parent: str | None = None
    parent_field = "canton_jurisdiction_id" if country_code == "CH" else "land_jurisdiction_id"

    for m in municipalities:
        parent = m.get(parent_field, "")
        if parent != current_parent:
            current_parent = parent
            # Extract label from jurisdiction id (e.g. jur_ch_ag -> AG, jur_de_nw -> NW)
            label = parent.rsplit("_", 1)[-1].upper() if parent else "??"
            prefix = "Canton" if country_code == "CH" else "Land"
            lines.append(f"  # --- {prefix} {label} ---")

        # Entry fields
        id_val = m.get(id_field)
        if id_field == "ags":
            lines.append(f'  - {id_field}: "{id_val}"')
        else:
            lines.append(f"  - {id_field}: {id_val}")
        lines.append(f"    {parent_field}: {parent}")
        lines.append(f"    name: {_yaml_escape_field(m.get('name', ''))}")
        lines.append(f"    primary_language: {m.get('primary_language', 'de')}")

        # Optional names block
        names = m.get("names")
        if names and isinstance(names, dict):
            lines.append("    names:")
            for lang_code in sorted(names):
                lines.append(f"      {lang_code}: {_yaml_escape_field(names[lang_code])}")

        # Optional law_collection block
        lc = m.get("law_collection")
        if lc and isinstance(lc, dict):
            lines.append("    law_collection:")
            for field in LC_FIELD_ORDER:
                if field in lc:
                    lines.append(f"      {field}: {_yaml_escape_field(str(lc[field]))}")

        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _yaml_escape_field(s: str) -> str:
    """Return *s* in a YAML-safe form, quoting if necessary."""
    if any(c in s for c in (":", "#", "'", '"', "{", "}", "[", "]", ",", "&", "*", "?", "|", "-", "<", ">", "=", "!", "%", "@", "`")):
        escaped = s.replace("'", "''")
        return f"'{escaped}'"
    if s.lower() in ("true", "false", "null", "yes", "no", "on", "off"):
        return f"'{s}'"
    return s


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge law_collection data from CSV into municipalities.yaml",
    )
    parser.add_argument(
        "--country",
        required=True,
        choices=sorted(COUNTRY_CONFIG),
        help="Country code (CH or DE)",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to the input CSV file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing the YAML file",
    )
    args = parser.parse_args()

    config = COUNTRY_CONFIG[args.country]
    yaml_path: Path = config["file"]
    id_field: str = config["id_field"]

    if not args.input.exists():
        print(f"ERROR: Input CSV not found: {args.input}", file=sys.stderr)
        return 1
    if not yaml_path.exists():
        print(f"ERROR: municipalities.yaml not found: {yaml_path}", file=sys.stderr)
        return 1

    # Load CSV
    print(f"Loading CSV from {args.input} ...", file=sys.stderr)
    csv_rows, csv_warnings = load_csv(args.input, id_field=id_field)
    for w in csv_warnings:
        print(f"  WARNING: {w}", file=sys.stderr)
    if not csv_rows:
        print("ERROR: No valid rows in CSV", file=sys.stderr)
        return 1
    print(f"  -> {len(csv_rows)} valid CSV rows", file=sys.stderr)

    # Load YAML
    print(f"Loading {yaml_path} ...", file=sys.stderr)
    data = load_yaml(yaml_path)
    municipalities = data.get("municipalities", [])
    print(f"  -> {len(municipalities)} municipalities", file=sys.stderr)

    # Merge
    matched, already_had, updated, unmatched_ids = merge(municipalities, csv_rows, id_field)

    # Report
    print(file=sys.stderr)
    print("--- Merge report ---", file=sys.stderr)
    print(f"  CSV rows:            {len(csv_rows)}", file=sys.stderr)
    print(f"  Matched:             {matched}", file=sys.stderr)
    print(f"  Updated:             {updated}", file=sys.stderr)
    print(f"  Already had LC:      {already_had} (overwritten)", file=sys.stderr)
    print(f"  Unmatched CSV rows:  {len(unmatched_ids)}", file=sys.stderr)
    if unmatched_ids:
        print(f"  Unmatched IDs:       {', '.join(unmatched_ids)}", file=sys.stderr)
    print(file=sys.stderr)

    if args.dry_run:
        print("DRY RUN -- no file written.", file=sys.stderr)
        return 0

    # Write
    print(f"Writing {yaml_path} ...", file=sys.stderr)
    dump_yaml(data, yaml_path)
    print("Done.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
