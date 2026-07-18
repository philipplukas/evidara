"""ADR-0036 Phase 0 spike — write a canonical surface through the catalog.

Proves the write half of the claim: DI can publish `published_documents` as an
Iceberg table registered in **Nessie**, addressed by *name*
(`evidara.published_documents`) rather than a hardcoded Delta URI — and with no
Spark (pyiceberg + delta-free, pure Python).

Run:  uv run --with pyiceberg[s3fs,pyarrow] python spikes/lakehouse/write_surface.py
Then: read it back with SQL via Trino (see README).
"""

from __future__ import annotations

import os

import pyarrow as pa
from pyiceberg.catalog import load_catalog

NAMESPACE = "evidara"
TABLE = f"{NAMESPACE}.published_documents"

# Nessie vends *server-side* storage config to clients (it advertises the
# in-network `minio:9000`), so the data-file write only resolves from inside the
# compose network. Run this in-network — which is also how the DI consumer will
# run it. Env-configurable so a host run can still target the published ports.
NESSIE_URI = os.environ.get("NESSIE_URI", "http://nessie:19120/iceberg/main")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")

CATALOG_CONFIG = {
    "type": "rest",
    # Nessie's Iceberg REST endpoint, pinned to the `main` branch. Swapping the
    # ref here is how "corpus as of <branch/tag>" works (ADR-0036 phase 4).
    "uri": NESSIE_URI,
    "warehouse": "warehouse",
    "s3.endpoint": S3_ENDPOINT,
    "s3.access-key-id": "minioadmin",
    "s3.secret-access-key": "minioadmin",
    "s3.path-style-access": "true",
}

# A deliberately realistic slice of the canonical surface: the Bundesverfassung
# row the M13 loop actually acquires, including the temporal-validity fields
# ADR-0033 cares about.
ROWS = pa.Table.from_pylist(
    [
        {
            "document_id": "doc_ch_bv_101",
            "title": "Bundesverfassung der Schweizerischen Eidgenossenschaft",
            "jurisdiction_id": "jur_ch_federal",
            "eli_uri": "https://fedlex.data.admin.ch/eli/cc/1999/404/20240303",
            "in_force_from": "2024-03-03",
            "in_force_until": "2028-12-31",
            "body": "Art. 1 Die Schweizerische Eidgenossenschaft ...",
        },
        {
            "document_id": "doc_ch_tschg_455",
            "title": "Tierschutzgesetz",
            "jurisdiction_id": "jur_ch_federal",
            "eli_uri": "https://fedlex.data.admin.ch/eli/cc/2008/414",
            "in_force_from": "2008-09-01",
            "in_force_until": None,
            "body": "Art. 1 Zweck dieses Gesetzes ist der Schutz der Wuerde ...",
        },
    ]
)


def main() -> None:
    catalog = load_catalog("nessie", **CATALOG_CONFIG)

    catalog.create_namespace_if_not_exists(NAMESPACE)
    print(f"namespace ready: {NAMESPACE}")

    if catalog.table_exists(TABLE):
        catalog.drop_table(TABLE)
    table = catalog.create_table(TABLE, schema=ROWS.schema)
    print(f"created iceberg table: {TABLE}")

    table.append(ROWS)
    print(f"appended {ROWS.num_rows} rows")

    scanned = table.scan().to_arrow()
    print(f"read back via pyiceberg: {scanned.num_rows} rows")
    for row in scanned.to_pylist():
        print(f"  - {row['document_id']}: {row['title'][:48]} "
              f"[{row['in_force_from']} → {row['in_force_until'] or 'open'}]")


if __name__ == "__main__":
    main()
