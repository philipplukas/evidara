import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.bootstrap.register_surfaces import (
    render_register_surfaces_sql,
)


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
