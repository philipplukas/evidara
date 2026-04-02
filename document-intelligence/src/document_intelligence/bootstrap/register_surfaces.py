"""Render SQL for registering published DI surfaces in Unity Catalog."""

import argparse
from typing import Optional

from document_intelligence.config.runtime import SurfaceUris
from document_intelligence.persist.surfaces import iter_surface_definitions


def render_register_surfaces_sql(
    *,
    catalog_name: str,
    schema_name: str,
    surfaces_root_uri: str,
) -> str:
    surface_uris = SurfaceUris.from_root_uri(surfaces_root_uri)
    location_by_surface = {
        "published_documents": surface_uris.published_documents_uri,
        "published_sections": surface_uris.published_sections_uri,
        "processing_manifests": surface_uris.processing_manifests_uri,
    }

    statements = [
        "-- Register document-intelligence published Delta surfaces in Unity Catalog.",
        "-- Run this after the DI job has created the Delta logs at the target locations.",
        "CREATE CATALOG IF NOT EXISTS `{catalog}`;".format(catalog=catalog_name),
        "CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`;".format(
            catalog=catalog_name,
            schema=schema_name,
        ),
        "",
    ]

    for surface in iter_surface_definitions():
        statements.extend(
            [
                "-- {description}".format(description=surface.description),
                "CREATE TABLE IF NOT EXISTS `{catalog}`.`{schema}`.`{surface}`".format(
                    catalog=catalog_name,
                    schema=schema_name,
                    surface=surface.surface_name,
                ),
                "USING DELTA",
                "LOCATION '{location}';".format(
                    location=location_by_surface[surface.surface_name]
                ),
                "",
            ]
        )

    return "\n".join(statements).rstrip() + "\n"


def cli(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="document_intelligence_render_surface_sql",
        description="Render SQL to register published DI surfaces in Unity Catalog.",
    )
    parser.add_argument("--catalog-name", required=True)
    parser.add_argument("--schema-name", required=True)
    parser.add_argument("--surfaces-root-uri", required=True)
    args = parser.parse_args(argv)

    print(
        render_register_surfaces_sql(
            catalog_name=args.catalog_name,
            schema_name=args.schema_name,
            surfaces_root_uri=args.surfaces_root_uri,
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
