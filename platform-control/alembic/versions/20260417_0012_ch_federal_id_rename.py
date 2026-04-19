"""Rename CH federal authority IDs to the flat scheme + restore jur_ch_federal.

Context: commit 9549fba (in PR #241) renamed three CH federal authorities
to a prefixed form (auth_ch_fedlex, auth_ch_bundesgericht,
auth_ch_bundesverwaltungsgericht) and dropped jur_ch_federal from the
jurisdiction seed — but ~20 downstream consumers (DI pipeline, contract
examples, golden datasets, fast-loop scripts, canary workflow, scraping
fixtures) still use the flat form. The authorities table has UNIQUE
constraints on `slug` and `name`, so the seeder cannot resolve the
collision on its own; a PK rename plus FK propagation are needed.

This migration reconciles the DB to the flat scheme and adds
jur_ch_federal as a distinct row, then updates the authorities' FK
jurisdiction from jur_ch to jur_ch_federal.

The sequence is INSERT-new / UPDATE-FKs / DELETE-old so no FK
constraint is violated on databases whose FKs do not declare
ON UPDATE CASCADE (the SQLAlchemy default).

Revision ID: 20260417_0012
Revises: 20260417_0011
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260417_0012"
down_revision = "20260417_0011"
branch_labels = None
depends_on = None


# (old_id, new_id) tuples for the authorities being renamed.
_AUTHORITY_RENAMES: tuple[tuple[str, str], ...] = (
    ("auth_ch_fedlex", "auth_fedlex"),
    ("auth_ch_bundesgericht", "auth_bger"),
    ("auth_ch_bundesverwaltungsgericht", "auth_bvger"),
)

# Tables whose authority_id FK must be re-pointed during the rename.
# Keep this in sync with ForeignKey("authorities.authority_id") usages.
_AUTHORITY_FK_TABLES: tuple[tuple[str, str], ...] = (
    ("sources", "authority_id"),
    ("scrape_targets", "authority_id"),
    ("authorities", "parent_id"),
)


# Prefix applied to slug/name on the soon-to-be-deleted old row to free up
# the UNIQUE columns for the new row during the rename window. The old row
# is DELETE-d a few statements later so the placeholder never persists.
_STAGING_PREFIX = "__renaming__"


def _rename_authority_row(
    conn: sa.Connection,
    *,
    old_id: str,
    new_id: str,
    new_jurisdiction_id: str,
) -> bool:
    """Rename old_id -> new_id (INSERT/UPDATE-FKs/DELETE).

    Portable across SQLite + PostgreSQL without ON UPDATE CASCADE or
    DEFERRED constraints: the old row's UNIQUE columns (slug, name) are
    temporarily prefixed so the new row can be inserted with the canonical
    slug/name, then FK references are re-pointed, then the old row is
    deleted.
    """
    row = conn.execute(
        sa.text(
            "SELECT parent_id, path, depth, name, slug, created_at, updated_at "
            "FROM authorities WHERE authority_id = :old_id"
        ),
        {"old_id": old_id},
    ).fetchone()
    if row is None:
        return False
    exists = conn.execute(
        sa.text("SELECT 1 FROM authorities WHERE authority_id = :new_id"),
        {"new_id": new_id},
    ).fetchone()
    if exists is not None:
        return False

    # 1. Free the UNIQUE slug/name on the old row so the new INSERT doesn't
    # collide. The prefixed values are transient; the row is deleted below.
    conn.execute(
        sa.text(
            "UPDATE authorities SET "
            "slug = :staged_slug, name = :staged_name "
            "WHERE authority_id = :old_id"
        ),
        {
            "old_id": old_id,
            "staged_slug": _STAGING_PREFIX + row.slug,
            "staged_name": _STAGING_PREFIX + row.name,
        },
    )

    # 2. Insert the new row with the canonical slug/name + new jurisdiction.
    conn.execute(
        sa.text(
            "INSERT INTO authorities "
            "(authority_id, parent_id, path, depth, jurisdiction_id, name, slug, "
            " created_at, updated_at) "
            "VALUES (:new_id, :parent_id, :path, :depth, :jurisdiction_id, "
            " :name, :slug, :created_at, :updated_at)"
        ),
        {
            "new_id": new_id,
            "parent_id": row.parent_id,
            "path": row.path,
            "depth": row.depth,
            "jurisdiction_id": new_jurisdiction_id,
            "name": row.name,
            "slug": row.slug,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        },
    )

    # 3. Re-point every FK that currently references the old row.
    for table, column in _AUTHORITY_FK_TABLES:
        conn.execute(
            sa.text(f"UPDATE {table} SET {column} = :new_id WHERE {column} = :old_id"),
            {"new_id": new_id, "old_id": old_id},
        )

    # 4. Drop the (now orphaned, placeholder-named) old row.
    conn.execute(
        sa.text("DELETE FROM authorities WHERE authority_id = :old_id"),
        {"old_id": old_id},
    )
    return True


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Ensure jur_ch_federal exists. Copy compliance_policy_id from jur_ch
    # so federal acquisition inherits the same policy, matching what main's
    # #262 decision did for jur_ch itself.
    jur_ch = conn.execute(
        sa.text("SELECT compliance_policy_id FROM jurisdictions WHERE jurisdiction_id = 'jur_ch'")
    ).fetchone()
    if jur_ch is not None:
        exists = conn.execute(
            sa.text("SELECT 1 FROM jurisdictions WHERE jurisdiction_id = 'jur_ch_federal'")
        ).fetchone()
        if exists is None:
            conn.execute(
                sa.text(
                    "INSERT INTO jurisdictions "
                    "(jurisdiction_id, parent_id, path, depth, name, slug, "
                    " compliance_policy_id, created_at, updated_at) "
                    "VALUES ('jur_ch_federal', NULL, NULL, 0, 'Swiss Confederation', "
                    " 'ch-federal', :compliance_policy_id, "
                    " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"compliance_policy_id": jur_ch.compliance_policy_id},
            )

    # 2. For each rename: stage the old row's UNIQUE columns, insert the
    # new row, re-point FKs, delete the old row.
    for old_id, new_id in _AUTHORITY_RENAMES:
        _rename_authority_row(
            conn, old_id=old_id, new_id=new_id, new_jurisdiction_id="jur_ch_federal"
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Reverse the authority renames (same pattern, swapped).
    for old_id, new_id in _AUTHORITY_RENAMES:
        _rename_authority_row(conn, old_id=new_id, new_id=old_id, new_jurisdiction_id="jur_ch")

    # Drop jur_ch_federal only if no authority still references it.
    still_refs = conn.execute(
        sa.text("SELECT 1 FROM authorities WHERE jurisdiction_id = 'jur_ch_federal' LIMIT 1")
    ).fetchone()
    if still_refs is None:
        conn.execute(sa.text("DELETE FROM jurisdictions WHERE jurisdiction_id = 'jur_ch_federal'"))
