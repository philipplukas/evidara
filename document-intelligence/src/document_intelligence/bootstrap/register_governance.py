"""CLI for rendering document-intelligence Unity Catalog governance SQL."""

import argparse

from document_intelligence.bootstrap.governance import (
    render_column_tags_sql,
    render_grants_sql,
)


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="document_intelligence_render_governance_sql",
        description="Render GRANTs and PII column tags for document-intelligence surfaces.",
    )
    parser.add_argument("--catalog-name", required=True)
    parser.add_argument(
        "--mode",
        choices=("grants", "tags", "all"),
        default="all",
        help="Which script to render.",
    )
    args = parser.parse_args(argv)

    if args.mode in ("grants", "all"):
        print(render_grants_sql(catalog_name=args.catalog_name), end="")
    if args.mode in ("tags", "all"):
        print(render_column_tags_sql(catalog_name=args.catalog_name), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
