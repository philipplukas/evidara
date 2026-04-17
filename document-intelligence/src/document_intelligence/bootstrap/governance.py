"""Render SQL for document-intelligence Unity Catalog governance.

Two layers:

- ``render_grants_sql``: GRANT statements for three principal-groups against
  the catalog and per-schema privileges. The groups are Databricks groups
  expected to exist at workspace level (create via Terraform separately).
- ``render_column_tags_sql``: ALTER TABLE ... ALTER COLUMN ... SET TAGS
  statements that annotate PII-sensitive columns. Downstream row filters
  and column masks attach to these tags.
"""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaGrant:
    schema: str
    privileges: tuple[str, ...]


@dataclass(frozen=True)
class PrincipalGroup:
    name: str
    catalog_privileges: tuple[str, ...]
    schema_grants: tuple[SchemaGrant, ...]


_DI_READERS = PrincipalGroup(
    name="di_readers",
    catalog_privileges=("USE_CATALOG",),
    schema_grants=(
        SchemaGrant("published", ("USE_SCHEMA", "SELECT")),
        SchemaGrant("di_marts", ("USE_SCHEMA", "SELECT")),
    ),
)

_DI_SERVICE = PrincipalGroup(
    name="di_service",
    catalog_privileges=("USE_CATALOG",),
    schema_grants=(
        SchemaGrant("bronze", ("USE_SCHEMA", "SELECT", "MODIFY")),
        SchemaGrant("published", ("USE_SCHEMA", "SELECT", "MODIFY")),
        SchemaGrant("di_staging", ("USE_SCHEMA", "SELECT", "MODIFY")),
        SchemaGrant("di_intermediate", ("USE_SCHEMA", "SELECT", "MODIFY")),
        SchemaGrant("di_marts", ("USE_SCHEMA", "SELECT", "MODIFY")),
        SchemaGrant("di_snapshots", ("USE_SCHEMA", "SELECT", "MODIFY")),
    ),
)

_DI_ENGINEERS = PrincipalGroup(
    name="di_engineers",
    catalog_privileges=("USE_CATALOG", "CREATE_SCHEMA"),
    schema_grants=(
        SchemaGrant("bronze", ("USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE")),
        SchemaGrant("published", ("USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE")),
        SchemaGrant("di_staging", ("USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE")),
        SchemaGrant("di_intermediate", ("USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE")),
        SchemaGrant("di_marts", ("USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE")),
        SchemaGrant("di_snapshots", ("USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE")),
    ),
)


PRINCIPAL_GROUPS: tuple[PrincipalGroup, ...] = (_DI_READERS, _DI_SERVICE, _DI_ENGINEERS)


def render_grants_sql(*, catalog_name: str) -> str:
    statements: list[str] = [
        "-- Document-intelligence Unity Catalog grants.",
        "-- Principal groups must exist at workspace level (Terraform-managed).",
        "",
    ]

    for group in PRINCIPAL_GROUPS:
        statements.append(f"-- {group.name}")
        if group.catalog_privileges:
            joined = ", ".join(group.catalog_privileges)
            statements.append(f"GRANT {joined} ON CATALOG `{catalog_name}` TO `{group.name}`;")
        for grant in group.schema_grants:
            joined = ", ".join(grant.privileges)
            statements.append(f"GRANT {joined} ON SCHEMA `{catalog_name}`.`{grant.schema}` TO `{group.name}`;")
        statements.append("")

    return "\n".join(statements).rstrip() + "\n"


@dataclass(frozen=True)
class ColumnTag:
    schema: str
    table: str
    column: str
    tag_key: str
    tag_value: str


PII_COLUMN_TAGS: tuple[ColumnTag, ...] = (
    ColumnTag("bronze", "raw_nlp_annotations", "entities_json", "pii", "raw_ner_output"),
    ColumnTag("di_intermediate", "int_entities", "entity_text", "pii", "person_name_candidate"),
    ColumnTag("di_marts", "srv_search_chunks", "chunk_text", "pii", "may_contain_personal_data"),
    ColumnTag("di_marts", "embeddings_ready", "chunk_text", "pii", "may_contain_personal_data"),
)


def render_column_tags_sql(*, catalog_name: str) -> str:
    statements: list[str] = [
        "-- Document-intelligence PII column tags.",
        "-- Tags power downstream row filters and column masks.",
        "",
    ]

    for tag in PII_COLUMN_TAGS:
        qualified = f"`{catalog_name}`.`{tag.schema}`.`{tag.table}`"
        statements.append(
            f"ALTER TABLE {qualified} ALTER COLUMN `{tag.column}` SET TAGS ('{tag.tag_key}' = '{tag.tag_value}');"
        )

    return "\n".join(statements).rstrip() + "\n"


def iter_principal_groups() -> Iterable[PrincipalGroup]:
    return PRINCIPAL_GROUPS


def iter_column_tags() -> Iterable[ColumnTag]:
    return PII_COLUMN_TAGS
