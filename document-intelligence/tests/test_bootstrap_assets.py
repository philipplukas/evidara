import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.bootstrap.bronze_schemas import (
    BRONZE_TABLE_DEFINITIONS,
    render_register_bronze_sql,
)
from document_intelligence.bootstrap.governance import (
    PII_COLUMN_TAGS,
    PRINCIPAL_GROUPS,
    render_column_tags_sql,
    render_grants_sql,
)
from document_intelligence.bootstrap.register_surfaces import (
    render_register_surfaces_sql,
)
from document_intelligence.bootstrap.render_source_contracts import (
    render_published_sources_yaml,
)
from document_intelligence.bootstrap.sql_exec import (
    iter_sql_statements,
    strip_sql_line_comments,
)
from document_intelligence.persist.surfaces import iter_surface_definitions


class BronzeBootstrapSqlTests(unittest.TestCase):
    def test_renders_schema_and_tables(self) -> None:
        sql = render_register_bronze_sql(catalog_name="document_intelligence")

        self.assertIn(
            "CREATE SCHEMA IF NOT EXISTS `document_intelligence`.`bronze`;",
            sql,
        )
        for table_name in (
            "landing_envelopes",
            "document_processing_events",
            "raw_docling_output",
            "raw_nlp_annotations",
            "raw_metadata",
            "raw_documents",
        ):
            self.assertIn(
                f"CREATE TABLE IF NOT EXISTS `document_intelligence`.`bronze`.`{table_name}`",
                sql,
            )
        self.assertIn("'delta.enableChangeDataFeed' = 'true'", sql)
        self.assertIn("'delta.columnMapping.mode' = 'name'", sql)

    def test_honours_custom_schema_name(self) -> None:
        sql = render_register_bronze_sql(
            catalog_name="document_intelligence",
            schema_name="bronze_v2",
        )

        self.assertIn(
            "CREATE SCHEMA IF NOT EXISTS `document_intelligence`.`bronze_v2`;",
            sql,
        )
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS `document_intelligence`.`bronze_v2`.`landing_envelopes`",
            sql,
        )

    def test_autoloader_bookkeeping_columns_are_present(self) -> None:
        for definition in BRONZE_TABLE_DEFINITIONS.values():
            column_names = {column.name for column in definition.columns}
            self.assertIn("ingested_at", column_names, definition.table_name)
            self.assertIn("_source_file", column_names, definition.table_name)

    def test_payload_columns_are_strings(self) -> None:
        # Staging models cast every payload column; bronze stays typed as STRING
        # so Auto Loader schema inference cannot conflict with the pre-declared
        # table shape. Only the bookkeeping `ingested_at` column is a TIMESTAMP.
        for definition in BRONZE_TABLE_DEFINITIONS.values():
            for column in definition.columns:
                if column.name == "ingested_at":
                    self.assertEqual(column.sql_type, "TIMESTAMP")
                else:
                    self.assertEqual(column.sql_type, "STRING", f"{definition.table_name}.{column.name}")


class SurfaceBootstrapSqlTests(unittest.TestCase):
    def test_renders_create_table_statements_for_all_published_surfaces(self) -> None:
        sql = render_register_surfaces_sql(
            catalog_name="document_intelligence",
            schema_name="published",
            surfaces_root_uri="gs://evidara-di-dev/published",
        )

        self.assertIn("CREATE CATALOG IF NOT EXISTS `document_intelligence`;", sql)
        self.assertIn("CREATE SCHEMA IF NOT EXISTS `document_intelligence`.`published`;", sql)
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS `document_intelligence`.`published`.`published_documents`",
            sql,
        )
        self.assertIn(
            "LOCATION 'gs://evidara-di-dev/published/published_documents';",
            sql,
        )
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS `document_intelligence`.`published`.`published_sections`",
            sql,
        )
        self.assertIn(
            "LOCATION 'gs://evidara-di-dev/published/published_sections';",
            sql,
        )
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS `document_intelligence`.`published`.`processing_manifests`",
            sql,
        )
        self.assertIn(
            "LOCATION 'gs://evidara-di-dev/published/processing_manifests';",
            sql,
        )
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS `document_intelligence`.`published`.`published_commentary_insights`",
            sql,
        )
        self.assertIn(
            "LOCATION 'gs://evidara-di-dev/published/published_commentary_insights';",
            sql,
        )

    def test_emits_alter_table_tblproperties_for_every_surface(self) -> None:
        sql = render_register_surfaces_sql(
            catalog_name="document_intelligence",
            schema_name="published",
            surfaces_root_uri="gs://evidara-di-dev/published",
        )

        for surface_name in (
            "published_documents",
            "published_sections",
            "processing_manifests",
            "published_commentary_insights",
        ):
            self.assertIn(
                f"ALTER TABLE `document_intelligence`.`published`.`{surface_name}` SET TBLPROPERTIES",
                sql,
            )
        self.assertIn("'delta.enableChangeDataFeed' = 'true'", sql)
        self.assertIn("'delta.columnMapping.mode' = 'name'", sql)


