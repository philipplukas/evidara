from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml

from evidara_cli.repo_root import resolve_repo_root

openapi_app = typer.Typer(
    no_args_is_help=True,
    help="Read-only helpers against repo OpenAPI files.",
)

SPEC_FILES = {
    "platform-control": "contracts/api/platform-control.openapi.yaml",
    "legal-search": "contracts/api/legal-search.openapi.yaml",
}


@openapi_app.command("paths")
def list_paths(
    service: Annotated[str, typer.Argument(help="platform-control | legal-search")],
    repo_root: Annotated[
        Path | None,
        typer.Option(
            "--repo-root",
            envvar="EVIDARA_REPO_ROOT",
            help="Monorepo root (auto-detected if omitted)",
        ),
    ] = None,
) -> None:
    """Print HTTP paths from the canonical OpenAPI spec (for discovery)."""
    key = service.strip().lower().replace("_", "-")
    if key not in SPEC_FILES:
        typer.echo(f"Unknown service {service!r}; choose: {', '.join(SPEC_FILES)}", err=True)
        raise typer.Exit(code=2)
    root = resolve_repo_root(repo_root)
    path = root / SPEC_FILES[key]
    if not path.is_file():
        typer.echo(f"Spec not found: {path}", err=True)
        raise typer.Exit(code=1)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    paths = data.get("paths") if isinstance(data, dict) else None
    if not isinstance(paths, dict):
        typer.echo(f"No paths: in {path}", err=True)
        raise typer.Exit(code=1)
    for p in sorted(paths):
        typer.echo(p)


@openapi_app.command("tags")
def list_tags(
    service: Annotated[str, typer.Argument(help="platform-control | legal-search")],
    repo_root: Annotated[
        Path | None,
        typer.Option(
            "--repo-root",
            envvar="EVIDARA_REPO_ROOT",
            help="Monorepo root (auto-detected if omitted)",
        ),
    ] = None,
) -> None:
    """Print unique OpenAPI operation tags (agent-friendly grouping for discovery)."""
    key = service.strip().lower().replace("_", "-")
    if key not in SPEC_FILES:
        typer.echo(f"Unknown service {service!r}; choose: {', '.join(SPEC_FILES)}", err=True)
        raise typer.Exit(code=2)
    root = resolve_repo_root(repo_root)
    path = root / SPEC_FILES[key]
    if not path.is_file():
        typer.echo(f"Spec not found: {path}", err=True)
        raise typer.Exit(code=1)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    paths = data.get("paths") if isinstance(data, dict) else None
    if not isinstance(paths, dict):
        typer.echo(f"No paths: in {path}", err=True)
        raise typer.Exit(code=1)
    tags: set[str] = set()
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if not isinstance(method, str) or method.startswith("x-"):
                continue
            if method.upper() not in {
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
                "HEAD",
                "OPTIONS",
            }:
                continue
            if not isinstance(operation, dict):
                continue
            for tag in operation.get("tags") or []:
                if isinstance(tag, str) and tag.strip():
                    tags.add(tag)
    for tag in sorted(tags):
        typer.echo(tag)
