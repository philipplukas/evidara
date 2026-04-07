"""Download RIS documents listed in documents.csv from the OGD-RIS API.

Usage:
    python eval/download_ris_documents.py [output_dir]

Downloads XML versions of all documents in the catalog to output_dir/xml/
and HTML versions to output_dir/html/.
"""

from __future__ import annotations

import csv
import sys
import time
import urllib.request
from pathlib import Path

EVAL_DIR = Path(__file__).parent
_USER_AGENT = "evidara-eval-download/1.0 (+https://evidara.ai)"


def download_catalog(output_dir: Path) -> None:
    catalog_path = EVAL_DIR / "documents.csv"
    xml_dir = output_dir / "xml"
    html_dir = output_dir / "html"
    xml_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)

    with open(catalog_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Downloading {len(rows)} documents...")
    success = 0
    skipped = 0
    failed = 0

    for row in rows:
        doc_id = row["doc_id"]
        ris_id = row.get("ris_id", "")

        for fmt, url_key, target_dir, ext in [
            ("xml", "content_url_xml", xml_dir, ".xml"),
            ("html", "content_url_html", html_dir, ".html"),
        ]:
            url = row.get(url_key, "").strip()
            if not url:
                skipped += 1
                continue

            filename = f"{doc_id}_{ris_id}{ext}" if ris_id else f"{doc_id}{ext}"
            target_path = target_dir / filename

            if target_path.exists() and target_path.stat().st_size > 0:
                print(f"  [skip] {filename} (already exists)")
                skipped += 1
                continue

            try:
                req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content = resp.read()
                target_path.write_bytes(content)
                print(f"  [ok]   {filename} ({len(content):,} bytes)")
                success += 1
                time.sleep(0.3)
            except Exception as exc:
                print(f"  [FAIL] {filename}: {exc}")
                failed += 1

    print(f"\nDone: {success} downloaded, {skipped} skipped, {failed} failed")


def main() -> None:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else EVAL_DIR / "data"
    download_catalog(output_dir)


if __name__ == "__main__":
    main()