class PublishedSourceContractsTests(unittest.TestCase):
    def test_renderer_emits_every_published_surface_with_column_set_test(self) -> None:
        yaml_text = render_published_sources_yaml()

        self.assertIn("version: 2", yaml_text)
        self.assertIn("- name: published", yaml_text)
        self.assertIn("schema: published", yaml_text)

        for definition in iter_surface_definitions():
            self.assertIn(f"- name: {definition.surface_name}", yaml_text)
            for column in definition.columns:
                self.assertIn(f"- {column.name}", yaml_text)
        self.assertIn(
            "- dbt_expectations.expect_table_columns_to_match_set:",
            yaml_text,
        )

    def test_checked_in_generated_yaml_matches_renderer(self) -> None:
        generated_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "dbt",
            "models",
            "sources_published.generated.yml",
        )
        self.assertTrue(os.path.exists(generated_path), generated_path)
        with open(generated_path, encoding="utf-8") as generated_file:
            on_disk = generated_file.read()

        expected = render_published_sources_yaml()
        self.assertEqual(
            on_disk,
            expected,
            "sources_published.generated.yml is out of sync; regenerate with "
            "`document_intelligence_render_source_contracts > dbt/models/sources_published.generated.yml`",
        )

    def test_nullable_false_columns_get_not_null_tests(self) -> None:
        yaml_text = render_published_sources_yaml()

        # document_id is nullable=False and should be enforced by a not_null test.
        self.assertIn("- name: document_id", yaml_text)
        # effective_date is nullable=True and should NOT have a not_null block attached
        # directly beneath it. We spot-check by ensuring the column description line is
        # not immediately followed by `tests:` + `- not_null`.
        lines = yaml_text.splitlines()
        for idx, line in enumerate(lines):
            if line.strip() == "- name: effective_date":
                # next line is description, then (for nullable columns) nothing; verify.
                self.assertNotIn("not_null", "\n".join(lines[idx : idx + 3]))
                break
        else:
            self.fail("effective_date column not found in rendered YAML")


class GovernanceSqlTests(unittest.TestCase):
    def test_grants_emits_catalog_and_schema_privileges_per_group(self) -> None:
        sql = render_grants_sql(catalog_name="document_intelligence")

        for group in PRINCIPAL_GROUPS:
            self.assertIn(f"TO `{group.name}`", sql)
            for grant in group.schema_grants:
                self.assertIn(
                    f"ON SCHEMA `document_intelligence`.`{grant.schema}` TO `{group.name}`",
                    sql,
                )

    def test_grants_covers_expected_group_set(self) -> None:
        names = {group.name for group in PRINCIPAL_GROUPS}
        self.assertEqual(names, {"di_readers", "di_service", "di_engineers"})

    def test_column_tags_emits_alter_for_every_pii_column(self) -> None:
        sql = render_column_tags_sql(catalog_name="document_intelligence")

        for tag in PII_COLUMN_TAGS:
            self.assertIn(
                f"ALTER TABLE `document_intelligence`.`{tag.schema}`.`{tag.table}` ALTER COLUMN `{tag.column}`",
                sql,
            )
            self.assertIn(f"'{tag.tag_key}' = '{tag.tag_value}'", sql)

    def test_column_tags_cover_known_pii_surfaces(self) -> None:
        columns = {(tag.schema, tag.table, tag.column) for tag in PII_COLUMN_TAGS}
        self.assertIn(("di_intermediate", "int_entities", "entity_text"), columns)
        self.assertIn(("di_marts", "embeddings_ready", "chunk_text"), columns)
        self.assertIn(("di_marts", "srv_search_chunks", "chunk_text"), columns)


class SqlExecTests(unittest.TestCase):
    def test_strip_sql_line_comments_removes_comment_lines(self) -> None:
        sql = "-- header\nCREATE SCHEMA foo;\n-- another\nCREATE TABLE t (a INT);"
        stripped = strip_sql_line_comments(sql)
        self.assertNotIn("--", stripped)
        self.assertIn("CREATE SCHEMA foo", stripped)
        self.assertIn("CREATE TABLE t", stripped)

    def test_strip_sql_line_comments_handles_embedded_semicolons(self) -> None:
        # Real-world bug: header comment contained "Safe to run; re-runs ...".
        # Splitting on ';' before stripping comments yields bogus fragments.
        sql = "-- Safe to run; re-runs are idempotent.\nCREATE SCHEMA foo;"
        statements = list(iter_sql_statements(sql))
        self.assertEqual(statements, ["CREATE SCHEMA foo"])

    def test_iter_sql_statements_executes_every_create_statement(self) -> None:
        from document_intelligence.bootstrap.bronze_schemas import render_register_bronze_sql
        from document_intelligence.bootstrap.governance import render_grants_sql

        bronze = list(iter_sql_statements(render_register_bronze_sql(catalog_name="c")))
        grants = list(iter_sql_statements(render_grants_sql(catalog_name="c")))

        # Every bronze table must produce an executable CREATE TABLE statement.
        creates = [s for s in bronze if s.startswith("CREATE TABLE")]
        self.assertEqual(len(creates), 6, creates)
        # Every principal group must produce an executable GRANT on CATALOG.
        catalog_grants = [s for s in grants if "ON CATALOG" in s]
        self.assertEqual(len(catalog_grants), 3, catalog_grants)

    def test_iter_sql_statements_skips_blank_and_comment_only_chunks(self) -> None:
        sql = "\n\n-- just a comment\n\n;CREATE TABLE t (a INT);"
        self.assertEqual(list(iter_sql_statements(sql)), ["CREATE TABLE t (a INT)"])


if __name__ == "__main__":
    unittest.main()
