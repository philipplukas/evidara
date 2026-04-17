"""Render SQL for bootstrapping document-intelligence bronze tables in Unity Catalog."""

import argparse

from document_intelligence.bootstrap.bronze_schemas import render_register_bronze_sql


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="document_intelligence_render_bronze_sql",
        description="Render SQL to create document-intelligence bronze landing tables in Unity Catalog.",
    )
    parser.add_argument("--catalog-name", required=True)
    parser.add_argument("--schema-name", default="bronze")
    args = parser.parse_args(argv)

    print(
        render_register_bronze_sql(
            catalog_name=args.catalog_name,
            schema_name=args.schema_name,
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
