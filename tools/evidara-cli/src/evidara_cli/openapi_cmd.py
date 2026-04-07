from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml

openapi_app = typer.Typer(
    no_args_is_help=True,
    help="Read-only helpers against repo OpenAPI files.",
)

SPEC_FILES = {
    "platform-control": "contracts/api/platform-control.openapi.yaml",
    "legal-search": "contracts/api/legal-search.openapi.yaml",
}


def _resolve_repo_root(explicit: Path) -> Path:
    """Find monorepo root containing contracts/api (supports cwd under tools/evidara-cli)."""
    candidates = [explicit, Path.cwd(), *Path.cwd().parents]
    for root in candidates:
        if root == Path.home():
            break
        if (root / "contracts" / "api").is_dir():
            return root
    return explicit


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
    root = _resolve_repo_root(repo_root or Path.cwd())
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
