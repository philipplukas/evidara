#!/usr/bin/env python3
"""Fetch the BFS Gemeindeverzeichnis and generate country-overlays/ch/municipalities.yaml.

Downloads the official Swiss municipality registry (Amtliches Gemeindeverzeichnis)
from the BFS and produces a YAML file matching the schema used by the existing
pilot file. Pilot entries that already carry a law_collection block are preserved.

Usage:
    python scripts/load_ch_gemeindeverzeichnis.py [--output PATH] [--pilot PATH]

The default output path is country-overlays/ch/municipalities.yaml relative to
the repository root.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import textwrap
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError

# ---------------------------------------------------------------------------
# BFS canton code -> ISO 3166-2:CH abbreviation (lowercase)
# ---------------------------------------------------------------------------
# The BFS assigns a numeric code to each canton (1-26). These map to the ISO
# two-letter abbreviations used in our jurisdiction IDs (jur_ch_xx).
CANTON_CODE_TO_ISO: dict[int, str] = {
    1: "zh",
    2: "be",
    3: "lu",
    4: "ur",
    5: "sz",
    6: "ow",
    7: "nw",
    8: "gl",
    9: "zg",
    10: "fr",
    11: "so",
    12: "bs",
    13: "bl",
    14: "sh",
    15: "ar",
    16: "ai",
    17: "sg",
    18: "gr",
    19: "ag",
    20: "tg",
    21: "ti",
    22: "vd",
    23: "vs",
    24: "ne",
    25: "ge",
    26: "ju",
}

# ---------------------------------------------------------------------------
# Default primary language per canton (used as fallback when the BFS data does
# not include a per-municipality language field).
# ---------------------------------------------------------------------------
CANTON_PRIMARY_LANGUAGE: dict[str, str] = {
    "zh": "de",
    "be": "de",  # bilingual canton, but majority German
    "lu": "de",
    "ur": "de",
    "sz": "de",
    "ow": "de",
    "nw": "de",
    "gl": "de",
    "zg": "de",
    "fr": "fr",  # bilingual, majority French
    "so": "de",
    "bs": "de",
    "bl": "de",
    "sh": "de",
    "ar": "de",
    "ai": "de",
    "sg": "de",
    "gr": "de",  # trilingual, majority German
    "ag": "de",
    "tg": "de",
    "ti": "it",
    "vd": "fr",
    "vs": "fr",  # bilingual, but majority French
    "ne": "fr",
    "ge": "fr",
    "ju": "fr",
}


# ---------------------------------------------------------------------------
# BFS API / data download
# ---------------------------------------------------------------------------

# The BFS publishes the Gemeindeverzeichnis as a machine-readable snapshot.
# We try multiple known endpoints in order of preference.
_BFS_URLS = [
    # The agvchapp web application renders municipality data as an HTML table.
    # Use SnapshotDate to pin to a specific point in time.
    "https://www.agvchapp.bfs.admin.ch/de/state/results?SnapshotDate=01.01.2026",
]


def _fetch_url(url: str, *, timeout: int = 60) -> bytes:
    """Download *url* and return the response body bytes."""
    req = request.Request(url, headers={"User-Agent": "evidara-ch-gemeinde-loader/1.0"})
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _try_json_api(url: str, timeout: int = 60) -> list[dict] | None:
    """Try the BFS JSON API and return a list of municipality dicts, or None."""
    try:
        raw = _fetch_url(url, timeout=timeout)
    except (HTTPError, URLError, OSError) as exc:
        print(f"  [skip] JSON API failed: {exc}", file=sys.stderr)
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("  [skip] Response is not JSON", file=sys.stderr)
        return None

    # The API may return the list directly or wrapped in an envelope.
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        # Try common envelope keys
        for key in ("communes", "municipalities", "data", "results", "items"):
            if key in data and isinstance(data[key], list):
                entries = data[key]
                break
        else:
            print("  [skip] Unrecognised JSON structure", file=sys.stderr)
            return None
    else:
        return None

    if not entries:
        return None

    # Normalise into our internal dict shape.
    result: list[dict] = []
    for e in entries:
        # The JSON API uses varying field names across versions.
        bfs_id = (
            e.get("bfsNr")
            or e.get("bfs_nr")
            or e.get("communeId")
            or e.get("commune_id")
            or e.get("id")
            or e.get("gdnr")
            or e.get("GDENR")
        )
        name = (
            e.get("communeName")
            or e.get("commune_name")
            or e.get("name")
            or e.get("gdename")
            or e.get("GDENAME")
        )
        canton_code = (
            e.get("cantonId")
            or e.get("canton_id")
            or e.get("cantonCode")
            or e.get("canton_code")
            or e.get("ktnr")
            or e.get("KTNR")
        )

        if bfs_id is None or name is None or canton_code is None:
            continue

        bfs_id = int(bfs_id)
        canton_code = int(canton_code)

        # Status: only include active municipalities (status == 1 or "active")
        status = e.get("status") or e.get("commune_status") or e.get("STATUS")
        if status is not None and str(status) not in ("1", "active", "True", "true"):
            continue

        # Language region (if available)
        lang = e.get("language") or e.get("sprachcode") or e.get("SPRACHCODE")

        result.append(
            {
                "bfs_id": bfs_id,
                "name": name,
                "canton_code": canton_code,
                "lang_raw": lang,
            }
        )

    return result if result else None


def _try_csv_download(url: str, timeout: int = 60) -> list[dict] | None:
    """Try a CSV/TSV download and return a list of municipality dicts, or None."""
    try:
        raw = _fetch_url(url, timeout=timeout)
    except (HTTPError, URLError, OSError) as exc:
        print(f"  [skip] CSV download failed: {exc}", file=sys.stderr)
        return None

    text = raw.decode("utf-8-sig")  # BFS files often have a BOM

    # Detect delimiter
    first_line = text.split("\n", 1)[0]
    delimiter = "\t" if "\t" in first_line else ";"  # BFS uses semicolons

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fieldnames = reader.fieldnames or []
    if not fieldnames:
        return None

    # Find column names (BFS CSVs use German headers)
    def _find_col(*candidates: str) -> str | None:
        lower_fields = {f.lower().strip(): f for f in fieldnames}
        for c in candidates:
            if c.lower() in lower_fields:
                return lower_fields[c.lower()]
        return None

    col_bfs = _find_col("GDENR", "BFS-Nr", "bfs_nr", "commune_id", "Gemeindenummer", "BFS Gde-nummer")
    col_name = _find_col("GDENAME", "Gemeindename", "commune_name", "name")
    col_canton = _find_col("KTNR", "Kantonsnummer", "canton_id", "canton_code", "KT")
    col_status = _find_col("STATUS", "Gemeindestatus", "commune_status")
    col_lang = _find_col("SPRACHCODE", "Sprachcode", "language")

    if col_bfs is None or col_name is None or col_canton is None:
        print(
            f"  [skip] Cannot map CSV columns (found: {fieldnames[:10]})",
            file=sys.stderr,
        )
        return None

    result: list[dict] = []
    for row in reader:
        bfs_id_str = row.get(col_bfs, "").strip()
        name = row.get(col_name, "").strip()
        canton_str = row.get(col_canton, "").strip()
        if not bfs_id_str or not name or not canton_str:
            continue

        try:
            bfs_id = int(bfs_id_str)
            canton_code = int(canton_str)
        except ValueError:
            continue

        # Skip retired municipalities
        if col_status:
            status_val = row.get(col_status, "").strip()
            # In BFS data, status 0 = retired/merged, 1 = active
            if status_val and status_val not in ("1", "active"):
                continue

        lang_raw = row.get(col_lang, "").strip() if col_lang else None

        result.append(
            {
                "bfs_id": bfs_id,
                "name": name,
                "canton_code": canton_code,
                "lang_raw": lang_raw,
            }
        )

    return result if result else None


def fetch_municipalities(timeout: int = 60) -> list[dict]:
    """Fetch the municipality list from BFS, trying multiple endpoints."""
    for url in _BFS_URLS:
        print(f"Trying {url} ...", file=sys.stderr)

        if "api" in url.lower() and ("json" in url.lower() or "communes" in url.lower()):
            entries = _try_json_api(url, timeout=timeout)
        else:
            entries = _try_csv_download(url, timeout=timeout)

        # If the first URL returns what looks like JSON but our JSON parser
        # didn't handle it, fall through and try it as CSV too.
        if entries is None and "api" in url.lower():
            entries = _try_csv_download(url, timeout=timeout)

        if entries:
            print(f"  -> loaded {len(entries)} municipalities", file=sys.stderr)
            return entries

    print(
        "ERROR: Could not fetch municipality data from any BFS endpoint.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Language mapping
# ---------------------------------------------------------------------------

_BFS_LANG_MAP: dict[str, str] = {
    # BFS numeric Sprachcode
    "1": "de",
    "2": "fr",
    "3": "it",
    "4": "rm",
    # Text variants
    "de": "de",
    "fr": "fr",
    "it": "it",
    "rm": "rm",
    "deutsch": "de",
    "französisch": "fr",
    "italienisch": "it",
    "rätoromanisch": "rm",
}


def _resolve_language(raw: str | None, canton_iso: str) -> str:
    """Map a BFS language code to ISO 639-1, falling back to the canton default."""
    if raw:
        lang = _BFS_LANG_MAP.get(raw.lower().strip())
        if lang:
            return lang
    return CANTON_PRIMARY_LANGUAGE.get(canton_iso, "de")


# ---------------------------------------------------------------------------
# Pilot data preservation
# ---------------------------------------------------------------------------


def _load_pilot_entries(path: Path) -> dict[int, dict]:
    """Load existing pilot entries keyed by bfs_id.

    We do a minimal YAML-like parse to avoid requiring PyYAML as a dependency,
    but if PyYAML is available we prefer it.
    """
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(text)
        if not data or "municipalities" not in data:
            return {}
        result: dict[int, dict] = {}
        for entry in data["municipalities"]:
            bfs_id = entry.get("bfs_id")
            if bfs_id is not None:
                result[int(bfs_id)] = entry
        return result
    except ImportError:
        pass

    # Fallback: crude line-based extraction for law_collection blocks.
    # This is only needed if PyYAML is not installed.
    result = {}
    current_bfs: int | None = None
    current_entry: dict = {}
    in_law_collection = False
    lc_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- bfs_id:"):
            # Save previous entry
            if current_bfs is not None and lc_lines:
                current_entry["_law_collection_lines"] = lc_lines
                result[current_bfs] = current_entry
            elif current_bfs is not None:
                result[current_bfs] = current_entry
            # Start new entry
            val = stripped.split(":", 1)[1].strip()
            try:
                current_bfs = int(val)
            except ValueError:
                current_bfs = None
            current_entry = {}
            in_law_collection = False
            lc_lines = []
        elif stripped.startswith("names:") and current_bfs is not None:
            current_entry["_has_names"] = True
        elif stripped.startswith("law_collection:") and current_bfs is not None:
            in_law_collection = True
            lc_lines = []
        elif in_law_collection:
            if stripped and not stripped.startswith("-") and ":" in stripped:
                lc_lines.append(line)
            else:
                in_law_collection = False

    # Don't forget the last entry
    if current_bfs is not None:
        if lc_lines:
            current_entry["_law_collection_lines"] = lc_lines
        result[current_bfs] = current_entry

    return result


# ---------------------------------------------------------------------------
# YAML output
# ---------------------------------------------------------------------------

_HEADER = """\
version: 1
country_code: CH

