from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from evidara_cli.client import (
    HttpJsonError,
    join_url,
    legal_search_base_url,
    legal_search_headers,
    platform_control_base_url,
    platform_control_headers,
    request_json,
    use_human_output,
)
from evidara_cli.openapi_cmd import openapi_app
from evidara_cli.repo_root import resolve_repo_root

app = typer.Typer(
    no_args_is_help=True,
    help="Evidara APIs — workflows and discovery for humans and agents.",
)
app.add_typer(openapi_app, name="openapi")

pc = typer.Typer(
    no_args_is_help=True,
    help="Platform-control FastAPI (see contracts/api/platform-control.openapi.yaml).",
)
ls = typer.Typer(
    no_args_is_help=True,
    help="Legal-search NestJS BFF (see contracts/api/legal-search.openapi.yaml).",
)
app.add_typer(pc, name="platform-control")
app.add_typer(ls, name="legal-search")


def _emit(data: Any, *, human: bool) -> None:
    if human or use_human_output():
        typer.echo(json.dumps(data, indent=2, sort_keys=True, default=str))
    else:
        typer.echo(json.dumps(data, separators=(",", ":"), default=str))


def _handle_exc(exc: Exception, *, human: bool) -> None:
    if isinstance(exc, HttpJsonError):
        payload = {
            "ok": False,
            "error": str(exc),
            "status_code": exc.status_code,
            "body": exc.body[:8000] if exc.body else "",
        }
        _emit(payload, human=human)
        raise typer.Exit(code=1) from exc
    raise exc


@pc.command("ping")
def pc_ping(
    human: Annotated[
        bool,
        typer.Option("--human", help="Pretty-print JSON (also EVIDARA_CLI_HUMAN=1)"),
    ] = False,
    correlation_id: Annotated[
        str | None,
        typer.Option("--correlation-id", help="Forwarded as X-Correlation-Id"),
    ] = None,
) -> None:
    """GET /health — verify platform-control is reachable."""
    base = platform_control_base_url()
    url = join_url(base, "/health")
    try:
        headers = platform_control_headers(correlation_id=correlation_id)
        out = request_json("GET", url, headers=headers)
        _emit(
            {"ok": True, "service": "platform-control", "url": url, "response": out},
            human=human,
        )
    except Exception as exc:
        _handle_exc(exc, human=human)


@pc.command("wizard-smoke")
def pc_wizard_smoke(
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    name: Annotated[
        str | None,
        typer.Option("--name", help="Project name (default: cli-smoke-<iso timestamp>)"),
    ] = None,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """POST /v1/wizard/projects then GET project — minimal wizard API smoke."""
    base = platform_control_base_url()
    headers = platform_control_headers(correlation_id=correlation_id)
    headers["Content-Type"] = "application/json"
    label = name or f"cli-smoke-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    create_url = join_url(base, "/v1/wizard/projects")
    try:
        created = request_json("POST", create_url, headers=headers, json_body={"name": label})
        if not isinstance(created, dict) or "wizard_project_id" not in created:
            _emit(
                {
                    "ok": False,
                    "error": "Unexpected create response shape",
                    "response": created,
                },
                human=human,
            )
            raise typer.Exit(code=1)
        pid = created["wizard_project_id"]
        get_url = join_url(base, f"/v1/wizard/projects/{pid}")
        fetched = request_json("GET", get_url, headers=headers)
        _emit(
            {
                "ok": True,
                "service": "platform-control",
                "created": created,
                "fetched": fetched,
            },
            human=human,
        )
    except Exception as exc:
        _handle_exc(exc, human=human)


@pc.command("ris-bootstrap")
def pc_ris_bootstrap(
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, help="Max OGD API pages")] = 1,
    applikation: Annotated[
        str | None,
        typer.Option("--applikation", help="OGD Applikation filter (e.g. Vfgh, BrKons)"),
    ] = None,
    process_di: Annotated[
        bool,
        typer.Option("--process-di", help="Run script's DI follow-up step when set"),
    ] = False,
    repo_root: Annotated[
        Path | None,
        typer.Option(
            "--repo-root",
            envvar="EVIDARA_REPO_ROOT",
            help="Monorepo root (auto-detected if omitted)",
        ),
    ] = None,
) -> None:
    """Run scripts/bootstrap-ris-source.py (RIS OGD end-to-end bootstrap).

    Uses EVIDARA_PLATFORM_CONTROL_URL and EVIDARA_PLATFORM_CONTROL_API_KEY like other commands.
    """
    root = resolve_repo_root(repo_root)
    script = root / "scripts" / "bootstrap-ris-source.py"
    if not script.is_file():
        typer.echo(f"Script not found: {script}", err=True)
        raise typer.Exit(code=1)
    api_url = platform_control_base_url()
    cmd: list[str] = [
        sys.executable,
        str(script),
        "--api-url",
        api_url,
        "--max-pages",
        str(max_pages),
    ]
    key = os.environ.get("EVIDARA_PLATFORM_CONTROL_API_KEY", "").strip()
    if key:
        cmd.extend(["--api-key", key])
    if applikation:
        cmd.extend(["--applikation", applikation])
    if process_di:
        cmd.append("--process-di")
    result = subprocess.run(cmd, cwd=root, check=False)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


@ls.command("ping")
def ls_ping(
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """GET /v1/search?q=test — verifies legal-search + OpenSearch path (local dev)."""
    base = legal_search_base_url()
    url = join_url(base, "/v1/search")
    headers = legal_search_headers(correlation_id=correlation_id)
    try:
        out = request_json(
            "GET",
            url,
            headers=headers,
            params={"q": "test", "page": "1", "page_size": "5"},
            timeout=60.0,
        )
        _emit({"ok": True, "service": "legal-search", "url": url, "response": out}, human=human)
    except Exception as exc:
        _handle_exc(exc, human=human)


@ls.command("search")
def ls_search(
    q: Annotated[str, typer.Option("--q", "-q", help="Search query (required)")],
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    page: Annotated[int, typer.Option("--page", min=1)] = 1,
    page_size: Annotated[int, typer.Option("--page-size", min=1, max=100)] = 10,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """GET /v1/search — search documents."""
    base = legal_search_base_url()
    url = join_url(base, "/v1/search")
    headers = legal_search_headers(correlation_id=correlation_id)
    try:
        out = request_json(
            "GET",
            url,
            headers=headers,
            params={"q": q, "page": str(page), "page_size": str(page_size)},
            timeout=60.0,
        )
        _emit({"ok": True, "service": "legal-search", "url": url, "response": out}, human=human)
    except Exception as exc:
        _handle_exc(exc, human=human)


@ls.command("document")
def ls_document(
    document_id: Annotated[str, typer.Argument(help="Document id, e.g. doc_001")],
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """GET /v1/documents/{document_id} — document detail ViewModel."""
    base = legal_search_base_url()
    url = join_url(base, f"/v1/documents/{document_id}")
    headers = legal_search_headers(correlation_id=correlation_id)
    try:
        out = request_json("GET", url, headers=headers, timeout=60.0)
        _emit({"ok": True, "service": "legal-search", "url": url, "response": out}, human=human)
    except Exception as exc:
        _handle_exc(exc, human=human)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
