"""Fix operator seed IDs to match the contract ULID pattern (M11/B2, #453).

Migration 20260426_0016 (#456) seeded operator rows with legible
identifiers like ``op_local_dev`` that violate
``contracts/schemas/corrections.json``'s
``^op_[0-9a-hjkmnp-tv-z]{26}$`` pattern. The mismatch went unnoticed
because B1 didn't yet read the seeds back through the API; B2
(this PR) threads the Principal into the corrections router and trips
the contract pattern as soon as ``operator_id`` lands in a response.

We update the three rows in place (cheap — there's no FK referencing
``operators.operator_id`` yet) instead of dropping + re-seeding so any
code already storing references to these IDs (none expected, but
defensive) keeps working at the row level.

Revision ID: 20260426_0017
Revises: 20260426_0016
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op

revision = "20260426_0017"
down_revision = "20260426_0016"
branch_labels = None
depends_on = None


# Deterministic ULID-shaped IDs reserved for system-seeded operators.
# Crockford alphabet (no i/l/o/u); 26 chars after the `op_` prefix.
_LOCAL_DEV_ID = "op_00000000000000000000000001"
_SCOPED_OPERATOR_ID = "op_00000000000000000000000002"
_LEGACY_FULL_ACCESS_ID = "op_00000000000000000000000003"


def upgrade() -> None:
    op.execute(
        f"UPDATE operators SET operator_id = '{_LOCAL_DEV_ID}' WHERE auth_principal = 'local_dev'"
    )
    op.execute(
        f"UPDATE operators SET operator_id = '{_SCOPED_OPERATOR_ID}' "
        "WHERE auth_principal = 'scoped_operator_key'"
    )
    op.execute(
        f"UPDATE operators SET operator_id = '{_LEGACY_FULL_ACCESS_ID}' "
        "WHERE auth_principal = 'legacy_full_access'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE operators SET operator_id = 'op_local_dev' WHERE auth_principal = 'local_dev'"
    )
    op.execute(
        "UPDATE operators SET operator_id = 'op_scoped_operator_key' "
        "WHERE auth_principal = 'scoped_operator_key'"
    )
    op.execute(
        "UPDATE operators SET operator_id = 'op_legacy_full_access' "
        "WHERE auth_principal = 'legacy_full_access'"
    )