# Swiss municipality registry (Gemeinden / communes / comuni / vischnancas).
#
# Scope:
#   This file is an out-of-band registry --- it is NOT part of the core
#   reference-data seeds consumed by platform-control's Jurisdiction /
#   Authority contract. Municipalities are tracked here because:
#     - there are ~2,100 of them, which is too large for the curated
#       reference-data.yaml pattern used by other overlays,
#     - not every municipality publishes a structured law collection, so
#       treating each as a first-class Authority would inflate the taxonomy
#       with non-publishing entities,
#     - publication practice varies (own Rechtssammlung, cantonal portal,
#       PDFs only, or print-only), and that variation is modelled below
#       with an optional law_collection block.
#
# Identifier:
#   Each entry is keyed by the BFS number (Bundesamt fuer Statistik
#   Gemeindenummer), the stable Swiss identifier for a municipality.
#
# Parent linkage:
#   canton_jurisdiction_id references an entry in reference-data.yaml.
#
# Generated by: scripts/load_ch_gemeindeverzeichnis.py
# Source: BFS Amtliches Gemeindeverzeichnis der Schweiz
#
# Attribution / terms:
#   Quelle: Bundesamt fuer Statistik (BFS) --- Amtliches Gemeindeverzeichnis
#   der Schweiz. Dataset "Historisiertes Gemeindeverzeichnis der Schweiz",
#   https://opendata.swiss/de/dataset/historisiertes-gemeindeverzeichnis-der-schweiz
#   Nutzungsbedingungen: https://opendata.swiss/terms-of-use#terms_open
#   ("Freie Nutzung" --- commercial use permitted, source citation recommended).
#
#   The citation is recorded because these rows are redistributed here, not
#   because terms_open compels it -- that tier recommends attribution rather
#   than requiring it. Verified against the opendata.swiss catalogue entry for
#   this exact resource URL on 2026-09-03; see THIRD-PARTY-NOTICES.md for the
#   evidence and for the one question left open (BFS's site-wide legal notice
#   is stricter than the catalogue entry).

