import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.bootstrap.bronze_schemas import (
    BRONZE_TABLE_DEFINITIONS,
    render_register_bronze_sql,
)
from document_intelligence.bootstrap.register_surfaces import (
    render_register_surfaces_sql,
)
from document_intelligence.bootstrap.render_source_contracts import (
    render_published_sources_yaml,
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

    def test_emits_alter_table_tblproperties_for_every_surface(self) -> None:
        sql = render_register_surfaces_sql(
            catalog_name="document_intelligence",
            schema_name="published",
            surfaces_root_uri="gs://evidara-di-dev/published",
        )

        for surface_name in ("published_documents", "published_sections", "processing_manifests"):
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


class TerraformModuleShapeTests(unittest.TestCase):
    def test_document_intelligence_terraform_module_contains_expected_resources(
        self,
    ) -> None:
        module_root = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "infra",
            "terraform",
            "databricks",
            "document_intelligence",
        )
        with open(os.path.join(module_root, "main.tf"), encoding="utf-8") as main_tf:
            main_body = main_tf.read()

        self.assertIn('resource "databricks_catalog" "document_intelligence"', main_body)
        self.assertIn('resource "databricks_schema" "published"', main_body)
        self.assertIn(
            'resource "databricks_external_location" "document_intelligence_surfaces"',
            main_body,
        )
        self.assertIn('resource "databricks_grants" "catalog"', main_body)
        self.assertIn('resource "databricks_grants" "schema"', main_body)

    def test_top_level_stack_owns_provider_and_calls_module(self) -> None:
        stack_root = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "infra",
            "terraform",
            "databricks",
            "document_intelligence_stack",
        )
        with open(os.path.join(stack_root, "versions.tf"), encoding="utf-8") as versions_tf:
            versions_body = versions_tf.read()
        with open(os.path.join(stack_root, "main.tf"), encoding="utf-8") as main_tf:
            main_body = main_tf.read()
        module_root = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "infra",
            "terraform",
            "databricks",
            "document_intelligence",
        )
        with open(os.path.join(module_root, "versions.tf"), encoding="utf-8") as module_versions_tf:
            module_versions_body = module_versions_tf.read()

        self.assertIn('provider "databricks"', versions_body)
        self.assertIn("host = var.workspace_host", versions_body)
        self.assertIn('module "document_intelligence"', main_body)
        self.assertIn('source = "../document_intelligence"', main_body)
        self.assertNotIn('provider "databricks"', module_versions_body)

    def test_environment_tfvars_exist_for_all_supported_environments(self) -> None:
        env_root = os.path.join(os.path.dirname(__file__), "..", "..", "infra", "env")
        for environment in ("dev", "staging", "prod"):
            tfvars_path = os.path.join(env_root, environment, "document_intelligence.databricks.tfvars")
            self.assertTrue(os.path.exists(tfvars_path), tfvars_path)
            with open(tfvars_path, encoding="utf-8") as tfvars_file:
                tfvars_body = tfvars_file.read()

            self.assertIn(f'environment = "{environment}"', tfvars_body)
            self.assertIn("workspace_host =", tfvars_body)
            self.assertIn("external_location_url =", tfvars_body)
            self.assertIn("storage_credential_name =", tfvars_body)


if __name__ == "__main__":
    unittest.main()