schema:
  required:
    - bfs_id
    - canton_jurisdiction_id
    - name
    - primary_language
  optional:
    - names  # localized display names keyed by language code
    - law_collection
  law_collection_shape:
    required:
      - publisher
      - format
    optional:
      - url
      - language
      - note

municipalities:
"""


def _yaml_escape(s: str) -> str:
    """Return *s* in a YAML-safe form, quoting if necessary."""
    # Quote strings that contain YAML-special characters
    if any(c in s for c in (":", "#", "'", '"', "{", "}", "[", "]", ",", "&", "*", "?", "|", "-", "<", ">", "=", "!", "%", "@", "`")):
        escaped = s.replace("'", "''")
        return f"'{escaped}'"
    if s.lower() in ("true", "false", "null", "yes", "no", "on", "off"):
        return f"'{s}'"
    return s


def _render_pilot_entry(pilot: dict) -> str:
    """Render a pilot entry that has a law_collection block using PyYAML data."""
    lines: list[str] = []

    # names block
    names = pilot.get("names")
    if names and isinstance(names, dict):
        lines.append("    names:")
        for lang_code, localized in sorted(names.items()):
            lines.append(f"      {lang_code}: {_yaml_escape(localized)}")

    # law_collection block
    lc = pilot.get("law_collection")
    if lc and isinstance(lc, dict):
        lines.append("    law_collection:")
        for key in ("publisher", "format", "url", "language", "note"):
            if key in lc:
                lines.append(f"      {key}: {_yaml_escape(str(lc[key]))}")

    # Fallback for crude parser
    lc_lines = pilot.get("_law_collection_lines")
    if lc_lines and not lc:
        lines.append("    law_collection:")
        for l in lc_lines:
            lines.append(l)

    return "\n".join(lines) if lines else ""


def generate_yaml(
    municipalities: list[dict],
    pilot_entries: dict[int, dict],
    valid_jurisdictions: set[str],
) -> str:
    """Generate the full YAML string."""
    # Sort by canton code, then by bfs_id
    municipalities.sort(key=lambda m: (m["canton_code"], m["bfs_id"]))

    out = io.StringIO()
    out.write(_HEADER)

    current_canton: int | None = None
    invalid_jur: list[str] = []

    for m in municipalities:
        bfs_id: int = m["bfs_id"]
        canton_code: int = m["canton_code"]
        canton_iso = CANTON_CODE_TO_ISO.get(canton_code)
        if canton_iso is None:
            print(
                f"  WARNING: unknown canton code {canton_code} for {m['name']} (BFS {bfs_id}), skipping",
                file=sys.stderr,
            )
            continue

        jur_id = f"jur_ch_{canton_iso}"
        if valid_jurisdictions and jur_id not in valid_jurisdictions:
            invalid_jur.append(jur_id)

        lang = _resolve_language(m.get("lang_raw"), canton_iso)

        # Canton separator comment
        if canton_code != current_canton:
            current_canton = canton_code
            canton_label = canton_iso.upper()
            out.write(f"\n  # --- Canton {canton_label} ---\n")

        out.write(f"  - bfs_id: {bfs_id}\n")
        out.write(f"    canton_jurisdiction_id: {jur_id}\n")
        out.write(f"    name: {_yaml_escape(m['name'])}\n")
        out.write(f"    primary_language: {lang}\n")

        # Preserve pilot data (names + law_collection)
        pilot = pilot_entries.get(bfs_id)
        if pilot:
            extra = _render_pilot_entry(pilot)
            if extra:
                out.write(extra + "\n")

        out.write("\n")

    if invalid_jur:
        unique = sorted(set(invalid_jur))
        print(
            f"WARNING: {len(unique)} canton jurisdiction IDs not found in seeds: {unique}",
            file=sys.stderr,
        )

    return out.getvalue()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def load_valid_jurisdictions(path: Path) -> set[str]:
    """Load jurisdiction IDs from the reference seeds file."""
    if not path.exists():
        print(f"WARNING: jurisdiction seeds not found at {path}", file=sys.stderr)
        return set()

    text = path.read_text(encoding="utf-8")
    ids: set[str] = set()

    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(text)
        if data and "items" in data:
            for item in data["items"]:
                jid = item.get("jurisdiction_id")
                if jid:
                    ids.add(jid)
        return ids
    except ImportError:
        pass

    # Crude fallback
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- jurisdiction_id:"):
            val = stripped.split(":", 1)[1].strip()
            if val:
                ids.add(val)
    return ids


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(description="Generate Swiss municipality YAML from BFS data")
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "country-overlays" / "ch" / "municipalities.yaml",
        help="Output YAML path (default: country-overlays/ch/municipalities.yaml)",
    )
    parser.add_argument(
        "--pilot",
        type=Path,
        default=None,
        help="Path to existing pilot file to preserve law_collection blocks from (default: same as --output)",
    )
    parser.add_argument(
        "--jurisdictions",
        type=Path,
        default=repo_root / "platform-control" / "seeds" / "reference" / "jurisdictions.yaml",
        help="Path to jurisdiction seeds for validation",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout in seconds",
    )
    args = parser.parse_args()

    pilot_path = args.pilot if args.pilot else args.output

    print("Loading existing pilot entries ...", file=sys.stderr)
    pilot_entries = _load_pilot_entries(pilot_path)
    print(f"  -> {len(pilot_entries)} pilot entries with law_collection data", file=sys.stderr)

    print("Loading jurisdiction seeds ...", file=sys.stderr)
    valid_jurs = load_valid_jurisdictions(args.jurisdictions)
    print(f"  -> {len(valid_jurs)} jurisdiction IDs loaded", file=sys.stderr)

    print("Fetching BFS Gemeindeverzeichnis ...", file=sys.stderr)
    municipalities = fetch_municipalities(timeout=args.timeout)
    print(f"  -> {len(municipalities)} active municipalities", file=sys.stderr)

    print("Generating YAML ...", file=sys.stderr)
    yaml_text = generate_yaml(municipalities, pilot_entries, valid_jurs)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml_text, encoding="utf-8")
    print(f"Wrote {args.output} ({len(municipalities)} municipalities)", file=sys.stderr)

    # Quick validation summary
    canton_counts: dict[str, int] = {}
    for m in municipalities:
        iso = CANTON_CODE_TO_ISO.get(m["canton_code"], "??")
        canton_counts[iso] = canton_counts.get(iso, 0) + 1
    print("\nMunicipalities per canton:", file=sys.stderr)
    for iso in sorted(canton_counts):
        print(f"  {iso.upper()}: {canton_counts[iso]}", file=sys.stderr)


if __name__ == "__main__":
    main()
